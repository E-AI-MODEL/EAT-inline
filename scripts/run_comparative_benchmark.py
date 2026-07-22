#!/usr/bin/env python3
"""Compare resolution conditions over the same gold cases via baseline adapters.

Each condition is a :class:`eat_baselines.BaselineAdapter`. The deterministic
plain-text and EAT Inline adapters run in CI; model-based adapters conform to
the same interface but are not bundled (see ``src/eat_baselines.py``).
"""

from __future__ import annotations

import json
from pathlib import Path

from eat_baselines import (
    Case,
    Cost,
    ResolverRegistry,
    default_adapters,
)
from eat_inline import VERSION

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
    registry = ResolverRegistry(load_jsonl(CORPUS / "entity-registry.jsonl"))
    cases = [Case.from_record(record) for record in load_jsonl(CORPUS / "comparison.jsonl")]
    adapters = default_adapters()

    totals = {
        adapter.condition: {"tp": 0, "fp": 0, "fn": 0, "exact": 0}
        for adapter in adapters
    }
    extras = {
        adapter.condition: {"ambiguous_mentions": 0, "unresolved": 0}
        for adapter in adapters
    }
    costs = {adapter.condition: Cost() for adapter in adapters}
    rows: list[dict[str, object]] = []

    for case in cases:
        gold = set(case.gold_ids)
        row: dict[str, object] = {"id": case.id, "gold_ids": sorted(gold)}
        for adapter in adapters:
            result = adapter.predict(case, registry)
            condition = adapter.condition
            tp, fp, fn = score(result.predicted_ids, gold)
            totals[condition]["tp"] += tp
            totals[condition]["fp"] += fp
            totals[condition]["fn"] += fn
            totals[condition]["exact"] += int(result.predicted_ids == gold)
            costs[condition].add(result.cost)
            row[f"{condition}_predicted_ids"] = sorted(result.predicted_ids)

            if condition == "plain":
                labels = list(result.diagnostics.get("ambiguous_labels", []))
                extras[condition]["ambiguous_mentions"] += len(labels)
                row["plain_ambiguous_labels"] = sorted(labels)
            elif condition == "eat_inline":
                unresolved = list(result.diagnostics.get("unresolved_references", []))
                extras[condition]["unresolved"] += len(unresolved)
                row["eat_inline_unresolved"] = unresolved
        rows.append(row)

    summary: dict[str, object] = {
        "eat_inline_version": VERSION,
        "dataset": "eat-inline-gold/comparison",
        "cases": len(cases),
        "design": "paired synthetic deterministic resolution benchmark",
        "adapters": [
            {
                "condition": adapter.condition,
                "name": adapter.name,
                "requires_model": adapter.requires_model,
            }
            for adapter in adapters
        ],
        "conditions": {},
        "limitations": [
            "Synthetic seed data is not evidence of real-world generalization.",
            "The plain-text baseline uses exact label matching and no language model.",
            "The EAT Inline condition receives author-supplied type and key information.",
            "Cost counters are deterministic effort proxies, not billed cost or latency.",
        ],
    }

    for adapter in adapters:
        condition = adapter.condition
        values = totals[condition]
        condition_result = {
            **metrics(values["tp"], values["fp"], values["fn"]),
            "exact_match_rate": round(values["exact"] / len(cases), 4),
            "true_positives": values["tp"],
            "false_positives": values["fp"],
            "false_negatives": values["fn"],
            "cost": costs[condition].to_dict(),
        }
        if condition == "plain":
            condition_result["ambiguous_mentions"] = extras[condition]["ambiguous_mentions"]
        elif condition == "eat_inline":
            condition_result["unresolved_references"] = extras[condition]["unresolved"]
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
        "Each condition is a baseline adapter over the same gold cases. Model-based "
        "conditions implement the same interface but are not bundled, to keep this "
        "benchmark deterministic and reproducible.\n\n"
        "> This is a paired synthetic benchmark. It demonstrates the measurable effect "
        "of supplying explicit type and key information under controlled conditions; "
        "it does not establish real-world superiority.\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
