# EAT Inline

**A small tag that tells software exactly which person, place or thing a sentence refers to.**

[![CI](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/ci.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/ci.yml)
[![Conformance](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/conformance.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/conformance.yml)
[![Benchmark](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/benchmark.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/benchmark.yml)
[![Docs](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/docs.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/docs.yml)

## The whole idea

Plain text can leave a name open to interpretation:

```text
The report was written by Hans Visser.
```

EAT Inline puts the intended identity in the text:

```text
The report was written by @@EAT person:Hans_Visser@@.
```

EAT Inline has one construct:

```text
@@EAT type:key@@
```

The surrounding sentence still describes the relationship. The EAT reference
only identifies the entity.

> Version `0.3.2` is experimental. It can be tested, but it is not yet a proven
> or frozen standard.

## What has actually been tested?

The repository contains two separate test groups:

| Test group | Size | What it checks |
|---|---:|---|
| Small synthetic tests | 76 records | Syntax, typing, resolution, generation and controlled comparisons |
| Public Wikipedia test | 40 articles | Entity linking with one frozen TF-IDF model |

The graphs below describe only the public Wikipedia test.

### Size of the public test

- **40 Wikipedia articles**
- **669 entity mentions** inside those articles
- **434 unique Wikidata entities**
- **1,063 possible entities** in the closed lookup registry

The 40 articles are stored as 40 records in one JSONL file. They are not 40
separate files.

### What does 50% EAT coverage mean?

Coverage counts entity mentions, not articles or files.

- `0%` means 0 of the 669 mentions have an EAT reference.
- `50%` means 335 of the 669 mentions have an EAT reference. The other 334 stay
  as plain text.
- `100%` means all 669 mentions have an EAT reference.

At 50% coverage, the selected mentions happen to occur in 37 of the 40
articles. At 100%, all 40 articles contain EAT references.

![EAT coverage across the 669 tested mentions](benchmark/results/wiki-fair-v2-eat-assistance/coverage-by-level.svg)

| Coverage | Mentions with EAT | Mentions left plain | Articles with at least one EAT reference |
|---:|---:|---:|---:|
| 0% | 0 | 669 | 0 of 40 |
| 25% | 167 | 502 | 36 of 40 |
| 50% | 335 | 334 | 37 of 40 |
| 75% | 502 | 167 | 39 of 40 |
| 100% | 669 | 0 | 40 of 40 |

The same model predictions are reused at every level. A correct EAT reference
replaces the model prediction only at that selected text span.

### What happened to the model score?

![F1 and recall as EAT coverage increases](benchmark/results/wiki-fair-v2-eat-assistance/performance-by-level.svg)

| EAT coverage | Precision | Recall | F1 | Missed entities |
|---:|---:|---:|---:|---:|
| 0% | 0.7247 | 0.6937 | 0.7089 | 136 |
| 25% | 0.7472 | 0.7523 | 0.7497 | 110 |
| 50% | 0.7819 | 0.8559 | 0.8172 | 64 |
| 75% | 0.8027 | 0.9257 | 0.8598 | 33 |
| 100% | 0.8253 | 1.0000 | 0.9043 | 0 |

In this test:

- Half coverage removed 72 of the model's 136 missed entities.
- Full coverage removed all 136 missed entities.
- Full coverage still left 94 false positives from model predictions outside
  the EAT-tagged spans.

### What this result does and does not show

The test shows what happens when correct entity identities are supplied to the
same frozen model pipeline.

The EAT references were generated from the known test answers. People did not
write them, and the model did not discover them. The result is an upper bound,
not proof that authors can add EAT references accurately or quickly.

The EAT-only score is `1.0` because it reads those known correct identities
directly. That number is a resolver check, not a model achievement.

## Using the format

Examples:

```text
@@EAT person:Hans_Visser@@
@@EAT organisation:EAI_Analyse_Advies@@
@@EAT project:EAT_Inline@@
```

Both `type` and `key` use:

```text
[A-Za-z_][A-Za-z0-9_]*
```

A minimal parser needs only a regular expression:

```python
import re

REFERENCE_RE = re.compile(
    r"@@EAT (?P<type>[A-Za-z_][A-Za-z0-9_]*):"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)@@"
)
```

A resolver can map the written reference to an internal ID:

```json
{
  "source_reference": "@@EAT person:Hans_Visser@@",
  "canonical_id": "person-10492",
  "resolution_status": "resolved"
}
```

EAT Inline is the writing format. Databases, registries and resolution metadata
belong to the system using it.

## Documentation and reproduction

- [`SPEC.md`](SPEC.md) defines the grammar and compatibility rules.
- [`BENCHMARKS.md`](BENCHMARKS.md) explains every test condition, metric,
  limitation and reproduction command.
- [`schemas/registry-entry.schema.json`](schemas/registry-entry.schema.json)
  defines a registry record.
- [`GOVERNANCE.md`](GOVERNANCE.md) describes change control.
- [`CHANGELOG.md`](CHANGELOG.md) records releases and compatibility changes.

Run the standard checks:

```bash
python -m pip install -e .
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/run_conformance.py
python scripts/validate_dataset.py
python scripts/run_benchmark.py
python scripts/run_comparative_benchmark.py
python scripts/check_docs.py
```

## Current limits

The repository does not yet show:

- how accurately people write EAT references;
- how much writing time EAT adds;
- performance against a strong NER, entity-linking or LLM baseline;
- improved retrieval or RAG results;
- production readiness.

Those questions need new tests with people, stronger models and larger public
datasets.

## Stewardship and license

EAT Inline is developed by **Hans Visser** under **EAI Analyse & Advies**.
It is licensed under the [Apache License 2.0](LICENSE).
