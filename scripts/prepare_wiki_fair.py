#!/usr/bin/env python3
"""Create the frozen Wiki-Fair v2 model-training and test files.

The source repository and input bytes are pinned below. The transformation
writes separate inference and scorer files. The inference file contains only
``id`` and ``plain_text``; the scorer file keeps the test gold IDs. A separate
oracle-assistance file encodes those public annotations as EAT references for
controlled upper-bound experiments.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


UPSTREAM_REPOSITORY = "https://github.com/ad-freiburg/wiki-entity-linker"
UPSTREAM_COMMIT = "c9a3fe9c4933888d756d702fdb9ff607fc36aa26"
SOURCES = {
    "dev": (
        "benchmarks/wiki-fair-v2-dev-no-coref.benchmark.jsonl",
        "19f859e0b23dc5c955879e0300e5193022480f1f89d350f926a69c59d71d7ef3",
    ),
    "test": (
        "benchmarks/wiki-fair-v2-test-no-coref.benchmark.jsonl",
        "a45e272855362fd8be3dc95480dc2948ee37f9b0f031f1a6dc5788a9bc8f7dc1",
    ),
}
DATASET_NAME = f"wiki-fair-v2/test-no-coref@{UPSTREAM_COMMIT}"
_WIKIDATA_ID = re.compile(r"Q[1-9][0-9]*\Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source(upstream: Path, split: str) -> list[dict[str, object]]:
    relative_path, expected_hash = SOURCES[split]
    path = upstream / relative_path
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise ValueError(
            f"{path}: expected SHA-256 {expected_hash}, got {actual_hash}"
        )
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def entity_labels(record: dict[str, object]) -> list[dict[str, object]]:
    return [
        label
        for label in record["labels"]
        if "parent" not in label and _WIKIDATA_ID.fullmatch(str(label["entity_id"]))
    ]


def canonical_names(records: list[dict[str, object]]) -> dict[str, str]:
    names: dict[str, Counter[str]] = {}
    for record in records:
        for label in entity_labels(record):
            entity_id = str(label["entity_id"])
            names.setdefault(entity_id, Counter())[str(label["name"])] += 1
    return {
        entity_id: sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0].casefold(), item[0]),
        )[0][0]
        for entity_id, counts in names.items()
    }


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def render_eat_text(
    plain_text: str, annotations: list[dict[str, object]]
) -> str:
    """Replace non-overlapping annotated spans with typed EAT references."""

    chunks: list[str] = []
    cursor = 0
    for annotation in sorted(
        annotations, key=lambda item: (int(item["start"]), int(item["end"]))
    ):
        start, end = int(annotation["start"]), int(annotation["end"])
        if start < cursor or end <= start or end > len(plain_text):
            raise ValueError(f"invalid or overlapping oracle span {start}:{end}")
        chunks.append(plain_text[cursor:start])
        chunks.append(f"@@EAT {annotation['type']}:{annotation['key']}@@")
        cursor = end
    chunks.append(plain_text[cursor:])
    return "".join(chunks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="pinned wiki-entity-linker checkout")
    parser.add_argument("output", type=Path, help="directory for transformed files")
    args = parser.parse_args(argv)

    dev = load_source(args.upstream, "dev")
    test = load_source(args.upstream, "test")
    names = canonical_names(dev + test)

    training: list[dict[str, object]] = []
    for record in dev:
        mentions = [
            {
                "canonical_id": str(label["entity_id"]),
                "end": int(label["span"][1]),
                "start": int(label["span"][0]),
            }
            for label in entity_labels(record)
        ]
        training.append(
            {
                "id": f"wiki-fair-v2-dev-{record['id']}",
                "mentions": mentions,
                "plain_text": str(record["text"]),
                "source_url": str(record["url"]),
            }
        )

    inputs: list[dict[str, object]] = []
    comparison: list[dict[str, object]] = []
    oracle: list[dict[str, object]] = []
    oracle_annotations = 0
    for record in test:
        case_id = f"wiki-fair-v2-test-{record['id']}"
        labels = entity_labels(record)
        annotations = [
            {
                "end": int(label["span"][1]),
                "key": str(label["entity_id"]),
                "start": int(label["span"][0]),
                "type": "entity",
            }
            for label in labels
        ]
        oracle_annotations += len(annotations)
        gold_ids = sorted({str(label["entity_id"]) for label in labels})
        inputs.append(
            {
                "id": case_id,
                "plain_text": str(record["text"]),
            }
        )
        comparison.append(
            {
                "gold_ids": gold_ids,
                "id": case_id,
                "language": "en",
                "plain_text": str(record["text"]),
                "source_url": str(record["url"]),
            }
        )
        oracle.append(
            {
                "annotations": annotations,
                "eat_text": render_eat_text(str(record["text"]), annotations),
                "gold_ids": gold_ids,
                "id": case_id,
                "language": "en",
                "plain_text": str(record["text"]),
                "source_url": str(record["url"]),
            }
        )

    registry = [
        {
            "canonical_id": entity_id,
            "key": entity_id,
            "label": names[entity_id],
            "same_as": [f"https://www.wikidata.org/wiki/{entity_id}"],
            "type": "entity",
        }
        for entity_id in sorted(names, key=lambda value: int(value[1:]))
    ]

    args.output.mkdir(parents=True, exist_ok=True)
    paths = {
        "training": args.output / "dev.training.jsonl",
        "inputs": args.output / "test.inputs.jsonl",
        "test": args.output / "test.comparison.jsonl",
        "oracle": args.output / "test.oracle-eat.jsonl",
        "registry": args.output / "entity-registry.jsonl",
    }
    write_jsonl(paths["training"], training)
    write_jsonl(paths["inputs"], inputs)
    write_jsonl(paths["test"], comparison)
    write_jsonl(paths["oracle"], oracle)
    write_jsonl(paths["registry"], registry)

    manifest = {
        "dataset_name": DATASET_NAME,
        "derived_files": {
            name: {"path": path.name, "sha256": sha256_file(path)}
            for name, path in paths.items()
        },
        "records": {
            "registry_entities": len(registry),
            "oracle_annotations": oracle_annotations,
            "oracle_test_articles": len(oracle),
            "test_articles": len(comparison),
            "test_input_articles": len(inputs),
            "training_articles": len(training),
        },
        "source": {
            "commit": UPSTREAM_COMMIT,
            "files": {
                split: {"path": values[0], "sha256": values[1]}
                for split, values in SOURCES.items()
            },
            "repository": UPSTREAM_REPOSITORY,
        },
        "transform": {
            "excluded": [
                "nested labels with a parent field",
                "non-Wikidata identifiers such as DATETIME, QUANTITY and <NIL>",
            ],
            "test_input_fields": ["id", "plain_text"],
            "oracle_assistance": (
                "gold-derived EAT references for a controlled upper bound; "
                "not model input and not human-authored"
            ),
            "type": "entity",
        },
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
