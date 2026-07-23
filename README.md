# EAT Inline

**A minimal writing format for explicit, readable and machine-processable references.**

[![CI](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/ci.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/ci.yml)
[![Conformance](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/conformance.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/conformance.yml)
[![Benchmark](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/benchmark.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/benchmark.yml)
[![Docs](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/docs.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/docs.yml)

EAT Inline lets a person or AI write a typed reference without knowing an internal database ID.

```text
Het rapport is geschreven door @@EAT person:Hans_Visser@@
voor @@EAT organisation:EAI_Analyse_Advies@@.
```

The tag makes the intended entity visible. The surrounding sentence keeps the relationship in natural language.

> **Status:** version `0.3.2` is an experimental candidate. It is usable for testing, but it is not yet a frozen or proven standard.

## Core syntax

EAT Inline has one construct:

```text
@@EAT type:key@@
```

Examples:

```text
@@EAT person:Hans_Visser@@
@@EAT organisation:EAI_Analyse_Advies@@
@@EAT project:EAT_Inline@@
```

`type` and `key` use:

```text
[A-Za-z_][A-Za-z0-9_]*
```

> **References identify entities. Natural language expresses relations.**

EAT Inline does not define special blocks for summaries or other document structure. Use the conventions of the host format.

The normative grammar, semantics and compatibility rules are defined in [`SPEC.md`](SPEC.md).

## Types

The syntax accepts any valid identifier as a type. The repository includes this benchmark-only vocabulary:

```text
person, organisation, location, document, project, event,
product, system, dataset, publication, website, method, concept
```

It is a scoring aid, not a normative registry. Domain-specific types remain possible.

## Writing format, not storage format

EAT Inline is primarily an authoring format. A resolver may map the written reference to an internal ID and store both:

```json
{
  "source_reference": "@@EAT person:Hans_Visser@@",
  "canonical_id": "person-10492",
  "resolution_status": "resolved"
}
```

The source reference records author intent. The canonical ID records the system's resolved entity. Resolution metadata belongs to the consuming system, not to the EAT Inline syntax.

A storage-neutral registry-entry schema is available at [`schemas/registry-entry.schema.json`](schemas/registry-entry.schema.json).

## Minimal implementation

A basic implementation only needs a regular expression:

```python
import re

REFERENCE_RE = re.compile(
    r"@@EAT (?P<type>[A-Za-z_][A-Za-z0-9_]*):"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)@@"
)
```

A type list, database resolver, governance process or gateway can be added when a use case needs it. None is required to parse or start using the notation.

## Benchmark corpus

The repository contains a synthetic, bilingual seed gold corpus with **76 records**:

| Task | Records | Purpose |
|---|---:|---|
| Syntax | 20 | Valid and invalid reference forms |
| Typing | 16 | Expected entity type and key |
| Resolution | 12 | Written references mapped to canonical IDs |
| Generation | 16 | Plain text paired with expected EAT Inline output |
| Comparison | 12 | The same intended references with and without EAT Inline |

The comparison set uses a small entity registry containing deliberately ambiguous labels such as `Phoenix`, `Atlas` and `Resolver API`.

## Paired evidence

The Benchmark Action runs three conditions over the same gold cases:

```text
plain exact-label matching
offline automatic linking
EAT Inline with explicit type and key
```

For each condition it reports:

- precision, recall and F1;
- exact-match rate per case;
- unresolved references;
- ambiguous plain-text mentions;
- machine-readable per-case predictions.

This produces reproducible evidence about the effect of supplying type and key information under controlled conditions. It does **not** by itself prove real-world superiority: the seed dataset is synthetic and the plain-text baseline uses deterministic label matching rather than a language model.

## Baseline adapter framework

Each benchmark condition is a `BaselineAdapter` (see [`src/eat_baselines.py`](src/eat_baselines.py)), so different resolution strategies are scored identically over the same gold cases. Three deterministic, offline conditions ship today:

| Condition | Adapter | Entity info | Uses a model? |
|---|---|---|---|
| `plain` | Exact label matching over the registry | none | No |
| `linker` | Offline gazetteer linker that places its own references | inferred | No |
| `eat_inline` | Resolves author-written references by `type` and `key` | author-supplied | No |

The `linker` condition reads only the plain text; it never receives the author's tags or the gold IDs. It detects complete registry labels, prefers the longest overlapping label, uses a nearby type word as a conservative cue (for example `project` near `Phoenix`), and otherwise abstains. On the current corpus the ambiguous mentions deliberately carry no type cue, so this simple linker matches the plain baseline while `eat_inline` resolves every case. This is a mechanical offline baseline, not evidence that a stronger model could not recover those entities. Its purpose is to make automatic linkers directly scorable without giving them perfect author annotations.

Model-based linkers — a named-entity recogniser, an entity linker, an LLM resolver or a retriever/reranker — use the same prediction and scoring boundary. The default synthetic benchmark remains model-free. A separate, pinned TF-IDF runner is included for the public-corpus experiment below; it is installed through the optional `model` dependency and recorded before deterministic replay. Each condition reports a deterministic cost proxy (registry lookups, label scans, references read, estimated tokens); wall-clock latency is left to callers as informational context, never as a pass/fail gate.

### Recorded model runs

An external model run can be replayed without giving CI network access or hiding the per-case output. The artifact format is defined in [`schemas/linker-run.schema.json`](schemas/linker-run.schema.json). Every run records:

- the exact dataset name, dataset SHA-256 and registry SHA-256;
- `plain_text` as the only benchmark input field;
- the model name, immutable version and source;
- the runner commit, command and parameters;
- complete per-case mention spans, typed keys and model-cost metadata.

The validator rejects missing, duplicate or unknown cases, changed datasets, labels that do not match their plain-text spans, unknown typed keys and undocumented fields such as `gold_ids` or `eat_text`. A validated run uses the same precision, recall, F1 and exact-match functions as the built-in benchmark:

```bash
python scripts/run_recorded_linker_benchmark.py path/to/linker-run.json
```

The committed Wiki-Fair result below was produced by its named, pinned model and includes the complete run artifact. New published results must meet the same requirement; illustrative or invented model output is not accepted as evidence.

### Independent public-corpus model run

The repository now includes a reproducible run on the no-coreference split of
[Wiki-Fair v2](https://github.com/ad-freiburg/wiki-entity-linker), pinned to
upstream commit `c9a3fe9c4933888d756d702fdb9ff607fc36aa26`:

- 80 development articles train entity profiles and mention aliases;
- 40 separate test articles are used only for evaluation;
- 1,063 Wikidata entities form a closed candidate registry;
- scikit-learn `1.8.0` builds a character 3–5-gram TF-IDF retriever;
- inference receives a separate file containing exactly `id` and `plain_text`;
- the scorer alone receives test `gold_ids`.

Results use the same canonical-ID set metrics as the recorded-run scorer. A
duplicate entity within an article therefore counts once; these are not
mention-level scores.

| Condition | Precision | Recall | F1 | Exact match |
|---|---:|---:|---:|---:|
| TF-IDF model linker | `0.7247` | `0.6937` | `0.7089` | `0.125` |
| Plain exact-label baseline | `0.6667` | `0.7072` | `0.6863` | `0.05` |

The model run improves F1 by `0.0226` over the label baseline on this setup,
mainly by reducing false positives. This is real non-synthetic linker evidence,
but it is deliberately narrow. Candidate names are constructed from entities
annotated in the dev and test splits rather than all of Wikidata, alias learning
uses dev only.

### Oracle EAT assistance on the same model

A second experiment freezes the model predictions above and adds correct EAT
references at a deterministic 0%, 25%, 50%, 75% or 100% of the 669 public test
mentions. At an assisted span, the EAT reference overrides an overlapping model
prediction; the same model output remains active everywhere else.

| Condition | EAT mentions | Precision | Recall | F1 | Exact match |
|---|---:|---:|---:|---:|---:|
| Model + EAT (0%) | `0` | `0.7247` | `0.6937` | `0.7089` | `0.125` |
| Model + EAT (25%) | `167` | `0.7472` | `0.7523` | `0.7497` | `0.15` |
| Model + EAT (50%) | `335` | `0.7819` | `0.8559` | `0.8172` | `0.225` |
| Model + EAT (75%) | `502` | `0.8027` | `0.9257` | `0.8598` | `0.275` |
| Model + EAT (100%) | `669` | `0.8253` | `1.0` | `0.9043` | `0.525` |
| EAT-only oracle | `669` | `1.0` | `1.0` | `1.0` | `1.0` |

In this controlled setup, complete EAT assistance removes all 136 false
negatives and raises model-pipeline F1 by `0.1954`. The remaining 94 false
positives come from model predictions outside annotated entity spans; an
EAT-only resolver does not make those predictions.

This is an oracle upper bound. The EAT references are generated from the public
test gold labels, not written by people and not inferred by the model. The
experiment therefore measures what correct explicit identity does to the same
pipeline. It does not show that authors can create those references accurately,
quickly or without assistance.

Reproduce the frozen run and replay its score:

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

Source checksums, transformation rules, attribution and data terms are in
[`benchmark/external/wiki-fair-v2/`](benchmark/external/wiki-fair-v2/).

## Automated verification

| Workflow | Purpose |
|---|---|
| `CI` | Runs unit tests on supported Python versions |
| `Conformance` | Checks the implementation against versioned examples |
| `Benchmark` | Validates the corpora and reproduces the Wiki-Fair model run and oracle EAT-assistance curve |
| `Docs` | Detects version drift, invalid JSON, missing foundation files and retired names or syntax |

Run the same checks locally:

```bash
python -m pip install -e .
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/run_conformance.py
python scripts/validate_dataset.py
python scripts/run_benchmark.py
python scripts/run_comparative_benchmark.py
python scripts/check_docs.py
```

Benchmark artifacts include:

```text
benchmark-results.json
benchmark-summary.md
comparative-results.json
comparative-summary.md
dataset-validation.json
recorded-linker-results.json       # only after replaying an external run
recorded-linker-summary.md         # only after replaying an external run
wiki-fair-v2-tfidf-linker-run.json # complete public-corpus predictions
wiki-fair-v2-eat-assistance/       # same-model oracle assistance curve
```

## Project foundation

- [`SPEC.md`](SPEC.md) defines the normative single-construct grammar.
- [`GOVERNANCE.md`](GOVERNANCE.md) describes change control and contribution rules.
- [`CHANGELOG.md`](CHANGELOG.md) records compatibility and release history.
- [`LICENSE`](LICENSE) makes the project available under Apache License 2.0.
- [`schemas/registry-entry.schema.json`](schemas/registry-entry.schema.json) defines a portable resolver-registry record.

The core grammar is intentionally conservative. New entity types do not require syntax changes, and application-specific metadata belongs in registries, resolvers or optional integration profiles.

## Evidence boundary

Version `0.3.2` establishes a testable notation, reference implementation,
gold corpus, paired benchmark harness and one independent public-corpus model
run plus a controlled oracle EAT-assistance curve.

It does not yet prove:

- acceptable writing friction in every context;
- improved performance against strong NER or LLM baselines;
- gains from naturally human-authored EAT references on a public corpus;
- improved retrieval or RAG outcomes;
- universal model compatibility;
- production readiness.

Those claims require larger public datasets and experiments with people, models and real resolver systems.

## Repository map

```text
.github/workflows/       automated checks
benchmark/corpora/       versioned gold corpus and entity registry
benchmark/external/      pinned public-corpus training, input and scorer data
benchmark/results/       generated benchmark artifacts
schemas/                 portable JSON Schemas
scripts/                 verification and benchmark scripts
src/eat_inline.py        minimal reference implementation
src/eat_baselines.py     benchmark adapter and scoring framework
src/eat_recorded_runs.py recorded model-run validation and replay
scripts/run_tfidf_linker.py reproducible Wiki-Fair model runner
scripts/run_eat_assistance_benchmark.py oracle assistance scorer
tests/                   unit tests and conformance examples
SPEC.md                  normative experimental specification
GOVERNANCE.md            change and contribution policy
CHANGELOG.md             release and compatibility history
pyproject.toml           package metadata
```

## Stewardship

EAT Inline is developed by **Hans Visser** under **EAI Analyse & Advies**. Governance details are in [`GOVERNANCE.md`](GOVERNANCE.md).

## License

Licensed under the [Apache License 2.0](LICENSE).
