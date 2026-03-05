# Tests for Pydantic data models: Chunk, SearchResult, IndexStats, generate_chunk_id.

import json

import pytest
from pydantic import ValidationError

from smart_search.models import Chunk, IndexStats, SearchResult, generate_chunk_id


def _make_chunk(**overrides):
    """Create a valid Chunk with sensible defaults, overriding any field."""
    defaults = {
        "id": "abc123",
        "source_path": "/docs/test.pdf",
        "source_type": "pdf",
        "content_type": "text",
        "text": "Sample chunk text for testing.",
        "page_number": 1,
        "section_path": '["Chapter 1", "Section 1.2"]',
        "embedding": [0.0] * 768,
        "has_image": False,
        "image_path": None,
        "entity_tags": None,
        "source_title": "Test Document",
        "source_date": None,
        "indexed_at": "2026-03-05T00:00:00Z",
        "model_name": "nomic-ai/nomic-embed-text-v1.5",
    }
    return Chunk(**{**defaults, **overrides})


class TestGenerateChunkId:
    """Tests for deterministic chunk ID generation."""

    def test_chunk_id_is_deterministic(self):
        """Same inputs always produce same id."""
        id_a = generate_chunk_id("/docs/test.pdf", 0)
        id_b = generate_chunk_id("/docs/test.pdf", 0)
        assert id_a == id_b

    def test_chunk_id_differs_for_different_inputs(self):
        """Different inputs produce different ids."""
        id_a = generate_chunk_id("/docs/test.pdf", 0)
        id_b = generate_chunk_id("/docs/test.pdf", 1)
        assert id_a != id_b

    def test_chunk_id_is_hex_string(self):
        """Chunk ID is a valid hex string (SHA-256)."""
        chunk_id = generate_chunk_id("/docs/test.pdf", 0)
        assert len(chunk_id) == 64
        int(chunk_id, 16)  # raises if not valid hex


class TestChunk:
    """Tests for the Chunk Pydantic model."""

    def test_chunk_requires_text(self):
        """Chunk without text raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_chunk(text="")

    def test_chunk_section_path_is_json_string(self):
        """section_path is a valid JSON array string."""
        chunk = _make_chunk()
        parsed = json.loads(chunk.section_path)
        assert isinstance(parsed, list)
        assert parsed == ["Chapter 1", "Section 1.2"]

    def test_chunk_optional_fields_default_none(self):
        """Optional fields accept None."""
        chunk = _make_chunk(image_path=None, entity_tags=None, source_date=None)
        assert chunk.image_path is None
        assert chunk.entity_tags is None
        assert chunk.source_date is None


class TestSearchResult:
    """Tests for the SearchResult wrapper model."""

    def test_search_result_has_rank_and_score(self):
        """SearchResult has correctly typed rank (int) and score (float)."""
        chunk = _make_chunk()
        result = SearchResult(rank=1, score=0.95, chunk=chunk)
        assert isinstance(result.rank, int)
        assert isinstance(result.score, float)
        assert result.rank == 1
        assert result.score == 0.95


class TestIndexStats:
    """Tests for the IndexStats model."""

    def test_index_stats_formats_is_list(self):
        """formats_indexed is a list."""
        stats = IndexStats(
            document_count=10,
            chunk_count=150,
            index_size_bytes=1024000,
            last_indexed_at="2026-03-05T00:00:00Z",
            formats_indexed=["pdf", "docx"],
        )
        assert isinstance(stats.formats_indexed, list)
        assert "pdf" in stats.formats_indexed
