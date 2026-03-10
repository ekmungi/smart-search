# FastMCP server entry point: exposes knowledge tools and file watcher.

from pathlib import Path
from typing import List, Optional

from fastmcp import FastMCP

from smart_search.config import SmartSearchConfig, get_config
from smart_search.indexer import DocumentIndexer, IndexFileResult, IndexFolderResult
from smart_search.models import IndexStats
from smart_search.search import SearchEngine
from smart_search.store import ChunkStore


def create_server(
    search_engine: Optional[SearchEngine] = None,
    store: Optional[ChunkStore] = None,
    config: Optional[SmartSearchConfig] = None,
    indexer: Optional[DocumentIndexer] = None,
) -> FastMCP:
    """Create and configure the FastMCP server with tools.

    Accepts optional pre-built components for testing. When called
    without arguments, creates real components from config.

    Args:
        search_engine: Optional SearchEngine (for testing).
        store: Optional ChunkStore (for testing).
        config: Optional SmartSearchConfig override.
        indexer: Optional DocumentIndexer (for testing).

    Returns:
        Configured FastMCP server instance.
    """
    if config is None:
        config = get_config()

    mcp = FastMCP("smart-search")

    # Lazy-init real components only when tools are first called
    _engine = search_engine
    _store = store
    _indexer = indexer

    def _get_engine() -> SearchEngine:
        """Get or create the search engine singleton."""
        nonlocal _engine, _store
        if _engine is None:
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

    def _get_indexer() -> DocumentIndexer:
        """Get or create the document indexer singleton."""
        nonlocal _indexer, _store
        if _indexer is None:
            from smart_search.chunker import DocumentChunker
            from smart_search.embedder import Embedder
            from smart_search.markdown_chunker import MarkdownChunker

            if _store is None:
                _store = ChunkStore(config)
                _store.initialize()

            _indexer = DocumentIndexer(
                config=config,
                chunker=DocumentChunker(config),
                embedder=Embedder(config),
                store=_store,
                markdown_chunker=MarkdownChunker(config),
            )
        return _indexer

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

    @mcp.tool()
    def knowledge_ingest(
        path: str,
        force: bool = False,
    ) -> str:
        """Ingest a file or folder into the knowledge base.

        Indexes documents by extracting text, generating embeddings,
        and storing chunks. Supports .md, .pdf, and .docx files.
        Uses hash-based change detection to skip unchanged files.

        Args:
            path: Absolute path to a file or folder to ingest.
            force: If True, re-index even if file hash is unchanged.

        Returns:
            Formatted ingestion result summary.
        """
        idx = _get_indexer()
        target = Path(path)

        if target.is_file():
            result = idx.index_file(str(target), force=force)
            return _format_file_result(result)
        elif target.is_dir():
            result = idx.index_folder(str(target), force=force)
            return _format_folder_result(result)
        else:
            return f"INGEST ERROR\nPath not found: {path}"

    @mcp.tool()
    def find_related(note_path: str, limit: int = 10) -> str:
        """Find notes similar to a given note by vector similarity.

        Looks up the note's embeddings in the index and finds the closest
        matches, excluding the source note itself.

        Args:
            note_path: Path to the source note (relative to a watch directory).
            limit: Maximum number of related notes to return.

        Returns:
            Formatted list of related notes ranked by similarity.
        """
        engine = _get_engine()
        return engine.find_related(note_path, limit=limit)

    @mcp.tool()
    def read_note(note_path: str) -> str:
        """Read the content of a note by path with safety validation.

        Resolves the path against configured watch directories and validates
        against path traversal attacks before reading.

        Args:
            note_path: Relative path to the note (max 500 characters).

        Returns:
            Note content as text, or an error message.
        """
        from smart_search.reader import read_note as _read_note

        return _read_note(note_path, config.watch_directories)

    return mcp


def _format_file_result(result: IndexFileResult) -> str:
    """Format a single-file indexing result as a human-readable string.

    Args:
        result: IndexFileResult from the indexer.

    Returns:
        Formatted status string.
    """
    if result.status == "failed":
        return (
            f"INGEST RESULT\n"
            f"=============\n"
            f"File: {result.file_path}\n"
            f"Status: FAILED\n"
            f"Error: {result.error}"
        )
    return (
        f"INGEST RESULT\n"
        f"=============\n"
        f"File: {result.file_path}\n"
        f"Status: {result.status}\n"
        f"Chunks: {result.chunk_count}"
    )


def _format_folder_result(result: IndexFolderResult) -> str:
    """Format a folder indexing result as a human-readable string.

    Args:
        result: IndexFolderResult from the indexer.

    Returns:
        Formatted summary string.
    """
    return (
        f"INGEST RESULT\n"
        f"=============\n"
        f"Indexed: {result.indexed} files\n"
        f"Skipped: {result.skipped} files (unchanged)\n"
        f"Failed: {result.failed} files\n"
        f"Total: {len(result.results)} files processed"
    )


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
