# Tests for DocumentIndexer: full ingestion pipeline.

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from smart_search.config import SmartSearchConfig
from smart_search.indexer import DocumentIndexer
from smart_search.models import Chunk
from smart_search.store import ChunkStore


def _make_fake_chunks(source_path, count=3):
    """Create fake chunks as if returned by a chunker."""
    rng = np.random.RandomState(42)
    return [
        Chunk(
            id=f"fake_{i}",
            source_path=source_path,
            source_type="pdf",
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
def mock_chunker():
    """Mock DocumentChunker that returns fake chunks."""
    chunker = MagicMock()
    chunker.chunk_file.side_effect = lambda path: _make_fake_chunks(path)
    return chunker


@pytest.fixture
def indexer_deps(tmp_config, mock_chunker, mock_embedder):
    """Set up all indexer dependencies with mocks."""
    store = ChunkStore(tmp_config)
    store.initialize()
    return {
        "config": tmp_config,
        "chunker": mock_chunker,
        "embedder": mock_embedder,
        "store": store,
    }


@pytest.fixture
def indexer(indexer_deps):
    """DocumentIndexer with mocked chunker and embedder."""
    return DocumentIndexer(**indexer_deps)


class TestIndexFile:
    """Tests for single-file indexing."""

    def test_index_file_creates_chunks_in_store(self, indexer, indexer_deps, sample_pdf_path):
        """Indexed file produces chunks retrievable from store."""
        result = indexer.index_file(str(sample_pdf_path))
        assert result.status == "indexed"
        assert result.chunk_count == 3
        # Indexer normalizes paths to POSIX
        posix_path = Path(sample_pdf_path).resolve().as_posix()
        chunks = indexer_deps["store"].get_chunks_for_file(posix_path)
        assert len(chunks) == 3

    def test_index_file_skips_unchanged_file(self, indexer, sample_pdf_path):
        """Second index call with same file returns 'skipped'."""
        indexer.index_file(str(sample_pdf_path))
        result = indexer.index_file(str(sample_pdf_path))
        assert result.status == "skipped"

    def test_index_file_force_reindexes(self, indexer, sample_pdf_path):
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

    def test_index_file_handles_failure_gracefully(self, indexer, indexer_deps, tmp_path):
        """Corrupted/unprocessable file returns 'failed', not crash."""
        bad_pdf = tmp_path / "corrupt.pdf"
        bad_pdf.write_text("not a real pdf")
        indexer_deps["chunker"].chunk_file.side_effect = Exception("Parse error")
        result = indexer.index_file(str(bad_pdf))
        assert result.status == "failed"


class TestIndexFolder:
    """Tests for folder-level indexing."""

    def test_index_folder_counts(self, indexer, tmp_path):
        """Folder with 2 supported files reports indexed=2."""
        (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4 fake2")
        (tmp_path / "c.txt").write_text("ignored")
        result = indexer.index_folder(str(tmp_path))
        assert result.indexed == 2
        assert result.skipped == 0


@pytest.mark.slow
class TestIndexerEndToEnd:
    """End-to-end test with real chunker and embedder."""

    def test_end_to_end_pdf_indexing(self, tmp_config, sample_pdf_path):
        """Real PDF -> real chunks -> real embeddings -> store."""
        from smart_search.chunker import DocumentChunker
        from smart_search.embedder import Embedder

        store = ChunkStore(tmp_config)
        store.initialize()
        chunker = DocumentChunker(tmp_config)
        embedder = Embedder(tmp_config)
        indexer = DocumentIndexer(
            config=tmp_config,
            chunker=chunker,
            embedder=embedder,
            store=store,
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
