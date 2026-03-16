# FastMCP server entry point: thin proxy to the HTTP backend.
#
# All global knowledge base operations are proxied through the HTTP server
# (localhost:9742) so there is a single source of truth. The UI always
# reflects MCP-triggered actions. No heavy dependencies are loaded here.
#
# Ephemeral index tools still run locally since they are independent.

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastmcp import FastMCP

from smart_search.config import SmartSearchConfig, get_config
from smart_search.config_manager import ConfigManager
from smart_search.data_dir import get_data_dir
from smart_search import mcp_client


def create_server(
    config: Optional[SmartSearchConfig] = None,
    config_manager: Optional[ConfigManager] = None,
) -> FastMCP:
    """Create and configure the FastMCP server with tools.

    All global knowledge base tools proxy through the HTTP backend.
    Ephemeral index tools run locally.

    Args:
        config: Optional SmartSearchConfig override.
        config_manager: Optional ConfigManager (for testing).

    Returns:
        Configured FastMCP server instance.
    """
    if config is None:
        config = get_config()

    mcp = FastMCP("smart-search")

    _config_mgr = config_manager
    _registry = None

    def _get_config_mgr():
        """Get or create the config manager singleton."""
        nonlocal _config_mgr
        if _config_mgr is None:
            _config_mgr = ConfigManager(get_data_dir())
        return _config_mgr

    def _get_registry():
        """Get or create the ephemeral registry singleton."""
        nonlocal _registry
        if _registry is None:
            from smart_search.ephemeral_registry import (
                EphemeralRegistry as _EphemeralRegistry,
            )

            _registry = _EphemeralRegistry(config.sqlite_path)
            _registry.initialize()
        return _registry

    def _ensure_backend():
        """Check that the HTTP backend is running, raise if not."""
        if not mcp_client.is_backend_running():
            raise ConnectionError(
                "Backend not reachable. Start it with: smart-search serve"
            )

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
            from smart_search.ephemeral_store import (
                create_ephemeral_components,
                ephemeral_index_exists,
            )

            path = Path(ephemeral_folder).resolve()
            path_posix = path.as_posix()
            if not ephemeral_index_exists(str(path)):
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
                doc_types=doc_types, folder=None,
            )

        _ensure_backend()
        data = mcp_client.search(
            query=query, limit=limit, folder=folder, doc_types=doc_types,
        )
        return _format_search_response(data)

    @mcp.tool()
    def knowledge_stats() -> str:
        """Get statistics about the indexed knowledge base.

        Returns document count, chunk count, index size, last indexed
        timestamp, and formats currently indexed.

        Returns:
            Formatted statistics as a string.
        """
        _ensure_backend()
        data = mcp_client.get_stats()
        return _format_stats_response(data)

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
        _ensure_backend()
        data = mcp_client.ingest(path=path, force=force)
        return _format_ingest_response(data)

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
            from smart_search.ephemeral_store import (
                create_ephemeral_components,
                ephemeral_index_exists,
            )

            path = Path(ephemeral_folder).resolve()
            path_posix = path.as_posix()
            if not ephemeral_index_exists(str(path)):
                _get_registry().deregister(path_posix)
                return (
                    f"ERROR: No ephemeral index found at {path_posix}/.smart-search/\n"
                    f"Run knowledge_temp_index first."
                )
            components = create_ephemeral_components(str(path))
            engine = components["engine"]
            _get_registry().touch(path_posix)
            return engine.find_related(note_path, limit=limit)

        _ensure_backend()
        data = mcp_client.find_related(note_path=note_path, limit=limit)
        return data.get("result", f"Error: {data}")

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

        _ensure_backend()
        data = mcp_client.add_folder(str(path))
        return (
            f"FOLDER ADDED\n"
            f"============\n"
            f"Path: {data.get('path', str(path))}\n"
            f"Task ID: {data.get('task_id', 'unknown')}\n"
            f"Status: {data.get('status', 'accepted')}\n"
            f"Indexing started in background."
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
        _ensure_backend()
        data = mcp_client.remove_folder(folder_path, remove_data=remove_data)
        data_line = (
            f"Data removed: {data.get('data_removed', 0)} files"
            if remove_data
            else "Data: kept (use remove_data=True to delete)"
        )
        return (
            f"FOLDER REMOVED\n"
            f"==============\n"
            f"Path: {data.get('path', folder_path)}\n"
            f"{data_line}"
        )

    @mcp.tool()
    def knowledge_list_folders() -> str:
        """List all watched folders and their status.

        Returns:
            Formatted list of watched directories from config.
        """
        _ensure_backend()
        data = mcp_client.list_folders()
        folders = data.get("folders", [])

        if not folders:
            return "No folders configured. Use knowledge_add_folder to add one."

        lines = [
            "WATCHED FOLDERS",
            "=" * 16,
            f"Total: {len(folders)}",
            "",
        ]
        for f in folders:
            status = f.get("status", "unknown")
            lines.append(f"  [{status}] {f['path']}")

        return "\n".join(lines)

    @mcp.tool()
    def knowledge_list_files() -> str:
        """List all indexed files with metadata.

        Returns:
            Formatted list of indexed files with chunk counts.
        """
        _ensure_backend()
        data = mcp_client.list_files()
        files = data.get("files", [])

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
            from smart_search.ephemeral_store import (
                calculate_ephemeral_size,
                create_ephemeral_components,
            )

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

        from smart_search.ephemeral_store import remove_ephemeral_index

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

        # Use live config from config manager for current watch dirs
        mgr = _get_config_mgr()
        watch_dirs = mgr.list_watch_dirs()
        return _read_note(note_path, watch_dirs)

    return mcp


def _format_search_response(data: dict) -> str:
    """Format HTTP search response as MCP-friendly text.

    Args:
        data: Search response dict from HTTP API.

    Returns:
        Formatted search results string.
    """
    results = data.get("results", [])
    query = data.get("query", "")
    mode = data.get("mode", "semantic")

    if not results:
        return (
            f"KNOWLEDGE SEARCH\n"
            f"================\n"
            f"Query: {query}\n"
            f"Mode: {mode}\n"
            f"No results found."
        )

    lines = [
        "KNOWLEDGE SEARCH",
        "=" * 16,
        f"Query: {query}",
        f"Mode: {mode}",
        f"Results: {len(results)}",
        "",
    ]

    for r in results:
        lines.append(f"--- Result {r['rank']} (score: {r['score']:.4f}) ---")
        lines.append(f"Source: {r['source_path']}")
        if r.get("section_path"):
            lines.append(f"Section: {r['section_path']}")
        if r.get("page_number"):
            lines.append(f"Page: {r['page_number']}")
        lines.append(f"Text: {r['text']}")
        lines.append("")

    return "\n".join(lines)


def _format_stats_response(data: dict) -> str:
    """Format HTTP stats response as MCP-friendly text.

    Args:
        data: Stats response dict from HTTP API.

    Returns:
        Formatted stats string.
    """
    size_mb = data.get("index_size_bytes", 0) / (1024 * 1024)
    formats = ", ".join(data.get("formats_indexed", [])) or "none"
    last = data.get("last_indexed_at") or "never"

    separator = "=" * 26
    return (
        f"KNOWLEDGE BASE STATISTICS\n"
        f"{separator}\n"
        f"Documents indexed: {data.get('document_count', 0)}\n"
        f"Chunks stored: {data.get('chunk_count', 0)}\n"
        f"Index size: {size_mb:.1f} MB\n"
        f"Last indexed: {last}\n"
        f"Formats indexed: {formats}"
    )


def _format_ingest_response(data: dict) -> str:
    """Format HTTP ingest response as MCP-friendly text.

    Args:
        data: Ingest response dict from HTTP API.

    Returns:
        Formatted ingest result string.
    """
    status = data.get("status", "unknown")
    path = data.get("path", "unknown")

    if status == "failed":
        return (
            f"INGEST RESULT\n"
            f"=============\n"
            f"Path: {path}\n"
            f"Status: FAILED\n"
            f"Error: {data.get('error', 'unknown')}"
        )

    if status == "accepted":
        return (
            f"INGEST RESULT\n"
            f"=============\n"
            f"Path: {path}\n"
            f"Status: Indexing started in background\n"
            f"Task ID: {data.get('task_id', 'unknown')}\n"
            f"Poll knowledge_stats() to check progress."
        )

    return (
        f"INGEST RESULT\n"
        f"=============\n"
        f"Path: {path}\n"
        f"Status: {status}\n"
        f"Indexed: {data.get('indexed', 0)} files\n"
        f"Skipped: {data.get('skipped', 0)} files\n"
        f"Failed: {data.get('failed', 0)} files\n"
        f"Chunks: {data.get('chunk_count', 0)}"
    )


# Default server for `python -m smart_search.server`
mcp = create_server()


def main():
    """Run the MCP server via stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
