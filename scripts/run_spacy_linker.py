#!/usr/bin/env python3
"""Run a spaCy NER + word-vector entity linker on plain text.

This is a recorded-run producer for the same boundary as
``scripts/run_tfidf_linker.py``: it reads only ``{id, plain_text}`` inference
records, detects entity spans with a real statistical NER model, links each span
to the closed registry with averaged word-vector cosine similarity, and writes a
``schemas/linker-run.schema.json``-conformant artifact. The heavy model runs once,
outside CI; ``scripts/run_recorded_linker_benchmark.py`` then validates provenance
and replays the recorded predictions deterministically.

The pure functions (input loading, article normalization, candidate lookup,
overlap selection, run assembly) are import-safe and unit-tested without spaCy.
spaCy and numpy are imported only inside :func:`make_run` / model helpers, so the
module can be imported in a model-free environment (CI, tests).
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

MODEL_NAME = "spaCy NER + word-vector entity linker"
MODEL_SOURCE = "https://github.com/explosion/spaCy/tree/v3.8.14"
SPACY_VERSION = "3.8.14"
MODEL_PACKAGE = "en_core_web_md"
MODEL_META_VERSION = "3.8.0"
CONTEXT_CHARACTERS = 160
_COMMIT_RE = re.compile(r"[0-9a-f]{7,40}\Z")
_ARTICLE_RE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


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


def normalize_surface(surface: str) -> tuple[str, int]:
    """Strip a single leading article and surrounding whitespace.

    Returns the normalized surface and the left character offset that was
    consumed, so the caller can keep emitted spans aligned to the text.
    """

    left = len(surface) - len(surface.lstrip())
    body = surface[left:]
    match = _ARTICLE_RE.match(body)
    if match:
        left += match.end()
        body = surface[left:]
    right = len(body) - len(body.rstrip())
    return (body[: len(body) - right] if right else body), left


def build_candidate_index(
    registry_records: list[dict[str, object]],
    training_records: list[dict[str, object]],
) -> tuple[list[Candidate], dict[str, tuple[str, ...]], dict[str, list[str]]]:
    """Build registry candidates, a casefold alias index and text profiles.

    Aliases and profiles are sourced only from the registry and the dev-split
    training mentions, never from the scored inputs, so the linker sees no test
    supervision.
    """

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
    return candidates, frozen_aliases, profiles


def candidate_ids(surface: str, aliases: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Return the registry candidate ids whose alias equals the surface."""

    return aliases.get(surface.casefold(), ())


def select_non_overlapping(detections: list[Detection]) -> list[Detection]:
    """Keep the longest span for each overlap; order-independent policy."""

    selected: list[Detection] = []
    for item in sorted(
        detections, key=lambda value: (-(value.end - value.start), value.start)
    ):
        if any(item.start < chosen.end and item.end > chosen.start for chosen in selected):
            continue
        selected.append(item)
    return sorted(selected, key=lambda value: (value.start, value.end))


def context(text: str, start: int, end: int) -> str:
    return text[
        max(0, start - CONTEXT_CHARACTERS) : min(len(text), end + CONTEXT_CHARACTERS)
    ]


def _load_model():
    """Load the pinned spaCy model, asserting the exact versions."""

    try:
        import spacy
    except ImportError as error:  # pragma: no cover - exercised only with the extra
        raise RuntimeError(
            "install the spacy extra with: pip install -e '.[spacy]' "
            "&& python -m spacy download en_core_web_md"
        ) from error

    if spacy.__version__ != SPACY_VERSION:
        raise RuntimeError(f"expected spaCy {SPACY_VERSION}, got {spacy.__version__}")
    nlp = spacy.load(MODEL_PACKAGE)
    meta_version = str(nlp.meta.get("version"))
    if meta_version != MODEL_META_VERSION:
        raise RuntimeError(
            f"expected {MODEL_PACKAGE} {MODEL_META_VERSION}, got {meta_version}"
        )
    if not nlp.vocab.vectors_length:
        raise RuntimeError(f"{MODEL_PACKAGE} has no word vectors; use a *_md or *_lg model")
    return nlp


def _cosine(vector_a, vector_b) -> float:  # pragma: no cover - needs model vectors
    import numpy as np

    norm_a = float(np.linalg.norm(vector_a))
    norm_b = float(np.linalg.norm(vector_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(vector_a, vector_b) / (norm_a * norm_b))


def make_run(
    *,
    training_path: Path,
    input_path: Path,
    dataset_path: Path,
    registry_path: Path,
    dataset_name: str,
    runner_commit: str,
) -> dict[str, object]:  # pragma: no cover - requires the spaCy model
    if not _COMMIT_RE.fullmatch(runner_commit):
        raise ValueError("runner commit must be a 7 to 40 character lowercase Git SHA")

    nlp = _load_model()
    registry_records = load_jsonl(registry_path)
    training_records = load_jsonl(training_path)
    inputs = load_inputs(input_path)
    candidates, aliases, profiles = build_candidate_index(
        registry_records, training_records
    )
    by_id = {candidate.canonical_id: candidate for candidate in candidates}
    profile_vectors = {
        candidate_id: nlp(" \n ".join(profile_texts)).vector
        for candidate_id, profile_texts in profiles.items()
    }

    cases: list[dict[str, object]] = []
    for item in inputs:
        text = item["plain_text"]
        doc = nlp(text)
        detections: list[Detection] = []
        for entity in doc.ents:
            surface = text[entity.start_char : entity.end_char]
            _, left = normalize_surface(surface)
            start = entity.start_char + left
            end = entity.end_char
            if end <= start:
                continue
            ids = candidate_ids(text[start:end], aliases)
            if ids:
                detections.append(Detection(start=start, end=end, candidates=ids))

        mentions: list[dict[str, object]] = []
        for detection in select_non_overlapping(detections):
            query_vector = nlp(context(text, detection.start, detection.end)).vector
            ranked = sorted(
                (
                    (-_cosine(query_vector, profile_vectors[entity_id]), entity_id)
                    for entity_id in detection.candidates
                )
            )
            entity_id = ranked[0][1]
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
                    "model_calls": 1,
                },
                "id": item["id"],
                "mentions": mentions,
            }
        )

    command = (
        "python scripts/run_spacy_linker.py "
        "--training benchmark/external/wiki-fair-v2/dev.training.jsonl "
        "--input benchmark/external/wiki-fair-v2/test.inputs.jsonl "
        "--dataset benchmark/external/wiki-fair-v2/test.comparison.jsonl "
        "--registry benchmark/external/wiki-fair-v2/entity-registry.jsonl "
        f"--dataset-name {dataset_name} --runner-commit {runner_commit} "
        "--output benchmark/results/wiki-fair-v2-spacy-linker-run.json"
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
            "version": f"spacy=={SPACY_VERSION};{MODEL_PACKAGE}=={MODEL_META_VERSION}",
        },
        "runner": {
            "command": command,
            "commit": runner_commit,
            "parameters": {
                "article_stripping": True,
                "candidate_generation": "registry labels plus dev-only mention aliases",
                "context_characters_each_side": CONTEXT_CHARACTERS,
                "detection": "spaCy named-entity recognition",
                "input_sha256": sha256_file(input_path),
                "linker": "mean word-vector cosine over candidate profiles",
                "model_package": MODEL_PACKAGE,
                "training_sha256": sha256_file(training_path),
            },
            "source": (
                "https://github.com/E-AI-MODEL/EAT-inline/blob/"
                f"{runner_commit}/scripts/run_spacy_linker.py"
            ),
        },
        "schema_version": "1.0",
    }


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wrapper
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
