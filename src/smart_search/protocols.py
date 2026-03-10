"""Protocol definitions for extensible pipeline stages.

Each protocol defines the interface for a pipeline component.
New implementations (models, chunkers, enrichers, retrievers)
implement the same protocol and are selected via config.
"""

from typing import List, Protocol, runtime_checkable

from smart_search.models import Chunk, SearchResult


@runtime_checkable
class EmbedderProtocol(Protocol):
    """Interface for text embedding generators."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for document chunks.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.
        """
        ...

    def embed_query(self, query: str) -> List[float]:
        """Generate embedding for a search query.

        Args:
            query: Search query string.

        Returns:
            Embedding vector.
        """
        ...


@runtime_checkable
class ChunkerProtocol(Protocol):
    """Interface for document chunking."""

    def chunk_file(self, file_path: str) -> List[Chunk]:
        """Split a file into chunks.

        Args:
            file_path: Path to the file to chunk.

        Returns:
            List of Chunk objects.
        """
        ...

    def chunk_text(
        self, text: str, source_path: str, source_type: str = "md"
    ) -> List[Chunk]:
        """Chunk a text string into Chunk objects.

        Args:
            text: Markdown text content to chunk.
            source_path: Path to attribute chunks to.
            source_type: File type identifier.

        Returns:
            List of Chunk objects.
        """
        ...


@runtime_checkable
class ChunkEnricher(Protocol):
    """Interface for chunk enrichment (entity tagging, summarization, etc.)."""

    def enrich(self, chunks: List[Chunk]) -> List[Chunk]:
        """Enrich chunks with additional metadata.

        Args:
            chunks: List of chunks to enrich.

        Returns:
            New list of enriched chunks (immutable pattern).
        """
        ...


@runtime_checkable
class RetrieverProtocol(Protocol):
    """Interface for search retrieval strategies."""

    def retrieve(self, query: str, limit: int) -> List[SearchResult]:
        """Retrieve relevant results for a query.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of SearchResult objects ranked by relevance.
        """
        ...
