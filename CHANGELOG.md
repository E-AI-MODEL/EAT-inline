# Changelog

All notable changes to EAT Inline are documented here.

The project follows semantic versioning for the reference implementation and specification. The current release remains an experimental candidate.

## Unreleased

### Added

- Apache License 2.0.
- Normative `SPEC.md` for the single-reference grammar and compatibility rules.
- Storage-neutral JSON Schema for registry entries.
- Public governance and contribution policy.
- Baseline adapter framework (`eat_baselines`) with a stable `BaselineAdapter`
  interface, deterministic cost accounting, and the plain-text and EAT Inline
  conditions refactored behind it. Model-based conditions implement the same
  interface as a documented plug-in point and are not bundled, to keep the
  benchmark reproducible.
- `EntityLinker` contract and `LinkerAdapter` bridge, plus an offline
  deterministic `GazetteerLinker` that places its own references from plain
  text (whole-label detection, longest-overlap selection, context-cue
  disambiguation and conservative abstention). Adds a no-tag `linker` condition
  to the comparative benchmark. Real model linkers plug into the same interface
  without being bundled.
- Versioned recorded model-linker run schema, strict provenance and leakage
  validation, and a replay command that scores external per-case predictions
  with the same metrics as the built-in benchmark. Recorded runs accept only
  `plain_text`, require exact dataset and registry hashes, and reject gold or
  EAT fields.
- Reproducible TF-IDF entity-retrieval run on the independent Wiki-Fair v2
  no-coreference dev/test split, including pinned source data, a closed
  Wikidata candidate registry, complete recorded predictions, shared scoring
  and CI reproduction.
- Controlled oracle EAT-assistance curve over the same frozen Wiki-Fair model
  run. Gold-derived EAT references override overlapping model predictions at
  0%, 25%, 50%, 75% and 100% mention coverage, with an EAT-only upper bound
  and explicit non-human-annotation limitations.
- Clear public-test scope reporting, coverage and performance charts, and a
  shorter README with the detailed benchmark method moved to `BENCHMARKS.md`.
- A machine-recorded 100,000-document scale-search workload with full EAT
  coverage, identical metadata-control and EAT-derived indexes, index-build
  throughput, entity-search latency, checksums, charts and CI execution.
- A separate 100,000-document RAG retrieval workload with exactly one EAT
  reference per document, 434 source-page questions, ordinary lexical,
  inferred-EAT, oracle EAT-filtered and hybrid routes, grounded source-answer
  scoring, charts and full CI execution. The inferred route resolves 427 exact
  registry labels without the answer ID, abstains on seven ambiguous questions
  and raises grounded source answers from 336 to 429 out of 434.
- Two SVG document examples showing the same source text with and without EAT,
  plus a README order that introduces the format before the benchmark details.
- A complete README description of all five tasks in the 76-record synthetic
  corpus: syntax, typing, resolution, generation and controlled comparison.
- A shorter reader-first README with a problem-and-solution explanation,
  headline benchmark results in plain language, and an honest comparison with
  Markdown links, HTML data attributes, XML elements and hashtags.

### Policy

- Patch releases do not change the accepted core grammar.
- Minor releases may add backward-compatible APIs, schemas, benchmarks and optional profiles.
- Grammar changes require a major version and migration guidance.

## 0.3.2

### Added

- Single `@@EAT type:key@@` core construct.
- Minimal Python reference parser.
- Versioned conformance and benchmark corpora.
- Paired deterministic plain-text versus EAT Inline benchmark.
- Validation for canonical IDs, generation gold references, label multiplicity and surplus plain-text mentions.

### Evidence boundary

The included benchmark is synthetic seed evidence. It does not establish real-world superiority over NER, language-model or production resolver baselines.
