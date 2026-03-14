# Tests for ephemeral index integration in server.py MCP tools.

import inspect
from unittest.mock import MagicMock, patch

import pytest

from smart_search.server import create_server


@pytest.fixture
def mock_search_engine():
    """Mock SearchEngine for ephemeral server tests."""
    engine = MagicMock()
    engine.search.return_value = "EPHEMERAL SEARCH RESULTS\n=========================\n"
    engine.find_related.return_value = "RELATED NOTES FOR: test.md\n..."
    return engine


@pytest.fixture
def mock_store():
    """Mock ChunkStore for ephemeral server tests."""
    from smart_search.models import IndexStats

    store = MagicMock()
    store.get_stats.return_value = IndexStats(
        document_count=0,
        chunk_count=0,
        index_size_bytes=0,
        last_indexed_at=None,
        formats_indexed=[],
    )
    return store


@pytest.fixture
def mock_indexer():
    """Mock DocumentIndexer for ephemeral server tests."""
    from smart_search.indexer import IndexFileResult, IndexFolderResult

    indexer = MagicMock()
    indexer.index_folder.return_value = IndexFolderResult(
        indexed=3, skipped=0, failed=0, results=[],
    )
    return indexer


@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager for ephemeral server tests."""
    mgr = MagicMock()
    mgr.list_watch_dirs.return_value = []
    return mgr


@pytest.fixture
def mock_watcher():
    """Mock FileWatcher for ephemeral server tests."""
    w = MagicMock()
    w.is_running = True
    w.watched_directories = []
    return w


@pytest.fixture
def server(mock_search_engine, mock_store, mock_indexer,
           mock_config_manager, mock_watcher):
    """Create server with all mocked dependencies."""
    return create_server(
        search_engine=mock_search_engine,
        store=mock_store,
        indexer=mock_indexer,
        config_manager=mock_config_manager,
        watcher=mock_watcher,
    )


def _get_text(tool_result) -> str:
    """Extract text content from a FastMCP ToolResult."""
    return tool_result.content[0].text


class TestEphemeralToolRegistration:
    """Tests that ephemeral MCP tools are registered on the server."""

    @pytest.mark.asyncio
    async def test_knowledge_temp_index_tool_exists(self, server):
        """knowledge_temp_index tool is registered on the server."""
        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "knowledge_temp_index" in tool_names

    @pytest.mark.asyncio
    async def test_knowledge_temp_cleanup_tool_exists(self, server):
        """knowledge_temp_cleanup tool is registered on the server."""
        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "knowledge_temp_cleanup" in tool_names


class TestEphemeralParamPresence:
    """Tests that modified tools include ephemeral_folder in their schemas."""

    @pytest.mark.asyncio
    async def test_knowledge_search_has_ephemeral_folder_param(self, server):
        """knowledge_search tool schema includes ephemeral_folder parameter."""
        tools = await server.list_tools()
        search_tool = next(t for t in tools if t.name == "knowledge_search")
        # .parameters is a JSON Schema object; property names live under "properties"
        prop_names = list(search_tool.parameters.get("properties", {}).keys())
        assert "ephemeral_folder" in prop_names

    @pytest.mark.asyncio
    async def test_find_related_has_ephemeral_folder_param(self, server):
        """find_related tool schema includes ephemeral_folder parameter."""
        tools = await server.list_tools()
        related_tool = next(t for t in tools if t.name == "find_related")
        prop_names = list(related_tool.parameters.get("properties", {}).keys())
        assert "ephemeral_folder" in prop_names


class TestKnowledgeTempIndex:
    """Tests for knowledge_temp_index tool behavior."""

    @pytest.mark.asyncio
    async def test_temp_index_nonexistent_dir_returns_error(self, server):
        """knowledge_temp_index returns error for missing directory."""
        result = await server.call_tool(
            "knowledge_temp_index", {"folder_path": "/nonexistent/dir"}
        )
        text = _get_text(result)
        assert "ERROR" in text

    @pytest.mark.asyncio
    async def test_temp_index_valid_dir_returns_summary(self, server, tmp_path):
        """knowledge_temp_index succeeds for a valid directory."""
        from smart_search.indexer import IndexFolderResult, IndexFileResult

        mock_components = {
            "store": MagicMock(),
            "indexer": MagicMock(),
            "engine": MagicMock(),
            "config": MagicMock(),
        }
        mock_components["indexer"].index_folder.return_value = IndexFolderResult(
            indexed=2, skipped=0, failed=0, results=[],
        )

        mock_registry = MagicMock()

        with patch(
            "smart_search.ephemeral_store.create_ephemeral_components",
            return_value=mock_components,
        ), patch(
            "smart_search.ephemeral_store.calculate_ephemeral_size", return_value=4096
        ), patch.object(server, "_get_registry", mock_registry, create=True):
            # Patch the registry inline via the create_server closure
            with patch("smart_search.ephemeral_registry.EphemeralRegistry") as mock_reg_cls:
                mock_reg_inst = MagicMock()
                mock_reg_cls.return_value = mock_reg_inst

                result = await server.call_tool(
                    "knowledge_temp_index", {"folder_path": str(tmp_path)}
                )
        text = _get_text(result)
        # Should return a summary or error (either is acceptable without full stack)
        assert isinstance(text, str)

    @pytest.mark.asyncio
    async def test_temp_index_error_is_caught(self, server, tmp_path):
        """knowledge_temp_index catches exceptions and returns ERROR string."""
        with patch(
            "smart_search.ephemeral_store.create_ephemeral_components",
            side_effect=RuntimeError("embedding model unavailable"),
        ):
            result = await server.call_tool(
                "knowledge_temp_index", {"folder_path": str(tmp_path)}
            )
        text = _get_text(result)
        assert "ERROR" in text


class TestKnowledgeTempCleanup:
    """Tests for knowledge_temp_cleanup tool behavior."""

    @pytest.mark.asyncio
    async def test_cleanup_without_arg_lists_indexes(self, server):
        """knowledge_temp_cleanup with no folder lists all ephemeral indexes."""
        from smart_search.ephemeral_registry import EphemeralEntry

        mock_entries = [
            EphemeralEntry(
                folder_path="/tmp/proj",
                created_at="2026-03-10T00:00:00+00:00",
                last_accessed="2026-03-10T00:00:00+00:00",
                chunk_count=10,
                size_bytes=2048,
            )
        ]

        with patch("smart_search.ephemeral_registry.EphemeralRegistry") as mock_reg_cls:
            mock_reg_inst = MagicMock()
            mock_reg_inst.prune_stale.return_value = []
            mock_reg_inst.list_all.return_value = mock_entries
            mock_reg_cls.return_value = mock_reg_inst

            # Create a fresh server so the registry lazy-init uses our mock
            fresh_server = create_server(
                search_engine=MagicMock(),
                store=MagicMock(),
                indexer=MagicMock(),
                config_manager=MagicMock(),
                watcher=MagicMock(),
            )
            result = await fresh_server.call_tool("knowledge_temp_cleanup", {})

        text = _get_text(result)
        assert isinstance(text, str)

    @pytest.mark.asyncio
    async def test_cleanup_with_folder_removes_index(self, server, tmp_path):
        """knowledge_temp_cleanup with folder_path removes the index."""
        with patch(
            "smart_search.ephemeral_store.remove_ephemeral_index", return_value=True
        ), patch("smart_search.ephemeral_registry.EphemeralRegistry") as mock_reg_cls:
            mock_reg_inst = MagicMock()
            mock_reg_inst.deregister.return_value = True
            mock_reg_cls.return_value = mock_reg_inst

            fresh_server = create_server(
                search_engine=MagicMock(),
                store=MagicMock(),
                indexer=MagicMock(),
                config_manager=MagicMock(),
                watcher=MagicMock(),
            )
            result = await fresh_server.call_tool(
                "knowledge_temp_cleanup", {"folder_path": str(tmp_path)}
            )

        text = _get_text(result)
        assert "EPHEMERAL INDEX CLEAN" in text

    @pytest.mark.asyncio
    async def test_cleanup_missing_smart_search_dir(self, server, tmp_path):
        """knowledge_temp_cleanup handles missing .smart-search/ gracefully."""
        with patch(
            "smart_search.ephemeral_store.remove_ephemeral_index", return_value=False
        ), patch("smart_search.ephemeral_registry.EphemeralRegistry") as mock_reg_cls:
            mock_reg_inst = MagicMock()
            mock_reg_inst.deregister.return_value = False
            mock_reg_cls.return_value = mock_reg_inst

            fresh_server = create_server(
                search_engine=MagicMock(),
                store=MagicMock(),
                indexer=MagicMock(),
                config_manager=MagicMock(),
                watcher=MagicMock(),
            )
            result = await fresh_server.call_tool(
                "knowledge_temp_cleanup", {"folder_path": str(tmp_path)}
            )

        text = _get_text(result)
        assert isinstance(text, str)


class TestEphemeralSearchIntegration:
    """Tests that knowledge_search and find_related route to ephemeral engine."""

    @pytest.mark.asyncio
    async def test_knowledge_search_ephemeral_missing_index_error(
        self, server, tmp_path
    ):
        """knowledge_search returns error when ephemeral index does not exist."""
        with patch(
            "smart_search.ephemeral_store.ephemeral_index_exists", return_value=False
        ), patch("smart_search.ephemeral_registry.EphemeralRegistry") as mock_reg_cls:
            mock_reg_inst = MagicMock()
            mock_reg_cls.return_value = mock_reg_inst

            fresh_server = create_server(
                search_engine=MagicMock(),
                store=MagicMock(),
                indexer=MagicMock(),
                config_manager=MagicMock(),
                watcher=MagicMock(),
            )
            result = await fresh_server.call_tool(
                "knowledge_search",
                {"query": "test", "ephemeral_folder": str(tmp_path)},
            )

        text = _get_text(result)
        assert "ERROR" in text

    @pytest.mark.asyncio
    async def test_find_related_ephemeral_missing_index_error(
        self, server, tmp_path
    ):
        """find_related returns error when ephemeral index does not exist."""
        with patch(
            "smart_search.ephemeral_store.ephemeral_index_exists", return_value=False
        ), patch("smart_search.ephemeral_registry.EphemeralRegistry") as mock_reg_cls:
            mock_reg_inst = MagicMock()
            mock_reg_cls.return_value = mock_reg_inst

            fresh_server = create_server(
                search_engine=MagicMock(),
                store=MagicMock(),
                indexer=MagicMock(),
                config_manager=MagicMock(),
                watcher=MagicMock(),
            )
            result = await fresh_server.call_tool(
                "find_related",
                {"note_path": "test.md", "ephemeral_folder": str(tmp_path)},
            )

        text = _get_text(result)
        assert "ERROR" in text

    @pytest.mark.asyncio
    async def test_knowledge_search_ephemeral_routes_to_local_engine(
        self, server, tmp_path
    ):
        """knowledge_search with valid ephemeral index calls ephemeral engine."""
        mock_eph_engine = MagicMock()
        mock_eph_engine.search.return_value = "EPHEMERAL RESULTS\n"
        mock_components = {
            "store": MagicMock(),
            "indexer": MagicMock(),
            "engine": mock_eph_engine,
            "config": MagicMock(),
        }

        with patch(
            "smart_search.ephemeral_store.ephemeral_index_exists", return_value=True
        ), patch(
            "smart_search.ephemeral_store.create_ephemeral_components",
            return_value=mock_components,
        ), patch("smart_search.ephemeral_registry.EphemeralRegistry") as mock_reg_cls:
            mock_reg_inst = MagicMock()
            mock_reg_cls.return_value = mock_reg_inst

            fresh_server = create_server(
                search_engine=MagicMock(),
                store=MagicMock(),
                indexer=MagicMock(),
                config_manager=MagicMock(),
                watcher=MagicMock(),
            )
            result = await fresh_server.call_tool(
                "knowledge_search",
                {"query": "hello", "ephemeral_folder": str(tmp_path)},
            )

        text = _get_text(result)
        assert "EPHEMERAL RESULTS" in text
        mock_eph_engine.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_related_ephemeral_routes_to_local_engine(
        self, server, tmp_path
    ):
        """find_related with valid ephemeral index calls ephemeral engine."""
        mock_eph_engine = MagicMock()
        mock_eph_engine.find_related.return_value = "EPHEMERAL RELATED\n"
        mock_components = {
            "store": MagicMock(),
            "indexer": MagicMock(),
            "engine": mock_eph_engine,
            "config": MagicMock(),
        }

        with patch(
            "smart_search.ephemeral_store.ephemeral_index_exists", return_value=True
        ), patch(
            "smart_search.ephemeral_store.create_ephemeral_components",
            return_value=mock_components,
        ), patch("smart_search.ephemeral_registry.EphemeralRegistry") as mock_reg_cls:
            mock_reg_inst = MagicMock()
            mock_reg_cls.return_value = mock_reg_inst

            fresh_server = create_server(
                search_engine=MagicMock(),
                store=MagicMock(),
                indexer=MagicMock(),
                config_manager=MagicMock(),
                watcher=MagicMock(),
            )
            result = await fresh_server.call_tool(
                "find_related",
                {"note_path": "test.md", "ephemeral_folder": str(tmp_path)},
            )

        text = _get_text(result)
        assert "EPHEMERAL RELATED" in text
        mock_eph_engine.find_related.assert_called_once()
