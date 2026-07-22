#!/usr/bin/env python3
"""Compare deterministic resolution with and without EAT Inline annotations."""

from __future__ import annotations

import json
from pathlib import Path

from eat_inline import VERSION, parse_references

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmark" / "corpora"
RESULTS = ROOT / "benchmark" / "results"


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def score(predicted: set[str], gold: set[str]) -> tuple[int, int, int]:
    return len(predicted & gold), len(predicted - gold), len(gold - predicted)


def metrics(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def main() -> int:
    registry = load_jsonl(CORPUS / "entity-registry.jsonl")
    cases = load_jsonl(CORPUS / "comparison.jsonl")

    by_typed_key = {
        (str(item["type"]), str(item["key"])): str(item["canonical_id"])
        for item in registry
    }
    by_label: dict[str, list[str]] = {}
    for item in registry:
        by_label.setdefault(str(item["label"]).casefold(), []).append(
            str(item["canonical_id"])
        )

    totals = {
        "plain": {"tp": 0, "fp": 0, "fn": 0, "exact": 0, "ambiguous_mentions": 0},
        "eat_inline": {"tp": 0, "fp": 0, "fn": 0, "exact": 0, "unresolved": 0},
    }
    rows: list[dict[str, object]] = []

    for case in cases:
        gold = set(str(value) for value in case["gold_ids"])

        plain_text = str(case["plain_text"]).casefold()
        plain_predicted: set[str] = set()
        ambiguous_labels: list[str] = []
        for label, candidates in by_label.items():
            occurrence_count = plain_text.count(label)
            if occurrence_count == 0:
                continue
            if len(candidates) == 1:
                plain_predicted.add(candidates[0])
            else:
                ambiguous_labels.extend([label] * occurrence_count)

        eat_predicted: set[str] = set()
        unresolved: list[str] = []
        for reference in parse_references(str(case["eat_text"])):
            canonical_id = by_typed_key.get((reference.type, reference.key))
            if canonical_id:
                eat_predicted.add(canonical_id)
            else:
                unresolved.append(reference.raw)

        for condition, predicted in (
            ("plain", plain_predicted),
            ("eat_inline", eat_predicted),
        ):
            tp, fp, fn = score(predicted, gold)
            totals[condition]["tp"] += tp
            totals[condition]["fp"] += fp
            totals[condition]["fn"] += fn
            totals[condition]["exact"] += int(predicted == gold)

        totals["plain"]["ambiguous_mentions"] += len(ambiguous_labels)
        totals["eat_inline"]["unresolved"] += len(unresolved)
        rows.append(
            {
                "id": case["id"],
                "gold_ids": sorted(gold),
                "plain_predicted_ids": sorted(plain_predicted),
                "eat_inline_predicted_ids": sorted(eat_predicted),
                "plain_ambiguous_labels": sorted(ambiguous_labels),
                "eat_inline_unresolved": unresolved,
            }
        )

    summary: dict[str, object] = {
        "eat_inline_version": VERSION,
        "dataset": "eat-inline-gold/comparison",
        "cases": len(cases),
        "design": "paired synthetic deterministic resolution benchmark",
        "conditions": {},
        "limitations": [
            "Synthetic seed data is not evidence of real-world generalization.",
            "The plain-text baseline uses exact label matching and no language model.",
            "The EAT Inline condition receives author-supplied type and key information.",
        ],
    }

    for condition in ("plain", "eat_inline"):
        values = totals[condition]
        condition_result = {
            **metrics(values["tp"], values["fp"], values["fn"]),
            "exact_match_rate": round(values["exact"] / len(cases), 4),
            "true_positives": values["tp"],
            "false_positives": values["fp"],
            "false_negatives": values["fn"],
        }
        if condition == "plain":
            condition_result["ambiguous_mentions"] = values["ambiguous_mentions"]
        else:
            condition_result["unresolved_references"] = values["unresolved"]
        summary["conditions"][condition] = condition_result

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "comparative-results.json").write_text(
        json.dumps({"summary": summary, "cases": rows}, indent=2) + "\n",
        encoding="utf-8",
    )

    plain = summary["conditions"]["plain"]
    eat = summary["conditions"]["eat_inline"]
    (RESULTS / "comparative-summary.md").write_text(
        "# EAT Inline comparative benchmark\n\n"
        f"- Dataset cases: `{len(cases)}`\n"
        f"- Plain-text F1: `{plain['f1']}`\n"
        f"- EAT Inline F1: `{eat['f1']}`\n"
        f"- Plain-text exact-match rate: `{plain['exact_match_rate']}`\n"
        f"- EAT Inline exact-match rate: `{eat['exact_match_rate']}`\n"
        f"- Plain ambiguous mentions: `{plain['ambiguous_mentions']}`\n"
        f"- EAT Inline unresolved references: `{eat['unresolved_references']}`\n\n"
        "> This is a paired synthetic benchmark. It demonstrates the measurable effect "
        "of supplying explicit type and key information under controlled conditions; "
        "it does not establish real-world superiority.\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
