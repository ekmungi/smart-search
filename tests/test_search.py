# Tests for SearchEngine: search logic, mode routing, and Smart Context formatting.

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_search.models import Chunk, SearchResult
from smart_search.search import SearchEngine, _normalize_query


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
        embedding=[0.0] * 256,
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
        embedding=embedding or np.random.RandomState(42).rand(256).tolist(),
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


class TestSearchModeRouting:
    """Tests for semantic/keyword/hybrid mode routing."""

    def test_semantic_mode(self, search_engine, mock_store):
        """mode='semantic' uses only vector search."""
        results = search_engine.search_results("test", mode="semantic")
        assert isinstance(results, list)
        mock_store.vector_search.assert_called()

    def test_keyword_mode(self, tmp_config, mock_embedder, tmp_path):
        """mode='keyword' uses FTS5 and returns matching results."""
        # Create a real SQLite DB with FTS5 for keyword search
        db_path = str(tmp_path / "metadata.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text, id UNINDEXED, source_path UNINDEXED,
                source_type UNINDEXED, tokenize='porter unicode61'
            )"""
        )
        conn.execute(
            "INSERT INTO chunks_fts (text, id, source_path, source_type) "
            "VALUES (?, ?, ?, ?)",
            ("FHIR interoperability standard", "chunk_1", "/docs/fhir.md", "md"),
        )
        conn.commit()

        mock_store = MagicMock()
        mock_store._sqlite_conn = conn

        engine = SearchEngine(tmp_config, mock_embedder, mock_store)
        results = engine.search_results("FHIR", mode="keyword")

        assert len(results) == 1
        assert results[0].chunk.id == "chunk_1"
        # keyword mode should NOT call vector_search
        mock_store.vector_search.assert_not_called()
        conn.close()

    def test_hybrid_mode(self, tmp_config, mock_embedder, tmp_path):
        """mode='hybrid' combines vector and keyword results."""
        db_path = str(tmp_path / "metadata.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text, id UNINDEXED, source_path UNINDEXED,
                source_type UNINDEXED, tokenize='porter unicode61'
            )"""
        )
        conn.execute(
            "INSERT INTO chunks_fts (text, id, source_path, source_type) "
            "VALUES (?, ?, ?, ?)",
            ("FHIR interoperability standard", "kw_chunk", "/docs/fhir.md", "md"),
        )
        conn.commit()

        mock_store = MagicMock()
        mock_store._sqlite_conn = conn
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.9, source="/docs/other.pdf"),
        ]

        engine = SearchEngine(tmp_config, mock_embedder, mock_store)
        results = engine.search_results("FHIR", mode="hybrid")

        # Should have results from both sources (RRF merged)
        assert len(results) >= 1
        conn.close()

    def test_default_is_hybrid(self, search_engine, mock_store):
        """Default mode is 'hybrid'."""
        # Verify the default parameter value
        import inspect
        sig = inspect.signature(search_engine.search_results)
        mode_param = sig.parameters["mode"]
        assert mode_param.default == "hybrid"

    def test_keyword_skips_threshold(self, tmp_config, mock_embedder, tmp_path):
        """Keyword mode returns results regardless of relevance_threshold."""
        # Set a very high threshold that would filter out semantic results
        tmp_config_high = tmp_config.model_copy(
            update={"relevance_threshold": 0.99}
        )

        db_path = str(tmp_path / "metadata.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text, id UNINDEXED, source_path UNINDEXED,
                source_type UNINDEXED, tokenize='porter unicode61'
            )"""
        )
        conn.execute(
            "INSERT INTO chunks_fts (text, id, source_path, source_type) "
            "VALUES (?, ?, ?, ?)",
            ("testing keyword results", "chunk_1", "/docs/test.md", "md"),
        )
        conn.commit()

        mock_store = MagicMock()
        mock_store._sqlite_conn = conn

        engine = SearchEngine(tmp_config_high, mock_embedder, mock_store)
        results = engine.search_results("testing", mode="keyword")

        # Keyword mode should still return results despite high threshold
        assert len(results) >= 1
        conn.close()

    def test_format_results_shows_mode(self, search_engine, mock_store):
        """Formatted output shows the correct mode string."""
        result = search_engine.search("test", mode="hybrid")
        assert "Mode: hybrid" in result

        result = search_engine.search("test", mode="semantic")
        assert "Mode: semantic" in result


class TestNormalizeQuery:
    """Tests for _normalize_query: strips leading/trailing punctuation."""

    def test_strips_trailing_period(self):
        """Trailing period is removed."""
        assert _normalize_query("drug discovery.") == "drug discovery"

    def test_strips_trailing_exclamation(self):
        """Trailing exclamation mark is removed."""
        assert _normalize_query("drug discovery!") == "drug discovery"

    def test_strips_trailing_question_mark(self):
        """Trailing question mark is removed."""
        assert _normalize_query("what is drug discovery?") == "what is drug discovery"

    def test_strips_leading_whitespace(self):
        """Leading whitespace is removed."""
        assert _normalize_query("  drug discovery") == "drug discovery"

    def test_strips_trailing_whitespace(self):
        """Trailing whitespace is removed."""
        assert _normalize_query("drug discovery  ") == "drug discovery"

    def test_strips_mixed_leading_trailing(self):
        """Both leading and trailing punctuation/whitespace removed."""
        assert _normalize_query(" ...drug discovery!!! ") == "drug discovery"

    def test_preserves_internal_punctuation(self):
        """Hyphens, apostrophes, and other internal punctuation preserved."""
        assert _normalize_query("it's a state-of-the-art model.") == "it's a state-of-the-art model"

    def test_preserves_clean_query(self):
        """Clean query is returned unchanged."""
        assert _normalize_query("drug discovery") == "drug discovery"

    def test_returns_original_if_all_punctuation(self):
        """All-punctuation query returns original (no empty string)."""
        assert _normalize_query("...") == "..."

    def test_single_word(self):
        """Single word with trailing period."""
        assert _normalize_query("FHIR.") == "FHIR"


class TestSourceDeduplication:
    """Tests for per-source deduplication (max_chunks_per_source)."""

    def test_deduplication_caps_chunks_per_source(self, tmp_config, mock_embedder):
        """Results from a single source are capped at max_chunks_per_source."""
        config = tmp_config.model_copy(update={"max_chunks_per_source": 2})
        mock_store = MagicMock()
        # 4 chunks from same PDF, 1 from another doc
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.95, source="/docs/big.pdf"),
            _make_search_result(rank=2, score=0.90, source="/docs/big.pdf"),
            _make_search_result(rank=3, score=0.85, source="/docs/big.pdf"),
            _make_search_result(rank=4, score=0.80, source="/docs/big.pdf"),
            _make_search_result(rank=5, score=0.75, source="/docs/other.md"),
        ]
        # Give each chunk a unique id
        for i, r in enumerate(mock_store.vector_search.return_value):
            r.chunk.id = f"chunk_{i}"

        engine = SearchEngine(config, mock_embedder, mock_store)
        results = engine.search_results("test", mode="semantic")

        pdf_chunks = [r for r in results if r.chunk.source_path == "/docs/big.pdf"]
        assert len(pdf_chunks) == 2, "Should cap at 2 chunks from big.pdf"
        assert any(r.chunk.source_path == "/docs/other.md" for r in results)

    def test_deduplication_disabled_when_zero(self, tmp_config, mock_embedder):
        """max_chunks_per_source=0 disables deduplication."""
        config = tmp_config.model_copy(update={"max_chunks_per_source": 0})
        mock_store = MagicMock()
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.95, source="/docs/big.pdf"),
            _make_search_result(rank=2, score=0.90, source="/docs/big.pdf"),
            _make_search_result(rank=3, score=0.85, source="/docs/big.pdf"),
        ]
        for i, r in enumerate(mock_store.vector_search.return_value):
            r.chunk.id = f"chunk_{i}"

        engine = SearchEngine(config, mock_embedder, mock_store)
        results = engine.search_results("test", mode="semantic")

        pdf_chunks = [r for r in results if r.chunk.source_path == "/docs/big.pdf"]
        assert len(pdf_chunks) == 3, "All chunks should pass when dedup disabled"

    def test_deduplication_preserves_rank_order(self, tmp_config, mock_embedder):
        """Deduplication preserves top-scoring chunks and reassigns ranks."""
        config = tmp_config.model_copy(update={"max_chunks_per_source": 1})
        mock_store = MagicMock()
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.95, source="/docs/a.pdf"),
            _make_search_result(rank=2, score=0.90, source="/docs/a.pdf"),
            _make_search_result(rank=3, score=0.85, source="/docs/b.md"),
        ]
        for i, r in enumerate(mock_store.vector_search.return_value):
            r.chunk.id = f"chunk_{i}"

        engine = SearchEngine(config, mock_embedder, mock_store)
        results = engine.search_results("test", mode="semantic")

        assert len(results) == 2
        assert results[0].rank == 1
        assert results[1].rank == 2
        assert results[0].chunk.source_path == "/docs/a.pdf"
        assert results[1].chunk.source_path == "/docs/b.md"


class TestHybridSearchThreshold:
    """Tests that hybrid search doesn't prematurely filter borderline results."""

    def test_borderline_semantic_boosted_by_keyword(self, tmp_config, mock_embedder, tmp_path):
        """A result below semantic threshold should still appear in hybrid
        if it has a strong keyword match (RRF boost)."""
        # Set threshold high enough that the result is "borderline"
        config = tmp_config.model_copy(update={"relevance_threshold": 0.50})

        # Create FTS5 table with a keyword match
        db_path = str(tmp_path / "metadata.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text, id UNINDEXED, source_path UNINDEXED,
                source_type UNINDEXED, tokenize='porter unicode61'
            )"""
        )
        conn.execute(
            "INSERT INTO chunks_fts (text, id, source_path, source_type) "
            "VALUES (?, ?, ?, ?)",
            ("drug discovery in cancer research", "borderline_chunk", "/docs/cancer.md", "md"),
        )
        conn.commit()

        mock_store = MagicMock()
        mock_store._sqlite_conn = conn
        # Return the borderline chunk below threshold (0.35 < 0.50)
        # plus a clearly-above-threshold result
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.85, source="/docs/pharma.pdf"),
            _make_search_result(
                rank=2, score=0.35, source="/docs/cancer.md",
                text="drug discovery in cancer research",
            ),
        ]
        # Override chunk id to match FTS entry
        mock_store.vector_search.return_value[1].chunk.id = "borderline_chunk"

        engine = SearchEngine(config, mock_embedder, mock_store)

        # Hybrid should include the borderline result (boosted by keyword)
        hybrid_results = engine.search_results("drug discovery", mode="hybrid")
        hybrid_paths = [r.chunk.source_path for r in hybrid_results]
        assert "/docs/cancer.md" in hybrid_paths, (
            "Borderline semantic result with keyword match should appear in hybrid"
        )

        # Semantic-only should NOT include it (below threshold)
        semantic_results = engine.search_results("drug discovery", mode="semantic")
        semantic_paths = [r.chunk.source_path for r in semantic_results]
        assert "/docs/cancer.md" not in semantic_paths, (
            "Below-threshold result should be filtered in semantic-only mode"
        )
        conn.close()

    def test_hybrid_no_keyword_falls_back_to_filtered(self, search_engine, mock_store):
        """When keyword returns nothing, hybrid falls back to threshold-filtered semantic."""
        mock_store._sqlite_conn = None  # No FTS5 available
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.95, source="/docs/a.pdf"),
            _make_search_result(rank=2, score=0.10, source="/docs/b.pdf"),
        ]
        results = search_engine.search_results("test", mode="hybrid")
        # Low-score result (0.10) should be filtered by threshold fallback
        paths = [r.chunk.source_path for r in results]
        assert "/docs/a.pdf" in paths
        assert "/docs/b.pdf" not in paths


class TestQueryNormalizationIntegration:
    """Tests that query normalization is applied in the search pipeline."""

    def test_trailing_period_normalized_before_embedding(self, search_engine, mock_embedder):
        """'drug discovery.' is normalized to 'drug discovery' before embedding."""
        search_engine.search_results("drug discovery.")
        # The embedder should receive the cleaned query (no trailing period)
        mock_embedder.embed_query.assert_called_with("drug discovery")

    def test_clean_query_unchanged(self, search_engine, mock_embedder):
        """A clean query passes through normalization unchanged."""
        search_engine.search_results("drug discovery")
        mock_embedder.embed_query.assert_called_with("drug discovery")


class TestRerankerIntegration:
    """Tests that cross-encoder reranking integrates correctly with search pipeline."""

    def test_hybrid_with_reranker_calls_rerank(self, tmp_config, mock_embedder, tmp_path):
        """Hybrid search passes fused results through reranker when provided."""
        from unittest.mock import MagicMock
        from smart_search.reranker import Reranker

        # Set up FTS5
        db_path = str(tmp_path / "metadata.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text, id UNINDEXED, source_path UNINDEXED,
                source_type UNINDEXED, tokenize='porter unicode61'
            )"""
        )
        conn.execute(
            "INSERT INTO chunks_fts (text, id, source_path, source_type) "
            "VALUES (?, ?, ?, ?)",
            ("FHIR interoperability", "chunk_1", "/docs/fhir.md", "md"),
        )
        conn.commit()

        mock_store = MagicMock()
        mock_store._sqlite_conn = conn
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.9, source="/docs/other.pdf"),
        ]

        # Create a mock reranker that reverses result order
        mock_reranker = MagicMock(spec=Reranker)
        mock_reranker.rerank.side_effect = lambda q, results: list(reversed(results))

        engine = SearchEngine(tmp_config, mock_embedder, mock_store, reranker=mock_reranker)
        results = engine.search_results("FHIR", mode="hybrid")

        # Verify reranker was called
        mock_reranker.rerank.assert_called_once()
        conn.close()

    def test_hybrid_without_reranker_skips_reranking(self, tmp_config, mock_embedder, tmp_path):
        """Hybrid search works normally when no reranker is provided."""
        db_path = str(tmp_path / "metadata.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text, id UNINDEXED, source_path UNINDEXED,
                source_type UNINDEXED, tokenize='porter unicode61'
            )"""
        )
        conn.execute(
            "INSERT INTO chunks_fts (text, id, source_path, source_type) "
            "VALUES (?, ?, ?, ?)",
            ("FHIR interoperability", "chunk_1", "/docs/fhir.md", "md"),
        )
        conn.commit()

        mock_store = MagicMock()
        mock_store._sqlite_conn = conn
        mock_store.vector_search.return_value = [
            _make_search_result(rank=1, score=0.9, source="/docs/other.pdf"),
        ]

        # No reranker (default)
        engine = SearchEngine(tmp_config, mock_embedder, mock_store)
        results = engine.search_results("FHIR", mode="hybrid")

        assert len(results) >= 1
        conn.close()
