# FastMCP server entry point: exposes knowledge_search and knowledge_stats tools.

from typing import List, Optional

from fastmcp import FastMCP

from smart_search.config import SmartSearchConfig, get_config
from smart_search.models import IndexStats
from smart_search.search import SearchEngine
from smart_search.store import ChunkStore


def create_server(
    search_engine: Optional[SearchEngine] = None,
    store: Optional[ChunkStore] = None,
    config: Optional[SmartSearchConfig] = None,
) -> FastMCP:
    """Create and configure the FastMCP server with tools.

    Accepts optional pre-built components for testing. When called
    without arguments, creates real components from config.

    Args:
        search_engine: Optional SearchEngine (for testing).
        store: Optional ChunkStore (for testing).
        config: Optional SmartSearchConfig override.

    Returns:
        Configured FastMCP server instance.
    """
    if config is None:
        config = get_config()

    mcp = FastMCP("smart-search")

    # Lazy-init real components only when tools are first called
    _engine = search_engine
    _store = store

    def _get_engine() -> SearchEngine:
        """Get or create the search engine singleton."""
        nonlocal _engine, _store
        if _engine is None:
            from smart_search.chunker import DocumentChunker
            from smart_search.embedder import Embedder

            if _store is None:
                _store = ChunkStore(config)
                _store.initialize()

            embedder = Embedder(config)
            _engine = SearchEngine(config, embedder, _store)
        return _engine

    def _get_store() -> ChunkStore:
        """Get or create the chunk store singleton."""
        nonlocal _store
        if _store is None:
            _store = ChunkStore(config)
            _store.initialize()
        return _store

    @mcp.tool()
    def knowledge_search(
        query: str,
        limit: int = 10,
        mode: str = "hybrid",
        doc_types: Optional[List[str]] = None,
    ) -> str:
        """Search the knowledge base for documents matching a query.

        Returns formatted context with source paths, page numbers,
        section headings, and relevance scores. Results are ranked
        by semantic similarity.

        Args:
            query: Natural language search query.
            limit: Maximum number of results (default 10).
            mode: Search mode - semantic, keyword, or hybrid (default hybrid).
            doc_types: Optional filter by document type (e.g., ["pdf", "docx"]).

        Returns:
            Formatted search results as a string.
        """
        engine = _get_engine()
        return engine.search(query=query, limit=limit, mode=mode, doc_types=doc_types)

    @mcp.tool()
    def knowledge_stats() -> str:
        """Get statistics about the indexed knowledge base.

        Returns document count, chunk count, index size, last indexed
        timestamp, and formats currently indexed.

        Returns:
            Formatted statistics as a string.
        """
        s = _get_store()
        stats = s.get_stats()
        return _format_stats(stats)

    return mcp


def _format_stats(stats: IndexStats) -> str:
    """Format IndexStats as a human-readable string.

    Args:
        stats: IndexStats from the chunk store.

    Returns:
        Formatted multi-line string.
    """
    size_mb = stats.index_size_bytes / (1024 * 1024)
    formats = ", ".join(stats.formats_indexed) if stats.formats_indexed else "none"
    last = stats.last_indexed_at or "never"

    separator = "=" * 26
    return (
        f"KNOWLEDGE BASE STATISTICS\n"
        f"{separator}\n"
        f"Documents indexed: {stats.document_count}\n"
        f"Chunks stored: {stats.chunk_count}\n"
        f"Index size: {size_mb:.1f} MB\n"
        f"Last indexed: {last}\n"
        f"Formats indexed: {formats}"
    )


# Default server for `python -m smart_search.server`
mcp = create_server()


def main():
    """Run the MCP server via stdio transport."""
    mcp.run(transport="stdio")
