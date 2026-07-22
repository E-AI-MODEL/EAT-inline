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

> **Status:** version `0.3.2` is an experimental candidate. It is usable for testing, but it is not a proven or frozen standard.

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

The core design rule is:

> **References identify entities. Natural language expresses relations.**

EAT Inline does not define special blocks for summaries or other document structure. Use the conventions of the host format, such as Markdown headings and paragraphs.

## Types

The syntax accepts any valid identifier as a type. The repository also includes a **benchmark-only vocabulary** for scoring experiments:

```text
person, organisation, location, document, project, event,
product, system, dataset, publication, website, method, concept
```

This list is not a normative registry. Domain-specific types remain possible.

## Writing format, not storage format

EAT Inline is primarily an authoring format. A resolver may map a written reference to an internal ID and store both:

```json
{
  "source_reference": "@@EAT person:Hans_Visser@@",
  "canonical_id": "person-10492",
  "resolution_status": "resolved"
}
```

The source reference records author intent. The canonical ID records the system's resolved entity. Resolution metadata belongs to the consuming system, not to the EAT Inline syntax.

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

## Seed gold corpus

The repository contains a synthetic, versioned seed dataset with **64 reviewed records** in Dutch and English:

| Task | Records | Purpose |
|---|---:|---|
| Syntax | 20 | Valid and invalid reference forms |
| Typing | 16 | Expected entity type and key |
| Resolution | 12 | Written references mapped to canonical IDs |
| Generation | 16 | Plain text paired with expected EAT Inline output |

The corpus lives in `benchmark/corpora/` and is validated automatically. It is a starting point for reproducible testing, not enough evidence for broad performance claims.

## Automated verification

The repository contains four GitHub Actions workflows:

| Workflow | Purpose |
|---|---|
| `CI` | Runs the unit tests on supported Python versions |
| `Conformance` | Checks the reference implementation against versioned examples |
| `Benchmark` | Validates the gold corpus and measures parser throughput and character overhead |
| `Docs` | Detects version drift and retired names or syntax |

Run the same checks locally:

```bash
python -m pip install -e .
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/run_conformance.py
python scripts/validate_dataset.py
python scripts/run_benchmark.py
python scripts/check_docs.py
```

Conformance protects compatibility between implementations. It does not make optional resolver architecture part of the language.

## Evidence boundary

Version `0.3.2` establishes:

- one compact reference syntax;
- a small Python reference parser;
- versioned examples and automated checks;
- a benchmark-only type vocabulary;
- a bilingual 64-record seed gold corpus;
- a reproducible parser and syntax-overhead benchmark.

It does not yet prove:

- acceptable writing friction in every context;
- improved retrieval, entity resolution or RAG results;
- universal model compatibility;
- production readiness.

Those claims require larger comparative datasets and experiments with people, models and real resolver systems.

## Repository map

```text
.github/workflows/       automated checks
benchmark/corpora/       versioned seed gold corpus
benchmark/results/       generated benchmark artifacts
scripts/                 verification and benchmark scripts
src/eat_inline.py        minimal reference implementation
tests/                   unit tests and conformance examples
pyproject.toml           package metadata
```

## Stewardship

EAT Inline is developed by **Hans Visser** under **EAI Analyse & Advies**.

## License

A license has not yet been selected. Until one is added, normal copyright restrictions apply.
