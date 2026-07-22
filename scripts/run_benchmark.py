#!/usr/bin/env python3
"""Deterministic parser and syntax-overhead benchmark for CI."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from eat_inline import VERSION, parse_references

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmark" / "results"
ITERATIONS = 50000
PLAIN_TEXT = "Het rapport is geschreven door Hans Visser voor EAI Analyse & Advies."
EAT_TEXT = (
    "Het rapport is geschreven door @@EAT person:Hans_Visser@@ voor "
    "@@EAT organisation:EAI_Analyse_Advies@@."
)


def main() -> int:
    start = perf_counter()
    references = 0
    for _ in range(ITERATIONS):
        references += len(parse_references(EAT_TEXT))
    elapsed = perf_counter() - start

    overhead_characters = len(EAT_TEXT) - len(PLAIN_TEXT)
    overhead_ratio = len(EAT_TEXT) / len(PLAIN_TEXT)

    result = {
        "specification": VERSION,
        "iterations": ITERATIONS,
        "references_parsed": references,
        "elapsed_seconds": round(elapsed, 6),
        "documents_per_second": round(ITERATIONS / elapsed, 2),
        "plain_text_characters": len(PLAIN_TEXT),
        "eat_inline_characters": len(EAT_TEXT),
        "syntax_overhead_characters": overhead_characters,
        "length_ratio": round(overhead_ratio, 3),
        "note": (
            "Deterministic CI benchmark. Character overhead is a proxy, not a "
            "human writing-friction measurement."
        ),
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
        f"- Documents per second: `{result['documents_per_second']}`\n"
        f"- Plain-text characters: `{len(PLAIN_TEXT)}`\n"
        f"- EAT Inline characters: `{len(EAT_TEXT)}`\n"
        f"- Added syntax characters: `{overhead_characters}`\n"
        f"- Length ratio: `{result['length_ratio']}`\n\n"
        "> This benchmark measures parser throughput and visible character overhead. "
        "It does not prove acceptable human writing friction or improved retrieval, resolution or RAG quality.\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
