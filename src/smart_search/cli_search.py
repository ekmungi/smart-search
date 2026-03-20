# CLI search subcommand handler.

"""Handles the 'search' CLI subcommand with global and ephemeral index support."""


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

    from smart_search.config import SmartSearchConfig
    cfg = SmartSearchConfig(
        lancedb_path=str(data_dir / "vectors"),
        sqlite_path=str(data_dir / "metadata.db"),
    )
    store = ChunkStore(cfg)
    store.initialize()
    embedder = Embedder(cfg)
    engine = SearchEngine(cfg, embedder, store)
    result = engine.search(
        query=args.query, limit=args.limit, folder=args.folder,
    )
    print(result)
