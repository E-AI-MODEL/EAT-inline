#!/usr/bin/env python3
"""Small deterministic parser benchmark for CI and regression tracking."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from eat_inline import VERSION, parse_references

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmark" / "results"
ITERATIONS = 50000
TEXT = (
    "Het rapport is geschreven door @@EAT person:Hans_Visser@@ voor "
    "@@EAT organisation:EAI_Analyse_Advies@@."
)


def main() -> int:
    start = perf_counter()
    references = 0
    for _ in range(ITERATIONS):
        references += len(parse_references(TEXT))
    elapsed = perf_counter() - start

    result = {
        "specification": VERSION,
        "iterations": ITERATIONS,
        "references_parsed": references,
        "elapsed_seconds": round(elapsed, 6),
        "documents_per_second": round(ITERATIONS / elapsed, 2),
        "note": "CI smoke benchmark; not evidence of downstream superiority.",
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "benchmark-results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (RESULTS / "benchmark-summary.md").write_text(
        "# EAT Inline benchmark summary\n\n"
        f"- Specification: `{VERSION}`\n"
        f"- Iterations: `{ITERATIONS}`\n"
        f"- References parsed: `{references}`\n"
        f"- Documents per second: `{result['documents_per_second']}`\n\n"
        "> This is a deterministic CI smoke benchmark. It does not prove improved retrieval, resolution or RAG quality.\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
