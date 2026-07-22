"""Validate and replay recorded model-linker runs.

A recorded run is the reproducible handoff between a model environment and the
deterministic EAT Inline benchmark. The model sees plain text and documented
candidate data outside CI. CI validates the complete per-case output, resolves
typed keys through the benchmark registry and applies the same scoring code as
the built-in conditions.

The artifact deliberately cannot contain gold IDs or author-written EAT text.
Unknown fields are rejected so evidence cannot enter through an undocumented
side channel.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from eat_baselines import AdapterResult, BaselineAdapter, Case, Cost, ResolverRegistry
from eat_inline import IDENTIFIER


SCHEMA_VERSION = "1.0"
INPUT_BOUNDARY = "plain_text"
_IDENTIFIER_RE = re.compile(rf"{IDENTIFIER}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{7,40}\Z")
_FORBIDDEN_RUNNER_FIELDS = {"eat_text", "gold_ids"}


class RecordedRunValidationError(ValueError):
    """Raised when a recorded run violates its schema or evidence boundary."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class RecordedMention:
    label: str
    start: int
    end: int
    type: str
    key: str


@dataclass(frozen=True)
class RecordedPrediction:
    case_id: str
    mentions: tuple[RecordedMention, ...]
    model_calls: int
    estimated_tokens: int


@dataclass(frozen=True)
class RecordedRun:
    dataset_name: str
    dataset_sha256: str
    registry_sha256: str
    model_name: str
    model_version: str
    model_source: str
    runner_source: str
    runner_commit: str
    runner_command: str
    runner_parameters: dict[str, object]
    predictions: dict[str, RecordedPrediction]


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a dataset exactly as stored."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(value: object, location: str, errors: list[str]) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    errors.append(f"{location}: expected object")
    return {}


def _list(value: object, location: str, errors: list[str]) -> list[object]:
    if isinstance(value, list):
        return value
    errors.append(f"{location}: expected array")
    return []


def _string(value: object, location: str, errors: list[str]) -> str:
    if isinstance(value, str) and value:
        return value
    errors.append(f"{location}: expected non-empty string")
    return ""


def _integer(value: object, location: str, errors: list[str]) -> int:
    if type(value) is int and value >= 0:
        return value
    errors.append(f"{location}: expected non-negative integer")
    return 0


def _reject_extra_keys(
    value: dict[str, object],
    allowed: set[str],
    location: str,
    errors: list[str],
) -> None:
    for key in sorted(set(value) - allowed):
        errors.append(f"{location}: unknown field {key!r}")


def _require_uri(value: str, location: str, errors: list[str]) -> None:
    parsed = urlparse(value)
    missing_network_location = parsed.scheme in {"http", "https"} and not parsed.netloc
    if value and (not parsed.scheme or missing_network_location):
        errors.append(f"{location}: expected an absolute URI")


def _reject_forbidden_runner_fields(
    value: object, location: str, errors: list[str]
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if key.casefold() in _FORBIDDEN_RUNNER_FIELDS:
                errors.append(f"{child_location}: forbidden benchmark input field")
            _reject_forbidden_runner_fields(child, child_location, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_runner_fields(child, f"{location}[{index}]", errors)


def validate_recorded_run(
    raw: object,
    cases: Iterable[Case],
    registry: ResolverRegistry,
    *,
    dataset_name: str,
    dataset_sha256: str,
    registry_sha256: str,
) -> RecordedRun:
    """Validate raw run data and return an immutable replay representation."""

    errors: list[str] = []
    root = _object(raw, "$", errors)
    _reject_extra_keys(
        root,
        {"schema_version", "dataset", "input", "model", "runner", "cases"},
        "$",
        errors,
    )

    schema_version = _string(root.get("schema_version"), "$.schema_version", errors)
    if schema_version and schema_version != SCHEMA_VERSION:
        errors.append(
            f"$.schema_version: expected {SCHEMA_VERSION!r}, got {schema_version!r}"
        )

    input_boundary = _string(root.get("input"), "$.input", errors)
    if input_boundary and input_boundary != INPUT_BOUNDARY:
        errors.append(
            f"$.input: expected {INPUT_BOUNDARY!r}, got {input_boundary!r}"
        )

    dataset = _object(root.get("dataset"), "$.dataset", errors)
    _reject_extra_keys(
        dataset, {"name", "sha256", "registry_sha256"}, "$.dataset", errors
    )
    recorded_dataset_name = _string(dataset.get("name"), "$.dataset.name", errors)
    recorded_dataset_hash = _string(dataset.get("sha256"), "$.dataset.sha256", errors)
    recorded_registry_hash = _string(
        dataset.get("registry_sha256"), "$.dataset.registry_sha256", errors
    )
    if recorded_dataset_name and recorded_dataset_name != dataset_name:
        errors.append(
            f"$.dataset.name: expected {dataset_name!r}, got {recorded_dataset_name!r}"
        )
    if recorded_dataset_hash and not _SHA256_RE.fullmatch(recorded_dataset_hash):
        errors.append("$.dataset.sha256: expected lowercase SHA-256")
    elif recorded_dataset_hash and recorded_dataset_hash != dataset_sha256:
        errors.append(
            "$.dataset.sha256: dataset hash does not match the scored corpus"
        )
    if recorded_registry_hash and not _SHA256_RE.fullmatch(recorded_registry_hash):
        errors.append("$.dataset.registry_sha256: expected lowercase SHA-256")
    elif recorded_registry_hash and recorded_registry_hash != registry_sha256:
        errors.append(
            "$.dataset.registry_sha256: registry hash does not match the scored registry"
        )

    model = _object(root.get("model"), "$.model", errors)
    _reject_extra_keys(model, {"name", "version", "source"}, "$.model", errors)
    model_name = _string(model.get("name"), "$.model.name", errors)
    model_version = _string(model.get("version"), "$.model.version", errors)
    model_source = _string(model.get("source"), "$.model.source", errors)
    _require_uri(model_source, "$.model.source", errors)

    runner = _object(root.get("runner"), "$.runner", errors)
    _reject_extra_keys(
        runner,
        {"source", "commit", "command", "parameters"},
        "$.runner",
        errors,
    )
    runner_source = _string(runner.get("source"), "$.runner.source", errors)
    _require_uri(runner_source, "$.runner.source", errors)
    runner_commit = _string(runner.get("commit"), "$.runner.commit", errors)
    if runner_commit and not _COMMIT_RE.fullmatch(runner_commit):
        errors.append("$.runner.commit: expected a 7 to 40 character commit SHA")
    runner_command = _string(runner.get("command"), "$.runner.command", errors)
    runner_parameters = _object(
        runner.get("parameters"), "$.runner.parameters", errors
    )
    _reject_forbidden_runner_fields(runner_parameters, "$.runner.parameters", errors)

    case_map = {case.id: case for case in cases}
    predictions: dict[str, RecordedPrediction] = {}
    for index, raw_prediction in enumerate(_list(root.get("cases"), "$.cases", errors)):
        location = f"$.cases[{index}]"
        prediction = _object(raw_prediction, location, errors)
        _reject_extra_keys(prediction, {"id", "mentions", "cost"}, location, errors)
        case_id = _string(prediction.get("id"), f"{location}.id", errors)
        if case_id in predictions:
            errors.append(f"{location}.id: duplicate case {case_id!r}")
            continue
        case = case_map.get(case_id)
        if case_id and case is None:
            errors.append(f"{location}.id: unknown case {case_id!r}")

        cost = _object(prediction.get("cost"), f"{location}.cost", errors)
        _reject_extra_keys(
            cost, {"model_calls", "estimated_tokens"}, f"{location}.cost", errors
        )
        model_calls = _integer(
            cost.get("model_calls"), f"{location}.cost.model_calls", errors
        )
        estimated_tokens = _integer(
            cost.get("estimated_tokens"),
            f"{location}.cost.estimated_tokens",
            errors,
        )

        mentions: list[RecordedMention] = []
        seen_mentions: set[tuple[int, int, str, str]] = set()
        for mention_index, raw_mention in enumerate(
            _list(prediction.get("mentions"), f"{location}.mentions", errors)
        ):
            mention_location = f"{location}.mentions[{mention_index}]"
            mention = _object(raw_mention, mention_location, errors)
            _reject_extra_keys(
                mention,
                {"label", "start", "end", "type", "key"},
                mention_location,
                errors,
            )
            label = _string(mention.get("label"), f"{mention_location}.label", errors)
            start = _integer(mention.get("start"), f"{mention_location}.start", errors)
            end = _integer(mention.get("end"), f"{mention_location}.end", errors)
            type_name = _string(
                mention.get("type"), f"{mention_location}.type", errors
            )
            key = _string(mention.get("key"), f"{mention_location}.key", errors)

            if type_name and not _IDENTIFIER_RE.fullmatch(type_name):
                errors.append(f"{mention_location}.type: invalid EAT identifier")
            if key and not _IDENTIFIER_RE.fullmatch(key):
                errors.append(f"{mention_location}.key: invalid EAT identifier")
            if end <= start:
                errors.append(f"{mention_location}: end must be greater than start")
            elif case is not None:
                if end > len(case.plain_text):
                    errors.append(f"{mention_location}: span exceeds plain_text")
                elif case.plain_text[start:end].casefold() != label.casefold():
                    errors.append(
                        f"{mention_location}: label does not match the plain_text span"
                    )
            if type_name and key and registry.resolve_typed(type_name, key) is None:
                errors.append(
                    f"{mention_location}: unknown typed key {type_name}:{key}"
                )

            identity = (start, end, type_name, key)
            if identity in seen_mentions:
                errors.append(f"{mention_location}: duplicate mention prediction")
            seen_mentions.add(identity)
            mentions.append(RecordedMention(label, start, end, type_name, key))

        if case_id and case is not None and case_id not in predictions:
            predictions[case_id] = RecordedPrediction(
                case_id=case_id,
                mentions=tuple(mentions),
                model_calls=model_calls,
                estimated_tokens=estimated_tokens,
            )

    missing = sorted(set(case_map) - set(predictions))
    if missing:
        errors.append(f"$.cases: missing cases {missing!r}")

    if errors:
        raise RecordedRunValidationError(errors)

    return RecordedRun(
        dataset_name=recorded_dataset_name,
        dataset_sha256=recorded_dataset_hash,
        registry_sha256=recorded_registry_hash,
        model_name=model_name,
        model_version=model_version,
        model_source=model_source,
        runner_source=runner_source,
        runner_commit=runner_commit,
        runner_command=runner_command,
        runner_parameters=runner_parameters,
        predictions=predictions,
    )


def load_recorded_run(
    path: Path,
    cases: Iterable[Case],
    registry: ResolverRegistry,
    *,
    dataset_name: str,
    dataset_path: Path,
    registry_path: Path,
) -> RecordedRun:
    """Load and validate a recorded run from disk."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RecordedRunValidationError([f"{path}: {error}"]) from error
    return validate_recorded_run(
        raw,
        cases,
        registry,
        dataset_name=dataset_name,
        dataset_sha256=sha256_file(dataset_path),
        registry_sha256=sha256_file(registry_path),
    )


class RecordedLinkerAdapter(BaselineAdapter):
    """Replay a validated model run as a benchmark adapter."""

    requires_model = True

    def __init__(
        self, run: RecordedRun, condition: str = "recorded_model_linker"
    ) -> None:
        self.run = run
        self.condition = condition
        self.name = f"Recorded model linker: {run.model_name}@{run.model_version}"

    def predict(self, case: Case, registry: ResolverRegistry) -> AdapterResult:
        prediction = self.run.predictions[case.id]
        predicted: set[str] = set()
        unresolved: list[str] = []
        cost = Cost(
            model_calls=prediction.model_calls,
            estimated_tokens=prediction.estimated_tokens,
        )
        for mention in prediction.mentions:
            cost.registry_lookups += 1
            canonical_id = registry.resolve_typed(mention.type, mention.key)
            if canonical_id is None:
                unresolved.append(f"{mention.type}:{mention.key}")
            else:
                predicted.add(canonical_id)
        return AdapterResult(
            predicted_ids=predicted,
            diagnostics={
                "mentions": len(prediction.mentions),
                "unresolved_predictions": unresolved,
            },
            cost=cost,
        )
