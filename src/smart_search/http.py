# HTTP REST API server for the smart-search desktop app.

"""Creates a FastAPI application exposing the knowledge base via REST.
Used by the Tauri desktop shell and any HTTP client. Shares the same
data directory and components as the MCP server."""

import threading
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from smart_search.config import SmartSearchConfig, get_config
from smart_search.config_manager import ConfigManager
from smart_search.data_dir import get_data_dir
from smart_search.http_routes import create_router
from smart_search.indexing_task import IndexingTaskManager

if TYPE_CHECKING:
    from smart_search.indexer import DocumentIndexer
    from smart_search.search import SearchEngine
    from smart_search.store import ChunkStore
    from smart_search.watcher import FileWatcher


def create_app(
    search_engine: Optional["SearchEngine"] = None,
    store: Optional["ChunkStore"] = None,
    config: Optional[SmartSearchConfig] = None,
    indexer: Optional["DocumentIndexer"] = None,
    config_manager: Optional[ConfigManager] = None,
    watcher: Optional["FileWatcher"] = None,
    task_manager: Optional[IndexingTaskManager] = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Accepts optional pre-built components for testing. When called
    without arguments, creates real components lazily on first use.

    Args:
        search_engine: Optional SearchEngine instance.
        store: Optional ChunkStore instance.
        config: Optional SmartSearchConfig override.
        indexer: Optional DocumentIndexer instance.
        config_manager: Optional ConfigManager instance.
        watcher: Optional FileWatcher instance.
        task_manager: Optional IndexingTaskManager instance.

    Returns:
        Configured FastAPI application.
    """
    if config is None:
        # Merge persisted config.json values into runtime config
        base = get_config()
        mgr = ConfigManager(get_data_dir())
        persisted = mgr.load()
        if persisted:
            # Build override dict from config.json, keeping only known fields
            overrides = {}
            for key, value in persisted.items():
                if hasattr(base, key):
                    overrides[key] = value
            if overrides:
                config = SmartSearchConfig(**overrides)
            else:
                config = base
        else:
            config = base

    # Mutable dict avoids nonlocal for start_time assignment in lifespan
    state = {"start_time": 0.0}
    # Lock protects lazy singleton creation from races between the
    # background startup thread and incoming HTTP request handlers.
    _singleton_lock = threading.Lock()
    _engine = search_engine
    _store = store
    _indexer = indexer
    _config_mgr = config_manager
    _watcher = watcher
    _task_mgr = task_manager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Record start time, launch background startup tasks, yield immediately.

        Heavy startup work (index compatibility check, orphan reconciliation,
        FTS backfill, auto-resume) runs in a daemon thread so uvicorn binds
        the port without waiting for those operations to complete.
        """
        import logging
        _logger = logging.getLogger(__name__)

        state["start_time"] = time.time()

        def _run_startup_tasks():
            """Run blocking startup checks and auto-resume in a background thread.

            Runs: check_index_compatibility -> reconcile_orphans ->
            backfill_fts_if_needed -> submit auto-resume for each watched folder.
            All errors are caught and logged so the server stays up regardless.
            """
            # Run startup checks (non-blocking, log-only)
            try:
                from smart_search.startup import (
                    backfill_fts_if_needed,
                    check_index_compatibility,
                    reconcile_orphans,
                )
                check_index_compatibility(config, config.sqlite_path)
                reconcile_orphans(get_store())
                backfill_fts_if_needed(get_store())
            except Exception as e:
                _logger.warning("Startup checks failed (non-fatal): %s", e)

            # Resume indexing for any watched folders that have un-indexed files.
            # Hash-based skip ensures already-indexed files are not re-processed.
            try:
                from smart_search.data_dir import get_data_dir
                data_dir = get_data_dir()
                resume_mgr = ConfigManager(data_dir)
                live_cfg = resume_mgr.load()
                folders = live_cfg.get("watch_directories", [])
                print(f"Startup: {len(folders)} watched folders to resume", flush=True)
                for folder in folders:
                    print(f"Startup: queuing {folder}", flush=True)
                    get_task_mgr().submit(folder, get_indexer())
            except Exception as e:
                import traceback
                print(f"Startup: auto-resume FAILED: {e}", flush=True)
                traceback.print_exc()

        # Start background thread before yielding; daemon=True ensures it does
        # not block process shutdown if the server exits before tasks complete.
        t = threading.Thread(target=_run_startup_tasks, daemon=True, name="startup-tasks")
        t.start()

        yield
        if _watcher is not None and getattr(_watcher, "is_running", False):
            _watcher.stop()
        if _task_mgr is not None:  # Only shutdown if it was created
            _task_mgr.shutdown()

    app = FastAPI(
        title="Smart Search API",
        version="0.8.3",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_store():
        """Get or create the ChunkStore singleton (thread-safe)."""
        nonlocal _store
        if _store is None:
            with _singleton_lock:
                if _store is None:
                    from smart_search.store import ChunkStore as _CS
                    _store = _CS(config)
                    _store.initialize()
        return _store

    def get_engine():
        """Get or create the SearchEngine singleton (thread-safe)."""
        nonlocal _engine
        if _engine is None:
            with _singleton_lock:
                if _engine is None:
                    from smart_search.embedder import Embedder
                    from smart_search.search import SearchEngine as _SE
                    _engine = _SE(config, Embedder(config), get_store())
        return _engine

    def get_indexer():
        """Get or create the DocumentIndexer singleton (thread-safe)."""
        nonlocal _indexer
        if _indexer is None:
            with _singleton_lock:
                if _indexer is None:
                    from smart_search.embedder import Embedder
                    from smart_search.indexer import DocumentIndexer as _DI
                    from smart_search.markdown_chunker import MarkdownChunker
                    _indexer = _DI(
                        config=config,
                        embedder=Embedder(config),
                        store=get_store(),
                        markdown_chunker=MarkdownChunker(config),
                    )
        return _indexer

    def get_config_mgr():
        """Get or create the ConfigManager singleton (thread-safe)."""
        nonlocal _config_mgr
        if _config_mgr is None:
            with _singleton_lock:
                if _config_mgr is None:
                    _config_mgr = ConfigManager(get_data_dir())
        return _config_mgr

    def get_watcher():
        """Get or create the FileWatcher singleton (thread-safe)."""
        nonlocal _watcher
        if _watcher is None:
            with _singleton_lock:
                if _watcher is None:
                    from smart_search.watcher import FileWatcher as _FW
                    _watcher = _FW(config, get_indexer(), get_store())
        return _watcher

    def get_task_mgr():
        """Get or create the IndexingTaskManager singleton (thread-safe)."""
        nonlocal _task_mgr
        if _task_mgr is None:
            with _singleton_lock:
                if _task_mgr is None:
                    _task_mgr = IndexingTaskManager()
        return _task_mgr

    _registry = None

    def get_registry():
        """Get or create the EphemeralRegistry singleton."""
        nonlocal _registry
        if _registry is None:
            from smart_search.ephemeral_registry import EphemeralRegistry
            _registry = EphemeralRegistry(config.sqlite_path)
            _registry.initialize()
        return _registry

    def get_uptime():
        """Return seconds since server started."""
        return time.time() - state["start_time"]

    def reset_embedding_singletons():
        """Invalidate cached engine and indexer so they're recreated with new config."""
        nonlocal _engine, _indexer
        _engine = None
        _indexer = None

    # Wire up all API routes
    router = create_router(
        get_engine=get_engine,
        get_store=get_store,
        get_indexer=get_indexer,
        get_config_mgr=get_config_mgr,
        get_watcher=get_watcher,
        get_uptime=get_uptime,
        get_task_mgr=get_task_mgr,
        get_registry=get_registry,
        reset_embedding_singletons=reset_embedding_singletons,
        config=config,
    )
    app.include_router(router)

    return app


def main(host: str = "127.0.0.1", port: int = 9742):
    """Start the HTTP API server with uvicorn.

    Args:
        host: Bind address (default localhost only).
        port: Listen port (default 9742).
    """
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
