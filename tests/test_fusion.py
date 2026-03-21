# Tests for Reciprocal Rank Fusion (RRF) in fusion.py.

import pytest

from smart_search.fusion import reciprocal_rank_fusion
from smart_search.models import Chunk, SearchResult


def _make_result(chunk_id: str, rank: int, score: float = 0.9) -> SearchResult:
    """Create a SearchResult with a given chunk ID and rank."""
    chunk = Chunk(
        id=chunk_id,
        source_path=f"/docs/{chunk_id}.md",
        source_type="md",
        content_type="text",
        text=f"Content of {chunk_id}",
        section_path="[]",
        embedding=[0.0] * 256,
        indexed_at="2026-03-16T00:00:00Z",
        model_name="test-model",
    )
    return SearchResult(rank=rank, score=score, chunk=chunk)


class TestReciprocalRankFusion:
    """Tests for the RRF merge function."""

    def test_rrf_merges_two_lists(self):
        """Two disjoint lists merge into one sorted by RRF score."""
        vector = [_make_result("a", 1), _make_result("b", 2)]
        keyword = [_make_result("c", 1), _make_result("d", 2)]

        fused = reciprocal_rank_fusion(vector, keyword, k=60, limit=10)

        assert len(fused) == 4
        ids = [r.chunk.id for r in fused]
        assert "a" in ids
        assert "c" in ids

    def test_rrf_overlapping_boosted(self):
        """Items appearing in both lists get boosted to the top."""
        vector = [_make_result("shared", 1), _make_result("vec_only", 2)]
        keyword = [_make_result("shared", 1), _make_result("kw_only", 2)]

        fused = reciprocal_rank_fusion(vector, keyword, k=60, limit=10)

        # "shared" should be rank 1 (boosted by appearing in both)
        assert fused[0].chunk.id == "shared"
        # Its score should be ~2x a single-list item
        assert fused[0].score > fused[1].score

    def test_rrf_empty_lists(self):
        """Two empty lists produce empty output."""
        fused = reciprocal_rank_fusion([], [], k=60, limit=10)
        assert fused == []

    def test_rrf_one_empty(self):
        """One empty list still returns results from the other."""
        vector = [_make_result("a", 1), _make_result("b", 2)]
        fused = reciprocal_rank_fusion(vector, [], k=60, limit=10)
        assert len(fused) == 2
        assert fused[0].chunk.id == "a"

    def test_rrf_respects_limit(self):
        """Output is truncated to the limit parameter."""
        vector = [_make_result(f"v{i}", i) for i in range(1, 6)]
        keyword = [_make_result(f"k{i}", i) for i in range(1, 6)]

        fused = reciprocal_rank_fusion(vector, keyword, k=60, limit=3)
        assert len(fused) == 3

    def test_rrf_scores_descending(self):
        """Fused results are sorted by score descending."""
        vector = [_make_result("a", 1), _make_result("b", 2), _make_result("c", 3)]
        keyword = [_make_result("d", 1), _make_result("e", 2), _make_result("f", 3)]

        fused = reciprocal_rank_fusion(vector, keyword, k=60, limit=10)

        for i in range(len(fused) - 1):
            assert fused[i].score >= fused[i + 1].score

    def test_rrf_ranks_are_sequential(self):
        """Fused results have sequential rank values starting at 1."""
        vector = [_make_result("a", 1)]
        keyword = [_make_result("b", 1)]

        fused = reciprocal_rank_fusion(vector, keyword, k=60, limit=10)
        ranks = [r.rank for r in fused]
        assert ranks == list(range(1, len(fused) + 1))

    def test_rrf_scores_normalized_to_zero_one(self):
        """Fused scores are normalized so top result is 1.0."""
        vector = [_make_result("a", 1), _make_result("b", 2)]
        keyword = [_make_result("c", 1), _make_result("d", 2)]

        fused = reciprocal_rank_fusion(vector, keyword, k=60, limit=10)
        # Top result should be exactly 1.0 (normalized max)
        assert fused[0].score == 1.0
        # All scores should be in 0-1 range
        assert all(0.0 <= r.score <= 1.0 for r in fused)

    def test_rrf_overlapping_normalized_score(self):
        """Item in both lists gets normalized score of 1.0 when it's the top hit."""
        vector = [_make_result("shared", 1), _make_result("vec_only", 2)]
        keyword = [_make_result("shared", 1), _make_result("kw_only", 2)]

        fused = reciprocal_rank_fusion(vector, keyword, k=60, limit=10)
        assert fused[0].chunk.id == "shared"
        assert fused[0].score == 1.0
        # Others should be strictly less than 1.0
        assert all(r.score < 1.0 for r in fused[1:])

    def test_rrf_configurable_k(self):
        """Different k values produce different relative score distributions."""
        # Use overlapping items so scores differ meaningfully between k values
        vector = [_make_result("shared", 1), _make_result("a", 2), _make_result("b", 3)]
        keyword = [_make_result("shared", 1), _make_result("c", 2), _make_result("d", 3)]

        fused_k60 = reciprocal_rank_fusion(vector, keyword, k=60, limit=10)
        fused_k30 = reciprocal_rank_fusion(vector, keyword, k=30, limit=10)

        # "shared" tops both, but the relative gap to non-shared items differs
        # Lower k amplifies rank differences, so non-shared items score lower relative to shared
        non_shared_k60 = [r.score for r in fused_k60 if r.chunk.id != "shared"]
        non_shared_k30 = [r.score for r in fused_k30 if r.chunk.id != "shared"]
        # With k=30 (lower), rank-2 items are further from rank-1 proportionally
        assert max(non_shared_k30) < max(non_shared_k60)
