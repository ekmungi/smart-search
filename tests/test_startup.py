# Tests for startup checks: orphan reconciliation and index compatibility.

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_search.config import SmartSearchConfig
from smart_search.index_metadata import IndexMetadata
from smart_search.models import Chunk, generate_chunk_id
from smart_search.startup import check_index_compatibility, reconcile_orphans
from smart_search.store import ChunkStore


def _make_chunk(source_path, idx=0):
    """Create a Chunk with a deterministic embedding for testing."""
    rng = np.random.RandomState(idx)
    return Chunk(
        id=generate_chunk_id(source_path, idx),
        source_path=source_path,
        source_type="md",
        content_type="text",
        text=f"Chunk {idx} from {source_path}.",
        page_number=None,
        section_path='["Root"]',
        embedding=rng.randn(256).tolist(),
        has_image=False,
        image_path=None,
        entity_tags=None,
        source_title="Test",
        source_date=None,
        indexed_at="2026-03-15T00:00:00Z",
        model_name="nomic-ai/nomic-embed-text-v1.5",
    )


@pytest.fixture
def initialized_store(tmp_config):
    """ChunkStore backed by tmp_path, initialized and ready."""
    store = ChunkStore(tmp_config)
    store.initialize()
    return store


class TestReconcileRemovesMissingFiles:
    """Tests for ChunkStore.reconcile() orphan removal."""

    def test_reconcile_removes_missing_files(self, initialized_store, tmp_path):
        """Index 3 files, delete 1 from disk, reconcile removes the orphan."""
        # Create 3 temp files
        file_a = tmp_path / "a.md"
        file_b = tmp_path / "b.md"
        file_c = tmp_path / "c.md"
        for f in (file_a, file_b, file_c):
            f.write_text(f"Content of {f.name}")

        paths = [
            Path(file_a).as_posix(),
            Path(file_b).as_posix(),
            Path(file_c).as_posix(),
        ]

        # Index all 3 files
        for p in paths:
            chunk = _make_chunk(source_path=p, idx=0)
            initialized_store.upsert_chunks([chunk])
            initialized_store.record_file_indexed(p, "hash", 1)

        # Delete file_b from disk
        file_b.unlink()

        # Reconcile
        result = initialized_store.reconcile()

        assert result["removed_count"] == 1
        assert paths[1] in result["removed_files"]

        # Verify only 2 files remain in SQLite
        files = initialized_store.list_indexed_files()
        remaining_paths = [f["source_path"] for f in files]
        assert len(remaining_paths) == 2
        assert paths[1] not in remaining_paths

    def test_reconcile_no_orphans(self, initialized_store, tmp_path):
        """When all indexed files exist, reconcile removes nothing."""
        file_a = tmp_path / "a.md"
        file_a.write_text("Content")
        p = Path(file_a).as_posix()

        chunk = _make_chunk(source_path=p, idx=0)
        initialized_store.upsert_chunks([chunk])
        initialized_store.record_file_indexed(p, "hash", 1)

        result = initialized_store.reconcile()

        assert result["removed_count"] == 0
        assert result["removed_files"] == []

    def test_reconcile_empty_index(self, initialized_store):
        """Empty store reconciles with no errors and zero removals."""
        result = initialized_store.reconcile()

        assert result["removed_count"] == 0
        assert result["removed_files"] == []


class TestCheckIndexCompatibility:
    """Tests for check_index_compatibility startup check."""

    def test_compatible_when_no_metadata(self, tmp_config):
        """Fresh DB with no stored metadata is considered compatible."""
        result = check_index_compatibility(tmp_config, tmp_config.sqlite_path)

        assert result["compatible"] is True
        assert result["mismatches"] == {}

    def test_compatible_when_matching(self, tmp_config):
        """Stored metadata matching current config returns compatible."""
        # Pre-populate metadata
        meta = IndexMetadata(tmp_config.sqlite_path)
        meta.initialize()
        meta.set("embedding_model", tmp_config.embedding_model)
        meta.set("embedding_dimensions", str(tmp_config.embedding_dimensions))

        result = check_index_compatibility(tmp_config, tmp_config.sqlite_path)

        assert result["compatible"] is True
        assert result["mismatches"] == {}

    def test_incompatible_on_model_change(self, tmp_config):
        """Changed model name is detected as incompatible."""
        # Store old model name
        meta = IndexMetadata(tmp_config.sqlite_path)
        meta.initialize()
        meta.set("embedding_model", "old-model/v1")
        meta.set("embedding_dimensions", str(tmp_config.embedding_dimensions))

        result = check_index_compatibility(tmp_config, tmp_config.sqlite_path)

        assert result["compatible"] is False
        assert "embedding_model" in result["mismatches"]
        stored, current = result["mismatches"]["embedding_model"]
        assert stored == "old-model/v1"
        assert current == tmp_config.embedding_model


class TestReconcileOrphansWrapper:
    """Tests for the reconcile_orphans convenience function."""

    def test_reconcile_orphans_delegates_to_store(self, initialized_store, tmp_path):
        """reconcile_orphans calls store.reconcile and returns its result."""
        file_a = tmp_path / "a.md"
        file_a.write_text("Content")
        p = Path(file_a).as_posix()

        chunk = _make_chunk(source_path=p, idx=0)
        initialized_store.upsert_chunks([chunk])
        initialized_store.record_file_indexed(p, "hash", 1)

        # Delete the file
        file_a.unlink()

        result = reconcile_orphans(initialized_store)

        assert result["removed_count"] == 1
        assert p in result["removed_files"]
