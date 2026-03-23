# Maximum Marginal Relevance (MMR) for search result diversity.

"""Greedy MMR selection balances relevance and diversity by penalizing
candidates that are too similar to already-selected results. Eliminates
redundant chunks from the same document that waste LLM context tokens.

Formula: MMR_score = lambda * relevance - (1-lambda) * max_sim(candidate, selected)
"""

from typing import List

import numpy as np

from smart_search.models import SearchResult


def mmr_rerank(
    results: List[SearchResult],
    lambda_param: float = 0.8,
    limit: int = 10,
) -> List[SearchResult]:
    """Select results that balance relevance and diversity via MMR.

    Greedily picks the next result that maximizes the MMR score:
    lambda * relevance - (1-lambda) * max_similarity_to_already_selected.

    Results with empty embeddings are treated as maximally diverse
    (zero similarity to everything), preserving their relevance rank.

    Args:
        results: Pre-ranked search results with embeddings.
        lambda_param: 0-1 trade-off. Higher = more relevance, lower = more diversity.
        limit: Maximum number of results to return.

    Returns:
        Reordered SearchResult list with updated ranks and scores.
    """
    if not results:
        return []

    if len(results) == 1:
        return [SearchResult(rank=1, score=results[0].score, chunk=results[0].chunk)]

    # Extract embeddings and relevance scores
    embeddings = []
    has_embedding = []
    for r in results:
        emb = r.chunk.embedding
        if emb and len(emb) > 0:
            embeddings.append(np.array(emb, dtype=np.float32))
            has_embedding.append(True)
        else:
            # Placeholder zero vector -- will be flagged as missing
            embeddings.append(np.zeros(1, dtype=np.float32))
            has_embedding.append(False)

    # Normalize relevance scores to 0-1 for consistent MMR computation
    relevance_scores = [r.score for r in results]
    max_rel = max(relevance_scores) if relevance_scores else 1.0
    min_rel = min(relevance_scores) if relevance_scores else 0.0
    rel_span = max_rel - min_rel
    if rel_span > 0:
        norm_relevance = [(s - min_rel) / rel_span for s in relevance_scores]
    else:
        norm_relevance = [1.0] * len(relevance_scores)

    # Greedy MMR selection
    selected_indices: List[int] = []
    remaining = set(range(len(results)))
    effective_limit = min(limit, len(results))

    for _ in range(effective_limit):
        best_idx = -1
        best_mmr = float("-inf")

        for idx in remaining:
            relevance = norm_relevance[idx]

            # Compute max similarity to already-selected results
            if not selected_indices or not has_embedding[idx]:
                # First pick or missing embedding: no diversity penalty
                max_sim = 0.0
            else:
                max_sim = _max_cosine_similarity(
                    embeddings[idx], embeddings, selected_indices, has_embedding
                )

            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim

            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = idx

        if best_idx < 0:
            break

        selected_indices.append(best_idx)
        remaining.remove(best_idx)

    # Build output with sequential ranks and normalized scores
    mmr_scores = []
    for idx in selected_indices:
        relevance = norm_relevance[idx]
        if not selected_indices or idx == selected_indices[0]:
            max_sim = 0.0
        elif not has_embedding[idx]:
            max_sim = 0.0
        else:
            # Recompute against predecessors only
            predecessors = selected_indices[: selected_indices.index(idx)]
            max_sim = _max_cosine_similarity(
                embeddings[idx], embeddings, predecessors, has_embedding
            ) if predecessors else 0.0
        mmr_scores.append(lambda_param * relevance - (1 - lambda_param) * max_sim)

    # Normalize MMR scores to 0-1
    if mmr_scores:
        max_mmr = max(mmr_scores)
        min_mmr = min(mmr_scores)
        mmr_span = max_mmr - min_mmr
        if mmr_span > 0:
            norm_mmr = [(s - min_mmr) / mmr_span for s in mmr_scores]
        else:
            norm_mmr = [1.0] * len(mmr_scores)
    else:
        norm_mmr = []

    return [
        SearchResult(
            rank=rank,
            score=round(score, 6),
            chunk=results[idx].chunk,
        )
        for rank, (idx, score) in enumerate(
            zip(selected_indices, norm_mmr), start=1
        )
    ]


def _max_cosine_similarity(
    candidate: np.ndarray,
    all_embeddings: List[np.ndarray],
    selected_indices: List[int],
    has_embedding: List[bool],
) -> float:
    """Compute max cosine similarity between candidate and selected results.

    Args:
        candidate: Embedding vector of the candidate.
        all_embeddings: All result embeddings.
        selected_indices: Indices of already-selected results.
        has_embedding: Flags for which results have valid embeddings.

    Returns:
        Maximum cosine similarity (0-1), or 0.0 if no valid comparisons.
    """
    if not selected_indices:
        return 0.0

    cand_norm = np.linalg.norm(candidate)
    if cand_norm == 0:
        return 0.0

    max_sim = 0.0
    for sel_idx in selected_indices:
        if not has_embedding[sel_idx]:
            continue
        sel_vec = all_embeddings[sel_idx]
        sel_norm = np.linalg.norm(sel_vec)
        if sel_norm == 0:
            continue
        sim = float(np.dot(candidate, sel_vec) / (cand_norm * sel_norm))
        # Clamp to [0, 1] -- negative cosine similarity means orthogonal/opposite
        sim = max(0.0, sim)
        if sim > max_sim:
            max_sim = sim

    return max_sim
