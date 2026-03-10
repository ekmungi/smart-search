# FastMCP server entry point: exposes knowledge tools and file watcher.

from pathlib import Path
from typing import List, Optional

from fastmcp import FastMCP

from smart_search.config import SmartSearchConfig, get_config
from smart_search.config_manager import ConfigManager
from smart_search.data_dir import get_data_dir
from smart_search.ephemeral_registry import EphemeralRegistry
from smart_search.ephemeral_store import (
    calculate_ephemeral_size,
    create_ephemeral_components,
    ephemeral_index_exists,
    remove_ephemeral_index,
)
from smart_search.indexer import DocumentIndexer, IndexFileResult, IndexFolderResult
from smart_search.models import IndexStats
from smart_search.search import SearchEngine
from smart_search.store import ChunkStore
from smart_search.watcher import FileWatcher


def create_server(
    search_engine: Optional[SearchEngine] = None,
    store: Optional[ChunkStore] = None,
    config: Optional[SmartSearchConfig] = None,
    indexer: Optional[DocumentIndexer] = None,
    config_manager: Optional[ConfigManager] = None,
    watcher: Optional[FileWatcher] = None,
) -> FastMCP:
    """Create and configure the FastMCP server with tools.

    Accepts optional pre-built components for testing. When called
    without arguments, creates real components from config.

    Args:
        search_engine: Optional SearchEngine (for testing).
        store: Optional ChunkStore (for testing).
        config: Optional SmartSearchConfig override.
        indexer: Optional DocumentIndexer (for testing).
        config_manager: Optional ConfigManager (for testing).
        watcher: Optional FileWatcher (for testing).

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
    _config_mgr = config_manager
    _watcher = watcher

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

    def _get_config_mgr() -> ConfigManager:
        """Get or create the config manager singleton."""
        nonlocal _config_mgr
        if _config_mgr is None:
            _config_mgr = ConfigManager(get_data_dir())
        return _config_mgr

    def _get_watcher() -> FileWatcher:
        """Get or create the file watcher singleton."""
        nonlocal _watcher
        if _watcher is None:
            _watcher = FileWatcher(config, _get_indexer(), _get_store())
        return _watcher

    _registry = None

    def _get_registry() -> EphemeralRegistry:
        """Get or create the ephemeral registry singleton."""
        nonlocal _registry
        if _registry is None:
            _registry = EphemeralRegistry(config.sqlite_path)
            _registry.initialize()
        return _registry

    @mcp.tool()
    def knowledge_search(
        query: str,
        limit: int = 10,
        mode: str = "hybrid",
        doc_types: Optional[List[str]] = None,
        folder: Optional[str] = None,
        ephemeral_folder: Optional[str] = None,
    ) -> str:
        """Search the knowledge base for documents matching a query.

        Returns formatted context with source paths, page numbers,
        section headings, and relevance scores. Results are ranked
        by semantic similarity.

        When ephemeral_folder is provided, searches a folder-local
        .smart-search/ index created by knowledge_temp_index instead
        of the global knowledge base.

        Args:
            query: Natural language search query.
            limit: Maximum number of results (default 10).
            mode: Search mode - semantic, keyword, or hybrid (default hybrid).
            doc_types: Optional filter by document type (e.g., ["pdf", "docx"]).
            folder: Optional folder path to restrict search results to.
            ephemeral_folder: Optional path to a folder with a local index.

        Returns:
            Formatted search results as a string.
        """
        if ephemeral_folder is not None:
            path = Path(ephemeral_folder).resolve()
            path_posix = path.as_posix()
            if not ephemeral_index_exists(str(path)):
                # Self-heal: remove stale registry entry
                _get_registry().deregister(path_posix)
                return (
                    f"ERROR: No ephemeral index found at {path_posix}/.smart-search/\n"
                    f"Run knowledge_temp_index first."
                )
            components = create_ephemeral_components(str(path))
            engine = components["engine"]
            _get_registry().touch(path_posix)
            return engine.search(
                query=query, limit=limit, mode=mode,
                doc_types=doc_types, folder=folder,
            )

        engine = _get_engine()
        return engine.search(
            query=query, limit=limit, mode=mode,
            doc_types=doc_types, folder=folder,
        )

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
    def find_related(
        note_path: str,
        limit: int = 10,
        ephemeral_folder: Optional[str] = None,
    ) -> str:
        """Find notes similar to a given note by vector similarity.

        Looks up the note's embeddings in the index and finds the closest
        matches, excluding the source note itself.

        When ephemeral_folder is provided, searches a folder-local
        .smart-search/ index created by knowledge_temp_index instead
        of the global knowledge base.

        Args:
            note_path: Path to the source note (relative to a watch directory).
            limit: Maximum number of related notes to return.
            ephemeral_folder: Optional path to a folder with a local index.

        Returns:
            Formatted list of related notes ranked by similarity.
        """
        if ephemeral_folder is not None:
            path = Path(ephemeral_folder).resolve()
            path_posix = path.as_posix()
            if not ephemeral_index_exists(str(path)):
                # Self-heal: remove stale registry entry
                _get_registry().deregister(path_posix)
                return (
                    f"ERROR: No ephemeral index found at {path_posix}/.smart-search/\n"
                    f"Run knowledge_temp_index first."
                )
            components = create_ephemeral_components(str(path))
            engine = components["engine"]
            _get_registry().touch(path_posix)
            return engine.find_related(note_path, limit=limit)

        engine = _get_engine()
        return engine.find_related(note_path, limit=limit)

    @mcp.tool()
    def knowledge_add_folder(folder_path: str) -> str:
        """Add a folder to the watch list and trigger initial indexing.

        Persists the folder to config.json and starts the file watcher
        on it. Future file changes in this folder will be auto-indexed.

        Args:
            folder_path: Absolute path to the folder to watch.

        Returns:
            Confirmation message or error.
        """
        path = Path(folder_path).resolve()
        if not path.is_dir():
            return f"ERROR: Directory not found: {folder_path}"

        mgr = _get_config_mgr()
        mgr.add_watch_dir(str(path))

        w = _get_watcher()
        if not w.is_running:
            w.start()
        w.add_directory(str(path))

        # Trigger initial indexing of existing files
        idx = _get_indexer()
        result = idx.index_folder(str(path))

        return (
            f"FOLDER ADDED\n"
            f"============\n"
            f"Path: {path.as_posix()}\n"
            f"Watching: yes\n"
            f"Initial index: {result.indexed} files indexed, "
            f"{result.skipped} skipped, {result.failed} failed"
        )

    @mcp.tool()
    def knowledge_remove_folder(
        folder_path: str, remove_data: bool = False,
    ) -> str:
        """Remove a folder from the watch list.

        Stops watching the folder and removes it from config.json.
        Optionally removes all indexed data from that folder.

        Args:
            folder_path: Path to the folder to stop watching.
            remove_data: If True, also delete indexed chunks from this folder.

        Returns:
            Confirmation message.
        """
        path = Path(folder_path).resolve()
        path_posix = path.as_posix()

        mgr = _get_config_mgr()
        mgr.remove_watch_dir(str(path))

        w = _get_watcher()
        w.remove_directory(str(path))

        removed_count = 0
        if remove_data:
            s = _get_store()
            removed_count = s.remove_files_for_folder(path_posix)

        data_line = (
            f"Data removed: {removed_count} files"
            if remove_data
            else "Data: kept (use remove_data=True to delete)"
        )
        return (
            f"FOLDER REMOVED\n"
            f"==============\n"
            f"Path: {path_posix}\n"
            f"{data_line}"
        )

    @mcp.tool()
    def knowledge_list_folders() -> str:
        """List all watched folders and their status.

        Returns:
            Formatted list of watched directories from config.
        """
        mgr = _get_config_mgr()
        dirs = mgr.list_watch_dirs()

        if not dirs:
            return "No folders configured. Use knowledge_add_folder to add one."

        lines = [
            "WATCHED FOLDERS",
            "=" * 16,
            f"Total: {len(dirs)}",
            "",
        ]
        for d in dirs:
            exists = "active" if Path(d).is_dir() else "missing"
            lines.append(f"  [{exists}] {d}")

        return "\n".join(lines)

    @mcp.tool()
    def knowledge_list_files() -> str:
        """List all indexed files with metadata.

        Returns:
            Formatted list of indexed files with chunk counts.
        """
        s = _get_store()
        files = s.list_indexed_files()

        if not files:
            return "No files indexed yet. Use knowledge_ingest to add files."

        lines = [
            "INDEXED FILES",
            "=" * 14,
            f"Total: {len(files)} files",
            "",
        ]
        for f in files:
            lines.append(
                f"  {f['source_path']} ({f['chunk_count']} chunks, "
                f"indexed {f['indexed_at']})"
            )

        return "\n".join(lines)

    @mcp.tool()
    def knowledge_temp_index(folder_path: str, force: bool = False) -> str:
        """Create an ephemeral index inside a folder for temporary searching.

        Creates a .smart-search/ directory inside the target folder containing
        a local LanceDB and SQLite index. Independent of the global knowledge base.
        Clean up with knowledge_temp_cleanup.

        Args:
            folder_path: Absolute path to the folder to index.
            force: If True, re-index even if files are unchanged.

        Returns:
            Formatted summary of indexing results.
        """
        path = Path(folder_path).resolve()
        if not path.is_dir():
            return f"ERROR: Directory not found: {folder_path}"

        try:
            components = create_ephemeral_components(str(path))
            indexer = components["indexer"]
            result = indexer.index_folder(str(path), force=force)

            registry = _get_registry()
            size = calculate_ephemeral_size(str(path))
            total_chunks = sum(
                r.chunk_count for r in result.results if r.status == "indexed"
            )
            registry.register(path.as_posix(), total_chunks, size)

            return (
                f"EPHEMERAL INDEX CREATED\n"
                f"======================\n"
                f"Folder: {path.as_posix()}\n"
                f"Index location: {path.as_posix()}/.smart-search/\n"
                f"Files indexed: {result.indexed}\n"
                f"Files skipped: {result.skipped}\n"
                f"Files failed: {result.failed}\n"
                f"Total chunks: {total_chunks}\n"
                f"Index size: {size / 1024:.1f} KB\n"
                f"\nSearch with: knowledge_search(query, ephemeral_folder=\"{path.as_posix()}\")"
            )
        except Exception as e:
            return f"ERROR: Failed to create ephemeral index: {e}"

    @mcp.tool()
    def knowledge_temp_cleanup(folder_path: Optional[str] = None) -> str:
        """Clean up ephemeral indexes or list all existing ones.

        Without arguments: lists all registered ephemeral indexes with stats,
        prunes stale entries whose .smart-search/ no longer exists.

        With folder_path: deletes the .smart-search/ directory from that folder
        and removes it from the registry.

        Args:
            folder_path: Optional path to a specific folder to clean up.

        Returns:
            Formatted list of indexes or cleanup confirmation.
        """
        registry = _get_registry()

        if folder_path is None:
            pruned = registry.prune_stale()
            entries = registry.list_all()

            if not entries and not pruned:
                return "No ephemeral indexes found."

            lines = ["EPHEMERAL INDEXES", "=" * 18]

            if pruned:
                lines.append(f"Pruned {len(pruned)} stale entries:")
                for p in pruned:
                    lines.append(f"  [stale] {p}")
                lines.append("")

            if entries:
                lines.append(f"Active: {len(entries)} indexes")
                lines.append("")
                for entry in entries:
                    size_kb = entry.size_bytes / 1024
                    lines.append(f"  {entry.folder_path}")
                    lines.append(
                        f"    Chunks: {entry.chunk_count}, "
                        f"Size: {size_kb:.1f} KB, "
                        f"Created: {entry.created_at}"
                    )
            else:
                lines.append("No active ephemeral indexes.")

            return "\n".join(lines)

        path = Path(folder_path).resolve()
        path_posix = path.as_posix()

        removed = remove_ephemeral_index(str(path))
        registry.deregister(path_posix)

        if removed:
            return (
                f"EPHEMERAL INDEX CLEANED\n"
                f"======================\n"
                f"Folder: {path_posix}\n"
                f"Removed: .smart-search/ directory deleted\n"
                f"Registry: entry removed"
            )
        else:
            return (
                f"EPHEMERAL INDEX CLEANUP\n"
                f"======================\n"
                f"Folder: {path_posix}\n"
                f"No .smart-search/ directory found (registry entry cleaned if present)"
            )

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


if __name__ == "__main__":
    main()
