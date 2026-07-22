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

Model-based linkers — a named-entity recogniser, an entity linker, an LLM resolver or a retriever/reranker — implement the same `EntityLinker` interface (`requires_model = True`) and plug into `LinkerAdapter` unchanged. They are **intentionally not bundled**: they need network access and non-deterministic models, which would make the benchmark irreproducible, and shipping a synthetic stand-in with an invented error rate would fabricate evidence. Each condition reports a deterministic cost proxy (registry lookups, label scans, references read, estimated tokens); wall-clock latency is left to callers as informational context, never a pass/fail gate.

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

No example model output is committed because an invented artifact would look like evidence. A published result must come from a named, pinned model and include the complete run artifact.

## Automated verification

| Workflow | Purpose |
|---|---|
| `CI` | Runs unit tests on supported Python versions |
| `Conformance` | Checks the implementation against versioned examples |
| `Benchmark` | Validates the corpus and runs parser, overhead and paired comparative benchmarks |
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
```

## Project foundation

- [`SPEC.md`](SPEC.md) defines the normative single-construct grammar.
- [`GOVERNANCE.md`](GOVERNANCE.md) describes change control and contribution rules.
- [`CHANGELOG.md`](CHANGELOG.md) records compatibility and release history.
- [`LICENSE`](LICENSE) makes the project available under Apache License 2.0.
- [`schemas/registry-entry.schema.json`](schemas/registry-entry.schema.json) defines a portable resolver-registry record.

The core grammar is intentionally conservative. New entity types do not require syntax changes, and application-specific metadata belongs in registries, resolvers or optional integration profiles.

## Evidence boundary

Version `0.3.2` establishes a testable notation, reference implementation, gold corpus and paired benchmark harness.

It does not yet prove:

- acceptable writing friction in every context;
- improved performance against strong NER or LLM baselines;
- improved retrieval or RAG outcomes;
- universal model compatibility;
- production readiness.

Those claims require larger public datasets and experiments with people, models and real resolver systems.

## Repository map

```text
.github/workflows/       automated checks
benchmark/corpora/       versioned gold corpus and entity registry
benchmark/results/       generated benchmark artifacts
schemas/                 portable JSON Schemas
scripts/                 verification and benchmark scripts
src/eat_inline.py        minimal reference implementation
src/eat_baselines.py     benchmark adapter and scoring framework
src/eat_recorded_runs.py recorded model-run validation and replay
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
