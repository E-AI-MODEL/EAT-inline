#!/usr/bin/env python3
"""Measure EAT indexing and entity lookup over a 100,000-document workload."""

from __future__ import annotations

import argparse
from array import array
import hashlib
from html import escape
import json
import math
import os
from pathlib import Path
import platform
import statistics
import time

from eat_baselines import ResolverRegistry
from eat_inline import parse_references
from eat_recorded_runs import sha256_file


BENCHMARK_NAME = "wiki-fair-v2-eat-scale-search-v1"
DEFAULT_DOCUMENTS = 100_000
DEFAULT_QUERY_REPETITIONS = 100
DEFAULT_QUERY_ROUNDS = 20


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def cpu_model() -> str:
    path = Path("/proc/cpuinfo")
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown"


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("cannot take a percentile of an empty sample")
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def resolve_source_documents(
    records: list[dict[str, object]],
    registry: ResolverRegistry,
) -> list[dict[str, object]]:
    resolved: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for row_number, record in enumerate(records, start=1):
        document_id = str(record["id"])
        if document_id in seen_ids:
            raise ValueError(f"duplicate source document {document_id}")
        seen_ids.add(document_id)
        gold_ids = frozenset(str(value) for value in record["gold_ids"])
        references = parse_references(str(record["eat_text"]))
        resolved_ids: set[str] = set()
        for reference in references:
            canonical_id = registry.resolve_typed(reference.type, reference.key)
            if canonical_id is None:
                raise ValueError(
                    f"source row {row_number}: unresolved "
                    f"{reference.type}:{reference.key}"
                )
            resolved_ids.add(canonical_id)
        if resolved_ids != set(gold_ids):
            raise ValueError(
                f"source row {row_number}: EAT references do not match gold IDs"
            )
        resolved.append(
            {
                "id": document_id,
                "plain_text": str(record["plain_text"]),
                "eat_text": str(record["eat_text"]),
                "gold_ids": gold_ids,
                "reference_count": len(references),
            }
        )
    if not resolved:
        raise ValueError("source dataset is empty")
    return resolved


def empty_index(entity_ids: set[str]) -> dict[str, array]:
    return {entity_id: array("I") for entity_id in sorted(entity_ids)}


def build_metadata_index(
    sources: list[dict[str, object]],
    document_count: int,
) -> tuple[dict[str, array], float]:
    """Build the control index from the same IDs stored as separate metadata."""

    entity_ids = {
        entity_id
        for source in sources
        for entity_id in source["gold_ids"]
    }
    index = empty_index(entity_ids)
    start = time.perf_counter()
    for ordinal in range(document_count):
        source = sources[ordinal % len(sources)]
        for entity_id in source["gold_ids"]:
            index[entity_id].append(ordinal)
    return index, time.perf_counter() - start


def build_eat_index(
    sources: list[dict[str, object]],
    document_count: int,
    registry: ResolverRegistry,
) -> tuple[dict[str, array], float, int]:
    """Parse full EAT text and build an entity-to-document index."""

    entity_ids = {
        entity_id
        for source in sources
        for entity_id in source["gold_ids"]
    }
    index = empty_index(entity_ids)
    reference_count = 0
    start = time.perf_counter()
    for ordinal in range(document_count):
        source = sources[ordinal % len(sources)]
        document_ids: set[str] = set()
        references = parse_references(source["eat_text"])
        reference_count += len(references)
        for reference in references:
            canonical_id = registry.resolve_typed(reference.type, reference.key)
            if canonical_id is None:
                raise ValueError(
                    f"workload document {ordinal}: unresolved "
                    f"{reference.type}:{reference.key}"
                )
            document_ids.add(canonical_id)
        for entity_id in document_ids:
            index[entity_id].append(ordinal)
    return index, time.perf_counter() - start, reference_count


def index_fingerprint(index: dict[str, array]) -> str:
    digest = hashlib.sha256()
    for entity_id, postings in sorted(index.items()):
        digest.update(entity_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(postings).to_bytes(8, "big"))
        digest.update(postings.tobytes())
    return digest.hexdigest()


def measure_search_pair(
    metadata_index: dict[str, array],
    eat_index: dict[str, array],
    query_ids: list[str],
    *,
    repetitions: int,
    rounds: int,
) -> dict[str, dict[str, object]]:
    indexes = {
        "metadata_control": metadata_index,
        "eat_inline": eat_index,
    }
    samples_us = {name: [] for name in indexes}
    checksums = {name: 0 for name in indexes}
    elapsed_ns = {name: 0 for name in indexes}
    for round_number in range(rounds):
        rotated = (
            query_ids[round_number % len(query_ids) :]
            + query_ids[: round_number % len(query_ids)]
        )
        for query_number, entity_id in enumerate(rotated):
            names = list(indexes)
            if (round_number + query_number) % 2:
                names.reverse()
            for name in names:
                sample_start = time.perf_counter_ns()
                for _ in range(repetitions):
                    postings = indexes[name][entity_id]
                    checksums[name] = (
                        checksums[name] + len(postings)
                    ) & ((1 << 64) - 1)
                    if postings:
                        checksums[name] = (
                            checksums[name] + postings[0] + postings[-1]
                        ) & ((1 << 64) - 1)
                sample_ns = time.perf_counter_ns() - sample_start
                elapsed_ns[name] += sample_ns
                samples_us[name].append(
                    sample_ns / repetitions / 1_000
                )
    operations = len(query_ids) * repetitions * rounds
    return {
        name: {
            "queries": len(query_ids),
            "rounds": rounds,
            "repetitions_per_query": repetitions,
            "lookup_operations": operations,
            "elapsed_seconds": round(elapsed_ns[name] / 1_000_000_000, 6),
            "p50_microseconds": round(
                statistics.median(samples_us[name]), 4
            ),
            "p95_microseconds": round(
                percentile(samples_us[name], 0.95), 4
            ),
            "p99_microseconds": round(
                percentile(samples_us[name], 0.99), 4
            ),
            "operations_per_second": round(
                operations / (elapsed_ns[name] / 1_000_000_000),
                2,
            ),
            "checksum": checksums[name],
        }
        for name in indexes
    }


def measure_result_scan_pair(
    metadata_index: dict[str, array],
    eat_index: dict[str, array],
    query_ids: list[str],
    *,
    rounds: int,
) -> dict[str, dict[str, object]]:
    """Measure lookup plus reading every matching document ordinal."""

    indexes = {
        "metadata_control": metadata_index,
        "eat_inline": eat_index,
    }
    samples_us = {name: [] for name in indexes}
    checksums = {name: 0 for name in indexes}
    document_ids_read = {name: 0 for name in indexes}
    elapsed_ns = {name: 0 for name in indexes}
    for round_number in range(rounds):
        rotated = (
            query_ids[round_number % len(query_ids) :]
            + query_ids[: round_number % len(query_ids)]
        )
        for query_number, entity_id in enumerate(rotated):
            names = list(indexes)
            if (round_number + query_number) % 2:
                names.reverse()
            for name in names:
                sample_start = time.perf_counter_ns()
                postings = indexes[name][entity_id]
                postings_sum = sum(postings)
                sample_ns = time.perf_counter_ns() - sample_start
                elapsed_ns[name] += sample_ns
                document_ids_read[name] += len(postings)
                checksums[name] = (
                    checksums[name] + postings_sum + len(postings)
                ) & ((1 << 64) - 1)
                samples_us[name].append(sample_ns / 1_000)
    searches = len(query_ids) * rounds
    return {
        name: {
            "queries": len(query_ids),
            "rounds": rounds,
            "searches": searches,
            "document_ids_read": document_ids_read[name],
            "elapsed_seconds": round(
                elapsed_ns[name] / 1_000_000_000, 6
            ),
            "p50_microseconds": round(
                statistics.median(samples_us[name]), 4
            ),
            "p95_microseconds": round(
                percentile(samples_us[name], 0.95), 4
            ),
            "p99_microseconds": round(
                percentile(samples_us[name], 0.99), 4
            ),
            "document_ids_per_second": round(
                document_ids_read[name]
                / (elapsed_ns[name] / 1_000_000_000),
                2,
            ),
            "checksum": checksums[name],
        }
        for name in indexes
    }


def workload_totals(
    sources: list[dict[str, object]],
    document_count: int,
) -> dict[str, int]:
    totals = {
        "plain_text_bytes": 0,
        "eat_text_bytes": 0,
        "eat_references": 0,
        "document_entity_pairs": 0,
    }
    for ordinal in range(document_count):
        source = sources[ordinal % len(sources)]
        totals["plain_text_bytes"] += len(source["plain_text"].encode("utf-8"))
        totals["eat_text_bytes"] += len(source["eat_text"].encode("utf-8"))
        totals["eat_references"] += int(source["reference_count"])
        totals["document_entity_pairs"] += len(source["gold_ids"])
    return totals


def run_benchmark(
    *,
    sources: list[dict[str, object]],
    registry: ResolverRegistry,
    document_count: int,
    query_repetitions: int,
    query_rounds: int,
) -> dict[str, object]:
    if document_count <= 0:
        raise ValueError("document_count must be positive")
    if document_count >= 2**32:
        raise ValueError("document_count exceeds the 32-bit postings format")
    if query_repetitions <= 0 or query_rounds <= 0:
        raise ValueError("query repetitions and rounds must be positive")

    totals = workload_totals(sources, document_count)
    metadata_index, metadata_seconds = build_metadata_index(
        sources, document_count
    )
    eat_index, eat_seconds, parsed_references = build_eat_index(
        sources, document_count, registry
    )
    if parsed_references != totals["eat_references"]:
        raise ValueError("parsed reference count does not match workload")

    metadata_fingerprint = index_fingerprint(metadata_index)
    eat_fingerprint = index_fingerprint(eat_index)
    if metadata_fingerprint != eat_fingerprint:
        raise ValueError("EAT and metadata indexes are not identical")

    query_ids = sorted(eat_index)
    lookup_results = measure_search_pair(
        metadata_index,
        eat_index,
        query_ids,
        repetitions=query_repetitions,
        rounds=query_rounds,
    )
    metadata_search = lookup_results["metadata_control"]
    eat_search = lookup_results["eat_inline"]
    if metadata_search["checksum"] != eat_search["checksum"]:
        raise ValueError("search result checksum differs between indexes")
    scan_results = measure_result_scan_pair(
        metadata_index,
        eat_index,
        query_ids,
        rounds=query_rounds,
    )
    metadata_scan = scan_results["metadata_control"]
    eat_scan = scan_results["eat_inline"]
    if metadata_scan["checksum"] != eat_scan["checksum"]:
        raise ValueError("result-scan checksum differs between indexes")

    postings = sum(len(values) for values in eat_index.values())
    item_size = next(iter(eat_index.values())).itemsize
    return {
        "workload": {
            "generated_documents": document_count,
            "different_source_documents": len(sources),
            "generation_method": (
                "repeat the 40 source documents in deterministic order and "
                "assign each workload copy a distinct integer document ID"
            ),
            "different_entities": len(eat_index),
            **totals,
            "eat_markup_extra_bytes": (
                totals["eat_text_bytes"] - totals["plain_text_bytes"]
            ),
        },
        "index": {
            "entity_keys": len(eat_index),
            "postings": postings,
            "postings_payload_bytes": postings * item_size,
            "postings_integer_bits": item_size * 8,
            "fingerprint_sha256": eat_fingerprint,
            "indexes_identical": True,
        },
        "index_build": {
            "metadata_control_seconds": round(metadata_seconds, 6),
            "eat_inline_seconds": round(eat_seconds, 6),
            "eat_documents_per_second": round(document_count / eat_seconds, 2),
            "eat_megabytes_per_second": round(
                totals["eat_text_bytes"] / 1_000_000 / eat_seconds, 2
            ),
            "eat_extra_seconds": round(eat_seconds - metadata_seconds, 6),
        },
        "entity_lookup": {
            "definition": (
                "given one canonical entity ID, return the indexed workload "
                "document ordinals that contain it"
            ),
            "index_lookup_only": {
                "metadata_control": metadata_search,
                "eat_inline": eat_search,
                "p50_difference_microseconds": round(
                    float(eat_search["p50_microseconds"])
                    - float(metadata_search["p50_microseconds"]),
                    4,
                ),
            },
            "lookup_and_read_all_results": {
                "metadata_control": metadata_scan,
                "eat_inline": eat_scan,
                "p50_difference_microseconds": round(
                    float(eat_scan["p50_microseconds"])
                    - float(metadata_scan["p50_microseconds"]),
                    4,
                ),
            },
        },
    }


def write_overview_chart(path: Path, result: dict[str, object]) -> None:
    workload = result["workload"]
    document_count = int(workload["generated_documents"])
    reference_count = int(workload["eat_references"])
    pair_count = int(workload["document_entity_pairs"])
    values = [
        ("Generated documents", document_count),
        ("EAT references parsed", reference_count),
        ("Document-entity pairs", pair_count),
    ]
    maximum = max(value for _, value in values)
    rows = []
    for index, (label, value) in enumerate(values):
        y = 145 + index * 85
        width = round(650 * value / maximum)
        rows.append(
            f'<text class="label" x="40" y="{y + 24}">{escape(label)}</text>'
            f'<rect class="bar" x="260" y="{y}" width="{width}" '
            f'height="34" rx="5"/>'
            f'<text class="value" x="{270 + width}" y="{y + 24}">'
            f'{value:,}</text>'
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="470" viewBox="0 0 1100 470" role="img">
  <title>Scale-search workload size</title>
  <desc>{document_count:,} generated documents containing {reference_count:,} EAT references and {pair_count:,} document-entity pairs.</desc>
  <style>
    .bg {{ fill: #ffffff; }}
    .title {{ font: 700 27px system-ui, sans-serif; fill: #111827; }}
    .subtitle {{ font: 15px system-ui, sans-serif; fill: #4b5563; }}
    .label {{ font: 15px system-ui, sans-serif; fill: #374151; }}
    .value {{ font: 700 15px ui-monospace, monospace; fill: #111827; }}
    .bar {{ fill: #2563eb; }}
  </style>
  <rect class="bg" width="1100" height="470"/>
  <text class="title" x="40" y="48">{document_count:,}-document EAT scale workload</text>
  <text class="subtitle" x="40" y="78">Generated from 40 different Wikipedia source pages; every scored position has EAT</text>
  {''.join(rows)}
  <text class="subtitle" x="40" y="430">The document copies have distinct IDs, but the underlying source text repeats.</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def write_search_chart(path: Path, result: dict[str, object]) -> None:
    lookup = result["entity_lookup"]
    scan = lookup["lookup_and_read_all_results"]
    control = scan["metadata_control"]
    eat = scan["eat_inline"]
    metrics = [
        ("p50", float(control["p50_microseconds"]), float(eat["p50_microseconds"])),
        ("p95", float(control["p95_microseconds"]), float(eat["p95_microseconds"])),
        ("p99", float(control["p99_microseconds"]), float(eat["p99_microseconds"])),
    ]
    maximum = max(max(control_value, eat_value) for _, control_value, eat_value in metrics)
    rows = []
    for index, (label, control_value, eat_value) in enumerate(metrics):
        y = 150 + index * 95
        control_width = round(580 * control_value / maximum)
        eat_width = round(580 * eat_value / maximum)
        rows.append(
            f'<text class="metric" x="75" y="{y + 34}">{label}</text>'
            f'<rect class="control" x="130" y="{y}" width="{control_width}" '
            f'height="26" rx="4"/>'
            f'<text class="value" x="{145 + control_width}" y="{y + 19}">'
            f'{control_value:.4f} µs</text>'
            f'<rect class="eat" x="130" y="{y + 34}" width="{eat_width}" '
            f'height="26" rx="4"/>'
            f'<text class="value" x="{145 + eat_width}" y="{y + 53}">'
            f'{eat_value:.4f} µs</text>'
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="520" viewBox="0 0 1050 520" role="img">
  <title>Entity search latency after indexing</title>
  <desc>p50, p95 and p99 latency for lookup plus reading every matching document ID from identical indexes.</desc>
  <style>
    .bg {{ fill: #ffffff; }}
    .title {{ font: 700 27px system-ui, sans-serif; fill: #111827; }}
    .subtitle {{ font: 15px system-ui, sans-serif; fill: #4b5563; }}
    .metric {{ font: 700 15px system-ui, sans-serif; fill: #111827; text-anchor: end; }}
    .value {{ font: 13px ui-monospace, monospace; fill: #111827; }}
    .legend {{ font: 13px system-ui, sans-serif; fill: #4b5563; }}
    .control {{ fill: #9ca3af; }}
    .eat {{ fill: #2563eb; }}
  </style>
  <rect class="bg" width="1050" height="520"/>
  <text class="title" x="40" y="48">Entity search time after indexing</text>
  <text class="subtitle" x="40" y="78">Same query and identical postings; lookup plus reading every matching document ID</text>
  <rect class="control" x="130" y="100" width="18" height="12" rx="2"/>
  <text class="legend" x="156" y="111">IDs stored as separate metadata</text>
  <rect class="eat" x="410" y="100" width="18" height="12" rx="2"/>
  <text class="legend" x="436" y="111">IDs parsed from inline EAT</text>
  {''.join(rows)}
  <text class="subtitle" x="40" y="485">This is canonical-entity lookup, not keyword, full-text or vector search.</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def write_outputs(
    output_dir: Path,
    *,
    oracle_path: Path,
    registry_path: Path,
    result: dict[str, object],
    command: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    workload = result["workload"]
    artifact = {
        "benchmark": BENCHMARK_NAME,
        "inputs": {
            "oracle_dataset": str(oracle_path),
            "oracle_dataset_sha256": sha256_file(oracle_path),
            "registry": str(registry_path),
            "registry_sha256": sha256_file(registry_path),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_model": cpu_model(),
            "logical_cpu_count": os.cpu_count(),
        },
        "command": command,
        "result": result,
        "limitations": [
            (
                f"The {workload['generated_documents']:,} workload documents "
                f"repeat {workload['different_source_documents']} different "
                "source documents."
            ),
            "Timings are machine-dependent and are not CI pass/fail thresholds.",
            "The control receives the same correct entity IDs as separate metadata.",
            "The benchmark measures canonical-entity lookup and result traversal after indexing.",
            "It does not measure keyword, full-text, semantic or vector search.",
            "It does not test Word, PDF, Excel, Markdown or HTML round trips.",
        ],
    }
    (output_dir / "scale-search-results.json").write_text(
        json.dumps(artifact, indent=2) + "\n",
        encoding="utf-8",
    )

    build = result["index_build"]
    lookup = result["entity_lookup"]
    lookup_only = lookup["index_lookup_only"]
    control = lookup_only["metadata_control"]
    eat = lookup_only["eat_inline"]
    scan = lookup["lookup_and_read_all_results"]
    control_scan = scan["metadata_control"]
    eat_scan = scan["eat_inline"]
    (output_dir / "scale-search-summary.md").write_text(
        f"# {workload['generated_documents']:,}-document EAT scale-search benchmark\n\n"
        "## What ran\n\n"
        f"- {workload['generated_documents']:,} generated workload documents\n"
        f"- {workload['different_source_documents']} different Wikipedia source pages\n"
        f"- {workload['eat_references']:,} parsed EAT references\n"
        f"- {workload['document_entity_pairs']:,} document-entity pairs\n"
        f"- {workload['different_entities']:,} different entities queried\n\n"
        f"Inline EAT adds {workload['eat_markup_extra_bytes']:,} bytes "
        "to the plain-text workload. The 32-bit postings payload is "
        f"{result['index']['postings_payload_bytes']:,} bytes, excluding "
        "Python container overhead.\n\n"
        "Every workload document has a distinct integer ID. The source text "
        "repeats, so this is a scale and overhead test, not a "
        f"{workload['generated_documents']:,}-different-source-document test.\n\n"
        "![Scale workload](scale-overview.svg)\n\n"
        "## Indexing\n\n"
        "| Input representation | Build time | Documents/second |\n"
        "|---|---:|---:|\n"
        f"| Correct IDs as separate metadata | {build['metadata_control_seconds']} s | n/a |\n"
        f"| IDs parsed from full inline EAT | {build['eat_inline_seconds']} s | "
        f"{build['eat_documents_per_second']:,} |\n\n"
        "## Entity lookup after indexing\n\n"
        "This first table measures only finding the existing postings list.\n\n"
        "| Index source | p50 | p95 | p99 | Operations/second |\n"
        "|---|---:|---:|---:|---:|\n"
        f"| Separate metadata | {control['p50_microseconds']} µs | "
        f"{control['p95_microseconds']} µs | {control['p99_microseconds']} µs | "
        f"{control['operations_per_second']:,} |\n"
        f"| Inline EAT | {eat['p50_microseconds']} µs | "
        f"{eat['p95_microseconds']} µs | {eat['p99_microseconds']} µs | "
        f"{eat['operations_per_second']:,} |\n\n"
        "This second table includes reading every matching document ID.\n\n"
        "| Index source | p50 | p95 | p99 | Document IDs read/second |\n"
        "|---|---:|---:|---:|---:|\n"
        f"| Separate metadata | {control_scan['p50_microseconds']} µs | "
        f"{control_scan['p95_microseconds']} µs | "
        f"{control_scan['p99_microseconds']} µs | "
        f"{control_scan['document_ids_per_second']:,} |\n"
        f"| Inline EAT | {eat_scan['p50_microseconds']} µs | "
        f"{eat_scan['p95_microseconds']} µs | "
        f"{eat_scan['p99_microseconds']} µs | "
        f"{eat_scan['document_ids_per_second']:,} |\n\n"
        "![Entity search latency](search-latency.svg)\n\n"
        "Both routes produce an identical entity-to-document index. Search "
        "means looking up one canonical entity ID and returning matching "
        "document IDs. It is not keyword, full-text or vector search.\n",
        encoding="utf-8",
    )
    write_overview_chart(output_dir / "scale-overview.svg", result)
    write_search_chart(output_dir / "search-latency.svg", result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-dataset", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--documents", type=int, default=DEFAULT_DOCUMENTS)
    parser.add_argument(
        "--query-repetitions",
        type=int,
        default=DEFAULT_QUERY_REPETITIONS,
    )
    parser.add_argument(
        "--query-rounds",
        type=int,
        default=DEFAULT_QUERY_ROUNDS,
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    registry = ResolverRegistry(load_jsonl(args.registry))
    sources = resolve_source_documents(
        load_jsonl(args.oracle_dataset),
        registry,
    )
    result = run_benchmark(
        sources=sources,
        registry=registry,
        document_count=args.documents,
        query_repetitions=args.query_repetitions,
        query_rounds=args.query_rounds,
    )
    command = (
        "python scripts/run_scale_search_benchmark.py "
        f"--oracle-dataset {args.oracle_dataset} "
        f"--registry {args.registry} "
        f"--documents {args.documents} "
        f"--query-repetitions {args.query_repetitions} "
        f"--query-rounds {args.query_rounds} "
        f"--output-dir {args.output_dir}"
    )
    write_outputs(
        args.output_dir,
        oracle_path=args.oracle_dataset,
        registry_path=args.registry,
        result=result,
        command=command,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
