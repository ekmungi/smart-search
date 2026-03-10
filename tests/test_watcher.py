# Tests for FileWatcher: watchdog-based directory monitoring.

import time
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from smart_search.config import SmartSearchConfig
from smart_search.watcher import FileWatcher


@pytest.fixture
def watcher_config(tmp_path):
    """Config with a temporary watch directory."""
    watch_dir = tmp_path / "vault"
    watch_dir.mkdir()
    return SmartSearchConfig(
        lancedb_path=str(tmp_path / "vectors"),
        sqlite_path=str(tmp_path / "metadata.db"),
        watch_directories=[str(watch_dir)],
        watcher_debounce_seconds=0.1,
        min_chunk_length=0,
    )


@pytest.fixture
def mock_indexer():
    """Mock DocumentIndexer."""
    indexer = MagicMock()
    indexer.index_file.return_value = MagicMock(status="indexed", chunk_count=3)
    return indexer


@pytest.fixture
def mock_store():
    """Mock ChunkStore."""
    return MagicMock()


@pytest.fixture
def watcher(watcher_config, mock_indexer, mock_store):
    """FileWatcher with mocked dependencies, auto-stopped after test."""
    w = FileWatcher(watcher_config, mock_indexer, mock_store)
    yield w
    w.stop()


class TestFileWatcher:
    """Tests for file watcher event handling."""

    def test_start_and_stop(self, watcher):
        """Watcher starts and stops without error."""
        watcher.start()
        assert watcher.is_running
        watcher.stop()
        assert not watcher.is_running

    def test_new_md_file_triggers_indexing(self, watcher, watcher_config, mock_indexer):
        """Creating a .md file triggers index_file."""
        watcher.start()
        watch_dir = Path(watcher_config.watch_directories[0])
        md_file = watch_dir / "new_note.md"
        md_file.write_text("# Hello\nContent here", encoding="utf-8")
        time.sleep(0.5)  # Wait for debounce + event processing
        mock_indexer.index_file.assert_called()
        call_path = mock_indexer.index_file.call_args[0][0]
        assert "new_note.md" in call_path

    def test_new_pdf_file_triggers_indexing(self, watcher, watcher_config, mock_indexer):
        """Creating a .pdf file triggers index_file."""
        watcher.start()
        watch_dir = Path(watcher_config.watch_directories[0])
        pdf_file = watch_dir / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")
        time.sleep(0.5)
        mock_indexer.index_file.assert_called()

    def test_unsupported_extension_ignored(self, watcher, watcher_config, mock_indexer):
        """Creating a .txt file does NOT trigger indexing."""
        watcher.start()
        watch_dir = Path(watcher_config.watch_directories[0])
        txt_file = watch_dir / "readme.txt"
        txt_file.write_text("hello", encoding="utf-8")
        time.sleep(0.5)
        mock_indexer.index_file.assert_not_called()

    def test_excluded_directory_ignored(self, watcher, watcher_config, mock_indexer):
        """Files in .git/ are not indexed."""
        watcher.start()
        watch_dir = Path(watcher_config.watch_directories[0])
        git_dir = watch_dir / ".git"
        git_dir.mkdir()
        md_file = git_dir / "config.md"
        md_file.write_text("# Git config", encoding="utf-8")
        time.sleep(0.5)
        mock_indexer.index_file.assert_not_called()

    def test_deleted_file_removes_chunks(self, watcher, watcher_config, mock_store):
        """Deleting a .md file calls delete_chunks_for_file and remove_file_record."""
        watch_dir = Path(watcher_config.watch_directories[0])
        md_file = watch_dir / "to_delete.md"
        md_file.write_text("# Will be deleted", encoding="utf-8")
        watcher.start()
        time.sleep(0.3)  # Let create event settle
        mock_store.reset_mock()
        md_file.unlink()
        time.sleep(0.5)
        mock_store.delete_chunks_for_file.assert_called()
        mock_store.remove_file_record.assert_called()

    def test_modified_file_triggers_reindex(self, watcher, watcher_config, mock_indexer):
        """Modifying a .md file triggers index_file."""
        watch_dir = Path(watcher_config.watch_directories[0])
        md_file = watch_dir / "edit_me.md"
        md_file.write_text("# Original", encoding="utf-8")
        watcher.start()
        time.sleep(0.3)
        mock_indexer.reset_mock()
        md_file.write_text("# Updated content", encoding="utf-8")
        time.sleep(0.5)
        mock_indexer.index_file.assert_called()

    def test_subdirectory_files_detected(self, watcher, watcher_config, mock_indexer):
        """Files in subdirectories are detected (recursive monitoring)."""
        watcher.start()
        watch_dir = Path(watcher_config.watch_directories[0])
        sub = watch_dir / "subfolder"
        sub.mkdir()
        md_file = sub / "deep_note.md"
        md_file.write_text("# Deep note", encoding="utf-8")
        time.sleep(0.5)
        mock_indexer.index_file.assert_called()

    def test_no_watch_directories_does_nothing(self, tmp_path, mock_indexer, mock_store):
        """Watcher with empty watch_directories starts without error."""
        config = SmartSearchConfig(
            lancedb_path=str(tmp_path / "v"),
            sqlite_path=str(tmp_path / "m.db"),
            watch_directories=[],
        )
        w = FileWatcher(config, mock_indexer, mock_store)
        w.start()
        assert w.is_running
        w.stop()


class TestRuntimeWatchManagement:
    """Tests for runtime add/remove of watch directories."""

    def test_watched_directories_property(self, watcher):
        """watched_directories returns list of currently watched paths."""
        watcher.start()
        dirs = watcher.watched_directories
        assert isinstance(dirs, list)
        assert len(dirs) == 1  # One dir from fixture

    def test_add_directory_at_runtime(self, watcher, tmp_path):
        """add_directory starts watching a new directory without restart."""
        new_dir = tmp_path / "new_folder"
        new_dir.mkdir()
        watcher.start()
        watcher.add_directory(str(new_dir))
        assert str(new_dir.resolve()) in watcher.watched_directories

    def test_remove_directory_at_runtime(self, watcher):
        """remove_directory stops watching a directory without full restart."""
        watcher.start()
        initial_count = len(watcher.watched_directories)
        assert initial_count > 0
        watcher.remove_directory(watcher.watched_directories[0])
        assert len(watcher.watched_directories) == initial_count - 1

    def test_add_nonexistent_directory_is_noop(self, watcher):
        """Adding a non-existent directory does not crash."""
        watcher.start()
        before = len(watcher.watched_directories)
        watcher.add_directory("/nonexistent/path/12345")
        assert len(watcher.watched_directories) == before

    def test_add_duplicate_directory_is_noop(self, watcher):
        """Adding a directory that's already watched does not duplicate."""
        watcher.start()
        existing = watcher.watched_directories[0]
        before = len(watcher.watched_directories)
        watcher.add_directory(existing)
        assert len(watcher.watched_directories) == before
