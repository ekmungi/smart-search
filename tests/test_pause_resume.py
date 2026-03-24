"""Tests for indexing pause/resume mechanism."""

import sqlite3
import threading
import time
from unittest.mock import MagicMock, patch

from smart_search.indexing_task import IndexingTaskManager


def _make_indexer_with_db(tmp_path):
    """Create a mock indexer with a real SQLite DB for pre-scan."""
    from smart_search.indexer import IndexFileResult

    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS indexed_files (
            source_path TEXT PRIMARY KEY,
            file_hash TEXT,
            chunk_count INTEGER DEFAULT 0,
            indexed_at TEXT,
            needs_ocr INTEGER DEFAULT 0,
            file_mtime REAL,
            file_size INTEGER,
            status TEXT DEFAULT 'indexed',
            error TEXT
        )
    """)
    conn.commit()
    conn.close()

    indexer = MagicMock()
    indexer._config = MagicMock()
    indexer._config.supported_extensions = [".md"]
    indexer._config.sqlite_path = db_path
    indexer._config.embedding_model = "test/model"
    indexer._store = MagicMock()
    indexer._store._config = MagicMock()
    indexer._store._config.sqlite_path = db_path
    indexer.index_file.return_value = IndexFileResult(
        file_path="test.md", status="indexed", chunk_count=1,
    )
    return indexer


def test_initial_state_not_paused():
    """Task manager should start in non-paused state."""
    mgr = IndexingTaskManager()
    assert mgr.is_paused is False


def test_pause_sets_paused_state():
    """Calling pause() should set is_paused to True."""
    mgr = IndexingTaskManager()
    mgr.pause()
    assert mgr.is_paused is True


def test_resume_clears_paused_state():
    """Calling resume() should set is_paused to False."""
    mgr = IndexingTaskManager()
    mgr.pause()
    mgr.resume()
    assert mgr.is_paused is False


@patch("smart_search.embedder.Embedder.is_model_cached", return_value=True)
def test_pause_blocks_indexing_loop(mock_cached, tmp_path):
    """When paused, indexing should block after the current file."""
    mgr = IndexingTaskManager()

    for i in range(5):
        (tmp_path / f"file{i}.md").write_text(f"# File {i}")

    processed_files = []
    process_event = threading.Event()

    def tracking_index_file(path, **kwargs):
        from smart_search.indexer import IndexFileResult
        processed_files.append(path)
        if len(processed_files) == 2:
            mgr.pause()
            process_event.set()
        return IndexFileResult(file_path=path, status="indexed", chunk_count=1)

    indexer = _make_indexer_with_db(tmp_path)
    indexer.index_file.side_effect = tracking_index_file

    task_id = mgr.submit(str(tmp_path), indexer)

    # Wait for pause to be triggered
    process_event.wait(timeout=10)
    time.sleep(0.5)

    # Should have processed ~2-3 files, then blocked
    count_at_pause = len(processed_files)
    assert count_at_pause <= 3

    # Resume and let it finish
    mgr.resume()
    for _ in range(50):
        status = mgr.get_status(task_id)
        if status and status.state != "running":
            break
        time.sleep(0.1)

    assert len(processed_files) == 5
