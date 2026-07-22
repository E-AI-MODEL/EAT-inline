"""Baseline adapter framework for the EAT Inline comparative benchmark.

This module defines a small, stable interface that lets different resolution
strategies be compared over the same gold cases under identical scoring.

Two deterministic reference adapters are provided:

- ``PlainLabelMatchAdapter`` resolves entities by exact label matching over the
  registry, with no author-supplied type or key. This is the plain-text
  baseline condition.
- ``EatResolverAdapter`` parses author-written ``@@EAT type:key@@`` references
  and resolves them by ``(type, key)``. This is the EAT Inline condition.

Model-based conditions (a named-entity recogniser, an entity linker, an LLM
resolver or a retriever/reranker) conform to the same :class:`BaselineAdapter`
interface. They are intentionally **not** bundled here: they require network
access and non-deterministic models, which would make the benchmark
irreproducible in CI, and shipping a synthetic stand-in with an invented error
rate would fabricate evidence. To add one, implement :class:`BaselineAdapter`,
set ``requires_model = True``, and register it with :func:`register_adapter`.

Cost is recorded as a deterministic proxy (registry lookups, label scans,
references read, estimated tokens) rather than wall-clock latency, so committed
benchmark artifacts stay byte-reproducible. Wall-clock latency is inherently
machine-dependent and should be reported as informational context by a caller,
never as a pass/fail gate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable

from eat_inline import parse_references


@dataclass(frozen=True)
class Case:
    """A single paired comparison case from the gold corpus."""

    id: str
    plain_text: str
    eat_text: str
    gold_ids: frozenset[str]
    language: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "Case":
        return cls(
            id=str(record["id"]),
            plain_text=str(record["plain_text"]),
            eat_text=str(record["eat_text"]),
            gold_ids=frozenset(str(value) for value in record["gold_ids"]),
            language=str(record["language"]) if "language" in record else None,
        )


class ResolverRegistry:
    """Storage-neutral view over registry entries used by the adapters."""

    def __init__(self, entries: Iterable[dict[str, object]]) -> None:
        self.by_typed_key: dict[tuple[str, str], str] = {}
        self.by_label: dict[str, list[str]] = {}
        for entry in entries:
            canonical_id = str(entry["canonical_id"])
            self.by_typed_key[(str(entry["type"]), str(entry["key"]))] = canonical_id
            self.by_label.setdefault(str(entry["label"]).casefold(), []).append(
                canonical_id
            )

    def resolve_typed(self, type_name: str, key: str) -> str | None:
        return self.by_typed_key.get((type_name, key))


@dataclass
class Cost:
    """Deterministic, machine-independent cost proxy for one condition.

    These counters are reproducible across machines and runs. They are proxies
    for effort, not billed cost or latency; a model-based adapter would also
    increment ``model_calls`` and a realistic ``estimated_tokens``.
    """

    registry_lookups: int = 0
    label_scans: int = 0
    references_read: int = 0
    model_calls: int = 0
    estimated_tokens: int = 0

    def add(self, other: "Cost") -> None:
        self.registry_lookups += other.registry_lookups
        self.label_scans += other.label_scans
        self.references_read += other.references_read
        self.model_calls += other.model_calls
        self.estimated_tokens += other.estimated_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "registry_lookups": self.registry_lookups,
            "label_scans": self.label_scans,
            "references_read": self.references_read,
            "model_calls": self.model_calls,
            "estimated_tokens": self.estimated_tokens,
        }


@dataclass
class AdapterResult:
    """The prediction of one adapter for one case."""

    predicted_ids: set[str]
    diagnostics: dict[str, object] = field(default_factory=dict)
    cost: Cost = field(default_factory=Cost)


def _estimate_tokens(text: str) -> int:
    """A deterministic, whitespace-based token proxy."""

    return len(text.split())


class BaselineAdapter(ABC):
    """Common interface every benchmark condition implements.

    ``condition`` is the machine-readable key used in benchmark artifacts.
    ``requires_model`` flags adapters that call an external model and therefore
    cannot run in the deterministic CI benchmark.
    """

    name: str
    condition: str
    requires_model: bool = False

    @abstractmethod
    def predict(self, case: Case, registry: ResolverRegistry) -> AdapterResult:
        """Predict canonical entity IDs for a single case."""


class PlainLabelMatchAdapter(BaselineAdapter):
    """Resolve entities from plain text by exact label matching.

    A label with a single registry candidate resolves to that candidate. A
    label with multiple candidates is ambiguous and is reported, not resolved.
    This mirrors what a system can do without author-supplied type and key
    information; it uses no language model.
    """

    name = "Deterministic plain-text label match"
    condition = "plain"
    requires_model = False

    def predict(self, case: Case, registry: ResolverRegistry) -> AdapterResult:
        plain_text = case.plain_text.casefold()
        predicted: set[str] = set()
        ambiguous_labels: list[str] = []
        cost = Cost(estimated_tokens=_estimate_tokens(case.plain_text))
        for label, candidates in registry.by_label.items():
            cost.label_scans += 1
            occurrence_count = plain_text.count(label)
            if occurrence_count == 0:
                continue
            cost.registry_lookups += 1
            if len(candidates) == 1:
                predicted.add(candidates[0])
            else:
                ambiguous_labels.extend([label] * occurrence_count)
        return AdapterResult(
            predicted_ids=predicted,
            diagnostics={
                "ambiguous_mentions": len(ambiguous_labels),
                "ambiguous_labels": ambiguous_labels,
            },
            cost=cost,
        )


class EatResolverAdapter(BaselineAdapter):
    """Resolve author-written EAT Inline references by ``(type, key)``.

    Author-supplied type and key remove the label ambiguity that the plain
    baseline cannot resolve. A reference with no matching registry entry is
    reported as unresolved rather than guessed.
    """

    name = "EAT Inline reference resolver"
    condition = "eat_inline"
    requires_model = False

    def predict(self, case: Case, registry: ResolverRegistry) -> AdapterResult:
        predicted: set[str] = set()
        unresolved: list[str] = []
        cost = Cost(estimated_tokens=_estimate_tokens(case.eat_text))
        for reference in parse_references(case.eat_text):
            cost.references_read += 1
            cost.registry_lookups += 1
            canonical_id = registry.resolve_typed(reference.type, reference.key)
            if canonical_id:
                predicted.add(canonical_id)
            else:
                unresolved.append(reference.raw)
        return AdapterResult(
            predicted_ids=predicted,
            diagnostics={
                "unresolved": len(unresolved),
                "unresolved_references": unresolved,
            },
            cost=cost,
        )


_REGISTRY: dict[str, BaselineAdapter] = {}


def register_adapter(adapter: BaselineAdapter) -> BaselineAdapter:
    """Register an adapter under its ``condition`` key.

    Raises ``ValueError`` on a duplicate condition so a plug-in cannot silently
    shadow a built-in condition.
    """

    if adapter.condition in _REGISTRY:
        raise ValueError(f"duplicate adapter condition: {adapter.condition!r}")
    _REGISTRY[adapter.condition] = adapter
    return adapter


def get_adapter(condition: str) -> BaselineAdapter:
    return _REGISTRY[condition]


def registered_conditions() -> list[str]:
    return list(_REGISTRY)


def default_adapters() -> list[BaselineAdapter]:
    """Return the deterministic adapters that run in CI, in report order."""

    return [get_adapter("plain"), get_adapter("eat_inline")]


register_adapter(PlainLabelMatchAdapter())
register_adapter(EatResolverAdapter())
