# Search Architecture

Smart Search uses a multi-stage retrieval pipeline that combines lexical matching, dense vector similarity, cross-encoder reranking, and diversity selection. Each stage is independently configurable and adds no resources when disabled.

## Pipeline Overview

```
Query
  |
  v
[Query Preprocessor] ── stopword removal (FTS5), whitespace normalization (embedding)
  |                |
  v                v
[FTS5 BM25]    [Vector Search]
  |                |
  v                v
  └──── [RRF Fusion (k=60)] ────┘
              |
              v
     [Cross-Encoder Reranker] ── TinyBERT-L-2, ~30-60ms on CPU
              |
              v
     [MMR Diversity Selection] ── lambda=0.8, <1ms
              |
              v
         Final Results
```

## Stage Details

### 1. Query Preprocessing

Splits the query into two paths optimized for each retrieval method:

- **FTS5 path**: Removes common English stopwords ("what", "is", "the", etc.) to sharpen BM25 scoring. Detects user-supplied quoted phrases for exact matching. Multi-term queries are OR-joined by default for broader recall.
- **Embedding path**: Light cleanup only (whitespace normalization). Stopwords carry semantic meaning for dense retrieval and are preserved.

**Module**: `query_preprocessor.py`
**Config**: None (always active)

### 2. Dual Retrieval

Two independent retrieval methods run in parallel, each over-fetching 5x the requested limit to ensure the fusion stage has enough candidates:

#### Vector Search (Semantic)

Dense retrieval using snowflake-arctic-embed-m-v2.0 embeddings (256-dim, int8 ONNX). Queries and documents are encoded independently by the bi-encoder, then compared via cosine similarity in LanceDB.

**Module**: `embedder.py`, `store.py`
**Distance metric**: Cosine similarity (1 - distance)
**Model**: snowflake-arctic-embed-m-v2.0 (137M params, 297MB)

#### Keyword Search (BM25)

Lexical retrieval using SQLite FTS5 with porter stemming. BM25 ranks documents by term frequency, inverse document frequency, and document length normalization. Particularly effective for exact-match queries, proper nouns, and technical terms that may not be well-represented in the embedding space.

**Module**: `fts.py`
**Tokenizer**: Porter stemming + Unicode61
**Score range**: BM25 scores negated and normalized (higher = more relevant)

### 3. Reciprocal Rank Fusion (RRF)

Merges the two ranked lists into a single ranking. RRF is a rank-based fusion method that does not require score calibration between systems:

```
RRF_score(d) = sum over lists L: 1 / (k + rank_L(d))
```

Documents appearing in both lists receive scores from both, naturally boosting consensus results. The constant k=60 (from the original RRF paper) controls how much top-ranked results are favored.

**Module**: `fusion.py`
**Config**: `rrf_k` (default: 60)

### 4. Cross-Encoder Reranking

The highest-impact quality improvement. After fusion produces a candidate set, each (query, document) pair is scored jointly by a cross-encoder that sees both texts together -- unlike the bi-encoder which encodes them independently.

Cross-encoders attend across the query-document boundary, catching subtle relevance signals that independent embeddings miss. The trade-off is speed: cross-encoders are ~100x slower than bi-encoders per document, making them impractical for first-stage retrieval but ideal for reranking a small candidate set.

**Module**: `reranker.py`
**Model**: cross-encoder/ms-marco-TinyBERT-L-2-v2 (14M params, ~15MB ONNX)
**Latency**: ~30-60ms for top-20 reranking on CPU
**Memory**: ~50MB when loaded, lazy-loads on first search, auto-unloads after 60s idle
**Config**: `reranking_enabled` (default: true), `reranker_model`, `reranker_idle_timeout`, `rerank_top_n`

### 5. MMR Diversity Selection

Maximum Marginal Relevance eliminates redundant results by penalizing candidates that are too similar to already-selected results:

```
MMR(d) = lambda * relevance(d) - (1 - lambda) * max_sim(d, selected)
```

Greedy selection iteratively picks the candidate with the highest MMR score. With lambda=0.8, relevance dominates (80% weight) but near-duplicate chunks from the same document are pushed down in favor of diverse information.

This is particularly important for LLM consumption: 10 diverse chunks from 8 documents provide far more context than 10 overlapping chunks from 2 documents.

**Module**: `mmr.py`
**Config**: `mmr_enabled` (default: true), `mmr_lambda` (default: 0.8)
**Latency**: <1ms (190 cosine ops on 256-dim vectors for top-20)

## Resource Budget

| Component | RAM (loaded) | RAM (idle) | Latency | On Disk |
|-----------|-------------|------------|---------|---------|
| Embedder (snowflake) | ~400MB | 0 (unloads) | ~50ms/query | 297MB |
| Reranker (TinyBERT) | ~50MB | 0 (unloads) | ~30-60ms/20 pairs | ~15MB |
| FTS5 index | Shared with SQLite | ~5MB | <5ms | Proportional to corpus |
| LanceDB vectors | Memory-mapped | ~10MB | <10ms | Proportional to corpus |
| MMR computation | Negligible | 0 | <1ms | 0 |

**Steady-state idle**: ~200MB (all models unloaded)
**During search**: ~650MB peak (both models loaded), returns to idle after 60s

## Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `search_default_mode` | `hybrid` | Default search mode (semantic/keyword/hybrid) |
| `search_default_limit` | `10` | Default number of results |
| `relevance_threshold` | `0.30` | Minimum score for semantic-only mode |
| `rrf_k` | `60` | RRF constant (lower = more weight to top ranks) |
| `reranking_enabled` | `true` | Enable cross-encoder reranking |
| `reranker_model` | `cross-encoder/ms-marco-TinyBERT-L-2-v2` | Cross-encoder model |
| `reranker_idle_timeout` | `60.0` | Seconds before reranker unloads from memory |
| `rerank_top_n` | `20` | Number of fusion results to rerank |
| `mmr_enabled` | `true` | Enable MMR diversity selection |
| `mmr_lambda` | `0.8` | Relevance vs diversity trade-off (0-1) |

## References

1. Cormack, G.V., Clarke, C.L.A., & Buettcher, S. (2009). [Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods](https://dl.acm.org/doi/10.1145/1571941.1572114). *SIGIR '09*.

2. Nogueira, R. & Cho, K. (2019). [Passage Re-ranking with BERT](https://arxiv.org/abs/1901.04085). *arXiv:1901.04085*.

3. Thakur, N., Reimers, N., Ruckle, A., Srivastava, A., & Gurevych, I. (2021). [BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models](https://arxiv.org/abs/2104.08663). *NeurIPS 2021 Datasets and Benchmarks Track*.

4. Carbonell, J. & Goldstein, J. (1998). [The Use of MMR, Diversity-Based Reranking for Reordering Documents and Producing Summaries](https://dl.acm.org/doi/10.1145/290941.291025). *SIGIR '98*.

5. Robertson, S. & Zaragoza, H. (2009). [The Probabilistic Relevance Framework: BM25 and Beyond](https://dl.acm.org/doi/10.1561/1500000019). *Foundations and Trends in Information Retrieval*.
