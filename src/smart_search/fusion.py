# Reciprocal Rank Fusion for combining vector and keyword search results.

"""Pure function implementing RRF (Cormack, Clarke & Buettcher, 2009).
Merges two ranked result lists by summing reciprocal rank scores,
naturally boosting items that appear in both lists. No dependencies
on store, embedder, or any other component."""

from typing import List

from smart_search.models import Chunk, SearchResult


def reciprocal_rank_fusion(
    vector_results: List[SearchResult],
    keyword_results: List[SearchResult],
    k: int = 60,
    limit: int = 10,
) -> List[SearchResult]:
    """Merge vector and keyword search results using RRF.

    Each result's RRF score is 1/(k + rank). Items appearing in both
    lists get both scores summed, naturally boosting overlapping results.
    The constant k=60 is from the original RRF paper.

    Args:
        vector_results: Ranked results from vector/semantic search.
        keyword_results: Ranked results from FTS5 keyword search.
        k: RRF constant (default 60, per original paper).
        limit: Maximum number of fused results to return.

    Returns:
        Merged list of SearchResult sorted by RRF score descending.
    """
    # Track RRF scores and chunk data by chunk ID
    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}

    for rank_idx, result in enumerate(vector_results, start=1):
        cid = result.chunk.id
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank_idx)
        chunks[cid] = result.chunk

    for rank_idx, result in enumerate(keyword_results, start=1):
        cid = result.chunk.id
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank_idx)
        # Keep chunk from vector results if already present (has embedding score)
        if cid not in chunks:
            chunks[cid] = result.chunk

    # Sort by RRF score descending, truncate to limit
    sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
    sorted_ids = sorted_ids[:limit]

    # Normalize scores to 0-1 range so display shows 0-100%
    # Top result always shows 1.0 (100%), others relative to it
    max_score = scores[sorted_ids[0]] if sorted_ids else 1.0

    return [
        SearchResult(
            rank=rank,
            score=round(scores[cid] / max_score, 6) if max_score > 0 else 0.0,
            chunk=chunks[cid],
        )
        for rank, cid in enumerate(sorted_ids, start=1)
    ]
