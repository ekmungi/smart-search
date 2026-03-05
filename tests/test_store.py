# Tests for ChunkStore: LanceDB vector storage + SQLite metadata.

import numpy as np
import pytest

from smart_search.models import Chunk, generate_chunk_id
from smart_search.store import ChunkStore


def _make_chunk(source_path="/docs/test.pdf", idx=0, embedding=None):
    """Helper to create a Chunk with a deterministic embedding."""
    if embedding is None:
        rng = np.random.RandomState(idx)
        embedding = rng.randn(768).tolist()
    return Chunk(
        id=generate_chunk_id(source_path, idx),
        source_path=source_path,
        source_type="pdf",
        content_type="text",
        text=f"Chunk number {idx} from {source_path}.",
        page_number=idx + 1,
        section_path='["Section 1"]',
        embedding=embedding,
        has_image=False,
        image_path=None,
        entity_tags=None,
        source_title="Test Doc",
        source_date=None,
        indexed_at="2026-03-05T00:00:00Z",
        model_name="nomic-ai/nomic-embed-text-v1.5",
    )


@pytest.fixture
def initialized_store(tmp_config):
    """ChunkStore backed by tmp_path, initialized and ready."""
    store = ChunkStore(tmp_config)
    store.initialize()
    return store


class TestStoreInitialization:
    """Tests for store initialization and idempotency."""

    def test_initialize_creates_lancedb_table(self, tmp_config):
        """initialize() creates the LanceDB table."""
        store = ChunkStore(tmp_config)
        store.initialize()
        stats = store.get_stats()
        assert stats.chunk_count == 0

    def test_initialize_is_idempotent(self, tmp_config):
        """Calling initialize() twice does not error."""
        store = ChunkStore(tmp_config)
        store.initialize()
        store.initialize()
        stats = store.get_stats()
        assert stats.chunk_count == 0


class TestStoreOperations:
    """Tests for CRUD operations on chunks."""

    def test_upsert_and_retrieve(self, initialized_store):
        """3 chunks inserted, 3 retrieved for the same file."""
        chunks = [_make_chunk(idx=i) for i in range(3)]
        initialized_store.upsert_chunks(chunks)
        retrieved = initialized_store.get_chunks_for_file("/docs/test.pdf")
        assert len(retrieved) == 3

    def test_upsert_replaces_existing(self, initialized_store):
        """Upserting same chunk ID twice results in 1 stored chunk."""
        chunk_v1 = _make_chunk(idx=0)
        chunk_v2 = _make_chunk(idx=0)
        initialized_store.upsert_chunks([chunk_v1])
        initialized_store.upsert_chunks([chunk_v2])
        retrieved = initialized_store.get_chunks_for_file("/docs/test.pdf")
        assert len(retrieved) == 1

    def test_delete_chunks_for_file(self, initialized_store):
        """Delete removes all chunks for a given file."""
        chunks = [_make_chunk(idx=i) for i in range(3)]
        initialized_store.upsert_chunks(chunks)
        count = initialized_store.delete_chunks_for_file("/docs/test.pdf")
        assert count == 3
        retrieved = initialized_store.get_chunks_for_file("/docs/test.pdf")
        assert len(retrieved) == 0


class TestVectorSearch:
    """Tests for vector similarity search."""

    def test_vector_search_returns_ranked_results(self, initialized_store):
        """Search returns results ranked by similarity (closest first)."""
        # Create chunks with known embeddings
        target = [1.0] * 768
        close = [0.9] * 768
        far = [0.0] * 768

        chunks = [
            _make_chunk(idx=0, embedding=far),
            _make_chunk(idx=1, embedding=close),
            _make_chunk(idx=2, embedding=target),
        ]
        initialized_store.upsert_chunks(chunks)

        results = initialized_store.vector_search(target, limit=3)
        assert len(results) >= 2
        # First result should be the closest match
        assert results[0].score >= results[1].score


class TestStoreStats:
    """Tests for stats and file tracking."""

    def test_get_stats_counts(self, initialized_store):
        """Stats reflect correct document and chunk counts."""
        chunks_a = [_make_chunk(source_path="/docs/a.pdf", idx=i) for i in range(2)]
        chunks_b = [_make_chunk(source_path="/docs/b.pdf", idx=i) for i in range(3)]
        initialized_store.upsert_chunks(chunks_a)
        initialized_store.upsert_chunks(chunks_b)
        stats = initialized_store.get_stats()
        assert stats.chunk_count == 5
        assert stats.document_count == 2

    def test_is_file_indexed_false_initially(self, initialized_store):
        """A file that was never indexed returns False."""
        assert not initialized_store.is_file_indexed("/docs/new.pdf", "abc123")

    def test_record_and_check_file_indexed(self, initialized_store):
        """After recording, is_file_indexed returns True for same hash."""
        initialized_store.record_file_indexed("/docs/a.pdf", "hash123", 5)
        assert initialized_store.is_file_indexed("/docs/a.pdf", "hash123")

    def test_record_different_hash_returns_false(self, initialized_store):
        """Changed file hash means the file needs re-indexing."""
        initialized_store.record_file_indexed("/docs/a.pdf", "hash_v1", 5)
        assert not initialized_store.is_file_indexed("/docs/a.pdf", "hash_v2")
