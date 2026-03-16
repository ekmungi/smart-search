# Pydantic request/response models for the HTTP REST API.

"""Typed models for all API endpoints, used by FastAPI for
automatic validation, serialization, and OpenAPI schema generation."""

from typing import List, Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response with server status and uptime."""

    status: str
    version: str
    uptime_seconds: float


class StatsResponse(BaseModel):
    """Index statistics response."""

    document_count: int
    chunk_count: int
    index_size_bytes: int
    index_size_mb: float
    total_files: int = 0
    last_indexed_at: Optional[str] = None
    formats_indexed: List[str]


class SearchHit(BaseModel):
    """A single search result with chunk metadata."""

    rank: int
    score: float
    source_path: str
    source_type: str
    text: str
    page_number: Optional[int] = None
    section_path: str
    filename: str


class SearchResponse(BaseModel):
    """Search results with query metadata."""

    query: str
    mode: str
    total: int
    results: List[SearchHit]


class FolderInfo(BaseModel):
    """Information about a watched folder."""

    path: str
    exists: bool
    status: str


class FoldersResponse(BaseModel):
    """List of watched folders."""

    total: int
    folders: List[FolderInfo]


class AddFolderRequest(BaseModel):
    """Request body to add a folder to the watch list."""

    path: str


class AddFolderResponse(BaseModel):
    """Result of submitting a folder for background indexing."""

    path: str
    task_id: str
    status: str = "accepted"


class RemoveFolderResponse(BaseModel):
    """Result of removing a folder from the watch list."""

    path: str
    data_removed: int


class FileInfo(BaseModel):
    """Metadata about an indexed file."""

    source_path: str
    chunk_count: int
    indexed_at: str


class FilesResponse(BaseModel):
    """List of indexed files."""

    total: int
    files: List[FileInfo]


class IngestRequest(BaseModel):
    """Request body to ingest a file or folder."""

    path: str
    force: bool = False


class IngestResponse(BaseModel):
    """Result of an ingestion operation."""

    path: str
    status: str
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    chunk_count: int = 0
    error: str = ""


class ConfigResponse(BaseModel):
    """Current configuration dictionary."""

    config: dict


class ConfigUpdateRequest(BaseModel):
    """Request body to update configuration keys."""

    config: dict


class ModelStatusResponse(BaseModel):
    """Embedding model cache status."""

    cached: bool
    model_name: str


class ModelLoadedResponse(BaseModel):
    """Whether the embedding model is currently loaded in memory."""

    loaded: bool


class ModelInfoResponse(BaseModel):
    """Metadata for a single curated embedding model."""

    model_id: str
    display_name: str
    size_mb: int
    mteb_retrieval: float
    native_dims: int
    mrl_dims: List[int]
    default_dims: int
    modalities: List[str]
    description: str


class ModelsResponse(BaseModel):
    """List of available embedding models."""

    models: List[ModelInfoResponse]


class IndexingTaskStatus(BaseModel):
    """Status of a single indexing task."""

    task_id: str
    folder: str
    state: str
    total: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    error: Optional[str] = None


class IndexingStatusResponse(BaseModel):
    """Response for GET /api/indexing/status."""

    active: int
    tasks: List[IndexingTaskStatus]


class ConfigUpdateResponse(BaseModel):
    """Result of a config update, with rebuild info."""

    config: dict
    requires_reindex: bool = False


class EphemeralIndexRequest(BaseModel):
    """Request body to create an ephemeral index."""

    folder_path: str
    force: bool = False


class EphemeralIndexResponse(BaseModel):
    """Result of creating an ephemeral index."""

    folder: str
    index_location: str
    files_indexed: int
    files_skipped: int
    files_failed: int
    total_chunks: int
    index_size_kb: float


class EphemeralCleanupRequest(BaseModel):
    """Request body to clean up a specific ephemeral index."""

    folder_path: str


class EphemeralEntryInfo(BaseModel):
    """Info about a single registered ephemeral index."""

    folder_path: str
    chunk_count: int
    size_kb: float
    created_at: str


class EphemeralListResponse(BaseModel):
    """List of active ephemeral indexes with pruned stale entries."""

    active: List[EphemeralEntryInfo]
    pruned: List[str]


class EphemeralCleanupResponse(BaseModel):
    """Result of cleaning up an ephemeral index."""

    folder: str
    removed: bool


class RepairResponse(BaseModel):
    """Result of running all index repair operations."""

    orphans_removed: int
    orphan_files: List[str]
    fts_rebuilt: bool
    fts_rows: int
    compacted: bool
    compatible: bool
    mismatches: dict
