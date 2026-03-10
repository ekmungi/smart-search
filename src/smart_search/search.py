# Search logic with Smart Context formatting for Claude-ready output.

import json
from typing import List, Optional

import numpy as np

from smart_search.config import SmartSearchConfig
from smart_search.embedder import Embedder
from smart_search.models import SearchResult
from smart_search.store import ChunkStore

# Maximum characters to display per chunk in results
_MAX_TEXT_LENGTH = 500


class SearchEngine:
    """Executes semantic search and formats results as Claude-ready context.

    v0.1: All modes fall back to semantic search.
    v0.3 will add keyword and hybrid modes via SQLite FTS5 + RRF.
    """

    def __init__(
        self,
        config: SmartSearchConfig,
        embedder: Embedder,
        store: ChunkStore,
    ) -> None:
        """Initialize with config, embedder, and store.

        Args:
            config: SmartSearchConfig with search defaults.
            embedder: Embedder for generating query vectors.
            store: ChunkStore for vector similarity search.
        """
        self._config = config
        self._embedder = embedder
        self._store = store

    def search(
        self,
        query: str,
        limit: int = 10,
        mode: str = "hybrid",
        doc_types: Optional[List[str]] = None,
    ) -> str:
        """Search the knowledge base and return formatted context.

        Args:
            query: Natural language search query.
            limit: Maximum number of results to return.
            mode: Search mode (semantic/keyword/hybrid). v0.1: all use semantic.
            doc_types: Optional filter by document type (e.g., ["pdf"]).

        Returns:
            Formatted string in Smart Context pattern, never raises.
        """
        try:
            query_vec = self._embedder.embed_query(query)
            results = self._store.vector_search(query_vec, limit=limit)

            # Apply doc_types filter if specified
            if doc_types:
                results = [
                    r for r in results
                    if r.chunk.source_type in doc_types
                ]

            if not results:
                return self._format_no_results(query)

            return self._format_results(query, results, mode)

        except Exception as e:
            return f"KNOWLEDGE SEARCH ERROR\n=====================\nQuery: {query}\nError: {e}"

    def find_related(
        self, note_path: str, limit: int = 10
    ) -> str:
        """Find notes similar to a given note by averaging its embeddings.

        Looks up the note's chunks in the store, averages their embedding
        vectors, and searches for nearest neighbors excluding the source.

        Args:
            note_path: Relative or absolute path to the source note.
            limit: Maximum number of related notes to return.

        Returns:
            Formatted string with ranked related notes, or error message.
        """
        chunks = self._store.get_chunks_for_file(note_path)
        if not chunks:
            return f"Note not found in index: '{note_path}'"

        # Average all chunk embeddings for the source note
        embeddings = np.array([c.embedding for c in chunks])
        avg_embedding = embeddings.mean(axis=0).tolist()

        # Search with extra results to account for self-matches
        candidates = self._store.vector_search(
            avg_embedding, limit=limit + len(chunks)
        )

        # Filter out chunks from the source note itself
        filtered = [
            r for r in candidates
            if r.chunk.source_path != note_path
        ][:limit]

        if not filtered:
            return f"No related notes found for '{note_path}'"

        return self._format_related_results(filtered, note_path)

    def _format_related_results(
        self, results: List[SearchResult], source_path: str
    ) -> str:
        """Format find_related results as a ranked list.

        Args:
            results: Ranked search results (source note excluded).
            source_path: Path of the source note for the header.

        Returns:
            Formatted multi-line string.
        """
        sources = list(dict.fromkeys(r.chunk.source_path for r in results))
        lines = [
            f"RELATED NOTES FOR: {source_path}",
            "=" * 25,
            f"Results: {len(results)} chunks from {len(sources)} documents",
            "",
        ]

        for result in results:
            chunk = result.chunk
            section = self._format_section_path(chunk.section_path)
            text = self._truncate_text(chunk.text)
            filename = (
                chunk.source_path.rsplit("/", 1)[-1]
                if "/" in chunk.source_path
                else chunk.source_path
            )

            header_parts = [f"[{result.rank}] {filename}"]
            if section:
                header_parts.append(f"Section: {section}")
            lines.append(", ".join(header_parts))
            lines.append(f"    {text}")
            lines.append(f"    Similarity: {result.score:.2f}")
            lines.append("")

        lines.append("Sources:")
        for source in sources:
            lines.append(f"- {source}")

        return "\n".join(lines)

    def _format_results(
        self, query: str, results: List[SearchResult], mode: str
    ) -> str:
        """Format search results as Smart Context block.

        Args:
            query: The original search query.
            results: Ranked search results.
            mode: Search mode used.

        Returns:
            Formatted multi-line string.
        """
        # Count unique source documents
        sources = list(dict.fromkeys(r.chunk.source_path for r in results))

        lines = [
            "KNOWLEDGE SEARCH RESULTS",
            "=" * 25,
            f"Query: {query}",
            f"Results: {len(results)} chunks from {len(sources)} documents",
            f"Mode: semantic",
            "",
        ]

        for result in results:
            chunk = result.chunk
            section = self._format_section_path(chunk.section_path)
            text = self._truncate_text(chunk.text)
            filename = chunk.source_path.rsplit("/", 1)[-1] if "/" in chunk.source_path else chunk.source_path

            header_parts = [f"[{result.rank}] {filename}"]
            if chunk.page_number:
                header_parts.append(f"Page {chunk.page_number}")
            if section:
                header_parts.append(f"Section: {section}")

            lines.append(", ".join(header_parts))
            lines.append(f"    {text}")
            lines.append(f"    Relevance: {result.score:.2f}")
            lines.append("")

        lines.append("Sources:")
        for source in sources:
            lines.append(f"- {source}")

        return "\n".join(lines)

    def _format_no_results(self, query: str) -> str:
        """Format a 'no results' message.

        Args:
            query: The original search query.

        Returns:
            Formatted string indicating no results found.
        """
        return (
            "KNOWLEDGE SEARCH RESULTS\n"
            "=" * 25 + "\n"
            f"Query: {query}\n"
            "No results found.\n"
            "Try broadening your query or indexing more documents."
        )

    def _format_section_path(self, section_path: str) -> str:
        """Convert JSON section_path to human-readable string.

        Args:
            section_path: JSON array string like '["Ch 1", "Sec 2"]'.

        Returns:
            Human-readable string like "Ch 1 > Sec 2", or raw string on error.
        """
        try:
            parts = json.loads(section_path)
            if isinstance(parts, list) and parts:
                return " > ".join(str(p) for p in parts)
            return ""
        except (json.JSONDecodeError, TypeError):
            return str(section_path)

    def _truncate_text(self, text: str) -> str:
        """Truncate text to _MAX_TEXT_LENGTH chars with ellipsis.

        Args:
            text: Original chunk text.

        Returns:
            Truncated text with '...' if it exceeds the limit.
        """
        if len(text) <= _MAX_TEXT_LENGTH:
            return text
        return text[:_MAX_TEXT_LENGTH] + "..."
