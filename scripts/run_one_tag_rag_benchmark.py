#!/usr/bin/env python3
"""Measure RAG retrieval over 100,000 documents with one EAT tag each."""

from __future__ import annotations

import argparse
from array import array
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import heapq
from html import escape
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
import time

from eat_baselines import ResolverRegistry
from eat_inline import parse_references
from eat_recorded_runs import sha256_file


BENCHMARK_NAME = "wiki-fair-v2-one-tag-rag-retrieval-v1"
DEFAULT_DOCUMENTS = 100_000
DEFAULT_TOP_K = 10
DEFAULT_QUERY_ROUNDS = 3
DEFAULT_HYBRID_CANDIDATES = 100
CONTEXT_CHARACTERS = 220
TOKEN_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True)
class PassagePrototype:
    prototype_id: str
    source_id: str
    source_title: str
    entity_id: str
    entity_label: str
    mention_text: str
    context_entity_ids: frozenset[str]
    plain_text: str
    eat_text: str
    terms: frozenset[str]
    word_count: int


@dataclass(frozen=True)
class Query:
    entity_id: str
    label: str
    question: str
    terms: tuple[str, ...]
    gold_source_titles: tuple[str, ...]


@dataclass
class WorkloadIndex:
    document_count: int
    prototypes: list[PassagePrototype]
    lexical_postings: dict[str, array]
    entity_postings: dict[str, array]
    idf: dict[str, float]
    build_seconds: float
    plain_text_bytes: int
    eat_text_bytes: int
    references_parsed: int


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


def tokenize(text: str) -> frozenset[str]:
    return frozenset(match.group(0).casefold() for match in TOKEN_RE.finditer(text))


def source_title(text: str) -> str:
    for line in text.splitlines():
        title = line.strip()
        if title:
            return title
    raise ValueError("source document has no title")


def build_prototypes(
    records: list[dict[str, object]],
    registry_records: list[dict[str, object]],
    *,
    context_characters: int = CONTEXT_CHARACTERS,
) -> list[PassagePrototype]:
    if context_characters < 0:
        raise ValueError("context_characters must be non-negative")
    labels = {
        str(record["canonical_id"]): str(record["label"])
        for record in registry_records
    }
    prototypes: list[PassagePrototype] = []
    source_ids: set[str] = set()
    for record in records:
        source_id = str(record["id"])
        if source_id in source_ids:
            raise ValueError(f"duplicate source document {source_id}")
        source_ids.add(source_id)
        text = str(record["plain_text"])
        title = source_title(text)
        annotations = sorted(
            record["annotations"],
            key=lambda item: (
                int(item["start"]),
                int(item["end"]),
                str(item["key"]),
            ),
        )
        for annotation_index, annotation in enumerate(annotations):
            start = int(annotation["start"])
            end = int(annotation["end"])
            type_name = str(annotation["type"])
            key = str(annotation["key"])
            if type_name != "entity":
                raise ValueError(
                    f"{source_id}: expected entity annotation, got {type_name}"
                )
            if key not in labels:
                raise ValueError(f"{source_id}: unknown entity {key}")
            if not (0 <= start < end <= len(text)):
                raise ValueError(f"{source_id}: invalid annotation span {start}:{end}")
            left = max(0, start - context_characters)
            right = min(len(text), end + context_characters)
            mention = text[start:end]
            plain_passage = text[left:right]
            eat_passage = (
                text[left:start]
                + f"@@EAT entity:{key}@@"
                + text[end:right]
            )
            plain_document = (
                f"Source page: {title}\n"
                f"Passage: {plain_passage}"
            )
            eat_document = (
                f"Source page: {title}\n"
                f"Passage: {eat_passage}"
            )
            context_entity_ids = frozenset(
                str(item["key"])
                for item in annotations
                if int(item["start"]) >= left and int(item["end"]) <= right
            )
            if key not in context_entity_ids:
                raise ValueError(
                    f"{source_id}:{annotation_index}: target is outside its context"
                )
            references = parse_references(eat_document)
            if len(references) != 1:
                raise ValueError(
                    f"{source_id}:{annotation_index}: expected exactly one EAT reference"
                )
            reference = references[0]
            if reference.type != "entity" or reference.key != key:
                raise ValueError(
                    f"{source_id}:{annotation_index}: generated reference changed identity"
                )
            prototypes.append(
                PassagePrototype(
                    prototype_id=f"{source_id}-mention-{annotation_index}",
                    source_id=source_id,
                    source_title=title,
                    entity_id=key,
                    entity_label=labels[key],
                    mention_text=mention,
                    context_entity_ids=context_entity_ids,
                    plain_text=plain_document,
                    eat_text=eat_document,
                    terms=tokenize(plain_document),
                    word_count=len(plain_document.split()),
                )
            )
    if not prototypes:
        raise ValueError("source dataset has no annotated passages")
    return prototypes


def build_queries(prototypes: list[PassagePrototype]) -> list[Query]:
    grouped: dict[str, list[PassagePrototype]] = defaultdict(list)
    for prototype in prototypes:
        grouped[prototype.entity_id].append(prototype)
    queries: list[Query] = []
    for entity_id, matches in sorted(grouped.items()):
        labels = {match.entity_label for match in matches}
        if len(labels) != 1:
            raise ValueError(f"inconsistent registry labels for {entity_id}")
        label = next(iter(labels))
        terms = tuple(sorted(tokenize(label)))
        if not terms:
            raise ValueError(f"entity {entity_id} has no searchable label terms")
        queries.append(
            Query(
                entity_id=entity_id,
                label=label,
                question=f"Which source page mentions {label}?",
                terms=terms,
                gold_source_titles=tuple(
                    sorted({match.source_title for match in matches})
                ),
            )
        )
    return queries


def build_workload_index(
    prototypes: list[PassagePrototype],
    registry: ResolverRegistry,
    *,
    document_count: int,
) -> WorkloadIndex:
    if document_count < len(prototypes):
        raise ValueError(
            "document_count must include every annotated passage prototype"
        )
    if document_count >= 2**32:
        raise ValueError("document_count must fit unsigned 32-bit document IDs")

    lexical_postings: dict[str, array] = defaultdict(lambda: array("I"))
    entity_postings: dict[str, array] = {
        entity_id: array("I")
        for entity_id in sorted({item.entity_id for item in prototypes})
    }
    plain_text_bytes = 0
    eat_text_bytes = 0
    references_parsed = 0
    start_time = time.perf_counter()
    for document_id in range(document_count):
        prototype = prototypes[document_id % len(prototypes)]
        plain_text_bytes += len(prototype.plain_text.encode("utf-8"))
        eat_text_bytes += len(prototype.eat_text.encode("utf-8"))

        references = parse_references(prototype.eat_text)
        if len(references) != 1:
            raise ValueError(
                f"workload document {document_id} does not contain exactly one tag"
            )
        reference = references[0]
        entity_id = registry.resolve_typed(reference.type, reference.key)
        if entity_id != prototype.entity_id:
            raise ValueError(
                f"workload document {document_id} resolved to the wrong entity"
            )
        references_parsed += 1
        entity_postings[entity_id].append(document_id)

        for term in sorted(tokenize(prototype.plain_text)):
            lexical_postings[term].append(document_id)

    build_seconds = time.perf_counter() - start_time
    frozen_lexical = dict(lexical_postings)
    idf = {
        term: math.log((document_count + 1) / (len(postings) + 1)) + 1.0
        for term, postings in frozen_lexical.items()
    }
    return WorkloadIndex(
        document_count=document_count,
        prototypes=prototypes,
        lexical_postings=frozen_lexical,
        entity_postings=entity_postings,
        idf=idf,
        build_seconds=build_seconds,
        plain_text_bytes=plain_text_bytes,
        eat_text_bytes=eat_text_bytes,
        references_parsed=references_parsed,
    )


def rank_scores(scores: dict[int, float], limit: int) -> list[int]:
    return [
        document_id
        for document_id, _ in heapq.nsmallest(
            limit,
            scores.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def lexical_scores(index: WorkloadIndex, query: Query) -> dict[int, float]:
    scores: dict[int, float] = defaultdict(float)
    for term in query.terms:
        postings = index.lexical_postings.get(term)
        if postings is None:
            continue
        weight = index.idf[term]
        for document_id in postings:
            scores[document_id] += weight
    return dict(scores)


def score_document(index: WorkloadIndex, query: Query, document_id: int) -> float:
    terms = index.prototypes[document_id % len(index.prototypes)].terms
    return sum(index.idf.get(term, 0.0) for term in query.terms if term in terms)


def retrieve_lexical(
    index: WorkloadIndex,
    query: Query,
    *,
    top_k: int,
) -> list[int]:
    return rank_scores(lexical_scores(index, query), top_k)


def retrieve_eat_filtered(
    index: WorkloadIndex,
    query: Query,
    *,
    top_k: int,
) -> list[int]:
    scores = {
        document_id: score_document(index, query, document_id)
        for document_id in index.entity_postings[query.entity_id]
    }
    return rank_scores(scores, top_k)


def retrieve_hybrid(
    index: WorkloadIndex,
    query: Query,
    *,
    top_k: int,
    candidate_count: int,
) -> list[int]:
    scores = lexical_scores(index, query)
    lexical_candidates = rank_scores(scores, max(top_k, candidate_count))
    candidate_scores = {
        document_id: scores[document_id]
        for document_id in lexical_candidates
    }
    maximum_lexical_score = sum(index.idf.get(term, 0.0) for term in query.terms)
    entity_boost = maximum_lexical_score + 1.0
    for document_id in index.entity_postings[query.entity_id]:
        candidate_scores[document_id] = (
            score_document(index, query, document_id) + entity_boost
        )
    return rank_scores(candidate_scores, top_k)


def route_metrics(
    *,
    route: str,
    queries: list[Query],
    rankings: dict[str, list[int]],
    index: WorkloadIndex,
    top_k: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    hits = {1: 0, 5: 0, top_k: 0}
    relevant_at_k = 0
    reciprocal_rank_sum = 0.0
    answer_exact_matches = 0
    context_words = 0
    details: list[dict[str, object]] = []
    digest = hashlib.sha256()

    for query in queries:
        documents = rankings[query.entity_id]
        relevant = [
            (
                query.entity_id
                in index.prototypes[
                    document_id % len(index.prototypes)
                ].context_entity_ids
            )
            for document_id in documents
        ]
        for cutoff in hits:
            if any(relevant[:cutoff]):
                hits[cutoff] += 1
        relevant_at_k += sum(relevant[:top_k])
        first_relevant = next(
            (rank for rank, is_relevant in enumerate(relevant, start=1) if is_relevant),
            None,
        )
        if first_relevant is not None and first_relevant <= top_k:
            reciprocal_rank_sum += 1.0 / first_relevant

        answer = None
        answer_correct = False
        if documents:
            answer = index.prototypes[
                documents[0] % len(index.prototypes)
            ].source_title
            answer_correct = bool(relevant[0]) and answer in query.gold_source_titles
            answer_exact_matches += int(answer_correct)
        context_words += sum(
            index.prototypes[
                document_id % len(index.prototypes)
            ].word_count
            for document_id in documents[:top_k]
        )
        digest.update(query.entity_id.encode("utf-8"))
        digest.update(b"\0")
        for document_id in documents:
            digest.update(document_id.to_bytes(4, "big"))

        details.append(
            {
                "entity_id": query.entity_id,
                "label": query.label,
                "question": query.question,
                "gold_source_titles": list(query.gold_source_titles),
                "document_ids": documents,
                "context_relevant": relevant,
                "answer": answer,
                "answer_correct": answer_correct,
            }
        )

    question_count = len(queries)
    return (
        {
            "route": route,
            "questions": question_count,
            "top_k": top_k,
            "hit_at_1": round(hits[1] / question_count, 4),
            "hit_at_5": round(hits[5] / question_count, 4),
            f"hit_at_{top_k}": round(hits[top_k] / question_count, 4),
            f"precision_at_{top_k}": round(
                relevant_at_k / (question_count * top_k),
                4,
            ),
            f"mrr_at_{top_k}": round(
                reciprocal_rank_sum / question_count,
                4,
            ),
            "source_answer_exact_match": round(
                answer_exact_matches / question_count,
                4,
            ),
            "source_answers_correct": answer_exact_matches,
            f"retrieved_context_words_at_{top_k}": context_words,
            "ranking_sha256": digest.hexdigest(),
        },
        details,
    )


def run_retrieval(
    index: WorkloadIndex,
    queries: list[Query],
    *,
    top_k: int,
    query_rounds: int,
    hybrid_candidates: int,
) -> tuple[
    dict[str, dict[str, object]],
    dict[str, list[dict[str, object]]],
    dict[str, dict[str, object]],
]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if query_rounds <= 0:
        raise ValueError("query_rounds must be positive")
    if hybrid_candidates < top_k:
        raise ValueError("hybrid_candidates must be at least top_k")

    route_functions = {
        "ordinary_lexical": lambda query: retrieve_lexical(
            index,
            query,
            top_k=top_k,
        ),
        "eat_filtered": lambda query: retrieve_eat_filtered(
            index,
            query,
            top_k=top_k,
        ),
        "hybrid": lambda query: retrieve_hybrid(
            index,
            query,
            top_k=top_k,
            candidate_count=hybrid_candidates,
        ),
    }
    samples_us: dict[str, list[float]] = {
        route: [] for route in route_functions
    }
    first_rankings: dict[str, dict[str, list[int]]] = {
        route: {} for route in route_functions
    }
    for round_number in range(query_rounds):
        rotated = (
            queries[round_number % len(queries) :]
            + queries[: round_number % len(queries)]
        )
        for query_number, query in enumerate(rotated):
            route_names = list(route_functions)
            if (round_number + query_number) % 2:
                route_names.reverse()
            for route in route_names:
                start = time.perf_counter_ns()
                documents = route_functions[route](query)
                elapsed_us = (time.perf_counter_ns() - start) / 1_000
                samples_us[route].append(elapsed_us)
                if round_number == 0:
                    first_rankings[route][query.entity_id] = documents

    metrics_by_route: dict[str, dict[str, object]] = {}
    details_by_route: dict[str, list[dict[str, object]]] = {}
    timing_by_route: dict[str, dict[str, object]] = {}
    for route in route_functions:
        metrics, details = route_metrics(
            route=route,
            queries=queries,
            rankings=first_rankings[route],
            index=index,
            top_k=top_k,
        )
        metrics_by_route[route] = metrics
        details_by_route[route] = details
        route_samples = samples_us[route]
        timing_by_route[route] = {
            "samples": len(route_samples),
            "query_rounds": query_rounds,
            "p50_microseconds": round(statistics.median(route_samples), 3),
            "p95_microseconds": round(percentile(route_samples, 0.95), 3),
            "p99_microseconds": round(percentile(route_samples, 0.99), 3),
        }
    return metrics_by_route, details_by_route, timing_by_route


def run_benchmark(
    *,
    source_records: list[dict[str, object]],
    registry_records: list[dict[str, object]],
    document_count: int,
    top_k: int,
    query_rounds: int,
    hybrid_candidates: int,
) -> dict[str, object]:
    registry = ResolverRegistry(registry_records)
    prototypes = build_prototypes(source_records, registry_records)
    queries = build_queries(prototypes)
    index = build_workload_index(
        prototypes,
        registry,
        document_count=document_count,
    )
    metrics, details, timings = run_retrieval(
        index,
        queries,
        top_k=top_k,
        query_rounds=query_rounds,
        hybrid_candidates=hybrid_candidates,
    )
    for route in ("eat_filtered", "hybrid"):
        if metrics[route]["hit_at_1"] != 1.0:
            raise RuntimeError(
                f"{route} failed to retrieve a relevant passage for every query"
            )
        if metrics[route]["source_answer_exact_match"] != 1.0:
            raise RuntimeError(
                f"{route} failed the grounded source-answer check"
            )
    lexical_postings = sum(
        len(postings) for postings in index.lexical_postings.values()
    )
    entity_postings = sum(
        len(postings) for postings in index.entity_postings.values()
    )
    example_entity_ids = [
        str(item["entity_id"])
        for item in details["ordinary_lexical"]
        if not item["answer_correct"]
    ][:5]
    if not example_entity_ids:
        example_entity_ids = [
            str(item["entity_id"])
            for item in details["ordinary_lexical"][:5]
        ]
    details_by_route_and_entity = {
        route: {
            str(item["entity_id"]): item
            for item in route_details
        }
        for route, route_details in details.items()
    }
    query_result_examples = []
    for entity_id in example_entity_ids:
        ordinary = details_by_route_and_entity["ordinary_lexical"][entity_id]
        query_result_examples.append(
            {
                "entity_id": entity_id,
                "label": ordinary["label"],
                "question": ordinary["question"],
                "gold_source_titles": ordinary["gold_source_titles"],
                "routes": {
                    route: {
                        "document_ids": route_details[entity_id]["document_ids"],
                        "context_relevant": route_details[entity_id][
                            "context_relevant"
                        ],
                        "answer": route_details[entity_id]["answer"],
                        "answer_correct": route_details[entity_id][
                            "answer_correct"
                        ],
                    }
                    for route, route_details in details_by_route_and_entity.items()
                },
            }
        )
    return {
        "workload": {
            "generated_documents": document_count,
            "different_source_documents": len(
                {item.source_id for item in prototypes}
            ),
            "different_passage_prototypes": len(prototypes),
            "generation_method": (
                "repeat 669 annotated Wiki-Fair passages in deterministic "
                "order and assign every copy a distinct integer document ID"
            ),
            "eat_references": index.references_parsed,
            "eat_references_per_document": round(
                index.references_parsed / document_count,
                4,
            ),
            "documents_with_exactly_one_eat_reference": document_count,
            "different_entities": len(queries),
            "plain_text_bytes": index.plain_text_bytes,
            "eat_text_bytes": index.eat_text_bytes,
            "eat_markup_extra_bytes": (
                index.eat_text_bytes - index.plain_text_bytes
            ),
        },
        "index": {
            "build_seconds": round(index.build_seconds, 6),
            "documents_per_second": round(
                document_count / index.build_seconds,
                2,
            ),
            "lexical_terms": len(index.lexical_postings),
            "lexical_postings": lexical_postings,
            "entity_keys": len(index.entity_postings),
            "entity_postings": entity_postings,
            "entity_postings_integer_bits": 32,
        },
        "questions": {
            "count": len(queries),
            "form": "Which source page mentions <registry label>?",
            "ordinary_input": "the registry label as plain query text",
            "eat_input": (
                "the gold canonical entity ID supplied directly to the "
                "retrieval route"
            ),
            "answer_step": (
                "return the source-page title from the top-ranked passage"
            ),
        },
        "retrieval": {
            "top_k": top_k,
            "query_rounds": query_rounds,
            "hybrid_lexical_candidate_count": hybrid_candidates,
            "ordinary_lexical": (
                "IDF-weighted lexical retrieval over all plain passages"
            ),
            "eat_filtered": (
                "filter by the one parsed EAT entity ID, then rank matching "
                "passages by the same lexical score"
            ),
            "hybrid": (
                "combine lexical candidates with an exact EAT entity boost"
            ),
            "quality": metrics,
            "latency": timings,
        },
        "query_result_examples": query_result_examples,
    }


def write_quality_chart(path: Path, result: dict[str, object]) -> None:
    quality = result["retrieval"]["quality"]
    routes = [
        ("ordinary_lexical", "Ordinary lexical", "#9ca3af"),
        ("eat_filtered", "EAT filtered", "#2563eb"),
        ("hybrid", "Hybrid", "#16a34a"),
    ]
    metrics = [
        ("source_answer_exact_match", "Source answer"),
        ("hit_at_10", "Entity hit@10"),
        ("mrr_at_10", "MRR@10"),
    ]
    rows: list[str] = []
    for metric_index, (metric_key, metric_label) in enumerate(metrics):
        y = 150 + metric_index * 120
        rows.append(
            f'<text class="metric" x="150" y="{y + 38}">'
            f"{escape(metric_label)}</text>"
        )
        for route_index, (route_key, _, color) in enumerate(routes):
            value = float(quality[route_key][metric_key])
            bar_y = y + route_index * 28
            width = round(value * 650)
            rows.append(
                f'<rect x="190" y="{bar_y}" width="{width}" height="20" '
                f'rx="3" fill="{color}"/>'
                f'<text class="value" x="{205 + width}" y="{bar_y + 15}">'
                f"{value * 100:.1f}%</text>"
            )
    legend: list[str] = []
    for index, (_, label, color) in enumerate(routes):
        x = 190 + index * 210
        legend.append(
            f'<rect x="{x}" y="92" width="16" height="12" rx="2" '
            f'fill="{color}"/>'
            f'<text class="legend" x="{x + 24}" y="103">{escape(label)}</text>'
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="560" viewBox="0 0 1050 560" role="img">
  <title>One-tag RAG retrieval quality</title>
  <desc>Source-answer accuracy, entity hit at ten and mean reciprocal rank at ten for ordinary lexical, EAT-filtered and hybrid retrieval.</desc>
  <style>
    .bg {{ fill: #ffffff; }}
    .title {{ font: 700 27px system-ui, sans-serif; fill: #111827; }}
    .subtitle {{ font: 15px system-ui, sans-serif; fill: #4b5563; }}
    .metric {{ font: 700 15px system-ui, sans-serif; fill: #111827; text-anchor: end; }}
    .value {{ font: 13px ui-monospace, monospace; fill: #111827; }}
    .legend {{ font: 13px system-ui, sans-serif; fill: #4b5563; }}
  </style>
  <rect class="bg" width="1050" height="560"/>
  <text class="title" x="40" y="48">100,000 documents, one EAT tag each</text>
  <text class="subtitle" x="40" y="76">434 source-page questions; top 10 passages available to the answer step</text>
  {''.join(legend)}
  {''.join(rows)}
  <text class="subtitle" x="40" y="530">The EAT routes receive the correct query entity ID; this is an oracle retrieval test.</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def write_latency_chart(path: Path, result: dict[str, object]) -> None:
    latency = result["retrieval"]["latency"]
    routes = [
        ("ordinary_lexical", "Ordinary lexical", "#9ca3af"),
        ("eat_filtered", "EAT filtered", "#2563eb"),
        ("hybrid", "Hybrid", "#16a34a"),
    ]
    maximum = max(
        float(latency[route]["p95_microseconds"])
        for route, _, _ in routes
    )
    rows: list[str] = []
    for index, (route, label, color) in enumerate(routes):
        y = 145 + index * 100
        p50 = float(latency[route]["p50_microseconds"])
        p95 = float(latency[route]["p95_microseconds"])
        p50_width = round(620 * p50 / maximum)
        p95_width = round(620 * p95 / maximum)
        rows.append(
            f'<text class="route" x="170" y="{y + 28}">{escape(label)}</text>'
            f'<rect x="210" y="{y}" width="{p50_width}" height="24" '
            f'rx="3" fill="{color}" opacity="0.65"/>'
            f'<text class="value" x="{225 + p50_width}" y="{y + 17}">'
            f"p50 {p50:.1f} µs</text>"
            f'<rect x="210" y="{y + 34}" width="{p95_width}" height="24" '
            f'rx="3" fill="{color}"/>'
            f'<text class="value" x="{225 + p95_width}" y="{y + 51}">'
            f"p95 {p95:.1f} µs</text>"
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="500" viewBox="0 0 1050 500" role="img">
  <title>One-tag RAG retrieval latency</title>
  <desc>Median and 95th percentile query latency for ordinary lexical, EAT-filtered and hybrid retrieval.</desc>
  <style>
    .bg {{ fill: #ffffff; }}
    .title {{ font: 700 27px system-ui, sans-serif; fill: #111827; }}
    .subtitle {{ font: 15px system-ui, sans-serif; fill: #4b5563; }}
    .route {{ font: 700 14px system-ui, sans-serif; fill: #111827; text-anchor: end; }}
    .value {{ font: 13px ui-monospace, monospace; fill: #111827; }}
  </style>
  <rect class="bg" width="1050" height="500"/>
  <text class="title" x="40" y="48">Retrieval time per question</text>
  <text class="subtitle" x="40" y="76">Machine-dependent timing; quality is checked separately</text>
  {''.join(rows)}
  <text class="subtitle" x="40" y="470">Hybrid includes lexical candidate retrieval plus the exact EAT entity boost.</text>
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
                "repeat 669 passage prototypes extracted from 40 source pages."
            ),
            "Every workload document contains exactly one generated EAT reference.",
            (
                "The EAT-filtered and hybrid routes receive the correct query "
                "entity ID from the benchmark answers."
            ),
            (
                "The ordinary route receives the registry label as plain query "
                "text; query entity-linking accuracy is not measured."
            ),
            (
                "The answer step extracts a source-page title. No language "
                "model, vector embedding or free-form answer generation runs."
            ),
            "Wall-clock timings are machine-dependent and are not pass thresholds.",
        ],
    }
    (output_dir / "one-tag-rag-results.json").write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    quality = result["retrieval"]["quality"]
    latency = result["retrieval"]["latency"]
    route_labels = {
        "ordinary_lexical": "Ordinary lexical",
        "eat_filtered": "EAT filtered",
        "hybrid": "Hybrid",
    }
    quality_rows = []
    latency_rows = []
    for route in ("ordinary_lexical", "eat_filtered", "hybrid"):
        route_quality = quality[route]
        route_latency = latency[route]
        quality_rows.append(
            f"| {route_labels[route]} | "
            f"{route_quality['source_answer_exact_match']:.4f} | "
            f"{route_quality['hit_at_1']:.4f} | "
            f"{route_quality['hit_at_10']:.4f} | "
            f"{route_quality['mrr_at_10']:.4f} |"
        )
        latency_rows.append(
            f"| {route_labels[route]} | "
            f"{route_latency['p50_microseconds']} µs | "
            f"{route_latency['p95_microseconds']} µs | "
            f"{route_latency['p99_microseconds']} µs |"
        )
    (output_dir / "one-tag-rag-summary.md").write_text(
        f"# {workload['generated_documents']:,}-document one-tag RAG retrieval benchmark\n\n"
        "## What ran\n\n"
        f"- {workload['generated_documents']:,} generated workload documents\n"
        f"- {workload['different_passage_prototypes']:,} annotated passage prototypes "
        f"from {workload['different_source_documents']} Wikipedia pages\n"
        f"- {workload['eat_references']:,} EAT references: exactly one per document\n"
        f"- {workload['different_entities']:,} entity questions\n"
        "- ordinary lexical, EAT-filtered and hybrid retrieval\n"
        "- a deterministic answer step that returns the selected source-page title\n\n"
        "The question asks which source page mentions a registry label. The "
        "ordinary route searches that label as plain text. The EAT routes "
        "receive the correct canonical entity ID directly. That makes this an "
        "oracle test of the retrieval layer, not a query-linking or LLM test.\n\n"
        "![Retrieval quality](retrieval-quality.svg)\n\n"
        "## Retrieval and source-answer quality\n\n"
        "| Route | Source answer exact match | Hit@1 | Hit@10 | MRR@10 |\n"
        "|---|---:|---:|---:|---:|\n"
        + "\n".join(quality_rows)
        + "\n\n"
        "A hit means that the requested entity has a known annotation inside "
        "the retrieved passage. Source-answer exact match also requires that "
        "the top passage provides that evidence before its page title counts "
        "as a correct answer.\n\n"
        "## Query time\n\n"
        "| Route | p50 | p95 | p99 |\n"
        "|---|---:|---:|---:|\n"
        + "\n".join(latency_rows)
        + "\n\n"
        "![Retrieval latency](retrieval-latency.svg)\n\n"
        "Timings depend on the machine. CI checks the complete workload, exact "
        "tag count and recorded quality invariants, not a fixed speed limit.\n\n"
        "## Boundary\n\n"
        "This is the retrieval and source-selection part of a RAG pipeline. It "
        "does not run embeddings, a vector database or a language model. The "
        "100,000 documents repeat 669 passages from 40 source pages, so they "
        "are not 100,000 different source documents.\n",
        encoding="utf-8",
    )
    write_quality_chart(output_dir / "retrieval-quality.svg", result)
    write_latency_chart(output_dir / "retrieval-latency.svg", result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-dataset", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--documents", type=int, default=DEFAULT_DOCUMENTS)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--query-rounds",
        type=int,
        default=DEFAULT_QUERY_ROUNDS,
    )
    parser.add_argument(
        "--hybrid-candidates",
        type=int,
        default=DEFAULT_HYBRID_CANDIDATES,
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    source_records = load_jsonl(args.oracle_dataset)
    registry_records = load_jsonl(args.registry)
    result = run_benchmark(
        source_records=source_records,
        registry_records=registry_records,
        document_count=args.documents,
        top_k=args.top_k,
        query_rounds=args.query_rounds,
        hybrid_candidates=args.hybrid_candidates,
    )
    command = (
        "python scripts/run_one_tag_rag_benchmark.py "
        f"--oracle-dataset {args.oracle_dataset} "
        f"--registry {args.registry} "
        f"--documents {args.documents} "
        f"--top-k {args.top_k} "
        f"--query-rounds {args.query_rounds} "
        f"--hybrid-candidates {args.hybrid_candidates} "
        f"--output-dir {args.output_dir}"
    )
    write_outputs(
        args.output_dir,
        oracle_path=args.oracle_dataset,
        registry_path=args.registry,
        result=result,
        command=command,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
