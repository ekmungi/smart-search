"""Tests for auto-retry of failed files when model becomes available."""

import time
from unittest.mock import MagicMock, patch

from smart_search.indexing_task import IndexingTaskManager


def test_model_watcher_starts_when_model_unavailable():
    """When model is not cached, watcher thread should start."""
    mgr = IndexingTaskManager()
    store = MagicMock()
    config_mgr = MagicMock()
    config_mgr.list_watch_dirs.return_value = []

    with patch("smart_search.embedder.Embedder.is_model_cached", return_value=False):
        mgr.start_model_watcher("test/model", store, config_mgr, MagicMock())

    assert mgr._model_watcher_active is True
    mgr.stop_model_watcher()


def test_model_watcher_clears_failed_on_availability():
    """When model transitions to cached, failed files should be cleared."""
    mgr = IndexingTaskManager()
    store = MagicMock()
    store.clear_failed_status.return_value = 3
    config_mgr = MagicMock()
    config_mgr.list_watch_dirs.return_value = ["/test/folder"]
    indexer = MagicMock()

    cache_returns = [False, False, True]

    with patch(
        "smart_search.embedder.Embedder.is_model_cached",
        side_effect=cache_returns,
    ):
        mgr.start_model_watcher(
            "test/model", store, config_mgr, indexer, check_interval=0.1,
        )
        time.sleep(1.0)

    store.clear_failed_status.assert_called_once()
    mgr.stop_model_watcher()


def test_model_watcher_does_not_start_when_model_cached():
    """When model is already cached, watcher should not start."""
    mgr = IndexingTaskManager()
    store = MagicMock()
    config_mgr = MagicMock()

    with patch("smart_search.embedder.Embedder.is_model_cached", return_value=True):
        mgr.start_model_watcher("test/model", store, config_mgr, MagicMock())

    assert mgr._model_watcher_active is False
