# API route handlers for the smart-search HTTP server.

"""All REST endpoint handlers as a FastAPI APIRouter. Routes receive
component getter functions from the app factory and delegate to the
same backend components used by the MCP server."""

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Query

from smart_search.config import SmartSearchConfig
from smart_search.http_models import (
    AddFolderRequest,
    AddFolderResponse,
    ConfigResponse,
    ConfigUpdateRequest,
    ConfigUpdateResponse,
    FileInfo,
    FilesResponse,
    FolderInfo,
    FoldersResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    ModelInfoResponse,
    ModelLoadedResponse,
    ModelStatusResponse,
    ModelsResponse,
    RemoveFolderResponse,
    SearchHit,
    SearchResponse,
    StatsResponse,
)


def create_router(
    get_engine: Callable,
    get_store: Callable,
    get_indexer: Callable,
    get_config_mgr: Callable,
    get_watcher: Callable,
    get_uptime: Callable,
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
        config: SmartSearchConfig instance.

    Returns:
        Configured APIRouter with /api prefix.
    """
    router = APIRouter(prefix="/api")

    @router.get("/health", response_model=HealthResponse)
    def health():
        """Server health check with version and uptime."""
        return HealthResponse(
            status="ok",
            version="0.7.0",
            uptime_seconds=round(get_uptime(), 1),
        )

    @router.get("/stats", response_model=StatsResponse)
    def stats():
        """Get index statistics: document count, chunks, size, formats."""
        store = get_store()
        s = store.get_stats()
        return StatsResponse(
            document_count=s.document_count,
            chunk_count=s.chunk_count,
            index_size_bytes=s.index_size_bytes,
            index_size_mb=round(s.index_size_bytes / (1024 * 1024), 2),
            total_files=s.total_files,
            last_indexed_at=s.last_indexed_at,
            formats_indexed=s.formats_indexed,
        )

    @router.get("/search", response_model=SearchResponse)
    def search(
        q: str = Query(..., description="Search query"),
        limit: int = Query(10, ge=1, le=100),
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
            query=q, limit=limit, doc_types=types_list, folder=folder,
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
            query=q, mode="semantic", total=len(hits), results=hits,
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

    @router.post("/folders", response_model=AddFolderResponse)
    def add_folder(req: AddFolderRequest):
        """Add a folder to the watch list and trigger initial indexing."""
        path = Path(req.path).resolve()
        if not path.is_dir():
            raise HTTPException(
                status_code=404,
                detail=f"Directory not found: {req.path}",
            )

        mgr = get_config_mgr()
        mgr.add_watch_dir(str(path))

        watcher = get_watcher()
        if not watcher.is_running:
            watcher.start()
        watcher.add_directory(str(path))

        indexer = get_indexer()
        result = indexer.index_folder(str(path))

        return AddFolderResponse(
            path=path.as_posix(),
            indexed=result.indexed,
            skipped=result.skipped,
            failed=result.failed,
        )

    @router.delete("/folders", response_model=RemoveFolderResponse)
    def remove_folder(
        path: str = Query(..., description="Folder path to remove"),
        remove_data: bool = Query(False),
    ):
        """Remove a folder from the watch list, optionally deleting data."""
        resolved = Path(path).resolve()
        path_posix = resolved.as_posix()

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

    @router.post("/ingest", response_model=IngestResponse)
    def ingest(req: IngestRequest):
        """Trigger indexing of a file or folder."""
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
            result = indexer.index_folder(str(target), force=req.force)
            return IngestResponse(
                path=str(target),
                status="completed",
                indexed=result.indexed,
                skipped=result.skipped,
                failed=result.failed,
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Path not found: {req.path}",
            )

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

        current.update(req.config)
        mgr.save(current)

        # Detect embedding config change requiring re-index
        new_model = current.get("embedding_model")
        new_dims = current.get("embedding_dimensions")
        requires_reindex = (new_model != old_model) or (new_dims != old_dims)

        if requires_reindex:
            store = get_store()
            store.rebuild_table()

        return ConfigUpdateResponse(
            config=current, requires_reindex=requires_reindex,
        )

    @router.get("/models", response_model=ModelsResponse)
    def list_models():
        """List all curated embedding models with metadata."""
        from smart_search.model_registry import list_models as _list

        models = [
            ModelInfoResponse(
                model_id=m.model_id,
                display_name=m.display_name,
                size_mb=m.size_mb,
                mteb_retrieval=m.mteb_retrieval,
                native_dims=m.native_dims,
                mrl_dims=m.mrl_dims,
                default_dims=m.default_dims,
                modalities=m.modalities,
                description=m.description,
            )
            for m in _list()
        ]
        return ModelsResponse(models=models)

    @router.get("/model/status", response_model=ModelStatusResponse)
    def model_status():
        """Check whether the embedding model is cached locally."""
        from smart_search.embedder import Embedder

        return ModelStatusResponse(
            cached=Embedder.is_model_cached(config.embedding_model),
            model_name=config.embedding_model,
        )

    @router.get("/model/loaded", response_model=ModelLoadedResponse)
    def model_loaded():
        """Check whether the embedding model is currently loaded in memory."""
        engine = get_engine()
        is_loaded = getattr(engine._embedder, "is_loaded", True)
        return ModelLoadedResponse(loaded=is_loaded)

    return router
