# 100,000-document one-tag RAG retrieval benchmark

## What ran

- 100,000 generated workload documents
- 669 annotated passage prototypes from 40 Wikipedia pages
- 100,000 EAT references: exactly one per document
- 434 entity questions
- ordinary lexical, EAT-filtered and hybrid retrieval
- a deterministic answer step that returns the selected source-page title

The question asks which source page mentions a registry label. The ordinary route searches that label as plain text. The EAT routes receive the correct canonical entity ID directly. That makes this an oracle test of the retrieval layer, not a query-linking or LLM test.

![Retrieval quality](retrieval-quality.svg)

## Retrieval and source-answer quality

| Route | Source answer exact match | Hit@1 | Hit@10 | MRR@10 |
|---|---:|---:|---:|---:|
| Ordinary lexical | 0.7742 | 0.7742 | 0.8272 | 0.7888 |
| EAT filtered | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Hybrid | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

A hit means that the requested entity has a known annotation inside the retrieved passage. Source-answer exact match also requires that the top passage provides that evidence before its page title counts as a correct answer.

## Query time

| Route | p50 | p95 | p99 |
|---|---:|---:|---:|
| Ordinary lexical | 523.169 µs | 18220.464 µs | 29334.083 µs |
| EAT filtered | 90.404 µs | 319.425 µs | 573.624 µs |
| Hybrid | 692.586 µs | 19038.451 µs | 30634.05 µs |

![Retrieval latency](retrieval-latency.svg)

Timings depend on the machine. CI checks the complete workload, exact tag count and recorded quality invariants, not a fixed speed limit.

## Boundary

This is the retrieval and source-selection part of a RAG pipeline. It does not run embeddings, a vector database or a language model. The 100,000 documents repeat 669 passages from 40 source pages, so they are not 100,000 different source documents.
