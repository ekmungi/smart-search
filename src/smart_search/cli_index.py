# CLI index and ingest subcommand handlers.

"""Functions for the 'index' CLI subcommand: list, remove, rebuild, ingest.
Also includes ephemeral ingest and the shared progress bar helper."""

from smart_search.data_dir import get_data_dir


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
            result = _index_folder_with_progress(indexer, d, force=True)
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
            result = _index_folder_with_progress(indexer, str(target))
            print(f"Indexed: {result.indexed} files, skipped: {result.skipped}, failed: {result.failed}")
        else:
            print(f"Path not found: {args.path}")
    else:
        print("Use: smart-search index [list|remove|rebuild|ingest]")


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


def _build_indexer(cfg, store):
    """Build a DocumentIndexer with the MarkdownChunker pipeline.

    Args:
        cfg: SmartSearchConfig instance.
        store: ChunkStore instance.

    Returns:
        Configured DocumentIndexer.
    """
    from smart_search.embedder import Embedder
    from smart_search.indexer import DocumentIndexer
    from smart_search.markdown_chunker import MarkdownChunker

    return DocumentIndexer(
        config=cfg,
        embedder=Embedder(cfg),
        store=store,
        markdown_chunker=MarkdownChunker(cfg),
    )


def _index_folder_with_progress(indexer, folder_path, force=False):
    """Index a folder with a tqdm progress bar.

    Counts files first, then indexes with a live progress bar showing
    file name, status counts, and ETA.

    Args:
        indexer: DocumentIndexer instance.
        folder_path: Path to the folder to index.
        force: If True, re-index all files regardless of hash.

    Returns:
        IndexFolderResult from the indexer.
    """
    from pathlib import Path

    from tqdm import tqdm

    # Count files first for the progress bar total.
    supported = indexer._config.supported_extensions
    files = [
        p for p in sorted(Path(folder_path).glob("**/*"))
        if p.is_file() and p.suffix.lower() in supported
    ]

    if not files:
        return indexer.index_folder(folder_path, force=force)

    pbar = tqdm(total=len(files), unit="file", desc="Indexing", ncols=80)
    counts = {"indexed": 0, "skipped": 0, "failed": 0}

    def on_progress(file_path, result):
        """Update progress bar after each file."""
        counts[result.status] = counts.get(result.status, 0) + 1
        name = Path(file_path).name
        # Truncate long filenames to keep the bar clean
        display = name if len(name) <= 30 else name[:27] + "..."
        pbar.set_postfix_str(
            f"{display} | +{counts['indexed']} ~{counts['skipped']} !{counts['failed']}",
            refresh=False,
        )
        pbar.update(1)

    result = indexer.index_folder(folder_path, force=force, on_progress=on_progress)
    pbar.close()
    return result


def _cmd_ingest_ephemeral(target):
    """Create an ephemeral index inside the target folder.

    Args:
        target: Resolved Path to the folder to index.
    """
    from smart_search.ephemeral_registry import EphemeralRegistry
    from smart_search.ephemeral_store import (
        calculate_ephemeral_size,
        create_ephemeral_components,
    )

    print(f"Creating ephemeral index in {target}/.smart-search/")
    components = create_ephemeral_components(str(target))
    indexer = components["indexer"]
    result = _index_folder_with_progress(indexer, str(target))

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
