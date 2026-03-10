# Tests for ephemeral_store: folder-local index factory functions.

from pathlib import Path

import pytest

from smart_search.ephemeral_store import (
    calculate_ephemeral_size,
    create_ephemeral_components,
    ephemeral_index_exists,
    remove_ephemeral_index,
)


@pytest.fixture
def target_folder(tmp_path):
    """Create a temporary folder with a sample Markdown file."""
    md_file = tmp_path / "notes.md"
    md_file.write_text("# Hello\n\nThis is a test note.")
    return tmp_path


class TestCreateEphemeralComponents:
    """Tests for create_ephemeral_components factory function."""

    def test_creates_smart_search_dir(self, target_folder):
        """create_ephemeral_components creates .smart-search/ inside folder."""
        create_ephemeral_components(str(target_folder))
        assert (target_folder / ".smart-search").is_dir()

    def test_returns_store_and_indexer_and_engine(self, target_folder):
        """Returned dict contains store, indexer, engine, and config keys."""
        result = create_ephemeral_components(str(target_folder))
        assert set(result.keys()) == {"store", "indexer", "engine", "config"}

    def test_store_uses_local_paths(self, target_folder):
        """Config paths point inside the .smart-search/ subdirectory."""
        result = create_ephemeral_components(str(target_folder))
        config = result["config"]
        smart_search_dir = str(target_folder / ".smart-search")
        assert config.lancedb_path.startswith(smart_search_dir)
        assert config.sqlite_path.startswith(smart_search_dir)

    def test_raises_for_nonexistent_folder(self, tmp_path):
        """ValueError raised when folder_path does not exist."""
        missing = str(tmp_path / "does_not_exist")
        with pytest.raises(ValueError, match="not a directory"):
            create_ephemeral_components(missing)


class TestEphemeralIndexExists:
    """Tests for ephemeral_index_exists predicate."""

    def test_ephemeral_index_exists_true(self, target_folder):
        """Returns True when .smart-search/ directory exists."""
        (target_folder / ".smart-search").mkdir()
        assert ephemeral_index_exists(str(target_folder)) is True

    def test_ephemeral_index_exists_false(self, target_folder):
        """Returns False when .smart-search/ directory does not exist."""
        assert ephemeral_index_exists(str(target_folder)) is False


class TestCalculateEphemeralSize:
    """Tests for calculate_ephemeral_size utility."""

    def test_calculate_ephemeral_size_empty(self, target_folder):
        """Returns 0 when .smart-search/ does not exist."""
        assert calculate_ephemeral_size(str(target_folder)) == 0

    def test_calculate_ephemeral_size_with_files(self, target_folder):
        """Returns total bytes of files inside .smart-search/."""
        smart_dir = target_folder / ".smart-search"
        smart_dir.mkdir()
        (smart_dir / "data.bin").write_bytes(b"x" * 100)
        size = calculate_ephemeral_size(str(target_folder))
        assert size == 100


class TestRemoveEphemeralIndex:
    """Tests for remove_ephemeral_index cleanup function."""

    def test_remove_ephemeral_index_deletes_dir(self, target_folder):
        """Deletes .smart-search/ and returns True."""
        smart_dir = target_folder / ".smart-search"
        smart_dir.mkdir()
        result = remove_ephemeral_index(str(target_folder))
        assert result is True
        assert not smart_dir.exists()

    def test_remove_ephemeral_index_returns_false_when_missing(self, target_folder):
        """Returns False when .smart-search/ does not exist."""
        result = remove_ephemeral_index(str(target_folder))
        assert result is False
