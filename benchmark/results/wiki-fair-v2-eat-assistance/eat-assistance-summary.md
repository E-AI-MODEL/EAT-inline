# Wiki-Fair oracle EAT-assistance benchmark

- Model: `scikit-learn TF-IDF character n-gram entity retriever`
- Version: `scikit-learn==1.8.0;eat-profile-v1`
- Dataset: `wiki-fair-v2/test-no-coref@c9a3fe9c4933888d756d702fdb9ff607fc36aa26`
- Test articles: `40`
- Oracle mention annotations: `669`

| Condition | EAT mentions | Precision | Recall | F1 | Exact match |
|---|---:|---:|---:|---:|---:|
| Model + EAT (0%) | `0` | `0.7247` | `0.6937` | `0.7089` | `0.125` |
| Model + EAT (25%) | `167` | `0.7472` | `0.7523` | `0.7497` | `0.15` |
| Model + EAT (50%) | `335` | `0.7819` | `0.8559` | `0.8172` | `0.225` |
| Model + EAT (75%) | `502` | `0.8027` | `0.9257` | `0.8598` | `0.275` |
| Model + EAT (100%) | `669` | `0.8253` | `1.0` | `0.9043` | `0.525` |
| EAT-only oracle | `669` | `1.0` | `1.0` | `1.0` | `1.0` |

> EAT references are generated from test gold labels. This measures the upper-bound effect of correct explicit identity, not whether people can create those references accurately or efficiently.
