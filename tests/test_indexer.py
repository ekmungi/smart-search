# Tests for DocumentIndexer: full ingestion pipeline.

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_search.config import SmartSearchConfig
from smart_search.indexer import DocumentIndexer
from smart_search.models import Chunk
from smart_search.store import ChunkStore


def _make_fake_chunks(source_path, count=3, source_type="md"):
    """Create fake chunks as if returned by a chunker.

    Args:
        source_path: Path to the source file.
        count: Number of fake chunks to create.
        source_type: The source type string to embed in each chunk.

    Returns:
        List of Chunk instances with synthetic data.
    """
    rng = np.random.RandomState(42)
    return [
        Chunk(
            id=f"fake_{i}",
            source_path=source_path,
            source_type=source_type,
            content_type="text",
            text=f"Chunk {i} content.",
            page_number=i + 1,
            section_path='["Section 1"]',
            embedding=[],
            has_image=False,
            indexed_at="2026-03-05T00:00:00Z",
            model_name="nomic-ai/nomic-embed-text-v1.5",
        )
        for i in range(count)
    ]


@pytest.fixture
def mock_md_chunker():
    """Mock MarkdownChunker that returns fake chunks for both methods."""
    chunker = MagicMock()
    chunker.chunk_file.side_effect = lambda path: _make_fake_chunks(path, source_type="md")
    chunker.chunk_text.side_effect = lambda text, source_path, source_type="md": _make_fake_chunks(
        source_path, source_type=source_type,
    )
    return chunker


@pytest.fixture
def indexer_deps(tmp_config, mock_md_chunker, mock_embedder):
    """Set up all indexer dependencies with mocks."""
    store = ChunkStore(tmp_config)
    store.initialize()
    return {
        "config": tmp_config,
        "embedder": mock_embedder,
        "store": store,
        "markdown_chunker": mock_md_chunker,
    }


@pytest.fixture
def indexer(indexer_deps):
    """DocumentIndexer with mocked chunker and embedder."""
    return DocumentIndexer(**indexer_deps)


@pytest.fixture
def indexer_with_md(tmp_config, mock_md_chunker, mock_embedder):
    """DocumentIndexer with mocked markdown chunker."""
    store = ChunkStore(tmp_config)
    store.initialize()
    return DocumentIndexer(
        config=tmp_config,
        embedder=mock_embedder,
        store=store,
        markdown_chunker=mock_md_chunker,
    ), mock_md_chunker


class TestIndexFile:
    """Tests for single-file indexing."""

    @patch("smart_search.markitdown_parser.convert_to_markdown", return_value="# Converted\nPDF content")
    def test_index_file_creates_chunks_in_store(self, mock_convert, indexer, indexer_deps, sample_pdf_path):
        """Indexed file produces chunks retrievable from store."""
        result = indexer.index_file(str(sample_pdf_path))
        assert result.status == "indexed"
        assert result.chunk_count == 3
        # Indexer normalizes paths to POSIX
        posix_path = Path(sample_pdf_path).resolve().as_posix()
        chunks = indexer_deps["store"].get_chunks_for_file(posix_path)
        assert len(chunks) == 3

    @patch("smart_search.markitdown_parser.convert_to_markdown", return_value="# Converted\nPDF content")
    def test_index_file_skips_unchanged_file(self, mock_convert, indexer, sample_pdf_path):
        """Second index call with same file returns 'skipped'."""
        indexer.index_file(str(sample_pdf_path))
        result = indexer.index_file(str(sample_pdf_path))
        assert result.status == "skipped"

    @patch("smart_search.markitdown_parser.convert_to_markdown", return_value="# Converted\nPDF content")
    def test_index_file_force_reindexes(self, mock_convert, indexer, sample_pdf_path):
        """force=True re-indexes even if file hash unchanged."""
        indexer.index_file(str(sample_pdf_path))
        result = indexer.index_file(str(sample_pdf_path), force=True)
        assert result.status == "indexed"

    def test_unsupported_extension_returns_failed(self, indexer, tmp_path):
        """Unsupported file extension returns 'failed' status."""
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("hello")
        result = indexer.index_file(str(txt_file))
        assert result.status == "failed"

    @patch("smart_search.markitdown_parser.convert_to_markdown", side_effect=Exception("Parse error"))
    def test_index_file_handles_failure_gracefully(self, mock_convert, indexer, tmp_path):
        """Corrupted/unprocessable file returns 'failed', not crash."""
        bad_pdf = tmp_path / "corrupt.pdf"
        bad_pdf.write_text("not a real pdf")
        result = indexer.index_file(str(bad_pdf))
        assert result.status == "failed"


class TestIndexFolder:
    """Tests for folder-level indexing."""

    @patch("smart_search.markitdown_parser.convert_to_markdown", return_value="# Converted\nPDF content")
    def test_index_folder_counts(self, mock_convert, indexer, tmp_path):
        """Folder with 2 supported files reports indexed=2."""
        (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4 fake2")
        (tmp_path / "c.txt").write_text("ignored")
        result = indexer.index_folder(str(tmp_path))
        assert result.indexed == 2
        assert result.skipped == 0

    def test_index_folder_respects_cancel_event(self, indexer, tmp_path):
        """Cancel event stops processing remaining files mid-folder.

        Creates 3 markdown files but sets the cancel event after the first
        file via on_progress callback. Expects fewer than 3 files indexed.
        """
        import threading

        (tmp_path / "a.md").write_text("# Note A\nContent A")
        (tmp_path / "b.md").write_text("# Note B\nContent B")
        (tmp_path / "c.md").write_text("# Note C\nContent C")

        cancel = threading.Event()
        call_count = 0

        def cancel_after_first(file_path, result):
            """Set cancel event after the first file completes."""
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                cancel.set()

        result = indexer.index_folder(
            str(tmp_path), on_progress=cancel_after_first, cancel_event=cancel,
        )
        # Should have processed 1 file, then stopped before the rest
        assert result.indexed < 3
        assert len(result.results) < 3


class TestIndexerRouting:
    """Tests that files are routed to the correct pipeline."""

    def test_md_routes_to_chunk_file(self, indexer_with_md, tmp_path):
        """Markdown file uses chunk_file (reads from disk directly)."""
        indexer, md_chunker = indexer_with_md
        md = tmp_path / "note.md"
        md.write_text("# Test\nContent here")
        result = indexer.index_file(str(md))
        assert result.status == "indexed"
        md_chunker.chunk_file.assert_called_once()
        md_chunker.chunk_text.assert_not_called()

    @patch("smart_search.markitdown_parser.convert_to_markdown", return_value="# Converted\nPDF content here")
    def test_pdf_routes_through_markitdown(self, mock_convert, indexer_with_md, tmp_path):
        """PDF file is converted via MarkItDown, then chunked via chunk_text."""
        indexer, md_chunker = indexer_with_md
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        result = indexer.index_file(str(pdf))
        assert result.status == "indexed"
        mock_convert.assert_called_once()
        md_chunker.chunk_text.assert_called_once()
        md_chunker.chunk_file.assert_not_called()

    @patch("smart_search.markitdown_parser.convert_to_markdown", return_value="# Slides\nContent")
    def test_pptx_routes_through_markitdown(self, mock_convert, indexer_with_md, tmp_path):
        """PPTX file is converted via MarkItDown pipeline."""
        indexer, md_chunker = indexer_with_md
        pptx = tmp_path / "slides.pptx"
        pptx.write_bytes(b"fake pptx")
        result = indexer.index_file(str(pptx))
        assert result.status == "indexed"
        mock_convert.assert_called_once()
        # source_type should be "pptx"
        call_kwargs = md_chunker.chunk_text.call_args
        assert call_kwargs[1].get("source_type", call_kwargs[0][2] if len(call_kwargs[0]) > 2 else None) == "pptx"


@pytest.mark.slow
class TestIndexerEndToEnd:
    """End-to-end test with real chunker and embedder."""

    def test_end_to_end_pdf_indexing(self, tmp_config, sample_pdf_path):
        """Real PDF -> MarkItDown -> MarkdownChunker -> embeddings -> store."""
        from smart_search.embedder import Embedder
        from smart_search.markdown_chunker import MarkdownChunker

        store = ChunkStore(tmp_config)
        store.initialize()
        embedder = Embedder(tmp_config)
        indexer = DocumentIndexer(
            config=tmp_config,
            embedder=embedder,
            store=store,
            markdown_chunker=MarkdownChunker(tmp_config),
        )
        result = indexer.index_file(str(sample_pdf_path))
        assert result.status == "indexed"
        assert result.chunk_count > 0

        # Verify embeddings are 768-dim
        chunks = store.get_chunks_for_file(
            Path(sample_pdf_path).resolve().as_posix()
        )
        assert len(chunks) > 0
        assert all(len(c.embedding) == 768 for c in chunks)

    def test_end_to_end_markdown_indexing(self, tmp_config, tmp_path):
        """Real Markdown -> heading chunks -> real embeddings -> store."""
        from smart_search.embedder import Embedder
        from smart_search.markdown_chunker import MarkdownChunker

        md = tmp_path / "test_note.md"
        md.write_text(
            "---\ntitle: Test Note\n---\n"
            "# Section 1\n"
            "This is the first section with enough content to index properly.\n"
            "## Section 2\n"
            "This is the second section with enough content to index properly.\n",
            encoding="utf-8",
        )

        cfg = tmp_config.model_copy(update={"min_chunk_length": 10})
        store = ChunkStore(cfg)
        store.initialize()
        indexer = DocumentIndexer(
            config=cfg,
            embedder=Embedder(cfg),
            store=store,
            markdown_chunker=MarkdownChunker(cfg),
        )
        result = indexer.index_file(str(md))
        assert result.status == "indexed"
        assert result.chunk_count == 2

        chunks = store.get_chunks_for_file(md.resolve().as_posix())
        assert len(chunks) == 2
        assert all(len(c.embedding) == 768 for c in chunks)
        assert all(c.source_type == "md" for c in chunks)
        assert chunks[0].source_title == "Test Note"
