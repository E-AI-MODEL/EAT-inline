# EAT Inline

<p align="center">
  <strong>A minimal inline language for explicit, readable and machine-processable references.</strong>
</p>

<p align="center">
  <img alt="Repository version 0.3.1" src="https://img.shields.io/badge/repository-0.3.1-2f6f5e">
  <img alt="Specification version 0.3.1" src="https://img.shields.io/badge/specification-0.3.1-3178c6">
  <img alt="Status research baseline" src="https://img.shields.io/badge/status-research_baseline-c88719">
  <img alt="Format plain text" src="https://img.shields.io/badge/format-plain_text-6f42c1">
  <img alt="Author Hans Visser" src="https://img.shields.io/badge/author-Hans_Visser-555555">
  <img alt="Organisation EAI Analyse and Advies" src="https://img.shields.io/badge/organisation-EAI_Analyse_%26_Advies-8A2BE2">
</p>

<p align="center">
  <code>@@EAT type:key@@</code> identifies the entity. The surrounding sentence expresses the relationship.
</p>

EAT Inline adds compact semantic references to ordinary writing without turning the document into a full markup format.

```text
The report was written by @@EAT person:Hans_Visser@@
for @@EAT organisation:EAI_Analyse_Advies@@.
```

The reference states **what an entity is** and **which entity is meant**. The natural-language sentence still states what happened, who did it, and how the entities relate.

> [!IMPORTANT]
> **EAT Inline 0.3.1 is a research baseline, not a production standard.**
>
> The current work defines the syntax, type model, validation approach, benchmark framework and implementation direction. It does not yet establish universal retrieval improvement, universal model compatibility or production readiness.

> [!NOTE]
> EAT Inline deliberately supports very little syntax. The current language contains explicit references and one optional content block: `tldr`.

---

## Choose your route

| I want to... | Start here |
|---|---|
| Understand the idea without reading the specification | [The idea in plain language](#the-idea-in-plain-language) |
| See the complete language at a glance | [The two constructs](#the-two-constructs) |
| Understand why relations stay in natural language | [The central design rule](#the-central-design-rule) |
| See valid reference types | [Reference vocabulary](#reference-vocabulary) |
| Understand unknown or domain-specific types | [Open vocabulary, controlled validation](#open-vocabulary-controlled-validation) |
| Review the formal syntax | [Grammar](#grammar) |
| Build a parser | [Parser architecture](#parser-architecture) |
| Evaluate whether EAT Inline is useful | [Benchmark and reference framework](#benchmark-and-reference-framework) |
| See what has and has not been established | [Evidence and claim boundaries](#evidence-and-claim-boundaries) |
| Contribute to the project | [Contribution principles](#contribution-principles) |
| Understand the intended repository structure | [Repository map](#repository-map) |
| Check authorship and stewardship | [Project stewardship](#project-stewardship) |

---

# The idea in plain language

Ordinary prose is easy for people to write and read, but names can be ambiguous.

```text
Hans wrote the report for EAI Analyse & Advies.
```

A person can usually infer who or what is meant from context. Software may not be able to do that reliably. A name can refer to multiple people, organisations, projects, documents or systems.

EAT Inline makes selected references explicit:

```text
@@EAT person:Hans_Visser@@ wrote the report for
@@EAT organisation:EAI_Analyse_Advies@@.
```

This adds two pieces of information:

- the entity type;
- a stable, machine-readable key.

It does **not** attempt to encode the full sentence as a data structure.

That boundary is intentional. EAT Inline is designed to preserve natural writing while adding only the smallest useful semantic layer.

## The problem it tries to solve

Many systems currently choose between two extremes:

1. keep text natural, but leave identity and entity type implicit;
2. add rich markup or structured records, but make writing heavier and less readable.

EAT Inline investigates a middle position:

```text
natural writing + explicit references + minimal syntax
```

The project therefore asks a research question rather than assuming the answer:

> Can a small inline language improve identification, resolution, retrieval and machine processing without creating unacceptable writing friction?

---

# The two constructs

EAT Inline 0.3.1 contains only two language constructs.

## 1. Reference

```text
@@EAT type:key@@
```

Example:

```text
The research was prepared by @@EAT person:Hans_Visser@@.
```

A reference contains:

| Part | Meaning |
|---|---|
| `@@EAT` | opening marker and language identifier |
| `type` | semantic category of the entity |
| `:` | separator |
| `key` | machine-readable entity key |
| `@@` | closing marker |

## 2. TLDR block

```text
@@EAT tldr:
A short summary of the document or section.
@@
```

Example:

```text
@@EAT tldr:
EAT Inline adds explicit references to ordinary prose while leaving
relationships and claims in natural language.
@@
```

The `tldr` block is the only content-level tag in the current language.

It is not a general container system. It does not introduce arbitrary block types such as `warning`, `decision`, `definition`, `question` or `note`.

---

# The central design rule

EAT Inline separates **identity** from **relationship**.

```text
The report was written by @@EAT person:Hans_Visser@@.
```

The tag identifies the person. The phrase `was written by` expresses authorship.

This is preferred over embedding the relationship inside the reference:

```text
@@EAT author:person:Hans_Visser@@
```

The richer form appears more explicit, but it also creates several costs:

- more syntax to learn;
- more opportunities for disagreement about relation names;
- more validation rules;
- more pressure to model the full sentence;
- more friction during ordinary writing;
- stronger coupling between language design and ontology design.

The current rule is therefore:

> **References identify entities. Natural language expresses relations.**

This rule may be revised only if benchmarks show that the extra syntax produces a meaningful downstream benefit.

---

# What EAT Inline is

EAT Inline is:

- a compact inline reference language;
- readable as plain text;
- suitable for deterministic parsing;
- independent of a specific editor;
- compatible with surrounding natural language;
- designed for humans, parsers and language models;
- open to controlled domain-specific reference types;
- intended for empirical evaluation rather than assumption-driven expansion.

# What EAT Inline is not

EAT Inline is not:

- a complete document format;
- a replacement for Markdown, HTML, XML, JSON or RDF;
- a general-purpose markup language;
- a knowledge graph serialization format;
- a claim that a key has already been resolved to a verified identity;
- a mechanism that automatically proves the truth of surrounding text;
- a universal solution for retrieval or RAG;
- a production standard at version 0.3.1.

A syntactically valid reference may still be unresolved, ambiguous, outdated or incorrect. Parsing and resolution must remain separate operations.

---

# Reference vocabulary

The syntax is open:

```text
@@EAT type:key@@
```

The initial core vocabulary is intentionally broader than the content vocabulary.

## Core types

```text
person
organisation
location
document
project
event
concept
```

## Extended types

```text
product
system
dataset
publication
website
course
team
policy
law
method
```

Examples:

```text
@@EAT person:Hans_Visser@@
@@EAT organisation:EAI_Analyse_Advies@@
@@EAT project:EAT_Inline@@
@@EAT document:EAT_Inline_Research_Report_0_3_1@@
@@EAT method:Controlled_Experiment@@
```

## Domain-specific extensions

Implementations may encounter valid domain types such as:

```text
school_subject
lesson
student_group
research_method
medical_condition
archive_record
```

Example:

```text
@@EAT research_method:Controlled_Experiment@@
```

The language does not require every possible type to be defined in the core specification.

---

# Open vocabulary, controlled validation

EAT Inline separates syntax validity from registry status.

A parser may accept:

```text
@@EAT research_method:Controlled_Experiment@@
```

while a validator reports:

```text
warning: unknown or extension type: research_method
```

This distinction allows the language to remain extensible without making validation meaningless.

Recommended validation states:

| State | Meaning |
|---|---|
| `valid-core` | syntax is valid and the type is in the core registry |
| `valid-extended` | syntax is valid and the type is in the extended registry |
| `valid-extension` | syntax is valid but the type is domain-specific or unregistered |
| `invalid-syntax` | the reference cannot be parsed according to the grammar |
| `unresolved` | the reference is syntactically valid but no entity was found |
| `ambiguous` | multiple candidate entities remain |
| `resolved` | the key was linked to a canonical entity |

Unknown types should normally produce warnings, not parser failures.

---

# Keys and identifiers

The current baseline uses identifiers that begin with a letter or underscore and continue with letters, numbers or underscores.

```text
[A-Za-z_][A-Za-z0-9_]*
```

Valid examples:

```text
Hans_Visser
EAI_Analyse_Advies
EAT_Inline
Report_2026
_private_reference
```

Invalid examples:

```text
Hans Visser
2026_Report
EAI-Analyse-Advies
```

Snake case is preferred because it is readable, portable and easy to process.

Unicode identifiers are not part of the current baseline. They require explicit decisions about normalization, confusable characters and cross-platform comparison.

---

# Grammar

A compact representation of the current grammar is:

```abnf
eat-reference = "@@EAT " type ":" key "@@"

type          = identifier
key           = identifier

identifier    = ( ALPHA / "_" ) *( ALPHA / DIGIT / "_" )

eat-tldr      = "@@EAT tldr:" line-end
                *tldr-content
                "@@"
```

The normative grammar should live in:

```text
spec/GRAMMAR.abnf
```

The specification must define at least:

- whitespace rules;
- line-ending behaviour;
- offset calculation;
- handling of incomplete references;
- handling of nested markers;
- handling inside code blocks;
- maximum lengths;
- error codes;
- preservation of raw source text.

---

# Parser architecture

The recommended processing pipeline is:

```text
detect
  -> parse
  -> validate
  -> resolve
  -> store
```

These stages must not be collapsed into one opaque operation.

## Detect

Find candidate opening markers and possible TLDR blocks.

## Parse

Convert valid syntax into a structured representation.

Example:

```json
{
  "kind": "reference",
  "type": "person",
  "key": "Hans_Visser",
  "raw": "@@EAT person:Hans_Visser@@",
  "line": 1,
  "column": 28
}
```

## Validate

Check grammar, registry status, limits and conformance rules.

## Resolve

Attempt to map the key to a canonical entity in a local registry, database, API or knowledge system.

## Store

Preserve both the structured result and the original source text.

The raw tag should always remain available for auditability, reprocessing and migration.

---

# Error model

Errors should be precise, stable and machine-readable.

Recommended categories:

```text
E001 incomplete_opening_marker
E002 missing_type
E003 missing_separator
E004 missing_key
E005 invalid_identifier
E006 missing_closing_marker
E007 invalid_tldr_termination
E008 disallowed_nesting
W001 unknown_reference_type
W002 duplicate_tldr_block
W003 unresolved_reference
W004 ambiguous_reference
```

Example diagnostic:

```text
E005 invalid_identifier at line 12, column 28:
keys may contain only ASCII letters, digits and underscores,
and may not begin with a digit
```

A good implementation should return both human-readable messages and stable codes.

---

# Benchmark and reference framework

A parser test proves that the syntax can be implemented. It does not prove that the language is useful.

EAT Inline therefore requires a benchmark framework that compares it with realistic alternatives.

## Central evaluation question

> Does EAT Inline improve semantic processing and entity resolution enough to justify its writing cost?

## Comparison conditions

The initial benchmark should include at least these conditions.

### A. Plain text

```text
Hans Visser wrote the report for EAI Analyse & Advies.
```

### B. Markdown link

```text
[Hans Visser](https://example.org/person/hans-visser) wrote the report
for [EAI Analyse & Advies](https://example.org/organisation/eai-analyse-advies).
```

### C. HTML data attributes

```html
<span data-type="person" data-key="Hans_Visser">Hans Visser</span>
wrote the report for
<span data-type="organisation" data-key="EAI_Analyse_Advies">EAI Analyse & Advies</span>.
```

### D. JSON-like inline records

```text
{{type:person,key:Hans_Visser,label:"Hans Visser"}} wrote the report for
{{type:organisation,key:EAI_Analyse_Advies,label:"EAI Analyse & Advies"}}.
```

### E. EAT Inline

```text
@@EAT person:Hans_Visser@@ wrote the report for
@@EAT organisation:EAI_Analyse_Advies@@.
```

These conditions represent different positions on the spectrum between writing convenience and explicit structure.

## Benchmark levels

### Level A: parser conformance

Measures whether an implementation follows the specification.

- valid references;
- invalid references;
- multiline TLDR blocks;
- exact offsets;
- error codes;
- boundary cases;
- deterministic output.

### Level B: human and model usability

Measures whether people and language models can use the language reliably.

- writing time;
- syntax-error rate;
- correction rate;
- type-selection accuracy;
- missing-reference rate;
- over-tagging rate;
- perceived writing burden;
- reading speed;
- comprehension;
- model generation validity.

### Level C: downstream system value

Measures whether the language improves later processing.

- entity extraction precision and recall;
- type accuracy;
- key accuracy;
- resolution accuracy;
- ambiguity reduction;
- retrieval quality;
- chunk robustness;
- indexing quality;
- RAG answer quality;
- token overhead.

## TLDR benchmark

The TLDR block should be evaluated separately.

Compare:

1. no summary;
2. an unmarked summary paragraph;
3. an automatically generated summary;
4. a manually written EAT TLDR block.

Measure:

- faithfulness to the document;
- usefulness for retrieval;
- preview quality;
- update drift;
- model selection accuracy;
- token cost.

## Gold corpus

Every benchmark item should have a reviewed expected result.

```json
{
  "document_id": "ambiguous-001",
  "references": [
    {
      "type": "person",
      "key": "Hans_Visser",
      "canonical_id": "person-0001"
    },
    {
      "type": "organisation",
      "key": "EAI_Analyse_Advies",
      "canonical_id": "organisation-0001"
    }
  ]
}
```

Without a gold set, claims about extraction, resolution or retrieval cannot be evaluated reliably.

---

# Evidence and claim boundaries

The repository should connect every major claim to an evidence level.

| Claim | Required evidence |
|---|---|
| The syntax can be parsed deterministically | conformance tests |
| The delimiters rarely collide with ordinary text | corpus analysis |
| People can write the syntax reliably | controlled usability study |
| Language models can generate valid references | multi-model generation benchmark |
| References improve entity resolution | controlled resolution benchmark |
| TLDR improves retrieval | retrieval benchmark with a gold set |
| EAT Inline improves RAG outcomes | end-to-end RAG evaluation |
| EAT Inline is production-ready | operational testing, security review and independent validation |

## What version 0.3.1 establishes

Version 0.3.1 establishes a coherent research baseline:

- a minimal language model;
- a reference syntax;
- a TLDR block;
- a proposed type registry;
- identifier rules;
- parser and validation architecture;
- a benchmark framework;
- explicit claim boundaries.

## What version 0.3.1 does not establish

Version 0.3.1 does not yet establish:

- universal improvement over plain text;
- universal model compatibility;
- stable production interoperability;
- a complete resolver standard;
- a final type ontology;
- a final Unicode policy;
- a final escaping model;
- production security or performance guarantees.

Negative findings should remain in the repository. A benchmark that shows no improvement is still useful evidence.

---

# Semantic density and writing friction

The project treats semantic density as an empirical design problem.

Minimal form:

```text
@@EAT person:Hans_Visser@@
```

Richer form:

```text
@@EAT author:person:Hans_Visser@@
```

The richer form encodes more information but may also create:

- slower writing;
- more syntax errors;
- larger type and relation vocabularies;
- lower agreement between writers;
- greater token overhead;
- stronger coupling to a domain model.

The repository should therefore compare at least three authoring conditions:

```text
condition-a-minimal
condition-b-enriched
condition-c-intensive
```

The language should grow only when measured benefits outweigh the additional cost.

---

# Security and trust boundaries

EAT Inline references are data, not instructions.

Implementations should:

- treat keys and types as untrusted input;
- enforce length limits;
- avoid executing resolved content;
- preserve source offsets;
- escape output appropriately for the target format;
- distinguish parser success from resolver trust;
- log resolution decisions;
- prevent silent replacement of unresolved references;
- avoid assuming that a reference proves the surrounding claim.

Example:

```text
@@EAT person:Hans_Visser@@ approved the deployment.
```

A parser can identify the reference. It cannot prove that the approval occurred.

---

# Interoperability principles

EAT Inline should remain usable inside ordinary text containers.

Target environments include:

- Markdown documents;
- plain-text notes;
- prompts;
- documentation;
- email bodies;
- issue descriptions;
- source comments;
- knowledge-base exports;
- retrieval corpora.

Interoperability does not mean that every host format must interpret the tags. A host may treat them as ordinary text while an EAT-aware processor extracts the semantic layer.

Recommended parser output should be serializable to JSON without losing:

- raw source;
- type;
- key;
- location;
- validation state;
- resolution state;
- diagnostics.

---

# Proposed command-line interface

The reference implementation should eventually support commands such as:

```bash
eat-inline check document.md
eat-inline extract document.md
eat-inline validate document.md --registry spec/type-registry.json
eat-inline benchmark benchmark/manifest.json
```

Example extraction output:

```json
{
  "version": "0.3.1",
  "references": [
    {
      "type": "person",
      "key": "Hans_Visser",
      "raw": "@@EAT person:Hans_Visser@@",
      "line": 1,
      "column": 28,
      "registry_status": "valid-core",
      "resolution_status": "unresolved"
    }
  ],
  "tldr": null,
  "errors": [],
  "warnings": []
}
```

These commands describe the intended interface. They should not be presented as available until the implementation exists and CI verifies them.

---

# Repository map

The intended repository structure is:

```text
EAT-inline/
âââ README.md
âââ CHANGELOG.md
âââ CONTRIBUTING.md
âââ CODE_OF_CONDUCT.md
âââ SECURITY.md
âââ LICENSE
â
âââ spec/
â   âââ SPECIFICATION.md
â   âââ GRAMMAR.abnf
â   âââ TYPE-REGISTRY.md
â   âââ TLDR.md
â   âââ ERROR-MODEL.md
â   âââ VERSIONING.md
â
âââ docs/
â   âââ quickstart.md
â   âââ writing-guide.md
â   âââ design-rationale.md
â   âââ interoperability.md
â   âââ claim-boundaries.md
â   âââ research/
â
âââ examples/
â   âââ minimal/
â   âââ documents/
â   âââ multilingual/
â   âââ invalid/
â
âââ src/
â   âââ eat_inline/
â
âââ tests/
â   âââ conformance/
â   âââ valid/
â   âââ invalid/
â   âââ regression/
â   âââ fixtures/
â
âââ benchmark/
â   âââ README.md
â   âââ manifest.json
â   âââ corpora/
â   âââ conditions/
â   âââ expected/
â   âââ scripts/
â   âââ results/
â
âââ schemas/
â   âââ type-registry.schema.json
â
âââ .github/
    âââ workflows/
    âââ ISSUE_TEMPLATE/
    âââ pull_request_template.md
```

## Repository authority

The repository should make authority explicit:

| Location | Status |
|---|---|
| `spec/` | normative language definition |
| `src/` | reference implementation |
| `tests/conformance/` | executable conformance expectations |
| `benchmark/expected/` | reviewed benchmark ground truth |
| `benchmark/results/` | generated research results |
| `docs/` | explanatory material |
| `examples/` | non-normative usage examples unless explicitly marked |
| `archive/` | historical material with no current normative authority |

This prevents an old example, benchmark fixture or research note from silently becoming part of the specification.

---

# Versioning

The project begins at version `0.3.1` because the repository follows the existing research and specification line.

```text
0.3.1  current research baseline and editorial correction
0.3.x  compatible corrections, fixtures and implementation fixes
0.4.0  measured, backward-compatible language or benchmark development
1.0.0  stable public specification with defined compatibility commitments
```

During the `0.x` phase, changes may still occur. Every grammar change must be documented in the changelog and accompanied by updated conformance tests.

A release should report versions separately where necessary:

```text
specification version
reference implementation version
benchmark dataset version
repository release version
```

They may initially move together, but the repository should not assume they will always remain identical.

---

# Roadmap

## 0.3.1 â research baseline

- publish the current specification;
- publish the type registry;
- publish the benchmark protocol;
- define conformance cases;
- document claim boundaries;
- provide valid and invalid examples.

## 0.3.x â implementation and correction cycle

- implement parser and validator;
- add stable error codes;
- add CLI output;
- add automated tests;
- add CI;
- expand the gold corpus;
- record negative and unexpected results.

## 0.4.0 â evidence-led revision

- evaluate semantic density;
- test human authoring burden;
- benchmark multiple language models;
- test resolution and retrieval;
- evaluate TLDR usefulness;
- revise the registry and grammar only where evidence supports a change.

## Toward 1.0

A stable release requires at least:

- a frozen grammar;
- defined compatibility rules;
- independent parser implementations or review;
- a versioned conformance suite;
- a versioned benchmark corpus;
- documented security considerations;
- explicit production limitations;
- evidence that the language provides value beyond its syntax cost.

---

# Contribution principles

Contributions should follow five rules.

## 1. Keep the language small

A new tag or field needs evidence that natural language plus an existing reference cannot handle the use case adequately.

## 2. Separate proposals from specification

New ideas belong in issues, design notes or experimental branches until accepted.

## 3. Add tests with every syntax change

A grammar change without conformance cases is incomplete.

## 4. Preserve negative results

Benchmarks that fail to show an advantage must remain visible.

## 5. State evidence levels precisely

Do not describe a prototype result as production proof.

A contribution template should ask:

```text
What problem does this solve?
Why is natural language insufficient here?
What additional writing cost does it introduce?
How can the benefit be measured?
Which existing examples become invalid?
Which conformance tests are required?
```

---

# Project stewardship

EAT Inline is developed by:

**Hans Visser**  
**EAI Analyse & Advies**

The project combines language design, parser engineering and empirical evaluation. Authorship does not replace independent review. The repository should be trusted only to the extent that its specification, tests, benchmarks and limitations can be inspected.

Recommended citation:

```text
Visser, Hans. EAT Inline, version 0.3.1.
EAI Analyse & Advies.
```

---

# Rights and licensing position

The final repository must include an explicit `LICENSE` file before reuse terms are assumed.

Until a license is selected and published:

> Public visibility does not by itself grant permission to copy, modify, redistribute or incorporate the work into another product.

The README badge and this section should be updated immediately when the licensing position is decided.

---

# One-page summary

EAT Inline adds two constructs to ordinary text:

```text
@@EAT type:key@@
```

and:

```text
@@EAT tldr:
...
@@
```

Its design principles are:

1. identify entities explicitly;
2. keep relationships in natural language;
3. separate parsing from validation and resolution;
4. allow controlled vocabulary extension;
5. preserve raw source text;
6. benchmark usefulness against realistic alternatives;
7. grow the language only when evidence justifies the added complexity.

The core research question remains open:

> Is this small amount of syntax enough to produce a meaningful gain in semantic reliability without making writing unnecessarily difficult?
