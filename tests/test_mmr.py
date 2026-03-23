# Tests for Maximum Marginal Relevance (MMR) diversity reranking.

"""Unit tests for mmr module -- greedy selection that balances relevance
and diversity by penalizing results similar to already-selected ones."""

import pytest

from smart_search.models import Chunk, SearchResult
from smart_search.mmr import mmr_rerank


def _make_result(
    chunk_id: str, rank: int, score: float,
    text: str = "", embedding: list = None,
    source_path: str = "",
) -> SearchResult:
    """Create a SearchResult for testing. Embeddings default to zeros."""
    return SearchResult(
        rank=rank,
        score=score,
        chunk=Chunk(
            id=chunk_id,
            source_path=source_path or f"/docs/{chunk_id}.md",
            source_type="md",
            content_type="text",
            text=text or f"Content for {chunk_id}",
            section_path="[]",
            embedding=embedding if embedding is not None else [0.0] * 256,
            indexed_at="2026-03-23T00:00:00Z",
            model_name="test-model",
        ),
    )


class TestMmrBasic:
    """Basic MMR selection tests."""

    def test_lambda_one_preserves_original_ranking(self):
        """With lambda=1.0, MMR uses pure relevance (no diversity penalty)."""
        results = [
            _make_result("c1", 1, 0.9, embedding=[1.0, 0.0, 0.0]),
            _make_result("c2", 2, 0.7, embedding=[0.9, 0.1, 0.0]),
            _make_result("c3", 3, 0.5, embedding=[0.0, 1.0, 0.0]),
        ]
        reranked = mmr_rerank(results, lambda_param=1.0, limit=3)
        # Pure relevance: original order preserved
        assert [r.chunk.id for r in reranked] == ["c1", "c2", "c3"]

    def test_lambda_zero_maximizes_diversity(self):
        """With lambda=0.0, MMR picks maximally diverse results."""
        # c1 and c2 are near-identical, c3 is orthogonal
        results = [
            _make_result("c1", 1, 0.9, embedding=[1.0, 0.0, 0.0]),
            _make_result("c2", 2, 0.8, embedding=[0.99, 0.01, 0.0]),
            _make_result("c3", 3, 0.5, embedding=[0.0, 0.0, 1.0]),
        ]
        reranked = mmr_rerank(results, lambda_param=0.0, limit=3)
        # After picking c1 first (highest relevance for tie-break on first pick),
        # c3 should come before c2 because c3 is more diverse from c1
        ids = [r.chunk.id for r in reranked]
        assert ids.index("c3") < ids.index("c2"), (
            "Diverse result c3 should rank before near-duplicate c2"
        )

    def test_penalizes_near_duplicate_chunks(self):
        """Near-duplicate chunks from same doc are penalized."""
        # Two chunks with very similar embeddings (same document)
        # and one with different embedding
        results = [
            _make_result("c1", 1, 0.9, embedding=[1.0, 0.0, 0.0],
                         source_path="/docs/report.md"),
            _make_result("c2", 2, 0.85, embedding=[0.98, 0.02, 0.0],
                         source_path="/docs/report.md"),
            _make_result("c3", 3, 0.7, embedding=[0.0, 1.0, 0.0],
                         source_path="/docs/other.md"),
        ]
        # With moderate lambda, c3 should be promoted above c2
        reranked = mmr_rerank(results, lambda_param=0.5, limit=3)
        ids = [r.chunk.id for r in reranked]
        assert ids[0] == "c1", "Highest relevance should still be first"
        assert ids.index("c3") < ids.index("c2"), (
            "Diverse c3 should rank above near-duplicate c2"
        )

    def test_single_result_returned_unchanged(self):
        """MMR with a single result returns it as-is with rank 1."""
        results = [_make_result("c1", 1, 0.9, embedding=[1.0, 0.0])]
        reranked = mmr_rerank(results, lambda_param=0.8, limit=1)
        assert len(reranked) == 1
        assert reranked[0].chunk.id == "c1"
        assert reranked[0].rank == 1

    def test_empty_results_returns_empty(self):
        """MMR with empty input returns empty list."""
        reranked = mmr_rerank([], lambda_param=0.8, limit=10)
        assert reranked == []


class TestMmrEdgeCases:
    """Edge cases for MMR selection."""

    def test_missing_embeddings_treated_as_diverse(self):
        """Results with empty embeddings are treated as maximally diverse."""
        results = [
            _make_result("c1", 1, 0.9, embedding=[1.0, 0.0, 0.0]),
            _make_result("c2", 2, 0.8, embedding=[]),  # No embedding
            _make_result("c3", 3, 0.7, embedding=[0.0, 1.0, 0.0]),
        ]
        # Should not crash, and c2 should be treated as diverse
        reranked = mmr_rerank(results, lambda_param=0.8, limit=3)
        assert len(reranked) == 3
        assert {r.chunk.id for r in reranked} == {"c1", "c2", "c3"}

    def test_limit_truncates_output(self):
        """MMR respects the limit parameter."""
        results = [
            _make_result(f"c{i}", i + 1, 0.9 - i * 0.1,
                         embedding=[float(i == j) for j in range(5)])
            for i in range(5)
        ]
        reranked = mmr_rerank(results, lambda_param=0.8, limit=3)
        assert len(reranked) == 3

    def test_ranks_are_sequential(self):
        """Output ranks are reassigned sequentially starting from 1."""
        results = [
            _make_result("c1", 1, 0.9, embedding=[1.0, 0.0]),
            _make_result("c2", 2, 0.7, embedding=[0.0, 1.0]),
            _make_result("c3", 3, 0.5, embedding=[0.5, 0.5]),
        ]
        reranked = mmr_rerank(results, lambda_param=0.8, limit=3)
        assert [r.rank for r in reranked] == [1, 2, 3]

    def test_scores_are_zero_to_one(self):
        """Output scores are normalized to 0-1 range."""
        results = [
            _make_result("c1", 1, 0.9, embedding=[1.0, 0.0]),
            _make_result("c2", 2, 0.7, embedding=[0.0, 1.0]),
        ]
        reranked = mmr_rerank(results, lambda_param=0.8, limit=2)
        for r in reranked:
            assert 0.0 <= r.score <= 1.0
