# Plan: Improve Retriever Performance

## Context

Smart-search has ~1500-2000 indexed documents: PDFs (research articles), DOCX, Excel (keyword-only), and short Markdown notes. Two problems need solving:

1. **Quick Search** — short MD notes buried in the vault don't surface. Large PDFs with 75-100 chunks dominate all 10 result slots.
2. **MCP Agentic Search** — the API lacks primitives for an LLM to do iterative multi-step retrieval (broad discovery → evaluate → drill-down → refine).

**Primary root cause:** Every pipeline stage operates at chunk level with zero `source_path` awareness. A 50-page PDF has 75-100x more representation than a 1-chunk markdown note.

**Secondary:** TinyBERT-L-2 reranker leaves 4.5 nDCG@10 points on the table vs MiniLM-L-6.

**NOT a gap:** Matryoshka 256-dim — only 1.8% quality loss, model was designed for this exact truncation.

---

## Root Cause Detail

### Document Dominance — No Stage Is Source-Aware

| Stage | File | Source-Aware? |
|---|---|---|
| Vector Search | `store.py:289` | NO — returns chunks |
| Keyword Search | `fts.py:53` | NO — returns chunks |
| RRF Fusion | `fusion.py:13` | NO — dedupes by chunk.id only |
| Cross-Encoder | `reranker.py:139` | NO — scores (query, text) pairs |
| MMR Diversity | `mmr.py:67` | **NO** — uses embedding similarity only, despite docstring claiming "eliminates redundant chunks from the same document" |

The `source_path` field exists on every `Chunk` (confirmed at `models.py:31`) but is NEVER used for ranking or diversity.

### Cross-Check Results

All proposed changes verified against actual code:

- `mmr.py:67-98`: Greedy loop accesses `norm_relevance[idx]` and `embeddings[idx]` but never `results[idx].chunk.source_path`. Adding source tracking is backward-compatible.
- `search.py:239-263`: Pipeline is Rerank→MMR. `_cap_per_source()` goes after MMR (after line 261). `search_results()` currently accepts only `query, limit, mode, doc_types, folder` — no per-query diversity params.
- `server.py:79-136`: `knowledge_search` passes params to `mcp_client.search()` at lines 132-135. Adding new params is straightforward.
- `http_routes.py:146-180`: `/api/search` accepts `q, limit, mode, folder, doc_types`. New params follow same pattern.
- `http_models.py:32-42`: `SearchHit` is missing `chunk_id`. Has `rank, score, source_path, source_type, text, page_number, section_path, filename`.
- `mcp_formatters.py:40-48`: Does not show chunk_id. Displays rank, score, source, section, page, text.
- `model_registry.py:44-84`: Models registered as `ModelInfo` in `CURATED_MODELS` list. Adding MiniLM-L-6 follows existing pattern.

---

## Part A: Quick Search Improvements

### A1. Source-Aware MMR
**Impact: HIGH | Effort: MEDIUM | Files: `mmr.py`, `config.py`**

Add same-source penalty to MMR greedy selection. When a chunk's `source_path` matches an already-selected result, inject a penalty into the diversity term.

**Changes to `src/smart_search/mmr.py:67-98`:**
```python
# Add source tracking in the greedy loop
selected_sources: set[str] = set()

for _ in range(effective_limit):
    for idx in remaining:
        relevance = norm_relevance[idx]
        max_sim = _max_cosine_similarity(...)
        
        # NEW: source penalty for already-selected documents
        source_path = results[idx].chunk.source_path
        if source_penalty > 0 and source_path in selected_sources:
            max_sim = max(max_sim, source_penalty)
        
        mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim
    
    # Track selected document
    selected_sources.add(results[best_idx].chunk.source_path)
```

Add `source_penalty: float = 0.0` parameter to `mmr_rerank()` function signature (backward-compatible default).

**Config addition to `src/smart_search/config.py`:**
```python
mmr_source_penalty: float = 0.5  # 0=disabled, 1=max same-source penalty
```

Pass from `search.py:256-261` when calling `mmr_rerank()`.

### A2. Max Results Per Document
**Impact: HIGH | Effort: LOW | Files: `search.py`, `config.py`**

Hard cap on results from any single document, applied AFTER MMR in `_apply_reranking()` (after line 261, before return).

**New method in `src/smart_search/search.py`:**
```python
@staticmethod
def _cap_per_source(results: List[SearchResult], max_per_source: int) -> List[SearchResult]:
    if max_per_source <= 0:
        return results
    seen: dict[str, int] = {}
    capped = []
    for r in results:
        count = seen.get(r.chunk.source_path, 0)
        if count < max_per_source:
            capped.append(r)
            seen[r.chunk.source_path] = count + 1
    return capped
```

Wire into `_apply_reranking()` after MMR step. Accept `max_per_source` as optional param (falls back to config default).

**Config:** `max_results_per_source: int = 3` (0=unlimited)

### A3. Upgrade Reranker to MiniLM-L-6
**Impact: MEDIUM-HIGH (+4.5 nDCG@10) | Effort: LOW | Files: `config.py`, `reranker.py`, `model_registry.py`**

From SBERT benchmarks:
- TinyBERT-L-2-v2: 69.84 nDCG@10, 32.56 MRR@10
- **MiniLM-L-6-v2: 74.30 nDCG@10, 39.01 MRR@10** ← sweet spot
- MiniLM-L-12-v2: 74.31 nDCG@10 (identical quality, 2x slower — skip)

CPU latency: ~50-150ms for 20-30 candidates. Memory: ~120MB (vs ~50MB). ONNX quantized available.

**Changes:**
- `src/smart_search/config.py:74` — change default: `reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"`
- `src/smart_search/reranker.py:300-307` — verify ONNX path works (same `onnx/model_quantized.onnx` structure)
- `src/smart_search/model_registry.py` — add MiniLM-L-6 to `CURATED_MODELS` list (follows existing `ModelInfo` pattern at lines 44-84)

### A4. Increase Rerank Budget: 20 → 30
**Impact: LOW-MEDIUM | Effort: TRIVIAL**

`src/smart_search/config.py:76` — change `rerank_top_n: int = 30`

### A5. Contextual Chunk Headers
**Impact: MEDIUM | Effort: LOW | Requires re-indexing**

Add section heading path to chunk prefix in `src/smart_search/markdown_chunker.py:163-168`:

```python
# In _build_chunks(), extend the title prefix
section_parts = section.get("section_path", [])
section_line = f"\nSection: {' > '.join(section_parts)}" if section_parts else ""
text = f"Title: {source_title}{section_line}{_TITLE_SEPARATOR}" + section["text"].strip()
```

---

## Part B: Agentic Retrieval

### B1. Agentic-Ready API Parameters

Add two new params to `knowledge_search` MCP tool and `/api/search` HTTP endpoint:

**`max_per_source: Optional[int]`** — per-query diversity control
- Broad discovery: `max_per_source=1` → 1 result per doc, max diversity
- Deep drill-down: `max_per_source=10` → allow concentration on best docs
- Default: `None` → uses config `max_results_per_source` (3)

**`source_paths: Optional[List[str]]`** — search within specific documents
- Agent identifies 3 relevant docs in phase 1, then drills down in phase 2
- Implementation: post-filter in `search.py` (simple first pass), optionally push to FTS5/vector queries later

**`chunk_id` in results** — expose in `SearchHit` model and MCP formatter so agent can reference specific chunks.

**Files:**
- `src/smart_search/server.py:80-86` — add params to `knowledge_search` signature
- `src/smart_search/http_routes.py:147-152` — add query params to `/api/search`
- `src/smart_search/http_models.py:32-42` — add `chunk_id: str` to `SearchHit`
- `src/smart_search/mcp_formatters.py:40-48` — include chunk_id in output
- `src/smart_search/search.py:76-83` — thread params through `search_results()` → `_apply_reranking()`

### B2. Skill File: `skill.md`

Teach the LLM the Corrective RAG pattern for iterative search. Based on the Agentic RAG Survey (arxiv.org/abs/2501.09136), key patterns: adaptive retrieval, relevance grading, query rewriting, iterative refinement.

**Create `docs/smart-search-skill.md`:**

```markdown
# Smart Search Skill

## When to use
Search when answering questions requiring the user's knowledge base.
Do NOT search for simple conversational queries.

## Phase 1: Broad Discovery
knowledge_search(query="...", max_per_source=1, limit=15)
Grade each result 0-3:
  3=directly answers, 2=relevant context, 1=tangential, 0=irrelevant

## Phase 2: Focused Retrieval (if Phase 1 average ≤1)
Option A: Rewrite query with more specific terms
Option B: Try mode="keyword" if semantic missed exact terms
Option C: Drill into promising docs:
  knowledge_search(query="...", source_paths=[...], max_per_source=5)

## Phase 3: Context Assembly
Use read_note() for short docs to get full text.
Select chunks scored ≥2 from all iterations.
Synthesize answer with source citations.

## When to Stop
- Found ≥3 highly relevant chunks → synthesize
- Two iterations with no results → tell user
- Already have enough context → don't search again

## Mode Guide
- hybrid (default): Most queries
- keyword: Exact terms, codes, filenames, error messages
- semantic: Concepts described differently than indexed text
```

### B3. Agent File: `agent.md`

For multi-step research tasks (comparing across documents, topic exploration).

**Create `docs/smart-search-agent.md`:**

```markdown
# Smart Search Research Agent

## When to use
Deep research requiring multiple documents, cross-referencing,
or synthesis from diverse sources.

## Workflow
1. Decompose question into 2-3 sub-queries
2. Broad search each sub-query (max_per_source=1)
3. Grade results, identify top documents
4. Drill into top docs with focused queries (source_paths=[...])
5. Use find_related() to discover connected documents
6. Cross-reference findings, report with citations

## Tools
- knowledge_search: Primary (mode, doc_types, folder, max_per_source, source_paths)
- find_related: Similar documents to a known relevant one
- read_note: Full text of a document
- knowledge_stats: Index status
- knowledge_list_files: Browse indexed documents
```

---

## Implementation Order

| Step | Change | Re-index? | Files |
|------|--------|-----------|-------|
| 1 | Source-aware MMR (A1) | No | `mmr.py`, `config.py` |
| 2 | Per-source cap + `max_per_source` param (A2+B1) | No | `search.py`, `config.py`, `server.py`, `http_routes.py` |
| 3 | Expose chunk_id in results (B1) | No | `http_models.py`, `mcp_formatters.py`, `http_routes.py` |
| 4 | `source_paths` filter param (B1) | No | `search.py`, `server.py`, `http_routes.py` |
| 5 | Upgrade reranker to MiniLM-L-6 (A3) | No | `config.py`, `reranker.py`, `model_registry.py` |
| 6 | Increase rerank budget to 30 (A4) | No | `config.py` |
| 7 | Section heading enrichment (A5) | **Yes** | `markdown_chunker.py` |
| 8 | Write skill.md + agent.md (B2+B3) | No | `docs/smart-search-skill.md`, `docs/smart-search-agent.md` |

Steps 1-6, 8: No re-indexing. Step 7: Requires re-indexing (group with any other re-index event).

All changes target CPU-first via ONNX. GPU/NPU acceleration is automatic via existing `gpu_provider.py` — MiniLM-L-6 reranking drops from ~100ms to ~5ms on GPU/NPU with zero additional code.

---

## Verification Plan

1. `pytest tests/ -x` — all existing tests pass
2. **MMR source diversity**: Add test to `tests/test_mmr.py` with same-source results, verify diverse docs surface
3. **Per-source cap**: Test no more than N results from any document
4. **Reranker**: `tests/test_reranker.py` passes with MiniLM-L-6
5. **API params**: `max_per_source` and `source_paths` work via HTTP and MCP
6. **chunk_id**: Appears in SearchHit JSON and MCP formatted output
7. **End-to-end**: Queries for short MD note topics return them in top-10 alongside PDFs
8. **Agentic loop**: Manual test — broad discovery (max_per_source=1) → drill-down (source_paths=[...])
9. **Memory**: Peak RSS ≤ ~750MB (reranker +70MB for MiniLM-L-6)
10. **Latency**: Total search under 300ms on CPU

---

## Research Sources

- [Agentic RAG Survey (Singh et al., 2025)](https://arxiv.org/abs/2501.09136)
- [A-RAG: Scaling via Hierarchical Retrieval (Feb 2026)](https://arxiv.org/html/2602.03442v1)
- [SBERT Cross-Encoder Benchmarks](https://www.sbert.net/docs/pretrained-models/ce-msmarco.html)
- [Arctic Embed 2.0 Paper](https://arxiv.org/html/2412.04506v2)
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- [Contextual Chunk Headers](https://github.com/NirDiamant/RAG_Techniques/blob/main/all_rag_techniques/contextual_chunk_headers.ipynb)
- [MCP Skills vs Tools (LlamaIndex)](https://www.llamaindex.ai/blog/skills-vs-mcp-tools-for-agents-when-to-use-what)
- [Corrective RAG Architecture](https://letsdatascience.com/blog/agentic-rag-self-correcting-retrieval)
