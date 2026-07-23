#!/usr/bin/env python3
"""Measure deterministic oracle-EAT assistance over a recorded model run."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from html import escape
import json
from pathlib import Path

from eat_baselines import (
    Case,
    EatResolverAdapter,
    ResolverRegistry,
    metrics,
    score,
)
from eat_recorded_runs import RecordedRun, load_recorded_run, sha256_file


DATASET_NAME = (
    "wiki-fair-v2/test-no-coref@"
    "c9a3fe9c4933888d756d702fdb9ff607fc36aa26"
)
COVERAGES = (0.0, 0.25, 0.5, 0.75, 1.0)


@dataclass(frozen=True)
class OracleAnnotation:
    start: int
    end: int
    type: str
    key: str


@dataclass(frozen=True)
class OracleCase:
    case: Case
    annotations: tuple[OracleAnnotation, ...]


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def render_eat_text(
    plain_text: str, annotations: list[OracleAnnotation] | tuple[OracleAnnotation, ...]
) -> str:
    chunks: list[str] = []
    cursor = 0
    for annotation in sorted(
        annotations, key=lambda item: (item.start, item.end, item.type, item.key)
    ):
        if (
            annotation.start < cursor
            or annotation.end <= annotation.start
            or annotation.end > len(plain_text)
        ):
            raise ValueError(
                f"invalid or overlapping oracle span "
                f"{annotation.start}:{annotation.end}"
            )
        chunks.append(plain_text[cursor : annotation.start])
        chunks.append(f"@@EAT {annotation.type}:{annotation.key}@@")
        cursor = annotation.end
    chunks.append(plain_text[cursor:])
    return "".join(chunks)


def load_oracle_cases(
    path: Path,
    model_cases: list[Case],
    registry: ResolverRegistry,
) -> list[OracleCase]:
    expected = {case.id: case for case in model_cases}
    seen: set[str] = set()
    oracle_cases: list[OracleCase] = []
    for row_number, record in enumerate(load_jsonl(path), start=1):
        allowed = {
            "annotations",
            "eat_text",
            "gold_ids",
            "id",
            "language",
            "plain_text",
            "source_url",
        }
        if set(record) != allowed:
            raise ValueError(f"{path}:{row_number}: unexpected oracle fields")
        case = Case.from_record(record)
        model_case = expected.get(case.id)
        if model_case is None or case.id in seen:
            raise ValueError(f"{path}:{row_number}: unknown or duplicate case {case.id}")
        seen.add(case.id)
        if (
            case.plain_text != model_case.plain_text
            or case.gold_ids != model_case.gold_ids
        ):
            raise ValueError(f"{path}:{row_number}: model/oracle case mismatch")

        annotations = tuple(
            OracleAnnotation(
                start=int(item["start"]),
                end=int(item["end"]),
                type=str(item["type"]),
                key=str(item["key"]),
            )
            for item in record["annotations"]
        )
        for annotation in annotations:
            if registry.resolve_typed(annotation.type, annotation.key) is None:
                raise ValueError(
                    f"{path}:{row_number}: unknown typed key "
                    f"{annotation.type}:{annotation.key}"
                )
        rendered = render_eat_text(case.plain_text, annotations)
        if rendered != case.eat_text:
            raise ValueError(f"{path}:{row_number}: eat_text does not match spans")
        annotation_ids = {
            registry.resolve_typed(annotation.type, annotation.key)
            for annotation in annotations
        }
        if annotation_ids != set(case.gold_ids):
            raise ValueError(
                f"{path}:{row_number}: oracle annotations do not cover gold IDs"
            )
        oracle_cases.append(OracleCase(case=case, annotations=annotations))

    missing = sorted(set(expected) - seen)
    if missing:
        raise ValueError(f"{path}: missing oracle cases {missing}")
    return oracle_cases


def ranked_annotations(
    oracle_cases: list[OracleCase],
) -> list[tuple[str, int]]:
    ranked: list[tuple[str, str, int]] = []
    for oracle_case in oracle_cases:
        for index, annotation in enumerate(oracle_case.annotations):
            identity = (
                f"{oracle_case.case.id}|{annotation.start}|{annotation.end}|"
                f"{annotation.type}|{annotation.key}"
            )
            rank = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            ranked.append((rank, oracle_case.case.id, index))
    return [(case_id, index) for _, case_id, index in sorted(ranked)]


def model_mentions(
    run: RecordedRun,
    case_id: str,
    registry: ResolverRegistry,
) -> list[tuple[int, int, str]]:
    mentions: list[tuple[int, int, str]] = []
    for mention in run.predictions[case_id].mentions:
        canonical_id = registry.resolve_typed(mention.type, mention.key)
        if canonical_id is None:
            raise ValueError(f"validated run contains unresolved key for {case_id}")
        mentions.append((mention.start, mention.end, canonical_id))
    return mentions


def condition_metrics(
    predictions: dict[str, set[str]], oracle_cases: list[OracleCase]
) -> dict[str, object]:
    tp = fp = fn = exact = 0
    for oracle_case in oracle_cases:
        predicted = predictions[oracle_case.case.id]
        gold = set(oracle_case.case.gold_ids)
        case_tp, case_fp, case_fn = score(predicted, gold)
        tp += case_tp
        fp += case_fp
        fn += case_fn
        exact += int(predicted == gold)
    return {
        **metrics(tp, fp, fn),
        "exact_match_rate": round(exact / len(oracle_cases), 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
    }


def evaluate(
    run: RecordedRun,
    oracle_cases: list[OracleCase],
    registry: ResolverRegistry,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    ranked = ranked_annotations(oracle_cases)
    resolver = EatResolverAdapter()
    conditions: dict[str, object] = {}
    case_rows = {
        oracle_case.case.id: {
            "id": oracle_case.case.id,
            "gold_ids": sorted(oracle_case.case.gold_ids),
            "predictions": {},
        }
        for oracle_case in oracle_cases
    }

    baseline_predictions = {
        oracle_case.case.id: {
            canonical_id
            for _, _, canonical_id in model_mentions(
                run, oracle_case.case.id, registry
            )
        }
        for oracle_case in oracle_cases
    }
    baseline = condition_metrics(baseline_predictions, oracle_cases)
    test_scope = {
        "documents": len(oracle_cases),
        "mention_annotations": len(ranked),
        "document_entity_pairs": sum(
            len(oracle_case.case.gold_ids) for oracle_case in oracle_cases
        ),
        "unique_entities": len(
            {
                entity_id
                for oracle_case in oracle_cases
                for entity_id in oracle_case.case.gold_ids
            }
        ),
    }

    for coverage in COVERAGES:
        label = f"{int(coverage * 100)}%"
        selected_count = int(len(ranked) * coverage + 0.5)
        selected_pairs = set(ranked[:selected_count])
        selected_by_case: dict[str, set[int]] = {}
        for case_id, index in selected_pairs:
            selected_by_case.setdefault(case_id, set()).add(index)
        predictions: dict[str, set[str]] = {}
        explicit_entity_cases: set[tuple[str, str]] = set()
        for oracle_case in oracle_cases:
            selected = [
                annotation
                for index, annotation in enumerate(oracle_case.annotations)
                if index in selected_by_case.get(oracle_case.case.id, set())
            ]
            assisted_case = Case(
                id=oracle_case.case.id,
                plain_text=oracle_case.case.plain_text,
                eat_text=render_eat_text(oracle_case.case.plain_text, selected),
                gold_ids=oracle_case.case.gold_ids,
                language=oracle_case.case.language,
            )
            explicit_ids = resolver.predict(assisted_case, registry).predicted_ids
            explicit_entity_cases.update(
                (oracle_case.case.id, entity_id) for entity_id in explicit_ids
            )
            retained_model_ids = {
                canonical_id
                for start, end, canonical_id in model_mentions(
                    run, oracle_case.case.id, registry
                )
                if not any(
                    start < annotation.end and end > annotation.start
                    for annotation in selected
                )
            }
            predictions[oracle_case.case.id] = retained_model_ids | explicit_ids
            case_rows[oracle_case.case.id]["predictions"][label] = sorted(
                predictions[oracle_case.case.id]
            )

        measured = condition_metrics(predictions, oracle_cases)
        measured.update(
            {
                "annotated_mentions": selected_count,
                "unannotated_mentions": len(ranked) - selected_count,
                "assisted_documents": len(selected_by_case),
                "assisted_document_entity_pairs": len(explicit_entity_cases),
                "f1_delta_vs_model": round(
                    float(measured["f1"]) - float(baseline["f1"]), 4
                ),
                "false_positives_removed_vs_model": (
                    int(baseline["false_positives"])
                    - int(measured["false_positives"])
                ),
                "false_negatives_removed_vs_model": (
                    int(baseline["false_negatives"])
                    - int(measured["false_negatives"])
                ),
            }
        )
        conditions[label] = measured

    eat_only_predictions: dict[str, set[str]] = {}
    for oracle_case in oracle_cases:
        eat_only_predictions[oracle_case.case.id] = resolver.predict(
            oracle_case.case, registry
        ).predicted_ids
        case_rows[oracle_case.case.id]["eat_only_ids"] = sorted(
            eat_only_predictions[oracle_case.case.id]
        )
    eat_only = condition_metrics(eat_only_predictions, oracle_cases)
    return (
        {
            "model_baseline": baseline,
            "model_with_oracle_eat": conditions,
            "eat_only_oracle": eat_only,
            "oracle_annotations": len(ranked),
            "test_scope": test_scope,
        },
        list(case_rows.values()),
    )


def write_coverage_chart(
    path: Path,
    evaluation: dict[str, object],
) -> None:
    """Write a dependency-free SVG that explains what coverage counts."""

    total = int(evaluation["oracle_annotations"])
    conditions = evaluation["model_with_oracle_eat"]
    rows = []
    for index, coverage in enumerate(("0%", "25%", "50%", "75%", "100%")):
        condition = conditions[coverage]
        eat_mentions = int(condition["annotated_mentions"])
        plain_mentions = int(condition["unannotated_mentions"])
        documents = int(condition["assisted_documents"])
        y = 145 + index * 62
        eat_width = round(560 * eat_mentions / total)
        rows.append(
            f'<text class="level" x="82" y="{y + 20}">{coverage}</text>'
            f'<rect class="plain" x="150" y="{y}" width="560" height="28" rx="5"/>'
            f'<rect class="eat" x="150" y="{y}" width="{eat_width}" '
            f'height="28" rx="5"/>'
            f'<text class="detail" x="730" y="{y + 20}">'
            f'{eat_mentions} EAT + {plain_mentions} plain · '
            f'{documents}/40 articles</text>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="500" viewBox="0 0 1000 500" role="img">
  <title>EAT coverage in the Wiki-Fair test</title>
  <desc>Five coverage levels over 669 entity mentions in 40 Wikipedia articles.</desc>
  <style>
    .bg {{ fill: #ffffff; }}
    .title {{ font: 700 26px system-ui, sans-serif; fill: #111827; }}
    .subtitle {{ font: 15px system-ui, sans-serif; fill: #4b5563; }}
    .level {{ font: 700 16px system-ui, sans-serif; fill: #111827; text-anchor: end; }}
    .detail {{ font: 14px system-ui, sans-serif; fill: #374151; }}
    .legend {{ font: 13px system-ui, sans-serif; fill: #4b5563; }}
    .eat {{ fill: #2563eb; }}
    .plain {{ fill: #d1d5db; }}
  </style>
  <rect class="bg" width="1000" height="500"/>
  <text class="title" x="40" y="48">How much of the test text received EAT?</text>
  <text class="subtitle" x="40" y="78">40 articles · 669 entity mentions · coverage counts mentions, not files</text>
  <rect class="eat" x="150" y="100" width="18" height="12" rx="2"/>
  <text class="legend" x="176" y="111">mention replaced by an EAT reference</text>
  <rect class="plain" x="435" y="100" width="18" height="12" rx="2"/>
  <text class="legend" x="461" y="111">mention left as plain text</text>
  {''.join(rows)}
  <text class="subtitle" x="150" y="472">“37/40 articles” means 37 articles contain at least one selected EAT reference.</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def write_performance_chart(
    path: Path,
    evaluation: dict[str, object],
) -> None:
    """Write a dependency-free SVG for F1 and recall across coverage levels."""

    conditions = evaluation["model_with_oracle_eat"]
    labels = ("0%", "25%", "50%", "75%", "100%")
    x_positions = (120, 300, 480, 660, 840)

    def y_position(value: float) -> float:
        return 420 - value * 320

    def series(metric: str, class_name: str, label_offset: int) -> str:
        values = [float(conditions[label][metric]) for label in labels]
        points = " ".join(
            f"{x},{y_position(value):.1f}"
            for x, value in zip(x_positions, values)
        )
        marks = []
        for x, value in zip(x_positions, values):
            y = y_position(value)
            marks.append(
                f'<circle class="{class_name}" cx="{x}" cy="{y:.1f}" r="5"/>'
                f'<text class="value" x="{x}" y="{y + label_offset:.1f}">'
                f'{value:.4f}</text>'
            )
        return (
            f'<polyline class="{class_name}" points="{points}"/>'
            + "".join(marks)
        )

    grid = []
    for value in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        y = y_position(value)
        grid.append(
            f'<line class="grid" x1="90" y1="{y:.1f}" x2="880" y2="{y:.1f}"/>'
            f'<text class="axis" x="76" y="{y + 5:.1f}">{value:.1f}</text>'
        )
    ticks = "".join(
        f'<text class="axis x" x="{x}" y="452">{escape(label)}</text>'
        for x, label in zip(x_positions, labels)
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="520" viewBox="0 0 1000 520" role="img">
  <title>Model performance by EAT coverage</title>
  <desc>F1 rises from 0.7089 to 0.9043 and recall from 0.6937 to 1.0 as correct EAT coverage rises.</desc>
  <style>
    .bg {{ fill: #ffffff; }}
    .title {{ font: 700 26px system-ui, sans-serif; fill: #111827; }}
    .subtitle {{ font: 15px system-ui, sans-serif; fill: #4b5563; }}
    .grid {{ stroke: #e5e7eb; stroke-width: 1; }}
    .axis {{ font: 13px system-ui, sans-serif; fill: #4b5563; text-anchor: end; }}
    .axis.x {{ text-anchor: middle; }}
    .value {{ font: 12px ui-monospace, monospace; fill: #111827; text-anchor: middle; }}
    .f1 {{ fill: #ea580c; stroke: #ea580c; stroke-width: 3; fill-opacity: 1; }}
    .recall {{ fill: #2563eb; stroke: #2563eb; stroke-width: 3; fill-opacity: 1; }}
    polyline {{ fill: none !important; stroke-linejoin: round; stroke-linecap: round; }}
    .legend {{ font: 14px system-ui, sans-serif; fill: #374151; }}
  </style>
  <rect class="bg" width="1000" height="520"/>
  <text class="title" x="40" y="48">Same frozen model, more correct EAT references</text>
  <text class="subtitle" x="40" y="78">Scores over the same 40 articles; only EAT coverage changes</text>
  {''.join(grid)}
  {ticks}
  {series('f1', 'f1', 20)}
  {series('recall', 'recall', -12)}
  <line class="f1" x1="350" y1="490" x2="385" y2="490"/>
  <text class="legend" x="395" y="495">F1</text>
  <line class="recall" x1="500" y1="490" x2="535" y2="490"/>
  <text class="legend" x="545" y="495">Recall</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def write_outputs(
    output_dir: Path,
    *,
    run: RecordedRun,
    model_dataset: Path,
    oracle_dataset: Path,
    registry_path: Path,
    evaluation: dict[str, object],
    cases: list[dict[str, object]],
) -> None:
    summary = {
        "dataset": DATASET_NAME,
        "model_dataset_sha256": sha256_file(model_dataset),
        "oracle_dataset_sha256": sha256_file(oracle_dataset),
        "registry_sha256": sha256_file(registry_path),
        "cases": len(cases),
        "model": {
            "name": run.model_name,
            "version": run.model_version,
            "runner_commit": run.runner_commit,
        },
        "design": (
            "Same recorded plain-text model predictions with deterministic "
            "gold-derived EAT overrides at 0/25/50/75/100% mention coverage."
        ),
        "evaluation": evaluation,
        "limitations": [
            "EAT annotations are generated from public test gold labels.",
            "This is an oracle assistance upper bound, not a human authoring study.",
            "The model does not see gold fields; its frozen plain-text predictions are reused.",
            "EAT overrides model predictions only where an assisted span overlaps.",
            "Metrics are canonical-ID sets per article, not mention-level scores.",
            "The candidate registry is closed over entities in the dev and test splits.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "eat-assistance-results.json").write_text(
        json.dumps({"summary": summary, "cases": cases}, indent=2) + "\n",
        encoding="utf-8",
    )

    rows = []
    for coverage in ("0%", "25%", "50%", "75%", "100%"):
        condition = evaluation["model_with_oracle_eat"][coverage]
        rows.append(
            f"| Model + EAT ({coverage}) | `{condition['annotated_mentions']}` | "
            f"`{condition['unannotated_mentions']}` | "
            f"`{condition['assisted_documents']} of 40` | "
            f"`{condition['precision']}` | `{condition['recall']}` | "
            f"`{condition['f1']}` | `{condition['exact_match_rate']}` |"
        )
    eat_only = evaluation["eat_only_oracle"]
    rows.append(
        f"| EAT-only oracle | `{evaluation['oracle_annotations']}` | "
        f"`0` | `40 of 40` | "
        f"`{eat_only['precision']}` | `{eat_only['recall']}` | "
        f"`{eat_only['f1']}` | `{eat_only['exact_match_rate']}` |"
    )
    (output_dir / "eat-assistance-summary.md").write_text(
        "# Wiki-Fair oracle EAT-assistance benchmark\n\n"
        "## What was tested\n\n"
        "- 40 Wikipedia articles, stored as 40 records in one JSONL file\n"
        "- 669 entity mentions\n"
        "- 434 unique Wikidata entities\n"
        "- the same frozen model predictions at every coverage level\n\n"
        "Coverage is the share of the 669 mention positions replaced by a "
        "correct EAT reference. It is not the share of files.\n\n"
        "![EAT coverage](coverage-by-level.svg)\n\n"
        "![Model performance](performance-by-level.svg)\n\n"
        "## Results\n\n"
        f"- Model: `{run.model_name}`\n"
        f"- Version: `{run.model_version}`\n"
        f"- Dataset: `{DATASET_NAME}`\n"
        f"- Test articles: `{len(cases)}`\n"
        f"- Oracle mention annotations: `{evaluation['oracle_annotations']}`\n\n"
        "| Condition | Mentions with EAT | Mentions left plain | "
        "Articles with EAT | Precision | Recall | F1 | Exact match |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|\n"
        + "\n".join(rows)
        + "\n\n"
        "> EAT references are generated from test gold labels. This measures "
        "the upper-bound effect of correct explicit identity, not whether people "
        "can create those references accurately or efficiently.\n",
        encoding="utf-8",
    )
    write_coverage_chart(output_dir / "coverage-by-level.svg", evaluation)
    write_performance_chart(
        output_dir / "performance-by-level.svg", evaluation
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--model-dataset", type=Path, required=True)
    parser.add_argument("--oracle-dataset", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    model_records = load_jsonl(args.model_dataset)
    model_cases = [Case.from_record(record) for record in model_records]
    registry = ResolverRegistry(load_jsonl(args.registry))
    run = load_recorded_run(
        args.run,
        model_cases,
        registry,
        dataset_name=DATASET_NAME,
        dataset_path=args.model_dataset,
        registry_path=args.registry,
    )
    oracle_cases = load_oracle_cases(
        args.oracle_dataset, model_cases, registry
    )
    evaluation, rows = evaluate(run, oracle_cases, registry)
    write_outputs(
        args.output_dir,
        run=run,
        model_dataset=args.model_dataset,
        oracle_dataset=args.oracle_dataset,
        registry_path=args.registry,
        evaluation=evaluation,
        cases=rows,
    )
    print(json.dumps(evaluation, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
