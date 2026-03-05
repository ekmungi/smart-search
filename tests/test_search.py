# Tests for SearchEngine: search logic and Smart Context formatting.

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from smart_search.models import Chunk, SearchResult
from smart_search.search import SearchEngine


def _make_search_result(rank=1, score=0.95, text="Sample result text.", source="/docs/test.pdf",
                        page=1, section_path='["Chapter 1", "Section 1.2"]'):
    """Create a SearchResult with sensible defaults."""
    chunk = Chunk(
        id=f"chunk_{rank}",
        source_path=source,
        source_type="pdf",
        content_type="text",
        text=text,
        page_number=page,
        section_path=section_path,
        embedding=[0.0] * 768,
        has_image=False,
        indexed_at="2026-03-05T00:00:00Z",
        model_name="nomic-ai/nomic-embed-text-v1.5",
    )
    return SearchResult(rank=rank, score=score, chunk=chunk)


@pytest.fixture
def mock_store():
    """Mock ChunkStore with controllable vector_search results."""
    store = MagicMock()
    store.vector_search.return_value = [
        _make_search_result(rank=1, score=0.95, source="/docs/report.pdf"),
        _make_search_result(rank=2, score=0.80, source="/docs/notes.docx"),
    ]
    return store


@pytest.fixture
def search_engine(tmp_config, mock_embedder, mock_store):
    """SearchEngine with mocked embedder and store."""
    return SearchEngine(tmp_config, mock_embedder, mock_store)


class TestSearchOutput:
    """Tests for search output formatting."""

    def test_search_returns_string(self, search_engine):
        """search() always returns a string."""
        result = search_engine.search("test query")
        assert isinstance(result, str)
        assert "KNOWLEDGE SEARCH RESULTS" in result

    def test_search_no_results_message(self, search_engine, mock_store):
        """Empty results produce a 'no results' message."""
        mock_store.vector_search.return_value = []
        result = search_engine.search("obscure query")
        assert "No results found" in result

    def test_search_formats_sources_section(self, search_engine):
        """Output includes a Sources section with unique file paths."""
        result = search_engine.search("test query")
        assert "Sources:" in result
        assert "/docs/report.pdf" in result
        assert "/docs/notes.docx" in result

    def test_section_path_human_readable(self, search_engine, mock_store):
        """JSON section_path is rendered as 'Ch 1 > Sec 2' format."""
        mock_store.vector_search.return_value = [
            _make_search_result(
                rank=1, score=0.9,
                section_path='["Chapter 1", "Section 1.2"]',
            ),
        ]
        result = search_engine.search("test")
        assert "Chapter 1 > Section 1.2" in result

    def test_text_truncated_at_500_chars(self, search_engine, mock_store):
        """Chunk text longer than 500 chars is truncated with ellipsis."""
        long_text = "A" * 600
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.9, text=long_text),
        ]
        result = search_engine.search("test")
        # The displayed text should be 500 chars + "..."
        assert "..." in result
        assert long_text not in result


class TestSearchFilters:
    """Tests for search filtering options."""

    def test_search_filters_doc_types(self, search_engine, mock_store):
        """doc_types filter is passed through to store."""
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.9, source="/docs/a.pdf"),
        ]
        result = search_engine.search("test", doc_types=["pdf"])
        assert isinstance(result, str)

    def test_search_malformed_section_path_fallback(self, search_engine, mock_store):
        """Invalid JSON in section_path falls back to raw string."""
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.9, section_path="not json"),
        ]
        result = search_engine.search("test")
        assert isinstance(result, str)
        # Should not crash, should display something


@pytest.mark.slow
class TestSearchEndToEnd:
    """End-to-end search with real embeddings."""

    def test_search_returns_relevant_result(self, tmp_config, sample_pdf_path):
        """Real PDF indexed and searched returns relevant content."""
        from smart_search.chunker import DocumentChunker
        from smart_search.embedder import Embedder
        from smart_search.indexer import DocumentIndexer
        from smart_search.store import ChunkStore

        store = ChunkStore(tmp_config)
        store.initialize()
        chunker = DocumentChunker(tmp_config)
        embedder = Embedder(tmp_config)

        indexer = DocumentIndexer(
            config=tmp_config, chunker=chunker, embedder=embedder, store=store,
        )
        indexer.index_file(str(sample_pdf_path))

        engine = SearchEngine(tmp_config, embedder, store)
        result = engine.search("machine learning")
        assert "KNOWLEDGE SEARCH RESULTS" in result
        assert "Results:" in result
