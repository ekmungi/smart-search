# Tests for cross-encoder reranker with lazy-load and idle-unload.

"""Unit tests for the Reranker module -- ONNX cross-encoder scoring,
lazy loading, idle auto-unload, and SearchResult re-ordering."""

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_search.config import SmartSearchConfig
from smart_search.models import Chunk, SearchResult
from smart_search.reranker import Reranker


def _make_result(chunk_id: str, rank: int, score: float, text: str = "") -> SearchResult:
    """Create a SearchResult with minimal Chunk data for testing."""
    return SearchResult(
        rank=rank,
        score=score,
        chunk=Chunk(
            id=chunk_id,
            source_path=f"/docs/{chunk_id}.md",
            source_type="md",
            content_type="text",
            text=text or f"Content for chunk {chunk_id}",
            section_path="[]",
            embedding=[0.1] * 256,
            indexed_at="2026-03-23T00:00:00Z",
            model_name="test-model",
        ),
    )


class TestRerankerInit:
    """Tests for Reranker initialization and lazy loading."""

    def test_not_loaded_on_init(self):
        """Reranker does not load ONNX session at construction time."""
        config = SmartSearchConfig(reranking_enabled=True)
        reranker = Reranker(config)
        assert not reranker.is_loaded

    def test_disabled_reranker_passes_through(self):
        """When reranking is disabled, rerank() returns input unchanged."""
        config = SmartSearchConfig(reranking_enabled=False)
        reranker = Reranker(config)

        results = [
            _make_result("c1", 1, 0.9, "highly relevant"),
            _make_result("c2", 2, 0.7, "somewhat relevant"),
            _make_result("c3", 3, 0.5, "less relevant"),
        ]

        reranked = reranker.rerank("test query", results)
        assert len(reranked) == 3
        # Order preserved when disabled
        assert [r.chunk.id for r in reranked] == ["c1", "c2", "c3"]
        # Should NOT load the model
        assert not reranker.is_loaded


class TestRerankerRerank:
    """Tests for the rerank() method with mocked ONNX session."""

    @patch.object(Reranker, "_ensure_loaded")
    def test_reranks_by_cross_encoder_score(self, mock_load):
        """rerank() re-orders results by cross-encoder score descending."""
        config = SmartSearchConfig(reranking_enabled=True, rerank_top_n=10)
        reranker = Reranker(config)
        reranker._loaded = True

        # Mock the scoring -- c3 should rank first, c1 second, c2 third
        reranker._score_pairs = MagicMock(
            return_value=[0.2, 0.1, 0.9]  # scores for c1, c2, c3
        )

        results = [
            _make_result("c1", 1, 0.9, "first result"),
            _make_result("c2", 2, 0.7, "second result"),
            _make_result("c3", 3, 0.5, "third result"),
        ]

        reranked = reranker.rerank("test query", results)
        assert [r.chunk.id for r in reranked] == ["c3", "c1", "c2"]
        # Ranks should be reassigned 1, 2, 3
        assert [r.rank for r in reranked] == [1, 2, 3]

    @patch.object(Reranker, "_ensure_loaded")
    def test_rerank_empty_returns_empty(self, mock_load):
        """rerank() with empty results returns empty list."""
        config = SmartSearchConfig(reranking_enabled=True)
        reranker = Reranker(config)

        reranked = reranker.rerank("test query", [])
        assert reranked == []

    @patch.object(Reranker, "_ensure_loaded")
    def test_rerank_single_result(self, mock_load):
        """rerank() with single result returns it with rank 1."""
        config = SmartSearchConfig(reranking_enabled=True, rerank_top_n=10)
        reranker = Reranker(config)
        reranker._loaded = True
        reranker._score_pairs = MagicMock(return_value=[0.8])

        results = [_make_result("c1", 1, 0.9, "only result")]
        reranked = reranker.rerank("test query", results)
        assert len(reranked) == 1
        assert reranked[0].rank == 1
        assert reranked[0].chunk.id == "c1"

    @patch.object(Reranker, "_ensure_loaded")
    def test_rerank_preserves_chunk_data(self, mock_load):
        """rerank() only changes rank and score, not chunk content."""
        config = SmartSearchConfig(reranking_enabled=True, rerank_top_n=10)
        reranker = Reranker(config)
        reranker._loaded = True
        reranker._score_pairs = MagicMock(return_value=[0.5, 0.9])

        original = _make_result("c1", 1, 0.8, "original text")
        results = [original, _make_result("c2", 2, 0.6, "second")]

        reranked = reranker.rerank("test query", results)
        # c2 should be first (higher cross-encoder score)
        reranked_c1 = next(r for r in reranked if r.chunk.id == "c1")
        assert reranked_c1.chunk.text == "original text"
        assert reranked_c1.chunk.source_path == "/docs/c1.md"
        assert reranked_c1.chunk.embedding == [0.1] * 256

    @patch.object(Reranker, "_ensure_loaded")
    def test_rerank_respects_top_n(self, mock_load):
        """rerank() only reranks up to rerank_top_n results."""
        config = SmartSearchConfig(reranking_enabled=True, rerank_top_n=2)
        reranker = Reranker(config)
        reranker._loaded = True
        # Only 2 scores needed (top_n=2), third result passed through
        reranker._score_pairs = MagicMock(return_value=[0.3, 0.8])

        results = [
            _make_result("c1", 1, 0.9, "first"),
            _make_result("c2", 2, 0.7, "second"),
            _make_result("c3", 3, 0.5, "third"),
        ]

        reranked = reranker.rerank("test query", results)
        # Should return all 3 but only rerank the top 2
        assert len(reranked) == 3

    @patch.object(Reranker, "_ensure_loaded")
    def test_rerank_normalizes_scores_zero_to_one(self, mock_load):
        """Reranked scores are normalized to 0-1 range."""
        config = SmartSearchConfig(reranking_enabled=True, rerank_top_n=10)
        reranker = Reranker(config)
        reranker._loaded = True
        reranker._score_pairs = MagicMock(return_value=[-2.0, 5.0, 1.0])

        results = [
            _make_result("c1", 1, 0.9, "first"),
            _make_result("c2", 2, 0.7, "second"),
            _make_result("c3", 3, 0.5, "third"),
        ]

        reranked = reranker.rerank("test query", results)
        scores = [r.score for r in reranked]
        assert max(scores) == 1.0
        assert all(0.0 <= s <= 1.0 for s in scores)


class TestRerankerIdleUnload:
    """Tests for idle timeout and unload behavior."""

    def test_unload_clears_session(self):
        """unload() releases the ONNX session and marks as not loaded."""
        config = SmartSearchConfig(reranking_enabled=True)
        reranker = Reranker(config)
        # Simulate loaded state
        reranker._session = MagicMock()
        reranker._tokenizer = MagicMock()
        reranker._loaded = True

        reranker.unload()
        assert not reranker.is_loaded
        assert reranker._session is None


class TestRerankerGpuProviders:
    """Tests for GPU provider integration in Reranker."""

    @patch("smart_search.reranker.detect_gpu")
    def test_gpu_active_when_gpu_detected(self, mock_detect):
        """Reranker sets _gpu_active=True when GPU is detected."""
        mock_detect.return_value = "cuda"
        config = SmartSearchConfig(reranking_enabled=True)
        reranker = Reranker(config)
        assert reranker._gpu_active is True

    @patch("smart_search.reranker.detect_gpu")
    def test_gpu_inactive_when_no_gpu(self, mock_detect):
        """Reranker sets _gpu_active=False when no GPU available."""
        mock_detect.return_value = None
        config = SmartSearchConfig(reranking_enabled=True)
        reranker = Reranker(config)
        assert reranker._gpu_active is False

    @patch("smart_search.reranker.detect_gpu")
    def test_disables_idle_unload_on_gpu(self, mock_detect):
        """When GPU is detected, idle timeout is 0 (no auto-unload)."""
        mock_detect.return_value = "directml"
        config = SmartSearchConfig(reranking_enabled=True)
        reranker = Reranker(config)
        assert reranker._idle_timeout == 0
