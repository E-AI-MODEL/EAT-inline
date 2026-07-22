#!/usr/bin/env python3
"""Run the deterministic EAT Inline conformance corpus."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from eat_inline import VERSION, validate_reference

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "conformance" / "manifest.json"


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures: list[str] = []

    if data["specification"] != VERSION:
        failures.append(
            f"version mismatch: corpus={data['specification']} implementation={VERSION}"
        )

    for case in data["cases"]:
        actual_valid, actual_result = validate_reference(case["input"])
        if actual_valid != case["valid"] or actual_result != case["result"]:
            failures.append(
                f"{case['id']}: expected ({case['valid']}, {case['result']!r}), "
                f"got ({actual_valid}, {actual_result!r})"
            )

    summary = {
        "specification": data["specification"],
        "implementation": VERSION,
        "cases": len(data["cases"]),
        "failures": len(failures),
        "status": "pass" if not failures else "fail",
    }
    print(json.dumps(summary, indent=2))

    for failure in failures:
        print(f"ERROR: {failure}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
