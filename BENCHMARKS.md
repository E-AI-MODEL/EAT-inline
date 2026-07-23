# EAT Inline benchmarks

This document contains the technical details behind the short test explanation
in the [README](README.md).

## Test groups

### Synthetic gold corpus

The bilingual seed corpus contains 76 records:

| Task | Records | Purpose |
|---|---:|---|
| Syntax | 20 | Valid and invalid reference forms |
| Typing | 16 | Expected entity type and key |
| Resolution | 12 | Written references mapped to canonical IDs |
| Generation | 16 | Plain text paired with expected EAT Inline output |
| Comparison | 12 | The same intended references with and without EAT Inline |

The comparison set contains deliberately ambiguous labels such as `Phoenix`,
`Atlas` and `Resolver API`.

Three offline conditions are scored over the same cases:

| Condition | Method | Entity information |
|---|---|---|
| `plain` | Exact registry-label match | None |
| `linker` | Gazetteer linker that adds its own references | Inferred |
| `eat_inline` | Resolver reading written `type:key` references | Supplied |

These small deterministic tests check the implementation. They are not evidence
of broad real-world performance.

## Public Wiki-Fair test

The public experiment uses the no-coreference split of
[Wiki-Fair v2](https://github.com/ad-freiburg/wiki-entity-linker), pinned to
commit `c9a3fe9c4933888d756d702fdb9ff607fc36aa26`.

| Material | Count |
|---|---:|
| Development documents from Wikipedia pages | 80 |
| Separate test documents from complete Wikipedia pages | 40 |
| Scored text positions in the test documents | 669 |
| Unique test entities | 434 |
| Article-entity pairs used by set-level scoring | 444 |
| Entities in the closed candidate registry | 1,063 |

The 40 test documents are 40 JSONL records. JSONL is the benchmark container,
not a required EAT Inline authoring format. The experiment does not currently
test Word, PDF, Excel, Markdown or HTML import and export.

### Frozen model run

Scikit-learn `1.8.0` builds a character 3-to-5-gram TF-IDF retriever. Inference
receives only `id` and `plain_text`. The scorer receives the gold IDs
separately.

| Condition | Precision | Recall | F1 | Exact match |
|---|---:|---:|---:|---:|
| TF-IDF model linker | 0.7247 | 0.6937 | 0.7089 | 0.1250 |
| Plain exact-label baseline | 0.6667 | 0.7072 | 0.6863 | 0.0500 |

Metrics are sets of canonical IDs per article. Repeated mentions of the same
entity in one article count once. These are not mention-level scores.

### EAT-assistance test

The assistance test reuses the frozen model predictions. It does not train or
run a different model.

The public gold spans are ranked deterministically. The first 0%, 25%, 50%,
75% or 100% are replaced with correct `@@EAT entity:QID@@` references. A
selected EAT reference overrides an overlapping model prediction. Model
predictions outside selected spans remain unchanged.

| Coverage | EAT text positions | Plain text positions | Documents containing EAT |
|---:|---:|---:|---:|
| 0% | 0 | 669 | 0 of 40 |
| 25% | 167 | 502 | 36 of 40 |
| 50% | 335 | 334 | 37 of 40 |
| 75% | 502 | 167 | 39 of 40 |
| 100% | 669 | 0 | 40 of 40 |

| Coverage | Precision | Recall | F1 | Exact match | False positives | False negatives |
|---:|---:|---:|---:|---:|---:|---:|
| 0% | 0.7247 | 0.6937 | 0.7089 | 0.125 | 117 | 136 |
| 25% | 0.7472 | 0.7523 | 0.7497 | 0.150 | 113 | 110 |
| 50% | 0.7819 | 0.8559 | 0.8172 | 0.225 | 106 | 64 |
| 75% | 0.8027 | 0.9257 | 0.8598 | 0.275 | 101 | 33 |
| 100% | 0.8253 | 1.0000 | 0.9043 | 0.525 | 94 | 0 |
| EAT-only oracle | 1.0000 | 1.0000 | 1.0000 | 1.000 | 0 | 0 |

The EAT-only row confirms that every generated reference resolves to its known
entity. It is not a fair model comparison because those references come from
the test answers.

### Limits

- EAT references are generated from public test labels.
- This is an oracle upper bound, not a human authoring study.
- The model never sees the gold fields.
- The candidate registry contains only entities from the development and test
  splits.
- Scores are canonical-ID sets per article, not mention-level scores.

## Recorded runs

[`schemas/linker-run.schema.json`](schemas/linker-run.schema.json) defines the
recorded-run format. A run records:

- the dataset and registry SHA-256 hashes;
- `plain_text` as its only benchmark input;
- model name, version and source;
- runner commit, command and parameters;
- every predicted mention span and typed key.

Validation rejects missing or duplicate cases, changed inputs, invalid spans,
unknown typed keys and leaked fields such as `gold_ids` or `eat_text`.

## 100,000-document scale-search test

This separate benchmark measures representation overhead and indexed entity
lookup. It does not rerun the TF-IDF model.

### Workload

- 40 complete Wikipedia source pages are repeated in deterministic order.
- Every copy receives a distinct 32-bit integer document ID.
- The final workload contains 100,000 generated documents.
- Every one of the 1,672,500 scored text positions has an EAT reference.
- The resulting index contains 1,110,000 document-entity pairs for 434
  different entities.

The plain-text workload is 259.9 MB. Inline EAT adds 16.8 MB, or 6.5%, for a
total of 276.8 MB. The 32-bit postings payload is 4.44 MB. That payload number
does not include Python dictionary and array-object overhead.

The repeated source text keeps the workload public and exactly checkable. It
does not provide the diversity of 100,000 different documents.

### Compared routes

The metadata control receives the correct entity IDs as separate structured
metadata. The EAT route parses the same IDs from the full inline-EAT text.
Both routes build an in-memory mapping from canonical entity ID to matching
document IDs.

The benchmark rejects the run unless both indexes have the same SHA-256
fingerprint and every search checksum matches.

### Recorded result

Environment: Python `3.12.13`, Linux `6.12.13`, AMD EPYC 9V74, 9 logical CPUs
visible to the container.

| Index build | Seconds | Documents/second | MB/second |
|---|---:|---:|---:|
| Correct IDs as separate metadata | 0.050861 | not comparable | not comparable |
| IDs parsed from inline EAT | 2.328733 | 42,941.80 | 118.84 |

The search test queried 434 entities over twenty rounds. The result-scan timing
includes looking up the postings list and reading every matching document ID,
for 22,200,000 document IDs in total.

| Index source | p50 | p95 | p99 | Document IDs read/second |
|---|---:|---:|---:|---:|
| Separate metadata | 30.496 µs | 36.524 µs | 61.001 µs | 80,405,355 |
| Inline EAT | 30.485 µs | 36.425 µs | 60.951 µs | 80,491,915 |

The 0.011-microsecond p50 difference is inside measurement noise. It is not a
claim that one route is faster. EAT affects index construction; after that,
both searches use identical postings.

This benchmark does not cover keyword search, full-text search, semantic
search, vector search, ranking, network transfer or result serialization.
Timings are informational and machine-dependent. CI checks correctness and
completion, not a fixed speed threshold.

### Reproduce the scale-search test

```bash
python scripts/run_scale_search_benchmark.py \
  --oracle-dataset benchmark/external/wiki-fair-v2/test.oracle-eat.jsonl \
  --registry benchmark/external/wiki-fair-v2/entity-registry.jsonl \
  --documents 100000 \
  --query-repetitions 100 \
  --query-rounds 20 \
  --output-dir /tmp/wiki-fair-v2-scale-search
```

## 100,000-document one-tag RAG retrieval test

This benchmark measures passage retrieval and a small extractive answer step.
It is separate from the full-coverage scale-search test.

### Workload

- The 669 annotated text positions in the 40 Wiki-Fair test pages become 669
  passage prototypes.
- Each prototype contains a 220-character context on both sides of one target
  mention.
- Only that target mention is replaced by an EAT reference.
- The prototypes repeat in deterministic order until the workload contains
  100,000 documents with distinct 32-bit integer IDs.
- Every document is parsed and rejected unless it contains exactly one
  resolvable EAT reference.

The final workload contains 100,000 EAT references, 45.1 MB of plain passage
text and 46.1 MB of EAT text. The text comes from 40 source pages; the 100,000
document IDs do not represent 100,000 different source documents.

### Questions and answers

There is one question for each of the 434 entities:

```text
Which source page mentions <registry label>?
```

The ordinary and inferred-EAT routes receive the registry label as plain query
text. Inferred EAT performs a case-insensitive exact lookup in the registry. It
uses the matching EAT postings only when the label has exactly one possible
canonical ID. It abstains and falls back to ordinary lexical retrieval when
the label is ambiguous or missing.

This resolves 427 of 434 questions uniquely, with 427 correct IDs and no wrong
ID guesses. Seven questions have ambiguous labels and use the fallback. There
are five distinct ambiguous labels: `Cambridge`, `Rosaline`, `captain`, `gold`
and `secretary`.

The EAT-filtered and hybrid routes still receive the correct canonical entity
ID from the benchmark answers. This known correct answer is also called the
gold ID. They are oracle ceilings: they measure retrieval after identity is
already known, not the system's ability to discover that identity.

A retrieved passage is relevant when the requested entity has a known
annotation inside its context window. The deterministic answer step returns
the source-page title from the top-ranked passage. The answer counts only when
that first passage contains the requested entity, so a correct title without
supporting passage evidence does not pass.

Hit@1 is the share of questions with a relevant first passage. Hit@10 is the
share with at least one relevant passage among the first ten results.

### Compared routes

| Route | Retrieval method |
|---|---|
| Ordinary lexical | IDF-weighted lexical retrieval over every plain passage |
| Inferred EAT | Unique exact registry-label lookup followed by an EAT entity filter; lexical fallback on ambiguity |
| Oracle EAT filter | Gold entity filter followed by the same lexical score |
| Hybrid oracle | Top 100 lexical candidates plus a gold EAT entity boost |

All ranking ties use the lowest document ID. The benchmark records every top-10
ranking and a SHA-256 digest for each route.

### Recorded quality

| Route | Source answer exact match | Hit@1 | Hit@10 | Precision@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|
| Ordinary lexical | 0.7742 | 0.7742 | 0.8272 | 0.7908 | 0.7888 |
| Inferred EAT | 0.9885 | 0.9885 | 0.9977 | 0.9942 | 0.9911 |
| Oracle EAT filter | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Hybrid oracle | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

The ordinary route produced 336 correct grounded source answers out of 434.
Inferred EAT produced 429 without receiving the answer ID. Both oracle routes
produced 434.

### Recorded timing

Environment: Python `3.12.13`, Linux `6.12.13`, AMD EPYC 9V74, 9 logical CPUs
visible to the container.

| Route | p50 | p95 | p99 |
|---|---:|---:|---:|
| Ordinary lexical | 546.493 µs | 19,950.143 µs | 32,507.424 µs |
| Inferred EAT | 93.063 µs | 371.172 µs | 1,257.259 µs |
| Oracle EAT filter | 89.042 µs | 328.979 µs | 617.629 µs |
| Hybrid oracle | 731.052 µs | 20,697.574 µs | 33,963.118 µs |

P50 means half of the measured questions finished within that time. P95 means
95% finished within that time; p99 means 99%.

The EAT filter examines a much smaller postings list. The hybrid route still
runs lexical candidate retrieval, so it does not have the filter-only latency
advantage. Timings are machine-dependent and are not CI thresholds.

### Boundary

This test covers the retrieval and source-selection part of a RAG pipeline. It
does not run a vector database, embeddings or a language model. It cannot
measure free-form answer quality or hallucinations. The inferred route measures
only exact canonical-label lookup; aliases, paraphrases and entity linking from
full natural-language questions remain untested. The perfect oracle results are
the expected upper bound when the correct query ID and document tags are
already known.

### Reproduce the one-tag RAG retrieval test

```bash
python scripts/run_one_tag_rag_benchmark.py \
  --oracle-dataset benchmark/external/wiki-fair-v2/test.oracle-eat.jsonl \
  --registry benchmark/external/wiki-fair-v2/entity-registry.jsonl \
  --documents 100000 \
  --top-k 10 \
  --query-rounds 3 \
  --hybrid-candidates 100 \
  --output-dir /tmp/wiki-fair-v2-one-tag-rag
```

## Reproduce the public experiment

```bash
python -m pip install -e '.[model]'
RUNNER_COMMIT=$(python -c "import json; print(json.load(open('benchmark/results/wiki-fair-v2-tfidf-linker-run.json'))['runner']['commit'])")
python scripts/run_tfidf_linker.py \
  --training benchmark/external/wiki-fair-v2/dev.training.jsonl \
  --input benchmark/external/wiki-fair-v2/test.inputs.jsonl \
  --dataset benchmark/external/wiki-fair-v2/test.comparison.jsonl \
  --registry benchmark/external/wiki-fair-v2/entity-registry.jsonl \
  --dataset-name wiki-fair-v2/test-no-coref@c9a3fe9c4933888d756d702fdb9ff607fc36aa26 \
  --runner-commit "$RUNNER_COMMIT" \
  --output /tmp/wiki-fair-v2-tfidf-linker-run.json
python scripts/run_recorded_linker_benchmark.py \
  /tmp/wiki-fair-v2-tfidf-linker-run.json \
  --dataset benchmark/external/wiki-fair-v2/test.comparison.jsonl \
  --registry benchmark/external/wiki-fair-v2/entity-registry.jsonl \
  --dataset-name wiki-fair-v2/test-no-coref@c9a3fe9c4933888d756d702fdb9ff607fc36aa26 \
  --output-dir /tmp/wiki-fair-v2-results
python scripts/run_eat_assistance_benchmark.py \
  --run benchmark/results/wiki-fair-v2-tfidf-linker-run.json \
  --model-dataset benchmark/external/wiki-fair-v2/test.comparison.jsonl \
  --oracle-dataset benchmark/external/wiki-fair-v2/test.oracle-eat.jsonl \
  --registry benchmark/external/wiki-fair-v2/entity-registry.jsonl \
  --output-dir /tmp/wiki-fair-v2-eat-assistance
```

Checksums, attribution and transformation rules are stored in
[`benchmark/external/wiki-fair-v2/`](benchmark/external/wiki-fair-v2/).

## Generated artifacts

The benchmark workflow reproduces and compares:

```text
benchmark-results.json
benchmark-summary.md
comparative-results.json
comparative-summary.md
dataset-validation.json
recorded-linker-results.json
recorded-linker-summary.md
wiki-fair-v2-tfidf-linker-run.json
wiki-fair-v2-eat-assistance/eat-assistance-results.json
wiki-fair-v2-eat-assistance/eat-assistance-summary.md
wiki-fair-v2-eat-assistance/coverage-by-level.svg
wiki-fair-v2-eat-assistance/performance-by-level.svg
wiki-fair-v2-scale-search/scale-search-results.json
wiki-fair-v2-scale-search/scale-search-summary.md
wiki-fair-v2-scale-search/scale-overview.svg
wiki-fair-v2-scale-search/search-latency.svg
wiki-fair-v2-one-tag-rag/one-tag-rag-results.json
wiki-fair-v2-one-tag-rag/one-tag-rag-summary.md
wiki-fair-v2-one-tag-rag/retrieval-quality.svg
wiki-fair-v2-one-tag-rag/retrieval-latency.svg
```
