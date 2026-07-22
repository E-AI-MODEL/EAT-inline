#!/usr/bin/env python3
"""Validate the seed benchmark corpus and produce a machine-readable summary."""

from __future__ import annotations

import json
from pathlib import Path

from eat_inline import VERSION, parse_references, validate_reference

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmark" / "corpora"
RESULTS = ROOT / "benchmark" / "results"


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    vocabulary = json.loads((CORPUS / "type-vocabulary.json").read_text(encoding="utf-8"))
    registry = load_jsonl(CORPUS / "entity-registry.jsonl")
    failures: list[str] = []
    counts: dict[str, int] = {}

    if manifest["eat_inline_version"] != VERSION:
        failures.append(
            f"version mismatch: corpus={manifest['eat_inline_version']} implementation={VERSION}"
        )

    allowed_types = set(vocabulary["types"])
    registry_by_typed_key: dict[tuple[str, str], str] = {}
    registry_ids: set[str] = set()
    for item in registry:
        typed_key = (str(item["type"]), str(item["key"]))
        canonical_id = str(item["canonical_id"])
        if typed_key in registry_by_typed_key:
            failures.append(f"duplicate registry typed key: {typed_key}")
        if canonical_id in registry_ids:
            failures.append(f"duplicate canonical id: {canonical_id}")
        if item["type"] not in allowed_types:
            failures.append(f"registry contains unknown benchmark type {item['type']!r}")
        registry_by_typed_key[typed_key] = canonical_id
        registry_ids.add(canonical_id)

    syntax = load_jsonl(CORPUS / "syntax.jsonl")
    counts["syntax"] = len(syntax)
    for case in syntax:
        value = str(case["input"])
        if value.startswith("@@EAT ") and value.endswith("@@"):
            actual_valid, actual_result = validate_reference(value)
        else:
            references = parse_references(value)
            actual_valid = bool(references)
            actual_result = "valid" if actual_valid else str(case.get("error", "invalid"))
        if actual_valid != bool(case["valid"]):
            failures.append(f"{case['id']}: expected valid={case['valid']} got {actual_valid}")
        if not case["valid"] and value.startswith("@@EAT ") and value.endswith("@@"):
            expected_error = case.get("error")
            if expected_error and actual_result != expected_error:
                failures.append(f"{case['id']}: expected {expected_error!r} got {actual_result!r}")

    typing = load_jsonl(CORPUS / "typing.jsonl")
    counts["typing"] = len(typing)
    for case in typing:
        if case["expected_type"] not in allowed_types:
            failures.append(f"{case['id']}: unknown benchmark type {case['expected_type']!r}")
        candidate = f"@@EAT {case['expected_type']}:{case['expected_key']}@@"
        valid, result = validate_reference(candidate)
        if not valid:
            failures.append(f"{case['id']}: generated reference is invalid: {result}")

    resolution = load_jsonl(CORPUS / "resolution.jsonl")
    counts["resolution"] = len(resolution)
    for case in resolution:
        parsed = parse_references(str(case["text"]))
        expected = case["references"]
        if [(item.type, item.key) for item in parsed] != [
            (item["type"], item["key"]) for item in expected
        ]:
            failures.append(f"{case['id']}: parsed references do not match gold references")
        for item in expected:
            typed_key = (str(item["type"]), str(item["key"]))
            if registry_by_typed_key.get(typed_key) != item["canonical_id"]:
                failures.append(f"{case['id']}: registry mismatch for {typed_key}")

    generation = load_jsonl(CORPUS / "generation.jsonl")
    counts["generation"] = len(generation)
    for case in generation:
        if not parse_references(str(case["expected"])):
            failures.append(f"{case['id']}: expected output contains no valid reference")

    comparison = load_jsonl(CORPUS / "comparison.jsonl")
    counts["comparison"] = len(comparison)
    for case in comparison:
        parsed = parse_references(str(case["eat_text"]))
        resolved_ids: list[str] = []
        for item in parsed:
            canonical_id = registry_by_typed_key.get((item.type, item.key))
            if canonical_id is None:
                failures.append(f"{case['id']}: EAT reference is absent from registry: {item.raw}")
            else:
                resolved_ids.append(canonical_id)
        if set(resolved_ids) != set(str(value) for value in case["gold_ids"]):
            failures.append(f"{case['id']}: resolved EAT IDs do not match gold IDs")
        if not str(case["plain_text"]).strip():
            failures.append(f"{case['id']}: empty plain-text condition")

    declared = {item["task"]: item["records"] for item in manifest["files"]}
    if counts != declared:
        failures.append(f"manifest counts {declared} do not match files {counts}")

    total = sum(counts.values())
    if total != manifest["records_total"]:
        failures.append(
            f"manifest total {manifest['records_total']} does not match actual total {total}"
        )

    summary = {
        "eat_inline_version": VERSION,
        "dataset": manifest["dataset"],
        "dataset_version": manifest["version"],
        "records": counts,
        "records_total": total,
        "benchmark_types": len(allowed_types),
        "registry_entities": len(registry),
        "failures": failures,
        "status": "pass" if not failures else "fail",
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "dataset-validation.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
