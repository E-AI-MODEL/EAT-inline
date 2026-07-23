#!/usr/bin/env python3
"""Run an OpenAI-compatible LLM as an entity linker on plain text.

This is a recorded-run producer with the same boundary as the other model
runners: it reads only ``{id, plain_text}`` inference records and writes a
``schemas/linker-run.schema.json``-conformant artifact. For each document it
sends the plain text and the closed-registry candidates that appear in it to a
chat-completions endpoint and asks the model to pick, for each mention, an exact
surface substring and a registry ``type``/``key``. The model only decides the
linking; this script keeps the hard guarantees in code: every emitted mention is
grounded to a verbatim, word-bounded, non-overlapping span in the text and to a
registry entry, so anything the model invents or mis-formats is dropped rather
than making the artifact invalid.

The model runs once, outside CI; ``scripts/run_recorded_linker_benchmark.py``
then validates provenance and replays the recorded predictions deterministically.
It is provider-agnostic: pass ``--base-url`` and ``--model`` for DeepSeek, GLM
(Zhipu), OpenAI or any OpenAI-compatible endpoint. The API key is read from an
environment variable (``LLM_API_KEY`` by default).

Pure functions (input loading, candidate lookup, prompt building, response
parsing, grounding, overlap selection) are import-safe and unit-tested without
any network call; only the chat request and :func:`make_run` reach the API.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re

MODEL_TASK_NAME = "LLM entity linker"
CONTEXT_CHARACTERS = 160
PROMPT_VERSION = "eat-llm-linker-v1"
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
    type: str
    key: str


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
    left = r"(?<!\w)" if label[:1].isalnum() or label[:1] == "_" else ""
    right = r"(?!\w)" if label[-1:].isalnum() or label[-1:] == "_" else ""
    return re.compile(left + re.escape(label) + right, re.IGNORECASE)


def build_candidate_index(
    registry_records: list[dict[str, object]],
    training_records: list[dict[str, object]],
) -> tuple[dict[str, Candidate], dict[str, tuple[str, ...]], set[tuple[str, str]]]:
    """Return candidates by id, a casefold alias index and the valid typed keys.

    Aliases come only from the registry and the dev-split training mentions, so
    the linker sees no test supervision.
    """

    by_id: dict[str, Candidate] = {}
    typed_keys: set[tuple[str, str]] = set()
    aliases: dict[str, set[str]] = defaultdict(set)
    for record in registry_records:
        candidate = Candidate(
            canonical_id=str(record["canonical_id"]),
            type=str(record["type"]),
            key=str(record["key"]),
            label=str(record["label"]),
        )
        by_id[candidate.canonical_id] = candidate
        typed_keys.add((candidate.type, candidate.key))
        aliases[candidate.label.casefold()].add(candidate.canonical_id)

    for record in training_records:
        text = str(record["plain_text"])
        for mention in record["mentions"]:
            entity_id = str(mention["canonical_id"])
            if entity_id not in by_id:
                raise ValueError(f"training data contains unknown entity {entity_id}")
            label = text[int(mention["start"]) : int(mention["end"])].strip()
            if len(label) >= 2:
                aliases[label.casefold()].add(entity_id)

    frozen_aliases = {
        alias: tuple(sorted(entity_ids))
        for alias, entity_ids in sorted(aliases.items())
        if alias
    }
    return by_id, frozen_aliases, typed_keys


def candidates_in_text(
    text: str, aliases: dict[str, tuple[str, ...]], by_id: dict[str, Candidate]
) -> list[dict[str, str]]:
    """Closed-registry candidates whose alias appears in the document."""

    present: dict[tuple[str, str], str] = {}
    for alias, entity_ids in aliases.items():
        if label_pattern(alias).search(text):
            for entity_id in entity_ids:
                candidate = by_id[entity_id]
                present[(candidate.type, candidate.key)] = candidate.label
    return [
        {"type": type_name, "key": key, "label": label}
        for (type_name, key), label in sorted(present.items())
    ]


def build_messages(text: str, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    """Build the chat messages that constrain the model to the closed registry."""

    system = (
        "You are an entity linker. You are given a document and a list of "
        "candidate entities, each with a type and a key. Find every place in the "
        "document that mentions one of these candidates. For each mention, return "
        "the exact surface substring as it appears in the document (verbatim, "
        "matching case and spelling), together with the type and key of the "
        "candidate it refers to. Only use type and key values from the candidate "
        "list. Do not invent entities. Respond with a JSON array of objects, each "
        'with the fields "surface", "type" and "key". Output only the JSON array.'
    )
    user = json.dumps(
        {"document": text, "candidates": candidates},
        ensure_ascii=False,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_llm_json(content: str) -> list[dict[str, str]]:
    """Extract a list of ``{surface, type, key}`` objects from a model reply."""

    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z0-9_]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text.strip())
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    items: list[dict[str, str]] = []
    if isinstance(data, list):
        for entry in data:
            if (
                isinstance(entry, dict)
                and "surface" in entry
                and "type" in entry
                and "key" in entry
            ):
                items.append(
                    {
                        "surface": str(entry["surface"]),
                        "type": str(entry["type"]),
                        "key": str(entry["key"]),
                    }
                )
    return items


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


def ground_items(
    text: str,
    items: list[dict[str, str]],
    typed_keys: set[tuple[str, str]],
) -> list[Detection]:
    """Ground model items to verbatim, resolvable, non-overlapping spans."""

    detections: list[Detection] = []
    for item in items:
        typed_key = (item["type"], item["key"])
        surface = item["surface"]
        if typed_key not in typed_keys or not surface:
            continue
        match = label_pattern(surface).search(text)
        if match is None:
            continue
        detections.append(
            Detection(
                start=match.start(),
                end=match.end(),
                type=item["type"],
                key=item["key"],
            )
        )
    return select_non_overlapping(detections)


def _chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    timeout: int = 120,
) -> str:  # pragma: no cover - network call
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps(
        {"model": model, "messages": messages, "temperature": temperature}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:  # noqa: PERF203
        detail = error.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"LLM API error {error.code}: {detail}") from error
    return str(body["choices"][0]["message"]["content"])


def make_run(
    *,
    training_path: Path,
    input_path: Path,
    dataset_path: Path,
    registry_path: Path,
    dataset_name: str,
    runner_commit: str,
    base_url: str,
    model: str,
    api_key: str,
    temperature: float,
) -> dict[str, object]:  # pragma: no cover - requires the LLM API
    if not _COMMIT_RE.fullmatch(runner_commit):
        raise ValueError("runner commit must be a 7 to 40 character lowercase Git SHA")
    if not api_key:
        raise RuntimeError("no API key found in the configured environment variable")

    by_id, aliases, typed_keys = build_candidate_index(
        load_jsonl(registry_path), load_jsonl(training_path)
    )
    inputs = load_inputs(input_path)

    cases: list[dict[str, object]] = []
    for item in inputs:
        text = item["plain_text"]
        candidates = candidates_in_text(text, aliases, by_id)
        mentions: list[dict[str, object]] = []
        model_calls = 0
        if candidates:
            model_calls = 1
            content = _chat_completion(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=build_messages(text, candidates),
                temperature=temperature,
            )
            for detection in ground_items(text, parse_llm_json(content), typed_keys):
                mentions.append(
                    {
                        "end": detection.end,
                        "key": detection.key,
                        "label": text[detection.start : detection.end],
                        "start": detection.start,
                        "type": detection.type,
                    }
                )
        cases.append(
            {
                "cost": {
                    "estimated_tokens": len(text.split()),
                    "model_calls": model_calls,
                },
                "id": item["id"],
                "mentions": mentions,
            }
        )

    command = (
        "python scripts/run_llm_linker.py "
        "--training benchmark/external/wiki-fair-v2/dev.training.jsonl "
        "--input benchmark/external/wiki-fair-v2/test.inputs.jsonl "
        "--dataset benchmark/external/wiki-fair-v2/test.comparison.jsonl "
        "--registry benchmark/external/wiki-fair-v2/entity-registry.jsonl "
        f"--dataset-name {dataset_name} --base-url {base_url} --model {model} "
        f"--runner-commit {runner_commit} "
        "--output benchmark/results/wiki-fair-v2-llm-linker-run.json"
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
            "name": MODEL_TASK_NAME,
            "source": base_url,
            "version": f"{model};temperature={temperature}",
        },
        "runner": {
            "command": command,
            "commit": runner_commit,
            "parameters": {
                "base_url": base_url,
                "candidate_generation": "closed registry labels plus dev-only mention aliases",
                "detection": "LLM selection grounded to verbatim registry surfaces",
                "input_sha256": sha256_file(input_path),
                "model": model,
                "prompt_version": PROMPT_VERSION,
                "temperature": temperature,
                "training_sha256": sha256_file(training_path),
            },
            "source": (
                "https://github.com/E-AI-MODEL/EAT-inline/blob/"
                f"{runner_commit}/scripts/run_llm_linker.py"
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
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible base URL")
    parser.add_argument("--model", required=True, help="model name for the endpoint")
    parser.add_argument(
        "--api-key-env",
        default="LLM_API_KEY",
        help="environment variable holding the API key (default LLM_API_KEY)",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args(argv)

    run = make_run(
        training_path=args.training,
        input_path=args.input,
        dataset_path=args.dataset,
        registry_path=args.registry,
        dataset_name=args.dataset_name,
        runner_commit=args.runner_commit,
        base_url=args.base_url,
        model=args.model,
        api_key=os.environ.get(args.api_key_env, ""),
        temperature=args.temperature,
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
