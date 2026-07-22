# Governance

EAT Inline is currently maintained by Hans Visser under EAI Analyse & Advies.

## Principles

- Keep the core syntax minimal.
- Prefer evidence over feature count.
- Separate authoring syntax from storage and resolver behavior.
- Preserve backward compatibility for valid references.
- Document limitations and avoid unsupported superiority claims.

## Change process

Changes should be proposed through a GitHub issue or pull request.

A proposal that affects the core grammar must include:

1. the user problem being solved;
2. examples and counterexamples;
3. compatibility and migration impact;
4. parser and conformance changes;
5. evidence that the benefit cannot be achieved in an optional profile, registry or resolver layer.

Core grammar changes require a major version. Minor releases may add compatible APIs, schemas, documentation, benchmarks and optional integration profiles.

## Decision making

The maintainer makes final release decisions after public review. Significant changes should remain open long enough for technical feedback and must pass all automated checks.

The maintainer may reject changes that add syntax without measured value, couple the notation to one vendor, or move application-specific resolver state into the core grammar.

## Contributions

Contributions are accepted under the Apache License 2.0 unless explicitly marked otherwise before submission.

Pull requests should be focused, tested and traceable to an issue or clearly stated problem. Benchmark changes must preserve paired conditions and make their evidence boundary explicit.

## Security

Security-sensitive reports should avoid publishing exploit details before a fix is available. Until a dedicated private reporting channel is added, contact `info@eai-advies.nl` with the subject `EAT Inline security`.

## Stewardship evolution

When multiple independent implementations or regular external contributors exist, the project should revisit this governance model and consider a multi-maintainer or technical-steering structure.
