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

import re
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


@dataclass(frozen=True)
class Candidate:
    """One registry entry that a label could refer to."""

    type: str
    key: str
    canonical_id: str


class ResolverRegistry:
    """Storage-neutral view over registry entries used by the adapters."""

    def __init__(self, entries: Iterable[dict[str, object]]) -> None:
        self.by_typed_key: dict[tuple[str, str], str] = {}
        self.by_label: dict[str, list[str]] = {}
        self.candidates_by_label: dict[str, list["Candidate"]] = {}
        for entry in entries:
            type_name = str(entry["type"])
            key = str(entry["key"])
            canonical_id = str(entry["canonical_id"])
            label = str(entry["label"])
            self.by_typed_key[(type_name, key)] = canonical_id
            self.by_label.setdefault(label.casefold(), []).append(canonical_id)
            self.candidates_by_label.setdefault(label.casefold(), []).append(
                Candidate(type=type_name, key=key, canonical_id=canonical_id)
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


@dataclass(frozen=True)
class LinkedMention:
    """A mention a linker found in text, optionally resolved to a type and key.

    ``type`` and ``key`` are ``None`` when the linker detected a mention but
    could not commit to a single entity (an abstention). ``candidate_count``
    records how many registry candidates the label had.
    """

    label: str
    start: int
    end: int
    type: str | None
    key: str | None
    candidate_count: int


@dataclass
class LinkOutput:
    mentions: list[LinkedMention]
    cost: Cost = field(default_factory=Cost)


class EntityLinker(ABC):
    """Contract for a component that finds and links entity mentions in text.

    This is the plug-in point for real models. A named-entity recogniser, an
    entity linker or an LLM resolver implements :meth:`link` and sets
    ``requires_model = True``; :class:`LinkerAdapter` turns any linker into a
    scored benchmark condition. The bundled :class:`GazetteerLinker` is offline
    and deterministic (``requires_model = False``) so it can run in CI.
    """

    name: str
    requires_model: bool = False

    @abstractmethod
    def link(self, text: str, registry: ResolverRegistry) -> LinkOutput:
        """Return the mentions found in ``text`` with any committed type/key."""


_WORD_RE = re.compile(r"[A-Za-z_]+")


class GazetteerLinker(EntityLinker):
    """A deterministic, offline linker.

    Detection uses the registry labels as a gazetteer. Linking:

    - a label with a single candidate links to it;
    - a label with several candidates is disambiguated only when a candidate's
      ``type`` word appears within :attr:`context_window` tokens of the mention
      (for example ``project`` near ``Phoenix``);
    - otherwise the linker abstains rather than guessing.

    Abstention is deliberate: committing to an arbitrary candidate would inject
    accuracy that reflects a coin toss, not the method. A committing variant is
    intentionally not provided here.
    """

    name = "Offline gazetteer entity linker"
    requires_model = False
    context_window = 3

    def link(self, text: str, registry: ResolverRegistry) -> LinkOutput:
        lowered = text.casefold()
        tokens = [(m.group(0).casefold(), m.start()) for m in _WORD_RE.finditer(text)]
        cost = Cost(estimated_tokens=len(text.split()))
        mentions: list[LinkedMention] = []
        for label, candidates in registry.candidates_by_label.items():
            cost.label_scans += 1
            start = lowered.find(label)
            while start != -1:
                cost.registry_lookups += 1
                end = start + len(label)
                if len(candidates) == 1:
                    only = candidates[0]
                    mentions.append(
                        LinkedMention(label, start, end, only.type, only.key, 1)
                    )
                else:
                    chosen = self._disambiguate(candidates, tokens, start, end)
                    mentions.append(
                        LinkedMention(
                            label,
                            start,
                            end,
                            chosen.type if chosen else None,
                            chosen.key if chosen else None,
                            len(candidates),
                        )
                    )
                start = lowered.find(label, end)
        return LinkOutput(mentions=mentions, cost=cost)

    def _disambiguate(
        self,
        candidates: list[Candidate],
        tokens: list[tuple[str, int]],
        start: int,
        end: int,
    ) -> Candidate | None:
        before = [tok for tok, offset in tokens if offset < start][-self.context_window :]
        after = [tok for tok, offset in tokens if offset >= end][: self.context_window]
        context = set(before) | set(after)
        matched = [c for c in candidates if c.type.casefold() in context]
        if len(matched) == 1:
            return matched[0]
        return None


class LinkerAdapter(BaselineAdapter):
    """Score any :class:`EntityLinker` as a benchmark condition.

    The linker must place its own mentions on the plain text; it never receives
    the author-written references. This isolates the effect of the EAT Inline
    notation from the effect of perfect author annotation.
    """

    def __init__(self, linker: EntityLinker, condition: str = "linker") -> None:
        self.linker = linker
        self.name = linker.name
        self.condition = condition
        self.requires_model = linker.requires_model

    def predict(self, case: Case, registry: ResolverRegistry) -> AdapterResult:
        output = self.linker.link(case.plain_text, registry)
        predicted: set[str] = set()
        abstained: list[str] = []
        unresolved: list[str] = []
        for mention in output.mentions:
            if mention.type is None or mention.key is None:
                abstained.append(mention.label)
                continue
            canonical_id = registry.resolve_typed(mention.type, mention.key)
            if canonical_id:
                predicted.add(canonical_id)
            else:
                unresolved.append(f"{mention.type}:{mention.key}")
        return AdapterResult(
            predicted_ids=predicted,
            diagnostics={
                "linked": len(predicted),
                "abstained_ambiguous": abstained,
                "unresolved_predictions": unresolved,
            },
            cost=output.cost,
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
    """Return the deterministic adapters that run in CI, in report order.

    The order is intentional: no entity information, automatic linking, then
    explicit author-supplied references.
    """

    return [get_adapter("plain"), get_adapter("linker"), get_adapter("eat_inline")]


register_adapter(PlainLabelMatchAdapter())
register_adapter(LinkerAdapter(GazetteerLinker()))
register_adapter(EatResolverAdapter())
