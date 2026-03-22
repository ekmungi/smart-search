# Tests for ChunkStore: LanceDB vector storage + SQLite metadata.

from pathlib import Path
from unittest.mock import patch, PropertyMock

import numpy as np
import pytest

from smart_search.constants import UPSERT_BATCH_SIZE
from smart_search.models import Chunk, generate_chunk_id
from smart_search.store import ChunkStore


def _make_chunk(source_path="/docs/test.pdf", idx=0, embedding=None, dims=256):
    """Helper to create a Chunk with a deterministic embedding."""
    if embedding is None:
        rng = np.random.RandomState(idx)
        embedding = rng.randn(dims).tolist()
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


class TestBatchedUpsert:
    """Tests for batched LanceDB upsert (memory management)."""

    def test_upsert_chunks_batched(self, initialized_store):
        """500 chunks are inserted correctly via batching."""
        chunks = [_make_chunk(idx=i) for i in range(500)]
        initialized_store.upsert_chunks(chunks)
        retrieved = initialized_store.get_chunks_for_file("/docs/test.pdf")
        assert len(retrieved) == 500

    def test_upsert_chunks_small_batch_no_issue(self, initialized_store):
        """Fewer than UPSERT_BATCH_SIZE chunks works normally (single batch)."""
        count = UPSERT_BATCH_SIZE - 50
        chunks = [_make_chunk(idx=i) for i in range(count)]
        initialized_store.upsert_chunks(chunks)
        retrieved = initialized_store.get_chunks_for_file("/docs/test.pdf")
        assert len(retrieved) == count

    def test_upsert_chunks_batched_calls_add_multiple_times(self, initialized_store):
        """Batching calls table.add() multiple times for large chunk lists."""
        chunks = [_make_chunk(idx=i) for i in range(UPSERT_BATCH_SIZE + 50)]
        with patch.object(initialized_store._table, "add", wraps=initialized_store._table.add) as mock_add:
            initialized_store.upsert_chunks(chunks)
        # Should call add() at least twice: one full batch + one partial
        assert mock_add.call_count == 2


class TestVectorSearch:
    """Tests for vector similarity search."""

    def test_vector_search_returns_ranked_results(self, initialized_store):
        """Search returns results ranked by similarity (closest first)."""
        # Create chunks with known embeddings (256 dims to match config)
        target = [1.0] * 256
        close = [0.9] * 256
        far = [0.0] * 256

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
        # Record in SQLite (as the indexer does in production)
        initialized_store.record_file_indexed("/docs/a.pdf", "hash_a", 2)
        initialized_store.record_file_indexed("/docs/b.pdf", "hash_b", 3)
        stats = initialized_store.get_stats()
        assert stats.chunk_count == 5
        assert stats.document_count == 2
        assert ".pdf" in stats.formats_indexed

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

    def test_remove_file_record(self, initialized_store):
        """remove_file_record deletes the SQLite indexed_files row."""
        initialized_store.record_file_indexed("/tmp/test.md", "abc123", 5)
        assert initialized_store.is_file_indexed("/tmp/test.md", "abc123")
        initialized_store.remove_file_record("/tmp/test.md")
        assert not initialized_store.is_file_indexed("/tmp/test.md", "abc123")

    def test_remove_file_record_nonexistent_no_error(self, initialized_store):
        """Removing a non-existent record does not raise."""
        initialized_store.remove_file_record("/tmp/does_not_exist.md")


class TestStoreExtensions:
    """Tests for list_indexed_files and remove_files_for_folder."""

    def test_list_indexed_files_returns_all_files(self, initialized_store):
        """list_indexed_files returns all recorded files with metadata."""
        initialized_store.record_file_indexed("C:/docs/file1.pdf", "hash1", 5)
        initialized_store.record_file_indexed("C:/docs/file2.pdf", "hash2", 3)
        files = initialized_store.list_indexed_files()
        assert len(files) == 2
        assert "source_path" in files[0]
        assert "chunk_count" in files[0]
        assert "indexed_at" in files[0]

    def test_list_indexed_files_empty_store(self, initialized_store):
        """list_indexed_files returns empty list when nothing indexed."""
        files = initialized_store.list_indexed_files()
        assert files == []

    def test_remove_files_for_folder(self, initialized_store):
        """remove_files_for_folder removes all files under a folder prefix."""
        initialized_store.record_file_indexed("C:/docs/sub/file1.pdf", "hash1", 2)
        initialized_store.record_file_indexed("C:/docs/other/file2.pdf", "hash2", 3)
        removed = initialized_store.remove_files_for_folder("C:/docs/sub")
        assert removed == 1
        files = initialized_store.list_indexed_files()
        paths = [f["source_path"] for f in files]
        assert "C:/docs/sub/file1.pdf" not in paths
        assert "C:/docs/other/file2.pdf" in paths

    def test_remove_files_for_folder_empty(self, initialized_store):
        """Removing from nonexistent folder returns 0."""
        removed = initialized_store.remove_files_for_folder("C:/nonexistent")
        assert removed == 0


class TestCachedIndexSize:
    """Tests for _get_cached_index_size() time-based caching (B54)."""

    def test_stats_includes_lancedb_size(self, initialized_store):
        """Index size should include LanceDB directory, not just SQLite."""
        # Insert some data so LanceDB has files on disk
        chunks = [_make_chunk(idx=i) for i in range(3)]
        initialized_store.upsert_chunks(chunks)
        initialized_store.record_file_indexed("/docs/test.pdf", "hash", 3)

        # Invalidate the startup cache so get_stats() recalculates
        initialized_store.invalidate_size_cache()
        stats = initialized_store.get_stats()
        # The full index size (LanceDB + SQLite) should be larger
        # than just the SQLite file
        sqlite_size = Path(initialized_store._config.sqlite_path).stat().st_size
        assert stats.index_size_bytes >= sqlite_size

    def test_init_size_cache_calculates_on_startup(self, initialized_store):
        """After initialize(), first get_stats() returns pre-calculated size without recalculating."""
        # _init_size_cache() already called _calculate_index_size() during initialize(),
        # so subsequent get_stats() within 120s should use the cached value.
        with patch.object(initialized_store, "_calculate_index_size") as mock_calc:
            stats = initialized_store.get_stats()
        # Cache is warm from initialize() -- no recalculation needed
        mock_calc.assert_not_called()

    def test_cache_returns_same_value_within_ttl(self, initialized_store):
        """Two calls within 120s only compute index size once."""
        # Invalidate startup cache, then verify caching behavior
        initialized_store.invalidate_size_cache()
        with patch.object(initialized_store, "_calculate_index_size", return_value=1000) as mock_calc:
            size1 = initialized_store._get_cached_index_size()
            size2 = initialized_store._get_cached_index_size()
        assert size1 == size2 == 1000
        mock_calc.assert_called_once()

    def test_cache_refreshes_after_ttl(self, initialized_store):
        """After 120s, the cache is refreshed with a new calculation."""
        initialized_store.invalidate_size_cache()
        with patch.object(initialized_store, "_calculate_index_size", return_value=1000) as mock_calc:
            initialized_store._get_cached_index_size()
            # Simulate 121 seconds passing
            initialized_store._cached_index_size_at -= 121.0
            initialized_store._get_cached_index_size()
        assert mock_calc.call_count == 2

    def test_cache_returns_stale_on_error(self, initialized_store):
        """On error, returns the stale cached value instead of crashing."""
        # Prime the cache
        initialized_store._cached_index_size = 5000
        initialized_store._cached_index_size_at = 0.0  # Force refresh
        with patch.object(initialized_store, "_calculate_index_size", side_effect=OSError("locked")):
            size = initialized_store._get_cached_index_size()
        assert size == 5000


class TestMtimeChangeDetection:
    """Tests for mtime+size fast change detection (is_file_unchanged, update_file_metadata)."""

    def test_is_file_unchanged_true_when_matching(self, initialized_store):
        """Exact mtime+size match returns True (file skipped without hash)."""
        initialized_store.record_file_indexed(
            "/docs/a.pdf", "hash_a", 5,
            file_mtime=1711100000.123, file_size=4096,
        )
        assert initialized_store.is_file_unchanged("/docs/a.pdf", 1711100000.123, 4096)

    def test_is_file_unchanged_false_when_mtime_differs(self, initialized_store):
        """Different mtime triggers hash check even if size is same."""
        initialized_store.record_file_indexed(
            "/docs/a.pdf", "hash_a", 5,
            file_mtime=1711100000.0, file_size=4096,
        )
        assert not initialized_store.is_file_unchanged("/docs/a.pdf", 1711100001.0, 4096)

    def test_is_file_unchanged_false_when_size_differs(self, initialized_store):
        """Different size triggers hash check even if mtime is same."""
        initialized_store.record_file_indexed(
            "/docs/a.pdf", "hash_a", 5,
            file_mtime=1711100000.0, file_size=4096,
        )
        assert not initialized_store.is_file_unchanged("/docs/a.pdf", 1711100000.0, 8192)

    def test_is_file_unchanged_false_when_null(self, initialized_store):
        """Pre-migration rows (NULL mtime/size) trigger hash check."""
        initialized_store.record_file_indexed("/docs/a.pdf", "hash_a", 5)
        assert not initialized_store.is_file_unchanged("/docs/a.pdf", 1711100000.0, 4096)

    def test_is_file_unchanged_false_when_not_indexed(self, initialized_store):
        """File not in index returns False."""
        assert not initialized_store.is_file_unchanged("/docs/new.pdf", 1711100000.0, 4096)

    def test_record_file_indexed_stores_mtime_and_size(self, initialized_store):
        """New mtime+size columns are populated and retrievable."""
        initialized_store.record_file_indexed(
            "/docs/a.pdf", "hash_a", 5,
            file_mtime=1711100000.5, file_size=2048,
        )
        assert initialized_store.is_file_unchanged("/docs/a.pdf", 1711100000.5, 2048)

    def test_update_file_metadata(self, initialized_store):
        """update_file_metadata changes mtime+size without affecting hash."""
        initialized_store.record_file_indexed(
            "/docs/a.pdf", "hash_a", 5,
            file_mtime=1711100000.0, file_size=4096,
        )
        initialized_store.update_file_metadata("/docs/a.pdf", 1711100999.0, 4096)
        # mtime updated -- old mtime no longer matches
        assert not initialized_store.is_file_unchanged("/docs/a.pdf", 1711100000.0, 4096)
        # New mtime matches
        assert initialized_store.is_file_unchanged("/docs/a.pdf", 1711100999.0, 4096)
        # Hash is unchanged
        assert initialized_store.is_file_indexed("/docs/a.pdf", "hash_a")


class TestRecordFileFailed:
    """Tests for recording failed file indexing attempts."""

    def test_record_file_failed_writes_row(self, initialized_store):
        """Failed file is recorded with status='failed' and error message."""
        initialized_store.record_file_failed(
            "/docs/bad.pdf", "hash_bad", "Parse error: corrupt PDF",
            file_mtime=1711100000.0, file_size=4096,
        )
        row = initialized_store._sqlite_conn.execute(
            "SELECT status, error, file_mtime, file_size FROM indexed_files WHERE source_path = ?",
            ("/docs/bad.pdf",),
        ).fetchone()
        assert row[0] == "failed"
        assert row[1] == "Parse error: corrupt PDF"
        assert row[2] == 1711100000.0
        assert row[3] == 4096

    def test_failed_file_is_skipped_by_mtime_check(self, initialized_store):
        """is_file_unchanged returns True for failed files with matching mtime+size."""
        initialized_store.record_file_failed(
            "/docs/bad.pdf", "", "Timeout after 120s",
            file_mtime=1711100000.0, file_size=8192,
        )
        assert initialized_store.is_file_unchanged("/docs/bad.pdf", 1711100000.0, 8192)

    def test_failed_file_retried_when_mtime_changes(self, initialized_store):
        """Changed mtime on a failed file triggers retry."""
        initialized_store.record_file_failed(
            "/docs/bad.pdf", "", "Timeout after 120s",
            file_mtime=1711100000.0, file_size=8192,
        )
        assert not initialized_store.is_file_unchanged("/docs/bad.pdf", 1711100999.0, 8192)

    def test_failed_file_retried_when_size_changes(self, initialized_store):
        """Changed size on a failed file triggers retry."""
        initialized_store.record_file_failed(
            "/docs/bad.pdf", "", "Timeout after 120s",
            file_mtime=1711100000.0, file_size=8192,
        )
        assert not initialized_store.is_file_unchanged("/docs/bad.pdf", 1711100000.0, 16384)

    def test_record_file_failed_with_empty_hash(self, initialized_store):
        """Failed file with empty hash (pre-hash failure) still records correctly."""
        initialized_store.record_file_failed(
            "/docs/bad.pdf", "", "Permission denied",
            file_mtime=1711100000.0, file_size=4096,
        )
        row = initialized_store._sqlite_conn.execute(
            "SELECT file_hash, status FROM indexed_files WHERE source_path = ?",
            ("/docs/bad.pdf",),
        ).fetchone()
        assert row[0] == ""
        assert row[1] == "failed"

    def test_record_file_failed_overwrites_previous_success(self, initialized_store):
        """Re-failing a previously indexed file updates status to 'failed'."""
        initialized_store.record_file_indexed(
            "/docs/a.pdf", "hash_a", 5,
            file_mtime=1711100000.0, file_size=4096,
        )
        initialized_store.record_file_failed(
            "/docs/a.pdf", "hash_a", "Now corrupt",
            file_mtime=1711100999.0, file_size=4096,
        )
        row = initialized_store._sqlite_conn.execute(
            "SELECT status, error FROM indexed_files WHERE source_path = ?",
            ("/docs/a.pdf",),
        ).fetchone()
        assert row[0] == "failed"
        assert row[1] == "Now corrupt"


class TestReconcile:
    """Tests for ChunkStore.reconcile() LanceDB compaction."""

    def test_reconcile_compacts_after_removal(self, initialized_store, tmp_path):
        """Verify LanceDB optimize is attempted when orphans are removed."""
        # Create a file, index it, then delete it
        file_a = tmp_path / "a.md"
        file_a.write_text("Content")
        p = Path(file_a).as_posix()

        chunk = _make_chunk(source_path=p, idx=0)
        initialized_store.upsert_chunks([chunk])
        initialized_store.record_file_indexed(p, "hash", 1)

        # Delete the file from disk
        file_a.unlink()

        # Patch optimize to verify it gets called
        original_table = initialized_store._table
        with patch.object(original_table, "optimize") as mock_compact:
            result = initialized_store.reconcile()

        assert result["removed_count"] == 1
        mock_compact.assert_called_once()

    def test_reconcile_handles_compact_import_error(self, initialized_store, tmp_path):
        """Reconcile succeeds even if optimize raises ImportError."""
        file_a = tmp_path / "a.md"
        file_a.write_text("Content")
        p = Path(file_a).as_posix()

        chunk = _make_chunk(source_path=p, idx=0)
        initialized_store.upsert_chunks([chunk])
        initialized_store.record_file_indexed(p, "hash", 1)

        file_a.unlink()

        # optimize raises ImportError (no pylance)
        original_table = initialized_store._table
        with patch.object(original_table, "optimize", side_effect=ImportError("no pylance")):
            result = initialized_store.reconcile()

        assert result["removed_count"] == 1
        assert len(initialized_store.list_indexed_files()) == 0
