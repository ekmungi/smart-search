"""Tests for configurable relevance threshold in search."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from smart_search.config import SmartSearchConfig
from smart_search.config_manager import ConfigManager
from smart_search.models import Chunk, SearchResult
from smart_search.search import SearchEngine


def test_config_default_threshold():
    """SmartSearchConfig should default relevance_threshold to 0.50."""
    config = SmartSearchConfig()
    assert config.relevance_threshold == 0.50


def test_config_manager_default_threshold(tmp_path: Path):
    """ConfigManager should include relevance_threshold=0.50 in defaults."""
    manager = ConfigManager(tmp_path)
    loaded = manager.load()
    assert loaded["relevance_threshold"] == 0.50
    assert isinstance(loaded["relevance_threshold"], float)


def _make_search_engine(threshold: float) -> SearchEngine:
    """Build a SearchEngine with a mocked embedder/store and given threshold.

    Args:
        threshold: The relevance_threshold to set on config.

    Returns:
        A SearchEngine with mocked dependencies.
    """
    config = SmartSearchConfig(relevance_threshold=threshold)
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.0] * 256
    store = MagicMock()
    return SearchEngine(config=config, embedder=embedder, store=store)


def _make_results(scores: list[float]) -> list[SearchResult]:
    """Create SearchResult objects with given scores.

    Args:
        scores: List of relevance scores.

    Returns:
        List of SearchResult objects with dummy chunks.
    """
    results = []
    for i, score in enumerate(scores):
        chunk = Chunk(
            id=f"chunk-{i}",
            source_path=f"notes/doc-{i}.md",
            source_type="md",
            content_type="text",
            section_path="[]",
            text=f"Content for chunk {i}",
            embedding=[0.0] * 256,
            indexed_at="2026-01-01T00:00:00",
            model_name="test-model",
        )
        results.append(SearchResult(chunk=chunk, score=score, rank=i + 1))
    return results


def test_threshold_zero_returns_all():
    """With threshold=0.0, all results should pass the filter."""
    engine = _make_search_engine(threshold=0.0)
    all_results = _make_results([0.10, 0.30, 0.50, 0.70, 0.90])
    engine._store.vector_search.return_value = all_results

    results = engine.search_results("test query")

    assert len(results) == 5


def test_threshold_high_filters_all():
    """With threshold=0.99, normal-score results should all be filtered out."""
    engine = _make_search_engine(threshold=0.99)
    all_results = _make_results([0.40, 0.55, 0.70, 0.85, 0.95])
    engine._store.vector_search.return_value = all_results

    results = engine.search_results("test query")

    assert len(results) == 0


def test_threshold_filters_correctly():
    """With threshold=0.60, only results scoring >= 0.60 should remain."""
    engine = _make_search_engine(threshold=0.60)
    all_results = _make_results([0.40, 0.55, 0.60, 0.75, 0.90])
    engine._store.vector_search.return_value = all_results

    results = engine.search_results("test query")

    assert len(results) == 3
    returned_scores = [r.score for r in results]
    assert all(s >= 0.60 for s in returned_scores)
    assert 0.40 not in returned_scores
    assert 0.55 not in returned_scores
