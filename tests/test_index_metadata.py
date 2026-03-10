"""Tests for index metadata tracking in SQLite."""

import sqlite3

import pytest

from smart_search.index_metadata import IndexMetadata


@pytest.fixture
def db_path(tmp_path):
    """Return a temporary SQLite path."""
    return str(tmp_path / "metadata.db")


@pytest.fixture
def metadata(db_path):
    """Create an initialized IndexMetadata instance."""
    m = IndexMetadata(db_path)
    m.initialize()
    return m


def test_initialize_creates_table(metadata, db_path):
    """initialize() creates the index_metadata table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='index_metadata'"
    )
    assert cursor.fetchone() is not None
    conn.close()


def test_set_and_get(metadata):
    """Can store and retrieve a key-value pair."""
    metadata.set("embedding_model", "nomic-ai/nomic-embed-text-v1.5")
    assert metadata.get("embedding_model") == "nomic-ai/nomic-embed-text-v1.5"


def test_get_missing_key_returns_none(metadata):
    """Getting a non-existent key returns None."""
    assert metadata.get("nonexistent") is None


def test_set_overwrites_existing(metadata):
    """Setting an existing key overwrites the value."""
    metadata.set("embedding_model", "old-model")
    metadata.set("embedding_model", "new-model")
    assert metadata.get("embedding_model") == "new-model"


def test_get_all_returns_dict(metadata):
    """get_all() returns all key-value pairs as a dict."""
    metadata.set("embedding_model", "nomic")
    metadata.set("embedding_dimensions", "256")
    result = metadata.get_all()
    assert result == {"embedding_model": "nomic", "embedding_dimensions": "256"}


def test_check_mismatch_detects_difference(metadata):
    """check_mismatch returns mismatched keys."""
    metadata.set("embedding_model", "nomic")
    metadata.set("embedding_dimensions", "256")
    mismatches = metadata.check_mismatch(
        {"embedding_model": "nomic", "embedding_dimensions": "768"}
    )
    assert "embedding_dimensions" in mismatches
    assert mismatches["embedding_dimensions"] == ("256", "768")


def test_check_mismatch_returns_empty_when_matching(metadata):
    """check_mismatch returns empty dict when config matches index."""
    metadata.set("embedding_model", "nomic")
    mismatches = metadata.check_mismatch({"embedding_model": "nomic"})
    assert mismatches == {}


def test_clear_removes_all(metadata):
    """clear() removes all metadata entries."""
    metadata.set("key1", "val1")
    metadata.clear()
    assert metadata.get_all() == {}
