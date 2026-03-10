# Command-line interface for smart-search.

"""CLI with subcommands for config, watch, index, search, and model management."""

import argparse
import sys

from smart_search.config_manager import ConfigManager
from smart_search.data_dir import get_data_dir


def main(argv=None):
    """Entry point for the smart-search CLI.

    Args:
        argv: Command line arguments (defaults to sys.argv).
    """
    parser = argparse.ArgumentParser(
        prog="smart-search",
        description="Local semantic search for documents and notes.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- stats ---
    subparsers.add_parser("stats", help="Show index statistics and data directory")

    # --- config ---
    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_sub = config_parser.add_subparsers(dest="config_command")
    config_sub.add_parser("show", help="Show current configuration")

    # --- watch ---
    watch_parser = subparsers.add_parser("watch", help="Watch directory management")
    watch_sub = watch_parser.add_subparsers(dest="watch_command")
    watch_sub.add_parser("list", help="List watched directories")
    watch_add = watch_sub.add_parser("add", help="Add a watch directory")
    watch_add.add_argument("path", help="Directory path to watch")
    watch_remove = watch_sub.add_parser("remove", help="Remove a watch directory")
    watch_remove.add_argument("path", help="Directory path to stop watching")

    # --- index ---
    index_parser = subparsers.add_parser("index", help="Index management")
    index_sub = index_parser.add_subparsers(dest="index_command")
    index_sub.add_parser("list", help="List indexed files")
    index_remove = index_sub.add_parser("remove", help="Remove files from index")
    index_remove.add_argument("path", help="File or folder path to remove")
    index_sub.add_parser("rebuild", help="Rebuild entire index")
    index_ingest = index_sub.add_parser("ingest", help="Index a file or folder")
    index_ingest.add_argument("path", help="File or folder path to index")
    index_ingest.add_argument(
        "--ephemeral", action="store_true",
        help="Create a local .smart-search/ index inside the folder (not global)",
    )

    # --- search ---
    search_parser = subparsers.add_parser("search", help="Search the knowledge base")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=10, help="Max results")
    search_parser.add_argument("--folder", help="Filter results to a folder")
    search_parser.add_argument(
        "--ephemeral", help="Search a folder's local .smart-search/ index",
    )

    # --- temp ---
    temp_parser = subparsers.add_parser("temp", help="Ephemeral index management")
    temp_sub = temp_parser.add_subparsers(dest="temp_command")
    temp_sub.add_parser("list", help="List all ephemeral indexes")
    temp_cleanup = temp_sub.add_parser("cleanup", help="Remove an ephemeral index")
    temp_cleanup.add_argument("path", help="Folder path to clean up")

    # --- model ---
    model_parser = subparsers.add_parser("model", help="Embedding model management")
    model_sub = model_parser.add_subparsers(dest="model_command")
    model_sub.add_parser("show", help="Show current and index models")
    model_set = model_sub.add_parser("set", help="Change embedding model")
    model_set.add_argument("name", help="Model name (e.g., nomic-ai/nomic-embed-text-v1.5)")
    model_set.add_argument("--dim", type=int, help="Embedding dimensions")

    args = parser.parse_args(argv)
    data_dir = get_data_dir()
    cm = ConfigManager(data_dir)

    if args.command == "stats":
        _cmd_stats(data_dir, cm)
    elif args.command == "config" and args.config_command == "show":
        _cmd_config_show(data_dir, cm)
    elif args.command == "watch":
        _cmd_watch(args, cm)
    elif args.command == "index":
        _cmd_index(args, data_dir)
    elif args.command == "search":
        _cmd_search(args, data_dir)
    elif args.command == "temp":
        _cmd_temp(args, data_dir)
    elif args.command == "model":
        _cmd_model(args, cm)
    else:
        parser.print_help()


def _build_config(data_dir):
    """Build a SmartSearchConfig using the data directory.

    Args:
        data_dir: Path to the data directory.

    Returns:
        SmartSearchConfig with paths set to data_dir.
    """
    from smart_search.config import SmartSearchConfig

    return SmartSearchConfig(
        lancedb_path=str(data_dir / "vectors"),
        sqlite_path=str(data_dir / "metadata.db"),
    )


def _cmd_stats(data_dir, cm):
    """Print index statistics.

    Args:
        data_dir: Path to the data directory.
        cm: ConfigManager instance.
    """
    from smart_search.store import ChunkStore

    print(f"Data directory: {data_dir}")
    config = cm.load()
    print(f"Watch directories: {len(config.get('watch_directories', []))}")

    cfg = _build_config(data_dir)
    store = ChunkStore(cfg)
    store.initialize()
    stats = store.get_stats()
    size_mb = stats.index_size_bytes / (1024 * 1024)
    print(f"Documents indexed: {stats.document_count}")
    print(f"Chunks stored: {stats.chunk_count}")
    print(f"Index size: {size_mb:.1f} MB")


def _cmd_config_show(data_dir, cm):
    """Print current configuration.

    Args:
        data_dir: Path to the data directory.
        cm: ConfigManager instance.
    """
    import json

    config = cm.load()
    print(f"Data directory: {data_dir}")
    print(f"Config file: {cm.config_path}")
    print(json.dumps(config, indent=2))


def _cmd_watch(args, cm):
    """Handle watch subcommands.

    Args:
        args: Parsed CLI arguments.
        cm: ConfigManager instance.
    """
    if args.watch_command == "list":
        dirs = cm.list_watch_dirs()
        if not dirs:
            print("No watch directories configured.")
        for d in dirs:
            print(f"  {d}")
    elif args.watch_command == "add":
        cm.add_watch_dir(args.path)
        print(f"Added: {args.path}")
    elif args.watch_command == "remove":
        cm.remove_watch_dir(args.path)
        print(f"Removed: {args.path}")
    else:
        print("Use: smart-search watch [list|add|remove]")


def _cmd_index(args, data_dir):
    """Handle index subcommands.

    Args:
        args: Parsed CLI arguments.
        data_dir: Path to the data directory.
    """
    from smart_search.store import ChunkStore

    cfg = _build_config(data_dir)
    store = ChunkStore(cfg)
    store.initialize()

    if args.index_command == "list":
        files = store.list_indexed_files()
        if not files:
            print("No files indexed yet.")
            return
        print(f"Indexed files: {len(files)}")
        for f in files:
            print(f"  {f['source_path']} ({f['chunk_count']} chunks)")
    elif args.index_command == "remove":
        count = store.remove_files_for_folder(args.path)
        print(f"Removed {count} files from index.")
    elif args.index_command == "rebuild":
        print("Rebuild: re-indexing all watched directories...")
        indexer = _build_indexer(cfg, store)
        from smart_search.config_manager import ConfigManager
        cm = ConfigManager(data_dir)
        for d in cm.list_watch_dirs():
            result = indexer.index_folder(d, force=True)
            print(f"  {d}: {result.indexed} indexed, {result.failed} failed")
    elif args.index_command == "ingest":
        from pathlib import Path
        target = Path(args.path).resolve()

        if getattr(args, "ephemeral", False) and target.is_dir():
            _cmd_ingest_ephemeral(target)
        elif target.is_file():
            indexer = _build_indexer(cfg, store)
            result = indexer.index_file(str(target))
            print(f"Indexed: {result.file_path} ({result.chunk_count} chunks, {result.status})")
        elif target.is_dir():
            indexer = _build_indexer(cfg, store)
            result = indexer.index_folder(str(target))
            print(f"Indexed: {result.indexed} files, skipped: {result.skipped}, failed: {result.failed}")
        else:
            print(f"Path not found: {args.path}")
    else:
        print("Use: smart-search index [list|remove|rebuild|ingest]")


def _build_indexer(cfg, store):
    """Build a DocumentIndexer with all chunkers.

    Args:
        cfg: SmartSearchConfig instance.
        store: ChunkStore instance.

    Returns:
        Configured DocumentIndexer.
    """
    from smart_search.chunker import DocumentChunker
    from smart_search.embedder import Embedder
    from smart_search.indexer import DocumentIndexer
    from smart_search.markdown_chunker import MarkdownChunker

    return DocumentIndexer(
        config=cfg,
        chunker=DocumentChunker(cfg),
        embedder=Embedder(cfg),
        store=store,
        markdown_chunker=MarkdownChunker(cfg),
    )


def _cmd_search(args, data_dir):
    """Handle search command.

    Args:
        args: Parsed CLI arguments.
        data_dir: Path to the data directory.
    """
    from smart_search.embedder import Embedder
    from smart_search.search import SearchEngine
    from smart_search.store import ChunkStore

    if getattr(args, "ephemeral", None):
        from pathlib import Path
        from smart_search.ephemeral_store import (
            create_ephemeral_components,
            ephemeral_index_exists,
        )
        eph_path = Path(args.ephemeral).resolve()
        if not ephemeral_index_exists(str(eph_path)):
            print(f"No ephemeral index at {eph_path}/.smart-search/")
            print("Run: smart-search index ingest <folder> --ephemeral")
            return
        components = create_ephemeral_components(str(eph_path))
        engine = components["engine"]
        result = engine.search(query=args.query, limit=args.limit)
        print(result)
        return

    cfg = _build_config(data_dir)
    store = ChunkStore(cfg)
    store.initialize()
    embedder = Embedder(cfg)
    engine = SearchEngine(cfg, embedder, store)
    result = engine.search(
        query=args.query, limit=args.limit, folder=args.folder,
    )
    print(result)


def _cmd_ingest_ephemeral(target):
    """Create an ephemeral index inside the target folder.

    Args:
        target: Resolved Path to the folder to index.
    """
    from smart_search.ephemeral_store import (
        calculate_ephemeral_size,
        create_ephemeral_components,
    )
    from smart_search.ephemeral_registry import EphemeralRegistry

    print(f"Creating ephemeral index in {target}/.smart-search/")
    components = create_ephemeral_components(str(target))
    indexer = components["indexer"]
    result = indexer.index_folder(str(target))

    size = calculate_ephemeral_size(str(target))
    total_chunks = sum(
        r.chunk_count for r in result.results if r.status == "indexed"
    )

    # Register in global registry
    data_dir = get_data_dir()
    cfg = _build_config(data_dir)
    registry = EphemeralRegistry(cfg.sqlite_path)
    registry.initialize()
    registry.register(target.as_posix(), total_chunks, size)

    print(f"Indexed: {result.indexed} files")
    print(f"Skipped: {result.skipped} files")
    print(f"Failed: {result.failed} files")
    print(f"Chunks: {total_chunks}")
    print(f"Size: {size / 1024:.1f} KB")
    print(f"\nSearch with: smart-search search \"query\" --ephemeral \"{target}\"")


def _cmd_temp(args, data_dir):
    """Handle temp (ephemeral index) subcommands.

    Args:
        args: Parsed CLI arguments.
        data_dir: Path to the data directory.
    """
    from smart_search.ephemeral_registry import EphemeralRegistry
    from smart_search.ephemeral_store import remove_ephemeral_index

    cfg = _build_config(data_dir)
    registry = EphemeralRegistry(cfg.sqlite_path)
    registry.initialize()

    if args.temp_command == "list":
        pruned = registry.prune_stale()
        if pruned:
            print(f"Pruned {len(pruned)} stale entries")
        entries = registry.list_all()
        if not entries:
            print("No ephemeral indexes found.")
            return
        print(f"Ephemeral indexes: {len(entries)}")
        for entry in entries:
            size_kb = entry.size_bytes / 1024
            print(f"  {entry.folder_path}")
            print(f"    Chunks: {entry.chunk_count}, Size: {size_kb:.1f} KB, Created: {entry.created_at}")
    elif args.temp_command == "cleanup":
        from pathlib import Path
        path = Path(args.path).resolve()
        removed = remove_ephemeral_index(str(path))
        registry.deregister(path.as_posix())
        if removed:
            print(f"Cleaned up: {path.as_posix()}/.smart-search/ deleted")
        else:
            print(f"No .smart-search/ found at {path.as_posix()}")
    else:
        print("Use: smart-search temp [list|cleanup]")


def _cmd_model(args, cm):
    """Handle model subcommands.

    Args:
        args: Parsed CLI arguments.
        cm: ConfigManager instance.
    """
    config = cm.load()
    if args.model_command == "show":
        print(f"Config model: {config.get('embedding_model', 'unknown')}")
        print(f"Config dimensions: {config.get('embedding_dimensions', 'unknown')}")
    elif args.model_command == "set":
        config["embedding_model"] = args.name
        if args.dim:
            config["embedding_dimensions"] = str(args.dim)
        cm.save(config)
        print(f"Model set to: {args.name}")
        print("WARNING: Run 'smart-search index rebuild' to re-index with the new model.")
    else:
        print("Use: smart-search model [show|set]")


if __name__ == "__main__":
    main()
