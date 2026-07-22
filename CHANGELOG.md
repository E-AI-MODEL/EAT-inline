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
