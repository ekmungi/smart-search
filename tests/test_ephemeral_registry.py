# Tests for EphemeralRegistry: CRUD operations and stale pruning logic.
import sqlite3
import time
import pytest

from smart_search.ephemeral_registry import EphemeralEntry, EphemeralRegistry


@pytest.fixture
def registry(tmp_path):
    """Create an initialized EphemeralRegistry backed by a temp SQLite DB."""
    reg = EphemeralRegistry(str(tmp_path / "metadata.db"))
    reg.initialize()
    return reg


def test_initialize_creates_table(tmp_path):
    """Verify that initialize() creates the ephemeral_indexes table in SQLite."""
    db_path = str(tmp_path / "metadata.db")
    reg = EphemeralRegistry(db_path)
    reg.initialize()

    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ephemeral_indexes'"
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "ephemeral_indexes"


def test_register_and_get(registry, tmp_path):
    """Register an entry and retrieve it; verify all fields are populated."""
    folder = str(tmp_path / "vault")
    registry.register(folder, chunk_count=10, size_bytes=2048)

    entry = registry.get(folder)

    assert entry is not None
    assert entry.folder_path == folder
    assert entry.chunk_count == 10
    assert entry.size_bytes == 2048
    assert entry.created_at != ""
    assert entry.last_accessed != ""


def test_register_updates_existing(registry, tmp_path):
    """Re-registering the same path replaces the row; only one entry should exist."""
    folder = str(tmp_path / "vault")
    registry.register(folder, chunk_count=5, size_bytes=100)
    registry.register(folder, chunk_count=20, size_bytes=500)

    all_entries = registry.list_all()
    assert len(all_entries) == 1

    entry = registry.get(folder)
    assert entry.chunk_count == 20
    assert entry.size_bytes == 500


def test_deregister_returns_true_when_found(registry, tmp_path):
    """Deregistering an existing path returns True and the entry is gone."""
    folder = str(tmp_path / "vault")
    registry.register(folder, chunk_count=1, size_bytes=64)

    result = registry.deregister(folder)

    assert result is True
    assert registry.get(folder) is None


def test_deregister_returns_false_when_not_found(registry, tmp_path):
    """Deregistering a path that was never registered returns False."""
    folder = str(tmp_path / "nonexistent")
    result = registry.deregister(folder)
    assert result is False


def test_list_all_empty(registry):
    """list_all() on a fresh registry returns an empty list."""
    assert registry.list_all() == []


def test_list_all_multiple(registry, tmp_path):
    """Registering two entries returns both from list_all()."""
    folder_a = str(tmp_path / "vault_a")
    folder_b = str(tmp_path / "vault_b")
    registry.register(folder_a, chunk_count=3, size_bytes=300)
    registry.register(folder_b, chunk_count=7, size_bytes=700)

    entries = registry.list_all()
    paths = {e.folder_path for e in entries}

    assert len(entries) == 2
    assert folder_a in paths
    assert folder_b in paths


def test_touch_updates_last_accessed(registry, tmp_path):
    """touch() updates last_accessed to a later timestamp than created_at."""
    folder = str(tmp_path / "vault")
    registry.register(folder, chunk_count=1, size_bytes=64)

    before = registry.get(folder).last_accessed
    # Small sleep so UTC timestamp advances at least 1 second
    time.sleep(1.1)
    registry.touch(folder)
    after = registry.get(folder).last_accessed

    assert after > before


def test_prune_stale_removes_missing_folders(registry, tmp_path):
    """prune_stale() removes entries whose .smart-search/ sub-dir does not exist."""
    folder = str(tmp_path / "missing_vault")
    # Register without creating the folder or its .smart-search/ subdir
    registry.register(folder, chunk_count=5, size_bytes=512)

    pruned = registry.prune_stale()

    assert folder in pruned
    assert registry.get(folder) is None


def test_prune_stale_keeps_existing_folders(registry, tmp_path):
    """prune_stale() keeps entries whose .smart-search/ sub-dir exists on disk."""
    folder = tmp_path / "live_vault"
    smart_search_dir = folder / ".smart-search"
    smart_search_dir.mkdir(parents=True)

    registry.register(str(folder), chunk_count=5, size_bytes=512)

    pruned = registry.prune_stale()

    assert str(folder) not in pruned
    assert registry.get(str(folder)) is not None
