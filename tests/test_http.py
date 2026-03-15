# Tests for the HTTP REST API server.

"""Comprehensive tests for all API endpoints using FastAPI TestClient
with mocked backend components. No real embeddings or databases."""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from smart_search.config import SmartSearchConfig
from smart_search.http import create_app
from smart_search.indexer import IndexFileResult, IndexFolderResult
from smart_search.indexing_task import IndexingStatus, IndexingTaskManager
from smart_search.models import Chunk, IndexStats, SearchResult


def _make_config(**overrides):
    """Create a test SmartSearchConfig with temp paths."""
    return SmartSearchConfig(
        lancedb_path="C:/tmp/test-vectors",
        sqlite_path="C:/tmp/test-meta.db",
        **overrides,
    )


def _make_chunk(**overrides):
    """Create a test Chunk with sensible defaults."""
    defaults = {
        "id": "test-chunk-1",
        "source_path": "C:/docs/test.md",
        "source_type": "md",
        "content_type": "text",
        "text": "Test chunk content about knowledge management",
        "section_path": '["Introduction"]',
        "embedding": [0.1] * 256,
        "indexed_at": "2026-03-14T10:00:00Z",
        "model_name": "nomic-ai/nomic-embed-text-v1.5",
    }
    defaults.update(overrides)
    return Chunk(**defaults)


@pytest.fixture
def mock_store():
    """Mock ChunkStore with realistic return values."""
    store = MagicMock()
    store.get_stats.return_value = IndexStats(
        document_count=5,
        chunk_count=42,
        index_size_bytes=1048576,
        last_indexed_at="2026-03-14T10:00:00Z",
        formats_indexed=["md", "pdf"],
    )
    store.list_indexed_files.return_value = [
        {
            "source_path": "C:/docs/test.md",
            "file_hash": "abc123",
            "chunk_count": 3,
            "indexed_at": "2026-03-14T10:00:00Z",
        },
    ]
    store.remove_files_for_folder.return_value = 2
    return store


@pytest.fixture
def mock_engine():
    """Mock SearchEngine returning one result by default."""
    engine = MagicMock()
    chunk = _make_chunk()
    engine.search_results.return_value = [
        SearchResult(rank=1, score=0.95, chunk=chunk),
    ]
    return engine


@pytest.fixture
def mock_indexer():
    """Mock DocumentIndexer with standard results."""
    indexer = MagicMock()
    indexer.index_file.return_value = IndexFileResult(
        file_path="C:/docs/test.md", status="indexed", chunk_count=3,
    )
    indexer.index_folder.return_value = IndexFolderResult(
        indexed=5, skipped=2, failed=0, results=[],
    )
    return indexer


@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager with two watch directories."""
    mgr = MagicMock()
    mgr.list_watch_dirs.return_value = ["C:/docs", "C:/notes"]
    mgr.load.return_value = {
        "watch_directories": ["C:/docs", "C:/notes"],
        "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
        "embedding_dimensions": "768",
    }
    return mgr


@pytest.fixture
def mock_watcher():
    """Mock FileWatcher in stopped state."""
    watcher = MagicMock()
    watcher.is_running = False
    return watcher


@pytest.fixture
def mock_task_manager():
    """Mock IndexingTaskManager with controllable returns."""
    mgr = MagicMock(spec=IndexingTaskManager)
    mgr.submit.return_value = "abc12345"
    mgr.get_all_tasks.return_value = []
    mgr.cancel_folder.return_value = True
    return mgr


@pytest.fixture
def client(
    mock_store, mock_engine, mock_indexer,
    mock_config_manager, mock_watcher, mock_task_manager,
):
    """FastAPI TestClient wired to mocked components."""
    config = _make_config()
    app = create_app(
        search_engine=mock_engine,
        store=mock_store,
        config=config,
        indexer=mock_indexer,
        config_manager=mock_config_manager,
        watcher=mock_watcher,
        task_manager=mock_task_manager,
    )
    return TestClient(app)


class TestHealth:
    """Tests for GET /api/health."""

    def test_returns_ok_status(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.7.0"

    def test_includes_uptime(self, client):
        resp = client.get("/api/health")
        assert "uptime_seconds" in resp.json()
        assert resp.json()["uptime_seconds"] >= 0


class TestStats:
    """Tests for GET /api/stats."""

    def test_returns_index_statistics(self, client, mock_store):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_count"] == 5
        assert data["chunk_count"] == 42
        assert data["index_size_bytes"] == 1048576
        assert data["index_size_mb"] == 1.0
        assert data["formats_indexed"] == ["md", "pdf"]
        assert data["last_indexed_at"] == "2026-03-14T10:00:00Z"
        mock_store.get_stats.assert_called_once()


class TestSearch:
    """Tests for GET /api/search."""

    def test_returns_search_results(self, client, mock_engine):
        resp = client.get("/api/search?q=knowledge")
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "knowledge"
        assert data["mode"] == "semantic"
        assert data["total"] == 1
        assert len(data["results"]) == 1
        hit = data["results"][0]
        assert hit["rank"] == 1
        assert hit["score"] == 0.95
        assert hit["filename"] == "test.md"

    def test_empty_results(self, client, mock_engine):
        mock_engine.search_results.return_value = []
        resp = client.get("/api/search?q=nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["results"] == []

    def test_passes_limit_parameter(self, client, mock_engine):
        client.get("/api/search?q=test&limit=5")
        mock_engine.search_results.assert_called_once_with(
            query="test", limit=5, doc_types=None, folder=None,
        )

    def test_passes_folder_filter(self, client, mock_engine):
        client.get("/api/search?q=test&folder=C:/docs")
        mock_engine.search_results.assert_called_once_with(
            query="test", limit=10, doc_types=None, folder="C:/docs",
        )

    def test_passes_doc_types(self, client, mock_engine):
        client.get("/api/search?q=test&doc_types=md,pdf")
        mock_engine.search_results.assert_called_once_with(
            query="test", limit=10, doc_types=["md", "pdf"], folder=None,
        )

    def test_requires_query_parameter(self, client):
        resp = client.get("/api/search")
        assert resp.status_code == 422


class TestFolders:
    """Tests for GET/POST/DELETE /api/folders."""

    def test_list_folders(self, client, mock_config_manager):
        resp = client.get("/api/folders")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["folders"]) == 2

    def test_add_folder_nonexistent(self, client):
        resp = client.post(
            "/api/folders", json={"path": "C:/nonexistent/dir"},
        )
        assert resp.status_code == 404

    def test_add_folder_returns_202_with_task_id(
        self, client, mock_config_manager, mock_watcher,
        mock_task_manager, tmp_path,
    ):
        """Adding a folder returns 202 Accepted with a background task ID."""
        resp = client.post("/api/folders", json={"path": str(tmp_path)})
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["task_id"] == "abc12345"
        assert "path" in data
        mock_config_manager.add_watch_dir.assert_called_once()
        mock_watcher.start.assert_called_once()
        mock_task_manager.submit.assert_called_once()

    def test_remove_folder(self, client, mock_config_manager, mock_watcher, mock_task_manager):
        """Removing a folder cancels active indexing first."""
        resp = client.delete("/api/folders?path=C:/docs")
        assert resp.status_code == 200
        mock_task_manager.cancel_folder.assert_called_once()
        mock_config_manager.remove_watch_dir.assert_called_once()
        mock_watcher.remove_directory.assert_called_once()

    def test_remove_folder_with_data(self, client, mock_store):
        resp = client.delete("/api/folders?path=C:/docs&remove_data=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_removed"] == 2
        mock_store.remove_files_for_folder.assert_called_once()


class TestFiles:
    """Tests for GET /api/files."""

    def test_list_files(self, client, mock_store):
        resp = client.get("/api/files")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["files"][0]["source_path"] == "C:/docs/test.md"
        assert data["files"][0]["chunk_count"] == 3

    def test_filter_by_folder(self, client, mock_store):
        resp = client.get("/api/files?folder=C:/other")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestIngest:
    """Tests for POST /api/ingest."""

    def test_ingest_nonexistent_path(self, client):
        resp = client.post(
            "/api/ingest", json={"path": "C:/nonexistent/file.md"},
        )
        assert resp.status_code == 404

    def test_ingest_file(self, client, mock_indexer, tmp_path):
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")
        resp = client.post("/api/ingest", json={"path": str(test_file)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "indexed"
        assert data["chunk_count"] == 3
        mock_indexer.index_file.assert_called_once()

    def test_ingest_directory_returns_202(self, client, mock_task_manager, tmp_path):
        """Ingesting a directory submits a background task and returns 202."""
        resp = client.post("/api/ingest", json={"path": str(tmp_path)})
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["task_id"] == "abc12345"
        mock_task_manager.submit.assert_called_once()


class TestConfig:
    """Tests for GET/PUT /api/config."""

    def test_get_config(self, client, mock_config_manager):
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data
        assert data["config"]["embedding_model"] == "nomic-ai/nomic-embed-text-v1.5"

    def test_update_config(self, client, mock_config_manager):
        resp = client.put(
            "/api/config",
            json={"config": {"search_default_limit": 20}},
        )
        assert resp.status_code == 200
        mock_config_manager.save.assert_called_once()
        # Verify the saved config includes the update
        saved = mock_config_manager.save.call_args[0][0]
        assert saved["search_default_limit"] == 20


class TestIndexingStatus:
    """Tests for GET /api/indexing/status (Phase A)."""

    def test_returns_empty_when_no_tasks(self, client, mock_task_manager):
        """No active tasks returns active=0 and empty tasks list."""
        resp = client.get("/api/indexing/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] == 0
        assert data["tasks"] == []

    def test_returns_running_task(self, client, mock_task_manager):
        """Active indexing task appears in response with correct fields."""
        mock_task_manager.get_all_tasks.return_value = [
            IndexingStatus(
                task_id="task-001",
                folder="C:/docs",
                state="running",
                indexed=3,
                skipped=1,
                failed=0,
            ),
        ]
        resp = client.get("/api/indexing/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] == 1
        assert len(data["tasks"]) == 1
        task = data["tasks"][0]
        assert task["task_id"] == "task-001"
        assert task["folder"] == "C:/docs"
        assert task["state"] == "running"
        assert task["indexed"] == 3
        assert task["skipped"] == 1
        assert task["failed"] == 0

    def test_returns_mixed_states(self, client, mock_task_manager):
        """Completed and running tasks both appear; active counts only running."""
        mock_task_manager.get_all_tasks.return_value = [
            IndexingStatus(
                task_id="task-001", folder="C:/docs",
                state="completed", indexed=10, skipped=2, failed=0,
            ),
            IndexingStatus(
                task_id="task-002", folder="C:/notes",
                state="running", indexed=1, skipped=0, failed=0,
            ),
        ]
        resp = client.get("/api/indexing/status")
        data = resp.json()
        assert data["active"] == 1
        assert len(data["tasks"]) == 2


class TestStatsLiveConfig:
    """Tests that stats endpoint uses live config (B22 fix)."""

    def test_stats_reads_live_watch_directories(self, client, mock_config_manager, mock_store):
        """get_stats receives watch_directories from ConfigManager, not frozen config."""
        mock_config_manager.list_watch_dirs.return_value = ["C:/docs", "C:/notes", "C:/new"]
        client.get("/api/stats")
        # Verify store.get_stats was called with the live directories
        call_kwargs = mock_store.get_stats.call_args
        assert call_kwargs == ((), {"watch_directories": ["C:/docs", "C:/notes", "C:/new"]})


class TestModelStatus:
    """Tests for GET /api/model/status (B4 fix)."""

    def test_reads_model_from_live_config(self, client, mock_config_manager):
        """model/status should read embedding_model from ConfigManager, not frozen config."""
        mock_config_manager.load.return_value = {
            "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
        }
        with patch("smart_search.embedder.Embedder.is_model_cached", return_value=True) as mock_cached:
            resp = client.get("/api/model/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_name"] == "nomic-ai/nomic-embed-text-v1.5"
        mock_cached.assert_called_once_with("nomic-ai/nomic-embed-text-v1.5")
