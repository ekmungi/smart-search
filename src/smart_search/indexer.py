# Document ingestion pipeline: file -> chunks -> embeddings -> store.

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List

from smart_search.chunker import DocumentChunker
from smart_search.config import SmartSearchConfig
from smart_search.embedder import Embedder
from smart_search.models import Chunk
from smart_search.store import ChunkStore


@dataclass(frozen=True)
class IndexFileResult:
    """Result of indexing a single file.

    Attributes:
        file_path: Path to the indexed file.
        status: One of 'indexed', 'skipped', 'failed'.
        chunk_count: Number of chunks produced (0 if skipped/failed).
        error: Error message if status is 'failed'.
    """

    file_path: str
    status: str
    chunk_count: int = 0
    error: str = ""


@dataclass(frozen=True)
class IndexFolderResult:
    """Result of indexing a folder of documents.

    Attributes:
        indexed: Number of files successfully indexed.
        skipped: Number of files skipped (already indexed).
        failed: Number of files that failed to index.
        results: Per-file results.
    """

    indexed: int
    skipped: int
    failed: int
    results: List[IndexFileResult]


class DocumentIndexer:
    """Orchestrates the full ingestion pipeline: chunk, embed, store.

    Supports single-file and folder-level indexing with hash-based
    change detection to avoid redundant re-indexing.
    """

    def __init__(
        self,
        config: SmartSearchConfig,
        chunker: DocumentChunker,
        embedder: Embedder,
        store: ChunkStore,
        markdown_chunker=None,
    ) -> None:
        """Initialize with all pipeline components.

        Args:
            config: SmartSearchConfig with supported extensions.
            chunker: DocumentChunker for extracting chunks from PDFs/DOCX/etc.
            embedder: Embedder for generating vectors.
            store: ChunkStore for persistence.
            markdown_chunker: Optional MarkdownChunker for .md files. When
                provided, .md files are routed here instead of chunker.
        """
        self._config = config
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._markdown_chunker = markdown_chunker

    def index_file(self, file_path: str, force: bool = False) -> IndexFileResult:
        """Index a single document file.

        Pipeline: validate -> hash -> check cache -> chunk -> embed -> store.
        .md files are routed to markdown_chunker when one is set; all other
        supported types use the document chunker.

        Args:
            file_path: Path to a supported document or Markdown file.
            force: If True, re-index even if file hash matches.

        Returns:
            IndexFileResult with status and chunk count.
        """
        path = Path(file_path).resolve()

        # Validate extension
        if path.suffix.lower() not in self._config.supported_extensions:
            return IndexFileResult(
                file_path=str(path), status="failed",
                error=f"Unsupported extension: {path.suffix}",
            )

        # Compute file hash
        file_hash = self._compute_file_hash(path)
        source_path = path.as_posix()

        # Check if already indexed at this hash
        if not force and self._store.is_file_indexed(source_path, file_hash):
            return IndexFileResult(
                file_path=str(path), status="skipped",
            )

        try:
            # Route to the appropriate chunker based on file extension.
            # .md files go to the markdown chunker when one is registered;
            # all other supported types use the document chunker.
            if path.suffix.lower() == ".md" and self._markdown_chunker is not None:
                chunks = self._markdown_chunker.chunk_file(str(path))
            else:
                chunks = self._chunker.chunk_file(str(path))
            if not chunks:
                return IndexFileResult(
                    file_path=str(path), status="indexed", chunk_count=0,
                )

            # Generate embeddings
            texts = [c.text for c in chunks]
            embeddings = self._embedder.embed_documents(texts)

            # Attach embeddings to chunks (create new immutable copies)
            embedded_chunks = [
                Chunk(**{**c.model_dump(), "embedding": emb, "source_path": source_path})
                for c, emb in zip(chunks, embeddings)
            ]

            # Delete old chunks and insert new ones
            self._store.delete_chunks_for_file(source_path)
            self._store.upsert_chunks(embedded_chunks)

            # Record in SQLite
            self._store.record_file_indexed(
                source_path, file_hash, len(embedded_chunks)
            )

            return IndexFileResult(
                file_path=str(path),
                status="indexed",
                chunk_count=len(embedded_chunks),
            )

        except Exception as e:
            return IndexFileResult(
                file_path=str(path), status="failed", error=str(e),
            )

    def index_folder(
        self, folder_path: str, recursive: bool = True, force: bool = False
    ) -> IndexFolderResult:
        """Index all supported documents in a folder.

        Args:
            folder_path: Path to the folder to scan.
            recursive: If True, scan subdirectories.
            force: If True, re-index all files regardless of hash.

        Returns:
            IndexFolderResult with counts and per-file results.
        """
        folder = Path(folder_path)
        results = []
        indexed = 0
        skipped = 0
        failed = 0

        pattern = "**/*" if recursive else "*"
        for path in sorted(folder.glob(pattern)):
            if path.is_file() and path.suffix.lower() in self._config.supported_extensions:
                result = self.index_file(str(path), force=force)
                results.append(result)
                if result.status == "indexed":
                    indexed += 1
                elif result.status == "skipped":
                    skipped += 1
                else:
                    failed += 1

        return IndexFolderResult(
            indexed=indexed, skipped=skipped, failed=failed, results=results,
        )

    def _compute_file_hash(self, path: Path) -> str:
        """Compute SHA-256 hash of file contents.

        Args:
            path: Path to the file.

        Returns:
            64-character hex digest string.
        """
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                sha.update(block)
        return sha.hexdigest()
