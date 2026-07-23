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
```
