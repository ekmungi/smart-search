# Data models for smart-search: Chunk, SearchResult, IndexStats.

import hashlib
from typing import List, Optional

from pydantic import BaseModel, field_validator


def generate_chunk_id(source_path: str, chunk_index: int) -> str:
    """Deterministic chunk ID from SHA-256 of (source_path + chunk_index).

    Args:
        source_path: Absolute path to the source document.
        chunk_index: Zero-based index of the chunk within the document.

    Returns:
        64-character hex string (SHA-256 digest).
    """
    raw = f"{source_path}{chunk_index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Chunk(BaseModel):
    """A single indexed chunk from a document.

    Represents extracted and embedded content with full provenance
    (source file, page, section path). Schema is frozen for v0.1.
    """

    id: str
    source_path: str
    source_type: str
    content_type: str
    text: str
    page_number: Optional[int] = None
    section_path: str
    embedding: List[float]
    has_image: bool = False
    image_path: Optional[str] = None
    entity_tags: Optional[str] = None
    source_title: Optional[str] = None
    source_date: Optional[str] = None
    indexed_at: str
    model_name: str

    @field_validator("text")
    @classmethod
    def text_must_not_be_empty(cls, v: str) -> str:
        """Reject empty text -- every chunk must have content."""
        if not v.strip():
            raise ValueError("text must not be empty")
        return v


class SearchResult(BaseModel):
    """A chunk with its search relevance score and rank position.

    Returned by the search engine, wrapping a Chunk with ranking metadata.
    """

    rank: int
    score: float
    chunk: Chunk


class IndexStats(BaseModel):
    """Statistics about the knowledge base, returned by knowledge_stats tool.

    Provides counts, size, and format information for the indexed corpus.
    """

    document_count: int
    chunk_count: int
    index_size_bytes: int
    total_files: int = 0
    last_indexed_at: Optional[str] = None
    formats_indexed: List[str]
