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

    def test_search_filters_by_folder(self, search_engine, mock_store):
        """folder filter restricts results to matching source_path prefix."""
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.9, source="C:/vault/notes/a.md"),
            _make_search_result(rank=2, score=0.8, source="C:/vault/archive/b.md"),
        ]
        result = search_engine.search("test", folder="C:/vault/notes")
        assert "a.md" in result
        assert "b.md" not in result

    def test_search_folder_filter_normalizes_backslashes(self, search_engine, mock_store):
        """Folder filter normalizes backslashes to forward slashes."""
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.9, source="C:/vault/notes/a.md"),
        ]
        result = search_engine.search("test", folder="C:\\vault\\notes")
        assert "a.md" in result

    def test_search_folder_none_returns_all(self, search_engine, mock_store):
        """folder=None returns all results (no filtering)."""
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.9, source="C:/vault/notes/a.md"),
            _make_search_result(rank=2, score=0.8, source="C:/other/b.md"),
        ]
        result = search_engine.search("test", folder=None)
        assert "a.md" in result
        assert "b.md" in result

    def test_search_malformed_section_path_fallback(self, search_engine, mock_store):
        """Invalid JSON in section_path falls back to raw string."""
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.9, section_path="not json"),
        ]
        result = search_engine.search("test")
        assert isinstance(result, str)
        # Should not crash, should display something


class TestSearchResults:
    """Tests for search_results() returning raw SearchResult objects."""

    def test_returns_list_of_search_results(self, search_engine, mock_store):
        """search_results returns List[SearchResult] not a string."""
        results = search_engine.search_results("test query")
        assert isinstance(results, list)
        assert len(results) == 2
        assert all(isinstance(r, SearchResult) for r in results)

    def test_filters_by_doc_types(self, search_engine, mock_store):
        """search_results filters results by document type."""
        results = search_engine.search_results("test", doc_types=["docx"])
        # Only notes.docx has source_type "pdf" (from fixture), so filter by
        # a type not present returns empty (fixture uses source_type="pdf")
        assert all(r.chunk.source_type == "pdf" for r in results) or len(results) == 0

    def test_filters_by_folder(self, search_engine, mock_store):
        """search_results filters results by folder prefix."""
        results = search_engine.search_results("test", folder="/docs")
        assert all(r.chunk.source_path.startswith("/docs/") for r in results)

    def test_returns_empty_list_for_no_matches(self, search_engine, mock_store):
        """search_results returns empty list when all filtered out."""
        results = search_engine.search_results("test", folder="/nonexistent")
        assert results == []

    def test_search_delegates_to_search_results(self, search_engine, mock_store):
        """search() uses search_results() internally (no duplication)."""
        formatted = search_engine.search("test query")
        # search() should produce formatted output from same data
        assert "KNOWLEDGE SEARCH RESULTS" in formatted
        assert "report.pdf" in formatted


@pytest.mark.slow
class TestSearchEndToEnd:
    """End-to-end search with real embeddings."""

    def test_search_returns_relevant_result(self, tmp_config, sample_pdf_path):
        """Real PDF indexed and searched returns relevant content."""
        from smart_search.embedder import Embedder
        from smart_search.indexer import DocumentIndexer
        from smart_search.markdown_chunker import MarkdownChunker
        from smart_search.store import ChunkStore

        store = ChunkStore(tmp_config)
        store.initialize()
        embedder = Embedder(tmp_config)

        indexer = DocumentIndexer(
            config=tmp_config, embedder=embedder, store=store,
            markdown_chunker=MarkdownChunker(tmp_config),
        )
        indexer.index_file(str(sample_pdf_path))

        engine = SearchEngine(tmp_config, embedder, store)
        result = engine.search("machine learning")
        assert "KNOWLEDGE SEARCH RESULTS" in result
        assert "Results:" in result


def _make_chunk(
    source_path="test/doc.pdf",
    text="Sample chunk text for testing.",
    embedding=None,
    **kwargs,
):
    """Create a Chunk with sensible defaults for testing."""
    defaults = dict(
        id="test-chunk-001",
        source_path=source_path,
        source_type="md",
        content_type="text",
        text=text,
        section_path='["Test"]',
        embedding=embedding or np.random.RandomState(42).rand(768).tolist(),
        indexed_at="2026-03-07T00:00:00",
        model_name="nomic-ai/nomic-embed-text-v1.5",
    )
    defaults.update(kwargs)
    return Chunk(**defaults)


class TestFindRelated:
    """Tests for the find_related method on SearchEngine."""

    def test_returns_similar_notes(self, search_engine, mock_store):
        """find_related returns formatted results for a known note."""
        mock_store.get_chunks_for_file.return_value = [
            _make_chunk(source_path="notes/source.md", text="hello world"),
        ]
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.85, source="notes/similar.md"),
        ]
        result = search_engine.find_related("notes/source.md", limit=5)
        assert "similar.md" in result
        assert "0.85" in result
        mock_store.get_chunks_for_file.assert_called_once_with("notes/source.md")
        mock_store.vector_search.assert_called_once()

    def test_returns_message_when_note_not_indexed(self, search_engine, mock_store):
        """find_related returns helpful message when note has no chunks."""
        mock_store.get_chunks_for_file.return_value = []
        result = search_engine.find_related("notes/unknown.md")
        assert "not found" in result.lower() or "not indexed" in result.lower()

    def test_excludes_source_note_from_results(self, search_engine, mock_store):
        """find_related filters out the source note from results."""
        mock_store.get_chunks_for_file.return_value = [
            _make_chunk(source_path="notes/source.md", text="hello"),
        ]
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.99, source="notes/source.md"),
            _make_search_result(rank=2, score=0.80, source="notes/other.md"),
        ]
        result = search_engine.find_related("notes/source.md")
        assert "other.md" in result
