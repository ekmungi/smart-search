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
    """Result of adding and initially indexing a folder."""

    path: str
    indexed: int
    skipped: int
    failed: int


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
