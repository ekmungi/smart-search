# Tests for FastMCP server: tool registration and responses.

from unittest.mock import MagicMock

import pytest

from smart_search.indexer import IndexFileResult, IndexFolderResult
from smart_search.server import create_server


@pytest.fixture
def mock_search_engine():
    """Mock SearchEngine that returns formatted strings."""
    engine = MagicMock()
    engine.search.return_value = (
        "KNOWLEDGE SEARCH RESULTS\n"
        "=========================\n"
        "Query: test\n"
        "Results: 1 chunks from 1 documents\n"
    )
    return engine


@pytest.fixture
def mock_store():
    """Mock ChunkStore with stats."""
    from smart_search.models import IndexStats

    store = MagicMock()
    store.get_stats.return_value = IndexStats(
        document_count=5,
        chunk_count=150,
        index_size_bytes=1024000,
        last_indexed_at="2026-03-05T00:00:00Z",
        formats_indexed=["pdf", "docx"],
    )
    return store


@pytest.fixture
def mock_indexer():
    """Mock DocumentIndexer for ingest tool tests."""
    indexer = MagicMock()
    indexer.index_file.return_value = IndexFileResult(
        file_path="/tmp/test.md", status="indexed", chunk_count=3,
    )
    indexer.index_folder.return_value = IndexFolderResult(
        indexed=2, skipped=1, failed=0, results=[],
    )
    return indexer


@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager for folder management tests."""
    mgr = MagicMock()
    mgr.list_watch_dirs.return_value = ["C:/vault/notes", "C:/vault/research"]
    return mgr


@pytest.fixture
def mock_watcher():
    """Mock FileWatcher for folder management tests."""
    w = MagicMock()
    w.is_running = True
    w.watched_directories = ["C:/vault/notes"]
    return w


@pytest.fixture
def server(mock_search_engine, mock_store, mock_indexer,
           mock_config_manager, mock_watcher):
    """Create server with mocked dependencies."""
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


class TestToolRegistration:
    """Tests that MCP tools are registered correctly."""

    @pytest.mark.asyncio
    async def test_knowledge_search_tool_exists(self, server):
        """knowledge_search tool is registered on the server."""
        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "knowledge_search" in tool_names

    @pytest.mark.asyncio
    async def test_knowledge_stats_tool_exists(self, server):
        """knowledge_stats tool is registered on the server."""
        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "knowledge_stats" in tool_names


class TestToolResponses:
    """Tests that tools return expected response types."""

    @pytest.mark.asyncio
    async def test_knowledge_search_returns_string(self, server):
        """knowledge_search returns a string result."""
        result = await server.call_tool("knowledge_search", {"query": "test"})
        text = _get_text(result)
        assert "KNOWLEDGE SEARCH RESULTS" in text

    @pytest.mark.asyncio
    async def test_knowledge_stats_returns_string(self, server):
        """knowledge_stats returns a string with stats."""
        result = await server.call_tool("knowledge_stats", {})
        text = _get_text(result)
        assert "KNOWLEDGE BASE STATISTICS" in text

    @pytest.mark.asyncio
    async def test_knowledge_stats_contains_expected_fields(self, server):
        """Stats output contains document count, chunk count, formats."""
        result = await server.call_tool("knowledge_stats", {})
        text = _get_text(result)
        assert "Documents indexed: 5" in text
        assert "Chunks stored: 150" in text
        assert "Formats indexed: pdf, docx" in text

    @pytest.mark.asyncio
    async def test_knowledge_search_with_doc_types_filter(self, server):
        """knowledge_search accepts doc_types parameter."""
        result = await server.call_tool(
            "knowledge_search",
            {"query": "test", "doc_types": ["pdf"]},
        )
        text = _get_text(result)
        assert isinstance(text, str)


class TestKnowledgeIngest:
    """Tests for the knowledge_ingest MCP tool."""

    @pytest.mark.asyncio
    async def test_knowledge_ingest_tool_exists(self, server):
        """knowledge_ingest tool is registered on the server."""
        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "knowledge_ingest" in tool_names

    @pytest.mark.asyncio
    async def test_ingest_single_file(self, server, mock_indexer, tmp_path):
        """Ingesting a file calls indexer.index_file and returns result."""
        md = tmp_path / "note.md"
        md.write_text("# Test")
        mock_indexer.index_file.return_value = IndexFileResult(
            file_path=str(md), status="indexed", chunk_count=3,
        )
        result = await server.call_tool(
            "knowledge_ingest", {"path": str(md)}
        )
        text = _get_text(result)
        assert "INGEST RESULT" in text
        assert "indexed" in text
        assert "Chunks: 3" in text

    @pytest.mark.asyncio
    async def test_ingest_folder(self, server, mock_indexer, tmp_path):
        """Ingesting a folder calls indexer.index_folder and returns summary."""
        result = await server.call_tool(
            "knowledge_ingest", {"path": str(tmp_path)}
        )
        text = _get_text(result)
        assert "INGEST RESULT" in text
        assert "Indexed: 2 files" in text
        assert "Skipped: 1 files" in text

    @pytest.mark.asyncio
    async def test_ingest_nonexistent_path(self, server):
        """Ingesting a non-existent path returns error."""
        result = await server.call_tool(
            "knowledge_ingest", {"path": "/nonexistent/path"}
        )
        text = _get_text(result)
        assert "INGEST ERROR" in text

    @pytest.mark.asyncio
    async def test_ingest_with_force(self, server, mock_indexer, tmp_path):
        """force=True is passed through to the indexer."""
        md = tmp_path / "note.md"
        md.write_text("# Test")
        await server.call_tool(
            "knowledge_ingest", {"path": str(md), "force": True}
        )
        mock_indexer.index_file.assert_called_once()
        call_kwargs = mock_indexer.index_file.call_args
        assert call_kwargs[1].get("force") is True or call_kwargs[0][1] is True


class TestFindRelatedTool:
    """Tests for the find_related MCP tool."""

    @pytest.mark.asyncio
    async def test_find_related_tool_exists(self, server):
        """find_related tool is registered on the server."""
        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "find_related" in tool_names

    @pytest.mark.asyncio
    async def test_find_related_delegates_to_engine(
        self, server, mock_search_engine
    ):
        """find_related calls search engine and returns results."""
        mock_search_engine.find_related.return_value = (
            "RELATED NOTES FOR: test.md\n..."
        )
        result = await server.call_tool(
            "find_related", {"note_path": "test.md", "limit": 5}
        )
        text = _get_text(result)
        mock_search_engine.find_related.assert_called_once_with(
            "test.md", limit=5
        )
        assert "RELATED NOTES" in text


class TestReadNoteTool:
    """Tests for the read_note MCP tool."""

    @pytest.mark.asyncio
    async def test_read_note_tool_exists(self, server):
        """read_note tool is registered on the server."""
        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "read_note" in tool_names

    @pytest.mark.asyncio
    async def test_read_note_returns_content(self, tmp_path):
        """read_note returns file content for valid path."""
        from smart_search.config import SmartSearchConfig

        note = tmp_path / "test.md"
        note.write_text("# Test Note\n\nContent here.")
        config = SmartSearchConfig(watch_directories=[str(tmp_path)])
        srv = create_server(config=config)
        result = await srv.call_tool("read_note", {"note_path": "test.md"})
        text = _get_text(result)
        assert "# Test Note" in text

    @pytest.mark.asyncio
    async def test_read_note_rejects_traversal(self, server):
        """read_note returns error for path traversal."""
        result = await server.call_tool(
            "read_note", {"note_path": "../../etc/passwd"}
        )
        text = _get_text(result)
        assert "error" in text.lower()


class TestKnowledgeFolderTools:
    """Tests for folder management MCP tools."""

    @pytest.mark.asyncio
    async def test_folder_tools_registered(self, server):
        """All folder management tools are registered."""
        tools = await server.list_tools()
        names = [t.name for t in tools]
        assert "knowledge_add_folder" in names
        assert "knowledge_remove_folder" in names
        assert "knowledge_list_folders" in names
        assert "knowledge_list_files" in names

    @pytest.mark.asyncio
    async def test_add_folder(self, server, mock_config_manager,
                              mock_watcher, mock_indexer, tmp_path):
        """knowledge_add_folder adds dir and triggers indexing."""
        folder = tmp_path / "vault"
        folder.mkdir()
        result = await server.call_tool(
            "knowledge_add_folder", {"folder_path": str(folder)}
        )
        text = _get_text(result)
        assert "FOLDER ADDED" in text
        mock_config_manager.add_watch_dir.assert_called_once()
        mock_watcher.add_directory.assert_called_once()
        mock_indexer.index_folder.assert_called()

    @pytest.mark.asyncio
    async def test_add_nonexistent_folder(self, server):
        """knowledge_add_folder returns error for missing directory."""
        result = await server.call_tool(
            "knowledge_add_folder", {"folder_path": "/nonexistent/dir"}
        )
        text = _get_text(result)
        assert "ERROR" in text

    @pytest.mark.asyncio
    async def test_remove_folder(self, server, mock_config_manager,
                                 mock_watcher, tmp_path):
        """knowledge_remove_folder removes dir from config and watcher."""
        folder = tmp_path / "vault"
        folder.mkdir()
        result = await server.call_tool(
            "knowledge_remove_folder", {"folder_path": str(folder)}
        )
        text = _get_text(result)
        assert "FOLDER REMOVED" in text
        mock_config_manager.remove_watch_dir.assert_called_once()
        mock_watcher.remove_directory.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_folder_with_data(self, server, mock_store, tmp_path):
        """knowledge_remove_folder with remove_data deletes indexed chunks."""
        folder = tmp_path / "vault"
        folder.mkdir()
        mock_store.remove_files_for_folder.return_value = 5
        result = await server.call_tool(
            "knowledge_remove_folder",
            {"folder_path": str(folder), "remove_data": True},
        )
        text = _get_text(result)
        assert "Data removed: 5 files" in text
        mock_store.remove_files_for_folder.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_folders(self, server, mock_config_manager):
        """knowledge_list_folders returns watched directories."""
        result = await server.call_tool("knowledge_list_folders", {})
        text = _get_text(result)
        assert "WATCHED FOLDERS" in text
        assert "C:/vault/notes" in text

    @pytest.mark.asyncio
    async def test_list_folders_empty(self, server, mock_config_manager):
        """knowledge_list_folders with no dirs returns helpful message."""
        mock_config_manager.list_watch_dirs.return_value = []
        result = await server.call_tool("knowledge_list_folders", {})
        text = _get_text(result)
        assert "No folders configured" in text

    @pytest.mark.asyncio
    async def test_list_files(self, server, mock_store):
        """knowledge_list_files returns indexed files."""
        mock_store.list_indexed_files.return_value = [
            {"source_path": "C:/vault/a.md", "chunk_count": 5,
             "indexed_at": "2026-03-10"},
        ]
        result = await server.call_tool("knowledge_list_files", {})
        text = _get_text(result)
        assert "INDEXED FILES" in text
        assert "a.md" in text

    @pytest.mark.asyncio
    async def test_list_files_empty(self, server, mock_store):
        """knowledge_list_files with no files returns helpful message."""
        mock_store.list_indexed_files.return_value = []
        result = await server.call_tool("knowledge_list_files", {})
        text = _get_text(result)
        assert "No files indexed" in text

    @pytest.mark.asyncio
    async def test_search_with_folder_filter(self, server, mock_search_engine):
        """knowledge_search passes folder param to engine."""
        result = await server.call_tool(
            "knowledge_search",
            {"query": "test", "folder": "C:/vault/notes"},
        )
        mock_search_engine.search.assert_called_once()
        call_kwargs = mock_search_engine.search.call_args[1]
        assert call_kwargs["folder"] == "C:/vault/notes"
