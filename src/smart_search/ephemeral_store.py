# Factory for folder-local ephemeral indexes stored in .smart-search/ subdirectories.

import shutil
from pathlib import Path
from typing import Any, Dict

from smart_search.config import SmartSearchConfig
from smart_search.store import ChunkStore


def create_ephemeral_components(folder_path: str) -> Dict[str, Any]:
    """Create all components for a folder-local ephemeral index.

    Resolves folder_path, creates a .smart-search/ subdirectory, and
    instantiates a full search stack (store, indexer, engine) pointed at
    that local directory so the index lives beside the content.

    Args:
        folder_path: Absolute or relative path to the target directory.

    Returns:
        Dict with keys: store (ChunkStore), indexer (DocumentIndexer),
        engine (SearchEngine), config (SmartSearchConfig).

    Raises:
        ValueError: If folder_path does not resolve to an existing directory.
    """
    # Imports inside function to avoid circular imports at module load time.
    from smart_search.embedder import Embedder
    from smart_search.indexer import DocumentIndexer
    from smart_search.markdown_chunker import MarkdownChunker
    from smart_search.search import SearchEngine

    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        raise ValueError(f"folder_path is not a directory: {folder_path}")

    smart_search_dir = folder / ".smart-search"
    smart_search_dir.mkdir(parents=True, exist_ok=True)

    config = SmartSearchConfig(
        lancedb_path=str(smart_search_dir / "vectors"),
        sqlite_path=str(smart_search_dir / "metadata.db"),
    )

    store = ChunkStore(config)
    store.initialize()

    embedder = Embedder(config)
    markdown_chunker = MarkdownChunker(config)
    indexer = DocumentIndexer(
        config=config,
        embedder=embedder,
        store=store,
        markdown_chunker=markdown_chunker,
    )
    engine = SearchEngine(config=config, embedder=embedder, store=store)

    return {
        "store": store,
        "indexer": indexer,
        "engine": engine,
        "config": config,
    }


def ephemeral_index_exists(folder_path: str) -> bool:
    """Check whether a folder-local .smart-search/ index exists.

    Args:
        folder_path: Path to the target directory.

    Returns:
        True if .smart-search/ exists inside folder_path, False otherwise.
    """
    smart_search_dir = Path(folder_path) / ".smart-search"
    return smart_search_dir.is_dir()


def calculate_ephemeral_size(folder_path: str) -> int:
    """Return total byte size of all files inside the .smart-search/ directory.

    Args:
        folder_path: Path to the target directory.

    Returns:
        Total size in bytes, or 0 if .smart-search/ does not exist.
    """
    smart_search_dir = Path(folder_path) / ".smart-search"
    if not smart_search_dir.exists():
        return 0
    return sum(
        f.stat().st_size
        for f in smart_search_dir.rglob("*")
        if f.is_file()
    )


def remove_ephemeral_index(folder_path: str) -> bool:
    """Delete the .smart-search/ directory for a folder.

    Args:
        folder_path: Path to the target directory.

    Returns:
        True if the directory was removed, False if it did not exist.
    """
    smart_search_dir = Path(folder_path) / ".smart-search"
    if not smart_search_dir.exists():
        return False
    shutil.rmtree(smart_search_dir)
    return True
