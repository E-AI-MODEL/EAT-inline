# EAT Inline Specification

Status: experimental candidate

Version: 0.3.2

## 1. Scope

EAT Inline is a minimal authoring notation for explicit, typed entity references inside host text formats such as Markdown, plain text, HTML source, prompts and generated documents.

The specification defines only the written reference form. Entity registries, resolution policies, canonical identifiers, confidence scores and storage records belong to consuming systems.

## 2. Normative language

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are to be interpreted as requirements for conforming implementations.

## 3. Core syntax

EAT Inline has exactly one core construct:

```text
@@EAT type:key@@
```

Both `type` and `key` MUST match:

```text
[A-Za-z_][A-Za-z0-9_]*
```

Equivalent ABNF:

```abnf
reference  = "@@EAT " identifier ":" identifier "@@"
identifier = (ALPHA / "_") *(ALPHA / DIGIT / "_")
```

A conforming parser MUST preserve the written `type`, `key`, raw source text and source offsets when those offsets are available.

## 4. Semantics

A reference communicates author-supplied intent:

```text
@@EAT person:Hans_Visser@@
```

The `type` identifies the entity class within the author's or application's vocabulary. The `key` identifies the intended entity within that class.

The syntax does not prescribe a global type registry. Implementations MUST accept every syntactically valid type unless they explicitly operate in a restricted application profile.

Natural language expresses relationships. EAT Inline does not define relation syntax, summary blocks, document sections or other host-document structure.

## 5. Resolution

A resolver MAY map a written reference to a canonical identifier:

```json
{
  "source_reference": "@@EAT person:Hans_Visser@@",
  "canonical_id": "person-10492",
  "resolution_status": "resolved"
}
```

Resolution metadata is not part of the inline syntax. A resolver SHOULD preserve the original source reference alongside any canonical identifier.

Resolvers MAY use application-specific statuses such as `resolved`, `unresolved`, `ambiguous` or `invalid`, but these values are not normative EAT Inline syntax.

## 6. Host-format behavior

EAT Inline references MAY appear anywhere the host format permits ordinary text.

A parser MUST NOT infer special document structure from surrounding Markdown headings, lists, paragraphs or code blocks. Host-format integrations MAY choose to ignore code spans or other protected regions, but such behavior MUST be documented as an integration profile rather than presented as core syntax.

## 7. Conformance

A parser conforms to this version when it:

1. recognizes every valid reference matching the grammar;
2. rejects malformed complete-reference candidates;
3. returns the exact written `type` and `key`;
4. does not require a predefined type vocabulary;
5. does not treat resolver state or canonical IDs as part of the inline grammar.

The versioned corpus in `benchmark/corpora/` provides executable examples. The corpus contains benchmark-specific vocabularies and is not itself a normative global registry.

## 8. Compatibility

Patch releases MUST NOT change the accepted core grammar.

Minor releases MAY add non-breaking APIs, schemas, integration guidance and optional profiles. A minor release MUST NOT reinterpret valid references from an earlier release.

A grammar change requires a major version and a migration document.

Unknown syntactically valid types MUST remain parseable across compatible releases.

## 9. Security and robustness

Consumers MUST treat `type` and `key` as untrusted input. They MUST NOT interpolate values directly into SQL, shell commands, file paths, URLs or executable code without appropriate validation and escaping.

Resolvers SHOULD apply explicit authorization rules before exposing records associated with canonical identifiers.

## 10. Non-goals

This specification does not define:

- a universal ontology;
- entity extraction from unannotated text;
- a mandatory database or resolver;
- confidence scoring;
- relationship syntax;
- retrieval or RAG algorithms;
- a claim of superiority over NER or language-model systems.
