# Tests for the background indexing task manager.

"""Verifies IndexingTaskManager submit, cancel, status, and shutdown
behavior using mock indexers with controllable blocking."""

import threading
import time
from unittest.mock import MagicMock

import pytest

from smart_search.indexing_task import IndexingTaskManager, IndexingStatus


def test_submit_task_returns_task_id():
    """Submitting a folder returns a task ID and tracks the task."""
    mgr = IndexingTaskManager()
    indexer = MagicMock()
    indexer.index_folder.return_value = MagicMock(indexed=5, skipped=0, failed=0)

    task_id = mgr.submit("C:/test/folder", indexer)

    assert task_id is not None
    status = mgr.get_status(task_id)
    assert status is not None
    assert status.folder == "C:/test/folder"
    # Wait for task to complete
    time.sleep(0.5)
    status = mgr.get_status(task_id)
    assert status.state in ("running", "completed")
    mgr.shutdown()


def test_task_completes_with_counts():
    """Completed task reports indexed/skipped/failed counts."""
    mgr = IndexingTaskManager()
    indexer = MagicMock()
    indexer.index_folder.return_value = MagicMock(indexed=3, skipped=2, failed=1)

    task_id = mgr.submit("C:/test/folder", indexer)
    time.sleep(0.5)

    status = mgr.get_status(task_id)
    assert status.state == "completed"
    assert status.indexed == 3
    assert status.skipped == 2
    assert status.failed == 1
    assert status.finished_at is not None
    mgr.shutdown()


def test_cancel_folder_stops_indexing():
    """Cancelling a folder sets the cancel event and marks task cancelled."""
    mgr = IndexingTaskManager()
    indexer = MagicMock()
    cancel_seen = threading.Event()

    def slow_index(folder, cancel_event=None):
        if cancel_event:
            cancel_event.wait(timeout=5)
            cancel_seen.set()
        return MagicMock(indexed=0, skipped=0, failed=0)

    indexer.index_folder.side_effect = slow_index

    task_id = mgr.submit("C:/test/folder", indexer)
    time.sleep(0.1)  # Let thread start

    cancelled = mgr.cancel_folder("C:/test/folder")
    assert cancelled is True

    cancel_seen.wait(timeout=2)
    time.sleep(0.1)
    status = mgr.get_status(task_id)
    assert status.state == "cancelled"
    mgr.shutdown()


def test_submit_same_folder_cancels_previous():
    """Submitting the same folder cancels any existing task."""
    mgr = IndexingTaskManager()
    indexer = MagicMock()

    def slow_index(folder, cancel_event=None):
        if cancel_event:
            cancel_event.wait(timeout=5)
        return MagicMock(indexed=0, skipped=0, failed=0)

    indexer.index_folder.side_effect = slow_index

    task_id_1 = mgr.submit("C:/test/folder", indexer)
    time.sleep(0.1)
    task_id_2 = mgr.submit("C:/test/folder", indexer)

    assert task_id_1 != task_id_2
    time.sleep(0.2)
    status_1 = mgr.get_status(task_id_1)
    assert status_1.state == "cancelled"
    mgr.shutdown()


def test_cancel_nonexistent_folder_returns_false():
    """Cancelling a folder with no active task returns False."""
    mgr = IndexingTaskManager()
    assert mgr.cancel_folder("C:/nonexistent") is False
    mgr.shutdown()


def test_get_all_active():
    """get_all_active returns only running tasks."""
    mgr = IndexingTaskManager()
    indexer = MagicMock()

    def slow_index(folder, cancel_event=None):
        if cancel_event:
            cancel_event.wait(timeout=5)
        return MagicMock(indexed=0, skipped=0, failed=0)

    indexer.index_folder.side_effect = slow_index

    mgr.submit("C:/folder1", indexer)
    mgr.submit("C:/folder2", indexer)
    time.sleep(0.1)

    active = mgr.get_all_active()
    assert len(active) == 2
    assert all(s.state == "running" for s in active)
    mgr.shutdown()


def test_get_folder_status():
    """get_folder_status returns latest task for a folder."""
    mgr = IndexingTaskManager()
    indexer = MagicMock()
    indexer.index_folder.return_value = MagicMock(indexed=1, skipped=0, failed=0)

    mgr.submit("C:/test/folder", indexer)
    time.sleep(0.5)

    status = mgr.get_folder_status("C:/test/folder")
    assert status is not None
    assert status.folder == "C:/test/folder"
    assert mgr.get_folder_status("C:/nonexistent") is None
    mgr.shutdown()


def test_shutdown_cancels_all():
    """shutdown() cancels all active tasks."""
    mgr = IndexingTaskManager()
    indexer = MagicMock()

    def slow_index(folder, cancel_event=None):
        if cancel_event:
            cancel_event.wait(timeout=5)
        return MagicMock(indexed=0, skipped=0, failed=0)

    indexer.index_folder.side_effect = slow_index

    mgr.submit("C:/folder1", indexer)
    mgr.submit("C:/folder2", indexer)
    time.sleep(0.1)

    mgr.shutdown()
    time.sleep(0.3)

    active = mgr.get_all_active()
    assert len(active) == 0


def test_failed_indexing_records_error():
    """When indexer raises, task state is 'failed' with error message."""
    mgr = IndexingTaskManager()
    indexer = MagicMock()
    indexer.index_folder.side_effect = RuntimeError("disk full")

    task_id = mgr.submit("C:/test/folder", indexer)
    time.sleep(0.5)

    status = mgr.get_status(task_id)
    assert status.state == "failed"
    assert "disk full" in status.error
    mgr.shutdown()
