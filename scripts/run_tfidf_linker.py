#!/usr/bin/env python3
"""Train and run the pinned TF-IDF entity retriever on plain text."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re


MODEL_NAME = "scikit-learn TF-IDF character n-gram entity retriever"
MODEL_VERSION = "scikit-learn==1.8.0;eat-profile-v1"
MODEL_SOURCE = "https://github.com/scikit-learn/scikit-learn/tree/1.8.0"
CONTEXT_CHARACTERS = 160
NGRAM_RANGE = (3, 5)
_COMMIT_RE = re.compile(r"[0-9a-f]{7,40}\Z")


@dataclass(frozen=True)
class Candidate:
    canonical_id: str
    type: str
    key: str
    label: str


@dataclass(frozen=True)
class Detection:
    start: int
    end: int
    candidates: tuple[str, ...]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_inputs(path: Path) -> list[dict[str, str]]:
    """Load inference records and reject every field outside the boundary."""

    inputs: list[dict[str, str]] = []
    for index, record in enumerate(load_jsonl(path)):
        if set(record) != {"id", "plain_text"}:
            raise ValueError(
                f"{path}:{index + 1}: inference fields must be exactly id and plain_text"
            )
        inputs.append(
            {"id": str(record["id"]), "plain_text": str(record["plain_text"])}
        )
    return inputs


def label_pattern(label: str) -> re.Pattern[str]:
    left = r"(?<!\w)" if label[0].isalnum() or label[0] == "_" else ""
    right = r"(?!\w)" if label[-1].isalnum() or label[-1] == "_" else ""
    return re.compile(left + re.escape(label) + right, re.IGNORECASE)


def detect_mentions(
    text: str, aliases: dict[str, tuple[str, ...]]
) -> list[Detection]:
    found: list[tuple[int, int, str, tuple[str, ...]]] = []
    for alias, candidates in aliases.items():
        for match in label_pattern(alias).finditer(text):
            found.append((match.start(), match.end(), alias, candidates))

    selected: list[tuple[int, int, str, tuple[str, ...]]] = []
    for item in sorted(found, key=lambda value: (-(value[1] - value[0]), value[0], value[2])):
        start, end, _, _ = item
        if any(start < chosen[1] and end > chosen[0] for chosen in selected):
            continue
        selected.append(item)
    return [
        Detection(start=start, end=end, candidates=candidates)
        for start, end, _, candidates in sorted(selected)
    ]


def context(text: str, start: int, end: int) -> str:
    return text[
        max(0, start - CONTEXT_CHARACTERS) : min(len(text), end + CONTEXT_CHARACTERS)
    ]


def build_model_data(
    registry_records: list[dict[str, object]],
    training_records: list[dict[str, object]],
) -> tuple[list[Candidate], dict[str, tuple[str, ...]], list[str]]:
    candidates = [
        Candidate(
            canonical_id=str(record["canonical_id"]),
            type=str(record["type"]),
            key=str(record["key"]),
            label=str(record["label"]),
        )
        for record in registry_records
    ]
    by_id = {candidate.canonical_id: candidate for candidate in candidates}
    aliases: dict[str, set[str]] = defaultdict(set)
    profiles: dict[str, list[str]] = {
        candidate.canonical_id: [candidate.label] for candidate in candidates
    }
    for candidate in candidates:
        aliases[candidate.label.casefold()].add(candidate.canonical_id)

    for record in training_records:
        text = str(record["plain_text"])
        for mention in record["mentions"]:
            entity_id = str(mention["canonical_id"])
            if entity_id not in by_id:
                raise ValueError(f"training data contains unknown entity {entity_id}")
            start, end = int(mention["start"]), int(mention["end"])
            label = text[start:end].strip()
            if len(label) < 2:
                continue
            aliases[label.casefold()].add(entity_id)
            profiles[entity_id].append(context(text, start, end))

    frozen_aliases = {
        alias: tuple(sorted(entity_ids))
        for alias, entity_ids in sorted(aliases.items())
        if alias
    }
    profile_texts = [
        " \n ".join(profiles[candidate.canonical_id]) for candidate in candidates
    ]
    return candidates, frozen_aliases, profile_texts


def make_run(
    *,
    training_path: Path,
    input_path: Path,
    dataset_path: Path,
    registry_path: Path,
    dataset_name: str,
    runner_commit: str,
) -> dict[str, object]:
    try:
        import sklearn
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError as error:
        raise RuntimeError("install the model extra with: pip install -e '.[model]'") from error

    if sklearn.__version__ != "1.8.0":
        raise RuntimeError(f"expected scikit-learn 1.8.0, got {sklearn.__version__}")
    if not _COMMIT_RE.fullmatch(runner_commit):
        raise ValueError("runner commit must be a 7 to 40 character lowercase Git SHA")

    training = load_jsonl(training_path)
    registry_records = load_jsonl(registry_path)
    inputs = load_inputs(input_path)
    candidates, aliases, profiles = build_model_data(registry_records, training)
    by_id = {candidate.canonical_id: candidate for candidate in candidates}
    candidate_index = {
        candidate.canonical_id: index for index, candidate in enumerate(candidates)
    }

    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        lowercase=True,
        ngram_range=NGRAM_RANGE,
        norm="l2",
        sublinear_tf=True,
    )
    profile_matrix = vectorizer.fit_transform(profiles)

    cases: list[dict[str, object]] = []
    for item in inputs:
        text = item["plain_text"]
        detections = detect_mentions(text, aliases)
        query_matrix = vectorizer.transform(
            [context(text, detection.start, detection.end) for detection in detections]
        )
        mentions: list[dict[str, object]] = []
        for row_index, detection in enumerate(detections):
            ranked: list[tuple[float, str]] = []
            for entity_id in detection.candidates:
                score = float(
                    query_matrix[row_index]
                    .multiply(profile_matrix[candidate_index[entity_id]])
                    .sum()
                )
                ranked.append((score, entity_id))
            _, entity_id = sorted(ranked, key=lambda value: (-value[0], value[1]))[0]
            candidate = by_id[entity_id]
            mentions.append(
                {
                    "end": detection.end,
                    "key": candidate.key,
                    "label": text[detection.start : detection.end],
                    "start": detection.start,
                    "type": candidate.type,
                }
            )
        cases.append(
            {
                "cost": {
                    "estimated_tokens": len(text.split()),
                    "model_calls": int(bool(detections)),
                },
                "id": item["id"],
                "mentions": mentions,
            }
        )

    command = (
        "python scripts/run_tfidf_linker.py "
        "--training benchmark/external/wiki-fair-v2/dev.training.jsonl "
        "--input benchmark/external/wiki-fair-v2/test.inputs.jsonl "
        "--dataset benchmark/external/wiki-fair-v2/test.comparison.jsonl "
        "--registry benchmark/external/wiki-fair-v2/entity-registry.jsonl "
        f"--dataset-name {dataset_name} --runner-commit {runner_commit} "
        "--output benchmark/results/wiki-fair-v2-tfidf-linker-run.json"
    )
    return {
        "cases": cases,
        "dataset": {
            "name": dataset_name,
            "registry_sha256": sha256_file(registry_path),
            "sha256": sha256_file(dataset_path),
        },
        "input": "plain_text",
        "model": {
            "name": MODEL_NAME,
            "source": MODEL_SOURCE,
            "version": MODEL_VERSION,
        },
        "runner": {
            "command": command,
            "commit": runner_commit,
            "parameters": {
                "candidate_generation": "registry labels plus dev-only mention aliases",
                "context_characters_each_side": CONTEXT_CHARACTERS,
                "input_sha256": sha256_file(input_path),
                "ngram_range": list(NGRAM_RANGE),
                "training_sha256": sha256_file(training_path),
                "vectorizer_analyzer": "char_wb",
                "vectorizer_norm": "l2",
                "vectorizer_sublinear_tf": True,
            },
            "source": (
                "https://github.com/E-AI-MODEL/EAT-inline/blob/"
                f"{runner_commit}/scripts/run_tfidf_linker.py"
            ),
        },
        "schema_version": "1.0",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--runner-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    run = make_run(
        training_path=args.training,
        input_path=args.input,
        dataset_path=args.dataset,
        registry_path=args.registry,
        dataset_name=args.dataset_name,
        runner_commit=args.runner_commit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(run, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
