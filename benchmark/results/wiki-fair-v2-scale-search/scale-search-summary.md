# 100,000-document EAT scale-search benchmark

## What ran

- 100,000 generated workload documents
- 40 different Wikipedia source pages
- 1,672,500 parsed EAT references
- 1,110,000 document-entity pairs
- 434 different entities queried

Inline EAT adds 16,842,500 bytes to the plain-text workload. The 32-bit postings payload is 4,440,000 bytes, excluding Python container overhead.

Every workload document has a distinct integer ID. The source text repeats, so this is a scale and overhead test, not a 100,000-different-source-document test.

![Scale workload](scale-overview.svg)

## Indexing

| Input representation | Build time | Documents/second |
|---|---:|---:|
| Correct IDs as separate metadata | 0.050861 s | n/a |
| IDs parsed from full inline EAT | 2.328733 s | 42,941.8 |

## Entity lookup after indexing

This first table measures only finding the existing postings list.

| Index source | p50 | p95 | p99 | Operations/second |
|---|---:|---:|---:|---:|
| Separate metadata | 0.1924 µs | 0.1984 µs | 0.3094 µs | 5,123,074.0 |
| Inline EAT | 0.189 µs | 0.1948 µs | 0.2937 µs | 5,225,723.53 |

This second table includes reading every matching document ID.

| Index source | p50 | p95 | p99 | Document IDs read/second |
|---|---:|---:|---:|---:|
| Separate metadata | 30.496 µs | 36.524 µs | 61.001 µs | 80,405,354.54 |
| Inline EAT | 30.485 µs | 36.425 µs | 60.951 µs | 80,491,915.25 |

![Entity search latency](search-latency.svg)

Both routes produce an identical entity-to-document index. Search means looking up one canonical entity ID and returning matching document IDs. It is not keyword, full-text or vector search.
