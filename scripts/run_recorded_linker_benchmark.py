#!/usr/bin/env python3
"""Validate and score a recorded model-linker run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from eat_baselines import (
    Case,
    Cost,
    PlainLabelMatchAdapter,
    ResolverRegistry,
    metrics,
    score,
)
from eat_inline import VERSION
from eat_recorded_runs import (
    RecordedLinkerAdapter,
    RecordedRunValidationError,
    load_recorded_run,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmark" / "corpora"
RESULTS = ROOT / "benchmark" / "results"
DATASET_NAME = "eat-inline-gold/comparison"


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate(
    adapter: RecordedLinkerAdapter,
    cases: list[Case],
    registry: ResolverRegistry,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    totals = {"tp": 0, "fp": 0, "fn": 0, "exact": 0}
    total_cost = Cost()
    rows: list[dict[str, object]] = []
    for case in cases:
        result = adapter.predict(case, registry)
        gold = set(case.gold_ids)
        tp, fp, fn = score(result.predicted_ids, gold)
        totals["tp"] += tp
        totals["fp"] += fp
        totals["fn"] += fn
        totals["exact"] += int(result.predicted_ids == gold)
        total_cost.add(result.cost)
        rows.append(
            {
                "id": case.id,
                "gold_ids": sorted(gold),
                "predicted_ids": sorted(result.predicted_ids),
                "diagnostics": result.diagnostics,
            }
        )

    condition = {
        **metrics(totals["tp"], totals["fp"], totals["fn"]),
        "exact_match_rate": round(totals["exact"] / len(cases), 4),
        "true_positives": totals["tp"],
        "false_positives": totals["fp"],
        "false_negatives": totals["fn"],
        "cost": total_cost.to_dict(),
    }
    return condition, rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="recorded linker-run JSON artifact")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=CORPUS / "comparison.jsonl",
        help="comparison JSONL to score",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=CORPUS / "entity-registry.jsonl",
        help="registry JSONL used by the recorded run",
    )
    parser.add_argument(
        "--dataset-name",
        default=DATASET_NAME,
        help="provenance name expected in the recorded run",
    )
    parser.add_argument("--output-dir", type=Path, default=RESULTS)
    args = parser.parse_args(argv)

    dataset_path = args.dataset
    registry_path = args.registry
    cases = [Case.from_record(item) for item in load_jsonl(dataset_path)]
    registry = ResolverRegistry(load_jsonl(registry_path))
    try:
        run = load_recorded_run(
            args.run,
            cases,
            registry,
            dataset_name=args.dataset_name,
            dataset_path=dataset_path,
            registry_path=registry_path,
        )
    except RecordedRunValidationError as error:
        print(json.dumps({"status": "fail", "errors": error.errors}, indent=2), file=sys.stderr)
        return 2

    adapter = RecordedLinkerAdapter(run)
    condition, rows = evaluate(adapter, cases, registry)
    baseline_condition, _ = evaluate(PlainLabelMatchAdapter(), cases, registry)
    summary = {
        "eat_inline_version": VERSION,
        "dataset": run.dataset_name,
        "dataset_sha256": run.dataset_sha256,
        "registry_sha256": run.registry_sha256,
        "cases": len(cases),
        "model": {
            "name": run.model_name,
            "version": run.model_version,
            "source": run.model_source,
        },
        "runner": {
            "source": run.runner_source,
            "commit": run.runner_commit,
            "command": run.runner_command,
            "parameters": run.runner_parameters,
        },
        "condition": condition,
        "baseline": {
            "name": PlainLabelMatchAdapter.name,
            "condition": baseline_condition,
        },
        "limitations": [
            "A recorded run proves only the supplied model, revision, configuration and dataset.",
            "The replay validates provenance and scoring but does not rerun the external model.",
            "Dataset provenance, candidate construction and limitations must be read alongside the result.",
        ],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "recorded-linker-results.json").write_text(
        json.dumps({"summary": summary, "cases": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "recorded-linker-summary.md").write_text(
        "# Recorded model-linker benchmark\n\n"
        f"- Model: `{run.model_name}`\n"
        f"- Version: `{run.model_version}`\n"
        f"- Dataset: `{run.dataset_name}`\n"
        f"- Dataset SHA-256: `{run.dataset_sha256}`\n"
        f"- Registry SHA-256: `{run.registry_sha256}`\n"
        f"- Cases: `{len(cases)}`\n"
        f"- Precision: `{condition['precision']}`\n"
        f"- Recall: `{condition['recall']}`\n"
        f"- F1: `{condition['f1']}`\n"
        f"- Exact-match rate: `{condition['exact_match_rate']}`\n\n"
        "| Condition | Precision | Recall | F1 | Exact match |\n"
        "|---|---:|---:|---:|---:|\n"
        f"| Recorded model | `{condition['precision']}` | `{condition['recall']}` | "
        f"`{condition['f1']}` | `{condition['exact_match_rate']}` |\n"
        f"| Plain label match | `{baseline_condition['precision']}` | "
        f"`{baseline_condition['recall']}` | `{baseline_condition['f1']}` | "
        f"`{baseline_condition['exact_match_rate']}` |\n\n"
        "> This file replays a validated external model run. It does not rerun the "
        "model or establish general superiority.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
