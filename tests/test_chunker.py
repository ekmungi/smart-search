# Tests for DocumentChunker: Docling-based document chunking.

import json

import pytest

from smart_search.chunker import DocumentChunker


class TestChunkerFast:
    """Fast tests that do not require Docling model loading."""

    def test_unsupported_extension_raises(self, tmp_config, tmp_path):
        """ValueError raised for unsupported file extension."""
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("hello")
        chunker = DocumentChunker(tmp_config)
        with pytest.raises(ValueError, match="Unsupported"):
            chunker.chunk_file(str(txt_file))

    def test_missing_file_raises(self, tmp_config):
        """FileNotFoundError raised for non-existent file."""
        chunker = DocumentChunker(tmp_config)
        with pytest.raises(FileNotFoundError):
            chunker.chunk_file("/nonexistent/file.pdf")


@pytest.mark.slow
class TestChunkerSlow:
    """Slow tests that load Docling and process real files."""

    @pytest.fixture(autouse=True)
    def setup_chunker(self, tmp_config):
        """Create chunker instance."""
        self.chunker = DocumentChunker(tmp_config)

    def test_chunk_file_pdf_returns_chunks(self, sample_pdf_path):
        """PDF produces at least 1 chunk."""
        chunks = self.chunker.chunk_file(str(sample_pdf_path))
        assert len(chunks) >= 1

    def test_docx_chunks(self, sample_docx_path):
        """DOCX produces chunks with source_type='docx'."""
        chunks = self.chunker.chunk_file(str(sample_docx_path))
        assert len(chunks) >= 1
        assert all(c.source_type == "docx" for c in chunks)

    def test_chunk_fields_populated(self, sample_pdf_path):
        """Each chunk has non-empty text, source_path, source_type."""
        chunks = self.chunker.chunk_file(str(sample_pdf_path))
        for chunk in chunks:
            assert chunk.text.strip()
            assert chunk.source_path
            assert chunk.source_type in ("pdf", "docx")

    def test_chunk_ids_unique(self, sample_pdf_path):
        """All chunk IDs within a file are unique."""
        chunks = self.chunker.chunk_file(str(sample_pdf_path))
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_ids_deterministic(self, sample_pdf_path):
        """Same file chunked twice produces same IDs."""
        chunks_a = self.chunker.chunk_file(str(sample_pdf_path))
        chunks_b = self.chunker.chunk_file(str(sample_pdf_path))
        ids_a = [c.id for c in chunks_a]
        ids_b = [c.id for c in chunks_b]
        assert ids_a == ids_b

    def test_embedding_empty_at_chunk_stage(self, sample_pdf_path):
        """Embeddings are empty lists at chunking stage."""
        chunks = self.chunker.chunk_file(str(sample_pdf_path))
        assert all(c.embedding == [] for c in chunks)

    def test_section_path_is_valid_json(self, sample_pdf_path):
        """section_path is a parseable JSON array."""
        chunks = self.chunker.chunk_file(str(sample_pdf_path))
        for chunk in chunks:
            parsed = json.loads(chunk.section_path)
            assert isinstance(parsed, list)
