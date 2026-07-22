# EAT Inline

**A minimal inline language for explicit, readable and machine-processable references.**

[![CI](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/ci.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/ci.yml)
[![Conformance](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/conformance.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/conformance.yml)
[![Benchmark](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/benchmark.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/benchmark.yml)
[![Docs](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/docs.yml/badge.svg)](https://github.com/E-AI-MODEL/EAT-inline/actions/workflows/docs.yml)

EAT Inline adds compact semantic references to ordinary text without turning the document into a full markup language.

```text
Het rapport is geschreven door @@EAT person:Hans_Visser@@
voor @@EAT organisation:EAI_Analyse_Advies@@.
```

The tag identifies **what an entity is** and **which entity is meant**. The surrounding sentence expresses the relationship.

> **Status:** version `0.3.1` is a research baseline, not a production standard.

## Language

EAT Inline currently has two constructs.

### Reference

```text
@@EAT type:key@@
```

Examples:

```text
@@EAT person:Hans_Visser@@
@@EAT organisation:EAI_Analyse_Advies@@
@@EAT project:EAT_Inline@@
```

Identifiers use:

```text
[A-Za-z_][A-Za-z0-9_]*
```

### TLDR block

```text
@@EAT tldr:
EAT Inline adds explicit references to ordinary prose.
@@
```

The `tldr` block is the only content-level construct in the current language.

## Design rule

> **References identify entities. Natural language expresses relations.**

EAT Inline does not attempt to encode complete sentences as data structures. Parsing, validation and entity resolution remain separate operations.

## Automated verification

The repository includes four GitHub Actions workflows:

| Workflow | Purpose |
|---|---|
| `CI` | Runs unit tests on supported Python versions |
| `Conformance` | Tests the implementation against the versioned corpus |
| `Benchmark` | Runs a deterministic parser smoke benchmark and uploads results |
| `Docs` | Detects version drift, retired terminology and naming inconsistencies |

Run the same checks locally:

```bash
python -m pip install -e .
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/run_conformance.py
python scripts/run_benchmark.py
python scripts/check_docs.py
```

The benchmark is deliberately limited. Parser throughput alone does not prove improved retrieval, entity resolution or RAG quality. Those claims require controlled comparative experiments.

## Repository map

```text
.github/workflows/       GitHub Actions
benchmark/results/       generated benchmark artifacts
scripts/                 conformance, benchmark and documentation checks
src/eat_inline.py        minimal reference implementation
tests/                   unit tests and conformance corpus
pyproject.toml           package metadata
```

Planned research materials belong under:

```text
spec/                    normative language specification
benchmark/corpora/       comparative benchmark datasets
docs/                    readable project documentation
research/                protocols, reports and evidence
```

## Current scope

Version `0.3.1` establishes:

- reference and TLDR syntax;
- identifier rules;
- a minimal parser and validator;
- a versioned conformance corpus;
- automated GitHub Actions checks;
- a reproducible benchmark harness.

It does **not** yet establish:

- universal model compatibility;
- improved retrieval or RAG performance;
- production readiness;
- verified identity resolution from a syntactically valid key.

## Stewardship

EAT Inline is developed by **Hans Visser** under **EAI Analyse & Advies**.

## License

A license has not yet been selected. Until one is added, normal copyright restrictions apply.
