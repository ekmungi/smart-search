"""Tests for model readiness gate in indexing task manager."""

import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from smart_search.indexing_task import IndexingTaskManager


def _make_sqlite_db(path: str) -> None:
    """Create a minimal indexed_files SQLite DB at the given path.

    Args:
        path: File path for the SQLite database.
    """
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS indexed_files (
        source_path TEXT PRIMARY KEY,
        file_hash   TEXT NOT NULL,
        chunk_count INTEGER NOT NULL,
        indexed_at  TEXT NOT NULL,
        needs_ocr   INTEGER DEFAULT 0,
        file_size   INTEGER DEFAULT NULL,
        file_mtime  REAL DEFAULT NULL,
        status      TEXT DEFAULT NULL,
        error       TEXT DEFAULT NULL
    )""")
    conn.commit()
    conn.close()


def _make_mock_indexer(sqlite_path: str):
    """Create a mock indexer for testing with a real SQLite pre-scan DB.

    Args:
        sqlite_path: Path to a pre-created SQLite DB for pre-scan queries.

    Returns:
        Configured MagicMock indexer.
    """
    from smart_search.indexer import IndexFileResult
    indexer = MagicMock()
    indexer._config = MagicMock()
    indexer._config.supported_extensions = [".md", ".txt", ".csv"]
    indexer._config.sqlite_path = sqlite_path
    indexer._config.embedding_model = "test/model"
    # _store._config.sqlite_path is used by the prescan connection
    indexer._store._config.sqlite_path = sqlite_path
    indexer.index_file.return_value = IndexFileResult(
        file_path="test.md", status="indexed", chunk_count=5,
    )
    return indexer


@patch("smart_search.embedder.Embedder.is_model_cached", return_value=False)
def test_indexing_skips_vector_files_when_model_not_cached(mock_cached, tmp_path):
    """When model not cached, only KEYWORD_ONLY_EXTENSIONS files processed."""
    mgr = IndexingTaskManager()
    (tmp_path / "test.md").write_text("# Hello")
    (tmp_path / "data.csv").write_text("a,b\n1,2")

    db_path = str(tmp_path / "index.db")
    _make_sqlite_db(db_path)
    indexer = _make_mock_indexer(db_path)
    task_id = mgr.submit(str(tmp_path), indexer)

    for _ in range(50):
        status = mgr.get_status(task_id)
        if status and status.state != "running":
            break
        time.sleep(0.1)

    calls = indexer.index_file.call_args_list
    processed_paths = [str(c.args[0]) for c in calls]
    # .csv should be processed (keyword-only)
    assert any("data.csv" in p for p in processed_paths)
    # .md should NOT be processed (needs embeddings)
    assert not any(p.endswith("test.md") for p in processed_paths)


@patch("smart_search.embedder.Embedder.is_model_cached", return_value=True)
def test_indexing_processes_all_files_when_model_cached(mock_cached, tmp_path):
    """When model is cached, all files processed normally."""
    mgr = IndexingTaskManager()
    (tmp_path / "test.md").write_text("# Hello")
    (tmp_path / "data.csv").write_text("a,b\n1,2")

    db_path = str(tmp_path / "index.db")
    _make_sqlite_db(db_path)
    indexer = _make_mock_indexer(db_path)
    task_id = mgr.submit(str(tmp_path), indexer)

    for _ in range(50):
        status = mgr.get_status(task_id)
        if status and status.state != "running":
            break
        time.sleep(0.1)

    calls = indexer.index_file.call_args_list
    processed_paths = [str(c.args[0]) for c in calls]
    assert any("test.md" in p for p in processed_paths)
    assert any("data.csv" in p for p in processed_paths)
