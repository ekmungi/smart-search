# IR Research Findings (2023-2026): Improving Retrieval Quality on CPU

Research compiled March 2026.

---

## 1. Highest-Impact Techniques for CPU-Only Semantic Search (Top-10 Quality)

### Hybrid Search (BM25 + Dense Embeddings)
Combining sparse keyword search (BM25) with dense vector retrieval consistently delivers **15-30% precision improvements** across enterprise deployments. This is the single highest-impact technique available today and works entirely on CPU.

### Re-ranking with Cross-Encoders
Neural re-ranking improves MAP from 0.523 to **0.797 (52% relative improvement)** per the LiveRAG Challenge 2025. However, latency increases significantly (1.74s to 84s per query with full models). Lightweight cross-encoders or ColBERT-style late interaction (see section 5) offer a better latency tradeoff.

### Contextual Retrieval (see section 2)
One-time preprocessing that yields 35-67% reduction in retrieval failure rate.

### Query Expansion (see section 4)
Classic PRF techniques like RM3/Bo1 improve recall without any LLM dependency.

### Key Architectural Pattern
The consensus pattern from 2024-2025 research: **Hybrid retrieval (BM25 + embeddings) → RRF fusion → Cross-encoder or ColBERT re-ranking**. Each stage is CPU-compatible.

**Sources:**
- [Searching for Best Practices in RAG (EMNLP 2024)](https://aclanthology.org/2024.emnlp-main.981.pdf)
- [Advanced RAG Techniques: Hybrid Search and Re-ranking](https://dasroot.net/posts/2025/12/advanced-rag-techniques-hybrid-search/)
- [RAG Retrieval Performance Enhancement: Hybrid Retrieval](https://dev.to/jamesli/rag-retrieval-performance-enhancement-practices-detailed-explanation-of-hybrid-retrieval-and-self-query-techniques-59ja)
- [Building Contextual RAG Systems with Hybrid Search and Reranking](https://www.analyticsvidhya.com/blog/2024/12/contextual-rag-systems-with-hybrid-search-and-reranking/)

---

## 2. Anthropic's Contextual Retrieval

### What They Prepend
For each chunk, both the chunk and its **full source document** are passed to Claude, which generates a **concise 50-100 token explanation** of what the chunk contains and where it fits in the overall document. This context text is prepended to the chunk before embedding AND before creating the BM25 index.

### Example Prompt (from Anthropic's blog)
The model is asked to "give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk."

### Concrete Improvement Numbers
| Configuration | Top-20 Retrieval Failure Rate | Reduction |
|---|---|---|
| Baseline (standard chunking) | 5.7% | — |
| + Contextual Embeddings | 3.7% | **35% reduction** |
| + Contextual Embeddings + Contextual BM25 | 2.9% | **49% reduction** |
| + All above + Reranking | ~1.9% | **67% reduction** |

In a codebase evaluation, Pass@10 improved from ~87% to ~95%.

### Cost
One-time ingestion cost: **$1.02 per million document tokens** (assuming 800-token chunks, 8k-token documents, 50-token instructions, 100-token context output). No query-time cost — context is baked into the index.

### Practical Notes
- Benefits stack with other techniques (hybrid search, reranking).
- Works across all embedding models tested; Voyage and Gemini embeddings benefited most.
- For knowledge bases <200k tokens (~500 pages), Anthropic recommends skipping retrieval entirely and stuffing the full context into the prompt.

**Sources:**
- [Anthropic: Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- [Together AI: How To Implement Contextual RAG](https://docs.together.ai/docs/how-to-implement-contextual-rag-from-anthropic)
- [DataCamp: Anthropic's Contextual Retrieval Guide](https://www.datacamp.com/tutorial/contextual-retrieval-anthropic)
- [Claude Platform Cookbook: Contextual Embeddings](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide)

---

## 3. Late Chunking & Sentence Window Retrieval

### Late Chunking (Jina AI, September 2024)
**Key idea:** Invert the traditional order — embed the entire document first through a long-context embedding model, THEN chunk the token-level embeddings and apply mean pooling per chunk.

**How it works:**
1. Pass entire document through embedding model to get per-token embeddings
2. Apply chunk boundaries to split the token embeddings
3. Mean-pool each chunk's token embeddings into a single vector

**Results:** Average **3.63% relative improvement** across 3 models and 4 datasets. Improvement scales with document length.

**Requirement:** The embedding model must use mean pooling (not CLS pooling) for its final output.

**Advantage over Contextual Retrieval:** No LLM call needed at ingestion — purely leverages the embedding model's existing long-context capabilities. Computationally much cheaper.

**Available in:** jina-embeddings-v3 API.

### Sentence Window Retrieval
- Index individual sentences, but store surrounding sentences (a "window") in metadata
- At query time, retrieve the best-matching sentence, then expand to include N surrounding sentences
- Provides precision of sentence-level matching with broader context for generation

### Parent Document Retrieval (Small-to-Large)
- Index small child chunks for precise matching
- Maintain links to larger parent chunks (paragraphs, sections)
- At retrieval time, return the parent chunk instead of the child
- Hierarchical: can navigate up/down the document tree

### Comparison

| Aspect | Standard Chunking | Sentence Window | Parent Document | Late Chunking |
|---|---|---|---|---|
| Index unit | Fixed chunks | Individual sentences | Small child chunks | Full-document token embeddings, chunked post-hoc |
| Retrieved unit | Same chunk | Expanded window | Larger parent chunk | Chunk (with document context baked in) |
| Extra storage | None | Window metadata | Parent-child links | None (same vectors) |
| LLM needed | No | No | No | No |

**Practical default:** Chunk size 256-512 tokens, overlap 10-20%.

**Sources:**
- [Late Chunking paper (arXiv:2409.04701)](https://arxiv.org/abs/2409.04701)
- [Jina AI: Late Chunking in Long-Context Embedding Models](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)
- [Weaviate: Late Chunking](https://weaviate.io/blog/late-chunking)
- [Evaluating Advanced Chunking Strategies (arXiv:2504.19754)](https://arxiv.org/abs/2504.19754)
- [Vectara: RAG Done Right - Chunking](https://www.vectara.com/blog/grounded-generation-done-right-chunking)
- [PIXION: RAG Strategies - Context Enrichment](https://pixion.co/blog/rag-strategies-context-enrichment)

---

## 4. Query Expansion Without LLM Dependency

### Classic Pseudo-Relevance Feedback (PRF)
**How it works:** Perform initial retrieval → assume top-N documents are relevant → extract expansion terms from those documents → re-query with expanded terms.

**Key methods (no LLM required):**
- **RM3:** Relevance Model 3 — probabilistic term selection from top-k docs. Widely used baseline.
- **Bo1:** Bose-Einstein divergence from randomness model for term weighting.
- **Rocchio:** Classic vector-space feedback that adjusts the query vector toward relevant documents and away from non-relevant ones.

### Knowledge-Base Query Expansion (No LLM)
- **SPRF model:** Uses ConceptNet to provide semantic information between terms, integrating it into PRF framework for better expansion term selection.
- **WKQE:** Uses tf-idf, k-nearest neighbor cosine similarity, and correlation scoring to weight expansion terms from web knowledge.

### PRF for Dense Retrieval (2025)
A March 2025 paper ("Pseudo Relevance Feedback is Enough to Close the Gap Between Small and Large Dense Retrieval Models") showed that PRF can make **small dense retrievers match the performance of much larger models**, entirely without LLM generation.

### HyDE Alternatives (No LLM at Query Time)
- **ReDE-RF (October 2024):** Replaces HyDE's hypothetical document generation with relevance feedback on real documents. Uses precomputed embeddings (no generation needed). Matches HyDE performance while being significantly cheaper.
- **Standard PRF + Dense Retrieval:** Rocchio/RM3-style feedback applied to dense vectors achieves strong results without any generative model.

### Practical Recommendation for CPU-Only Systems
Use a **two-pass approach**: (1) Initial BM25+dense hybrid retrieval, (2) Extract top terms from top-5 results via RM3/Bo1, (3) Re-query with expanded terms. This is entirely local, no LLM needed, and adds minimal latency.

**Sources:**
- [PRF Closes the Gap (arXiv:2503.14887)](https://arxiv.org/html/2503.14887)
- [ReDE-RF: Real Document Embeddings from Relevance Feedback (arXiv:2410.21242)](https://arxiv.org/html/2410.21242v1)
- [Knowledge-Based PRF (Springer 2025)](https://link.springer.com/article/10.1007/s10115-025-02581-5)
- [Semantics-Aware PRF (SAGE 2025)](https://journals.sagepub.com/doi/abs/10.1177/01655515231184831)
- [PRF with Deep Language Models (ACM TOIS)](https://dl.acm.org/doi/10.1145/3570724)

---

## 5. ColBERT / Late Interaction Models on CPU

### Are They Practical for CPU-Only Local Search? **Yes, with the right engine.**

### PLAID Engine (Primary Recommendation)
- **45x CPU speedup** over vanilla ColBERTv2
- Achieves **tens to few hundreds of milliseconds** per query on CPU, even at 140M passages
- Uses centroid interaction + centroid pruning to eliminate low-scoring passages early

### MUVERA+Rerank (Fastest Option)
- **3.33x faster than PLAID** with +1.7% relative mAP gain
- Achieves **0.54 ms query times** under MUVERA encoding
- Supports flexible embedding dimensionalities (128D to 2048D); 512D is the sweet spot

### SPLATE (Best for Standard Search Libraries)
- Adapts ColBERTv2's frozen representations to enable **standard sparse retrieval** (Lucene-compatible)
- Candidate retrieval under **10ms** with only 50 documents re-ranked
- Ideal for CPU environments that want to use existing inverted index infrastructure

### SLIM (Lucene-Compatible)
- Maps each contextualized token vector to sparse high-dimensional lexical space
- Fully compatible with off-the-shelf libraries like Lucene
- Two-stage retrieval architecture

### Storage
- ColBERTv2 residual compression: **20-36 bytes/vector** (down from 256 bytes in ColBERTv1)
- 6-10x reduction in index size
- Jina-ColBERT-v2: Matryoshka loss allows reducing dims from 128→64 with negligible quality loss, cutting storage by 50%
- Memory-mapped indexes (ColBERT-serve): **90%+ RAM reduction**

### Ultra-Compact Models
- colbert-hash-nano-tr: 1.0M parameters, **600x smaller** than comparable dense encoders, retains 71% of mAP

### Practical Latency Summary

| Engine | CPU Latency | Notes |
|---|---|---|
| Vanilla ColBERTv2 | Seconds | Not practical for CPU |
| PLAID | 10s-100s ms | Production-ready on CPU |
| MUVERA+Rerank | <1 ms (query) | Fastest option |
| SPLATE | <10 ms (candidate gen) | Lucene-compatible |

**Sources:**
- [ColBERTv2 paper (arXiv:2112.01488)](https://arxiv.org/abs/2112.01488)
- [Jina-ColBERT-v2 (ACL 2024)](https://aclanthology.org/2024.mrl-1.11/)
- [ColBERT GitHub](https://github.com/stanford-futuredata/ColBERT)
- [SPLATE: Sparse Late Interaction Retrieval](https://liner.com/review/splate-sparse-late-interaction-retrieval)
- [ColBERT and Friends: Re-Ranking That Feels Instant](https://medium.com/@2nick2patel2/colbert-and-friends-re-ranking-that-feels-instant-6c09102b7526)

---

## 6. Score Fusion Improvements

### RRF (Reciprocal Rank Fusion) — The Baseline
- Formula: `score(d) = Σ 1/(k + rank_i(d))` where k=60 is standard
- Outperforms Condorcet Fuse and CombMNZ in nearly all TREC evaluations (Cormack et al., SIGIR 2009)
- Rank-only: avoids score normalization issues entirely
- Simple, unsupervised, no training data needed

### Alternatives to RRF

| Method | Key Idea | When to Use |
|---|---|---|
| **Weighted RRF** | Per-list weights (e.g., 0.7 semantic + 0.3 BM25) | When you know one retriever is stronger |
| **TM2C2 (Convex Combination)** | Combines normalized scores, not ranks | When tuning data is available; more sample-efficient than RRF |
| **Rank-Biased Centroids (RBC)** | Aggressively discounts deep ranks using a user model | Significantly outperformed Borda-fuse and CombMNZ on ClueWeb12B (SIGIR 2024) using AP and NDCG |
| **Inverse Square Rank (ISR)** | Quadratic decay + log document frequency normalization | Outperforms RRF on AP, BPref, P@10, P@30 for textual data (ImageCLEF 2013) |
| **CombSUM/CombMNZ** | Aggregate normalized scores across rankers | Classic; heavily depends on score normalization quality |
| **ProbFuse/SlideFuse** | Probabilistic per-rank relevance estimation | When you have relevance judgment data |
| **Learning to Rank (LTR)** | ML-trained combination model | When labeled data is available; most powerful but complex |

### Practical Recommendations

1. **Start with RRF** (k=60) — robust zero-shot baseline
2. **Try Weighted RRF** with simple grid search if you have eval data (e.g., 0.7/0.3 split favoring the stronger retriever)
3. **Consider RBC** if you care primarily about top-of-ranking quality (aggressive top-rank emphasis)
4. **Use TM2C2** when you have modest tuning data and want to leverage actual score distributions
5. **Production pattern:** Hybrid search → RRF fusion → Cross-encoder reranking

### Known Limitations
- RRF's k=60 constant is a one-size-fits-all; not optimal for all domains
- RRF ignores score magnitudes, which can be informative
- Performance can degrade when combining weak or misaligned rankers
- Weighted approaches require hyperparameter tuning

**Sources:**
- [RRF outperforms Condorcet (SIGIR 2009)](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [Advanced RAG: Understanding RRF in Hybrid Search (2026)](https://glaforge.dev/posts/2026/02/10/advanced-rag-understanding-reciprocal-rank-fusion-in-hybrid-search/)
- [RRF vs Weighted Fusion for Hybrid Ranking](https://www.maxpetrusenko.com/blog/rrf-vs-weighted-fusion-for-hybrid-ranking)
- [Risk-Reward Trade-offs in Rank Fusion](https://rodgerbenham.github.io/bc17-adcs.pdf)
- [Rank-Biased Centroids (GitHub)](https://github.com/mpetri/rank_biased_centroids)
- [Inverse Square Rank Fusion (IEEE)](https://ieeexplore.ieee.org/document/6849825)
- [Exploring Rank Fusion of Dense Retrievers and Re-rankers](https://ceur-ws.org/Vol-3740/paper-23.pdf)

---

## Summary: Highest-ROI Improvements for CPU-Only Local Search

Ranked by impact-to-effort ratio for a CPU-only system:

1. **Hybrid BM25 + Dense retrieval with RRF fusion** — 15-30% precision improvement, straightforward to implement
2. **Contextual Retrieval** (Anthropic-style context prepending) — 35-67% failure rate reduction, one-time ingestion cost
3. **Cross-encoder or ColBERT reranking** (PLAID/SPLATE on CPU) — 52% MAP improvement with reranking; 10-100ms on CPU with PLAID
4. **Late Chunking** — 3.6% average improvement, zero extra cost if using compatible embedding model
5. **PRF-based query expansion** (RM3/Bo1) — closes gap between small and large retrievers, no LLM needed
6. **Sentence window / parent document retrieval** — better context for generation, minimal overhead
7. **Weighted RRF or RBC fusion** — incremental gains over standard RRF when tuning data available
