# API route handlers for the smart-search HTTP server.

"""All REST endpoint handlers as a FastAPI APIRouter. Routes receive
component getter functions from the app factory and delegate to the
same backend components used by the MCP server."""

import logging
from pathlib import Path
from typing import Callable

_logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import JSONResponse

from smart_search.config import SmartSearchConfig
from smart_search.constants import APP_VERSION, BYTES_PER_MB
from smart_search.http_models import (
    AddFolderRequest,
    AddFolderResponse,
    ConfigResponse,
    ConfigUpdateRequest,
    ConfigUpdateResponse,
    RepairResponse,
    FailedFileInfo,
    FileInfo,
    ProcessedFileInfo,
    FilesResponse,
    FolderInfo,
    FoldersResponse,
    HealthResponse,
    IndexingStatusResponse,
    IndexingTaskStatus,
    IngestRequest,
    IngestResponse,
    RemoveFolderResponse,
    SearchHit,
    SearchResponse,
    StatsResponse,
)
from smart_search.http_routes_ephemeral import create_ephemeral_router
from smart_search.http_routes_model import create_model_router


def create_router(
    get_engine: Callable,
    get_store: Callable,
    get_indexer: Callable,
    get_config_mgr: Callable,
    get_watcher: Callable,
    get_uptime: Callable,
    get_task_mgr: Callable,
    get_registry: Callable,
    reset_embedding_singletons: Callable,
    config: SmartSearchConfig,
) -> APIRouter:
    """Create an APIRouter with all REST endpoints.

    Each getter is a zero-arg callable that returns a lazily-initialized
    component. This mirrors the closure pattern in server.py.

    Args:
        get_engine: Returns SearchEngine instance.
        get_store: Returns ChunkStore instance.
        get_indexer: Returns DocumentIndexer instance.
        get_config_mgr: Returns ConfigManager instance.
        get_watcher: Returns FileWatcher instance.
        get_uptime: Returns server uptime in seconds.
        get_task_mgr: Returns IndexingTaskManager instance.
        get_registry: Returns EphemeralRegistry instance.
        reset_embedding_singletons: Invalidates cached engine/indexer singletons.
        config: SmartSearchConfig instance.

    Returns:
        Configured APIRouter with /api prefix.
    """
    router = APIRouter(prefix="/api")

    # Include sub-routers for ephemeral and model endpoints
    router.include_router(create_ephemeral_router(get_registry))
    router.include_router(create_model_router(get_engine, get_config_mgr, config))

    @router.get("/health", response_model=HealthResponse)
    def health():
        """Server health check with version and uptime."""
        return HealthResponse(
            status="ok",
            version=APP_VERSION,
            uptime_seconds=round(get_uptime(), 1),
        )

    @router.get("/stats", response_model=StatsResponse)
    def stats():
        """Get index statistics: document count, chunks, size, formats.

        Uses live watch_directories from ConfigManager so stats reflect
        folders added/removed since server start (B22).
        """
        store = get_store()
        live_dirs = get_config_mgr().list_watch_dirs()
        s = store.get_stats(watch_directories=live_dirs)
        return StatsResponse(
            document_count=s.document_count,
            chunk_count=s.chunk_count,
            index_size_bytes=s.index_size_bytes,
            index_size_mb=round(s.index_size_bytes / BYTES_PER_MB, 2),
            total_files=s.total_files,
            last_indexed_at=s.last_indexed_at,
            formats_indexed=s.formats_indexed,
        )

    @router.get("/find-related")
    def find_related_endpoint(
        note_path: str = Query(..., description="Path to source note"),
        limit: int = Query(10, ge=1, le=100),
    ):
        """Find notes related to a given note by vector similarity."""
        engine = get_engine()
        result = engine.find_related(note_path, limit=limit)
        return {"note_path": note_path, "limit": limit, "result": result}

    @router.get("/search", response_model=SearchResponse)
    def search(
        q: str = Query(..., description="Search query"),
        limit: int = Query(10, ge=1, le=100),
        mode: str = Query("hybrid", description="Search mode: semantic, keyword, hybrid"),
        folder: str = Query(None, description="Folder prefix filter"),
        doc_types: str = Query(None, description="Comma-separated types"),
    ):
        """Search the knowledge base with optional filters."""
        engine = get_engine()
        types_list = (
            [t.strip() for t in doc_types.split(",") if t.strip()]
            if doc_types
            else None
        )
        results = engine.search_results(
            query=q, limit=limit, mode=mode,
            doc_types=types_list, folder=folder,
        )
        hits = [
            SearchHit(
                rank=r.rank,
                score=round(r.score, 4),
                source_path=r.chunk.source_path,
                source_type=r.chunk.source_type,
                text=r.chunk.text[:500],
                page_number=r.chunk.page_number,
                section_path=r.chunk.section_path,
                filename=r.chunk.source_path.rsplit("/", 1)[-1],
            )
            for r in results
        ]
        return SearchResponse(
            query=q, mode=mode, total=len(hits), results=hits,
        )

    @router.get("/folders", response_model=FoldersResponse)
    def list_folders():
        """List all watched folders with existence status."""
        mgr = get_config_mgr()
        dirs = mgr.list_watch_dirs()
        folders = [
            FolderInfo(
                path=d,
                exists=Path(d).is_dir(),
                status="active" if Path(d).is_dir() else "missing",
            )
            for d in dirs
        ]
        return FoldersResponse(total=len(folders), folders=folders)

    @router.post("/folders")
    def add_folder(req: AddFolderRequest):
        """Add a folder to the watch list and submit background indexing.

        Returns 202 Accepted immediately. Use GET /api/indexing/status
        to poll for progress.
        """
        path = Path(req.path).resolve()
        if not path.is_dir():
            raise HTTPException(
                status_code=404,
                detail=f"Directory not found: {req.path}",
            )

        _logger.info("add_folder: submitting background index for %s", path.as_posix())
        mgr = get_config_mgr()
        mgr.add_watch_dir(str(path))

        watcher = get_watcher()
        if not watcher.is_running:
            watcher.start()
        watcher.add_directory(str(path))

        task_id = get_task_mgr().submit(str(path), get_indexer())

        return JSONResponse(
            status_code=202,
            content={
                "path": path.as_posix(),
                "task_id": task_id,
                "status": "accepted",
            },
        )

    @router.delete("/folders", response_model=RemoveFolderResponse)
    def remove_folder(
        path: str = Query(..., description="Folder path to remove"),
        remove_data: bool = Query(False),
    ):
        """Remove a folder from the watch list, optionally deleting data.

        Cancels any active background indexing task for the folder first.
        """
        resolved = Path(path).resolve()
        path_posix = resolved.as_posix()

        # Cancel any active indexing for this folder before removal
        get_task_mgr().cancel_folder(path_posix)

        mgr = get_config_mgr()
        mgr.remove_watch_dir(str(resolved))

        watcher = get_watcher()
        watcher.remove_directory(str(resolved))

        removed_count = 0
        if remove_data:
            store = get_store()
            removed_count = store.remove_files_for_folder(path_posix)

        return RemoveFolderResponse(
            path=path_posix, data_removed=removed_count,
        )

    @router.get("/files", response_model=FilesResponse)
    def list_files(
        folder: str = Query(None, description="Filter by folder prefix"),
    ):
        """List all indexed files with optional folder filter."""
        store = get_store()
        files = store.list_indexed_files()

        if folder:
            normalized = folder.replace("\\", "/")
            if not normalized.endswith("/"):
                normalized += "/"
            files = [
                f for f in files
                if f["source_path"].startswith(normalized)
            ]

        file_infos = [
            FileInfo(
                source_path=f["source_path"],
                chunk_count=f["chunk_count"],
                indexed_at=f["indexed_at"],
            )
            for f in files
        ]
        return FilesResponse(total=len(file_infos), files=file_infos)

    @router.post("/ingest")
    def ingest(req: IngestRequest):
        """Trigger indexing of a file or folder.

        Single files are indexed synchronously (fast). Directories are
        submitted as background tasks and return 202 Accepted immediately.
        """
        target = Path(req.path).resolve()
        indexer = get_indexer()

        if target.is_file():
            result = indexer.index_file(str(target), force=req.force)
            return IngestResponse(
                path=str(target),
                status=result.status,
                indexed=1 if result.status == "indexed" else 0,
                chunk_count=result.chunk_count,
                error=result.error,
            )
        elif target.is_dir():
            _logger.info("ingest: submitting background index for %s (force=%s)", target.as_posix(), req.force)
            task_id = get_task_mgr().submit(str(target), indexer, force=req.force)
            return JSONResponse(
                status_code=202,
                content={
                    "path": target.as_posix(),
                    "task_id": task_id,
                    "status": "accepted",
                },
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Path not found: {req.path}",
            )

    @router.get("/indexing/status", response_model=IndexingStatusResponse)
    def indexing_status():
        """Get status of all indexing tasks, including active ones.

        Returns a list of all tracked tasks with state, folder, and counts.
        Use this endpoint to poll for background indexing progress.
        """
        task_mgr = get_task_mgr()
        all_tasks = task_mgr.get_all_tasks()
        active_count = sum(1 for t in all_tasks if t.state == "running")
        task_statuses = [
            IndexingTaskStatus(
                task_id=t.task_id,
                folder=t.folder,
                state=t.state,
                total=t.total,
                indexed=t.indexed,
                skipped=t.skipped,
                failed=t.failed,
                error=t.error,
                failed_files=[
                    FailedFileInfo(path=f["path"], error=f["error"])
                    for f in getattr(t, "failed_files", [])
                ],
                processed_files=[
                    ProcessedFileInfo(
                        name=f["name"], path=f["path"], status=f["status"],
                        chunks=f.get("chunks"), error=f.get("error"),
                    )
                    for f in getattr(t, "processed_files", [])
                ],
            )
            for t in all_tasks
        ]
        return IndexingStatusResponse(active=active_count, tasks=task_statuses)

    @router.get("/config", response_model=ConfigResponse)
    def get_config():
        """Get current configuration as a dictionary."""
        mgr = get_config_mgr()
        return ConfigResponse(config=mgr.load())

    @router.put("/config", response_model=ConfigUpdateResponse)
    def update_config(req: ConfigUpdateRequest):
        """Merge provided keys into the current configuration.

        If embedding_model or embedding_dimensions changed, triggers
        a table rebuild (drops and recreates LanceDB table).
        """
        mgr = get_config_mgr()
        current = mgr.load()
        old_model = current.get("embedding_model")
        old_dims = current.get("embedding_dimensions")

        merged = {**current, **req.config}
        mgr.save(merged)

        # Detect embedding config change requiring re-index
        new_model = merged.get("embedding_model")
        new_dims = merged.get("embedding_dimensions")
        requires_reindex = (new_model != old_model) or (new_dims != old_dims)

        if requires_reindex:
            store = get_store()
            store.rebuild_table()
            reset_embedding_singletons()

            # Submit all watched folders for background re-indexing
            folders = get_config_mgr().list_watch_dirs()
            for folder in folders:
                get_task_mgr().submit(folder, get_indexer())

        return ConfigUpdateResponse(
            config=merged, requires_reindex=requires_reindex,
        )

    @router.post("/rebuild")
    def rebuild():
        """Clear all file hashes and re-index every watched folder.

        Forces a full re-index by clearing stored content hashes, then
        submits each watched folder as a background indexing task.
        Returns the number of folders queued and hashes cleared.
        """
        store = get_store()
        store.rebuild_table()
        hashes_cleared = store.clear_all_file_hashes()

        folders = get_config_mgr().list_watch_dirs()
        indexer = get_indexer()
        for folder in folders:
            get_task_mgr().submit(folder, indexer)

        _logger.info("rebuild: cleared %d file hashes, queued %d folders", hashes_cleared, len(folders))
        return JSONResponse(
            content={
                "status": "accepted",
                "folders_queued": len(folders),
                "hashes_cleared": hashes_cleared,
            },
        )

    @router.post("/repair", response_model=RepairResponse)
    def repair():
        """Run all index maintenance operations.

        Removes orphan chunks, rebuilds FTS5 from LanceDB, compacts
        LanceDB, and checks index compatibility. Returns a summary
        of all operations performed.
        """
        from smart_search.startup import repair_index

        result = repair_index(get_store(), config, config.sqlite_path)
        return RepairResponse(**result)

    return router
