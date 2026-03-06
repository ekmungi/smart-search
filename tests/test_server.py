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
def server(mock_search_engine, mock_store, mock_indexer):
    """Create server with mocked dependencies."""
    return create_server(
        search_engine=mock_search_engine,
        store=mock_store,
        indexer=mock_indexer,
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
