# Ephemeral index HTTP route handlers.

"""APIRouter factory for ephemeral (folder-local) index endpoints.
Handles creating, listing, and cleaning up .smart-search/ indexes."""

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Query

from smart_search.http_models import (
    EphemeralCleanupRequest,
    EphemeralCleanupResponse,
    EphemeralEntryInfo,
    EphemeralIndexRequest,
    EphemeralIndexResponse,
    EphemeralListResponse,
)


def create_ephemeral_router(
    get_registry: Callable,
) -> APIRouter:
    """Create an APIRouter for ephemeral index endpoints.

    Args:
        get_registry: Zero-arg callable returning EphemeralRegistry instance.

    Returns:
        Configured APIRouter with ephemeral endpoints.
    """
    router = APIRouter()

    @router.post(
        "/ephemeral/index", response_model=EphemeralIndexResponse,
    )
    def ephemeral_index(req: EphemeralIndexRequest):
        """Create an ephemeral index inside a folder.

        Creates a .smart-search/ directory with a local LanceDB + SQLite
        index. Independent of the global knowledge base.
        """
        from smart_search.ephemeral_store import (
            calculate_ephemeral_size,
            create_ephemeral_components,
        )

        path = Path(req.folder_path).resolve()
        if not path.is_dir():
            raise HTTPException(
                status_code=404,
                detail=f"Directory not found: {req.folder_path}",
            )

        components = create_ephemeral_components(str(path))
        indexer_local = components["indexer"]
        result = indexer_local.index_folder(str(path), force=req.force)

        registry = get_registry()
        size = calculate_ephemeral_size(str(path))

        # Explicitly close SQLite connection so Windows can delete the
        # .smart-search/ directory later (avoids WinError 32).
        components["store"].close()
        del components
        total_chunks = sum(
            r.chunk_count for r in result.results if r.status == "indexed"
        )
        registry.register(path.as_posix(), total_chunks, size)

        return EphemeralIndexResponse(
            folder=path.as_posix(),
            index_location=f"{path.as_posix()}/.smart-search/",
            files_indexed=result.indexed,
            files_skipped=result.skipped,
            files_failed=result.failed,
            total_chunks=total_chunks,
            index_size_kb=round(size / 1024, 1),
        )

    @router.get("/ephemeral", response_model=EphemeralListResponse)
    def ephemeral_list():
        """List all registered ephemeral indexes, pruning stale entries."""
        registry = get_registry()
        pruned = registry.prune_stale()
        entries = registry.list_all()

        active = [
            EphemeralEntryInfo(
                folder_path=e.folder_path,
                chunk_count=e.chunk_count,
                size_kb=round(e.size_bytes / 1024, 1),
                created_at=e.created_at,
            )
            for e in entries
        ]
        return EphemeralListResponse(
            active=active, pruned=[str(p) for p in pruned],
        )

    @router.delete(
        "/ephemeral", response_model=EphemeralCleanupResponse,
    )
    def ephemeral_cleanup(
        folder_path: str = Query(
            ..., description="Folder path to clean up",
        ),
    ):
        """Delete an ephemeral index and deregister it."""
        from smart_search.ephemeral_store import remove_ephemeral_index

        path = Path(folder_path).resolve()
        path_posix = path.as_posix()

        removed = remove_ephemeral_index(str(path))
        get_registry().deregister(path_posix)

        return EphemeralCleanupResponse(
            folder=path_posix, removed=removed,
        )

    return router
