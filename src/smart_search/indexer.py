# Document ingestion pipeline: file -> chunks -> embeddings -> store.

import gc
import hashlib
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional

_logger = logging.getLogger(__name__)

from smart_search.config import SmartSearchConfig
from smart_search.markdown_chunker import MarkdownChunker
from smart_search.models import Chunk
from smart_search.store import ChunkStore

if TYPE_CHECKING:
    from smart_search.embedder import Embedder


def _get_rss_mb() -> int:
    """Get current process RSS in megabytes using OS-native APIs.

    Returns:
        RSS in MB, or 0 if unavailable.
    """
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            # Windows: use kernel32.K32GetProcessMemoryInfo
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(pmc)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(pmc), pmc.cb,
            )
            return int(pmc.WorkingSetSize / (1024 * 1024))
        else:
            import resource
            # On macOS resource returns bytes; on Linux it returns KB
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if os.uname().sysname == "Darwin":
                return int(usage / (1024 * 1024))
            return int(usage / 1024)
    except (OSError, AttributeError, ImportError):
        _logger.debug("Failed to get process RSS", exc_info=True)
        return 0


def _convert_with_timeout(
    convert_fn: Callable[[str], str],
    file_path: str,
    timeout: int = 120,
) -> str:
    """Run a file conversion function with a timeout.

    Prevents MarkItDown from blocking the indexing thread indefinitely
    on problematic files (e.g. complex PDFs).

    Args:
        convert_fn: Callable that takes a file path and returns markdown text.
        file_path: Path to the file to convert.
        timeout: Max seconds to wait (default 120).

    Returns:
        Converted markdown text.

    Raises:
        TimeoutError: If conversion exceeds the timeout.
    """
    result: list[str] = []
    error: list[Exception] = []

    def _worker() -> None:
        try:
            result.append(convert_fn(file_path))
        except Exception as e:
            error.append(e)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        _logger.warning("Conversion timed out after %ds: %s", timeout, file_path)
        raise TimeoutError(f"File conversion timed out after {timeout}s: {file_path}")
    if error:
        raise error[0]
    return result[0]


def discover_files(
    folder: Path,
    extensions: set[str],
    recursive: bool = True,
) -> list[Path]:
    """Discover supported files in a folder, resolved and deduplicated.

    Resolves symlinks and normalizes paths so the same physical file
    is never counted twice (fixes B48: 94 vs 93 discrepancy).

    Args:
        folder: Root folder to scan.
        extensions: Set of lowercase extensions including dot (e.g. {".md", ".pdf"}).
        recursive: If True, scan subdirectories.

    Returns:
        Sorted list of unique resolved Paths.
    """
    pattern = "**/*" if recursive else "*"
    seen: set[Path] = set()
    result: list[Path] = []
    for p in folder.glob(pattern):
        if not p.is_file():
            continue
        if p.suffix.lower() not in extensions:
            continue
        resolved = p.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    result.sort()
    _logger.debug("discover_files: %d unique files in %s", len(result), folder)
    return result


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
        embedder: "Embedder",
        store: ChunkStore,
        markdown_chunker: MarkdownChunker | None = None,
    ) -> None:
        """Initialize with all pipeline components.

        Args:
            config: SmartSearchConfig with supported extensions.
            embedder: Embedder for generating vectors.
            store: ChunkStore for persistence.
            markdown_chunker: Optional MarkdownChunker instance. Created
                automatically if not provided.
        """
        self._config = config
        self._embedder = embedder
        self._store = store
        self._markdown_chunker = markdown_chunker or MarkdownChunker(config)

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

        # Capture file size for debug logging before any processing.
        file_size_kb = path.stat().st_size // 1024

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
            # Route by extension: .md files are chunked directly;
            # all other types are converted to Markdown via MarkItDown first.
            is_binary = path.suffix.lower() != ".md"
            if not is_binary:
                chunks = self._markdown_chunker.chunk_file(str(path))
            else:
                from smart_search.markitdown_parser import convert_to_markdown

                markdown_text = _convert_with_timeout(
                    convert_to_markdown, str(path), timeout=120,
                )
                source_type = path.suffix.lower().lstrip(".")
                chunks = self._markdown_chunker.chunk_text(
                    markdown_text,
                    source_path=source_path,
                    source_type=source_type,
                )
                del markdown_text
            if not chunks:
                # Record in SQLite even with 0 chunks so the file is not
                # retried on every restart. Binary files (PDF, DOCX, etc.)
                # with no text are tagged needs_ocr for future retry.
                self._store.record_file_indexed(
                    source_path, file_hash, 0, needs_ocr=is_binary,
                )
                return IndexFileResult(
                    file_path=str(path), status="indexed", chunk_count=0,
                )

            # Generate embeddings
            texts = [c.text for c in chunks]
            embeddings = self._embedder.embed_documents(texts)
            del texts

            # Attach embeddings to chunks (create new immutable copies)
            embedded_chunks = [
                Chunk(**{**c.model_dump(), "embedding": emb, "source_path": source_path})
                for c, emb in zip(chunks, embeddings)
            ]
            del chunks
            del embeddings

            # Delete old chunks and insert new ones
            self._store.delete_chunks_for_file(source_path)
            self._store.upsert_chunks(embedded_chunks)

            # Save count before releasing the list
            chunk_count = len(embedded_chunks)
            del embedded_chunks

            # Record in SQLite
            self._store.record_file_indexed(
                source_path, file_hash, chunk_count
            )

            _logger.debug(
                "Indexed %s: %d chunks from %d KB file (RSS: %d MB)",
                file_path,
                chunk_count,
                file_size_kb,
                _get_rss_mb(),
            )
            return IndexFileResult(
                file_path=str(path),
                status="indexed",
                chunk_count=chunk_count,
            )

        except Exception as e:
            return IndexFileResult(
                file_path=str(path), status="failed", error=str(e),
            )

    def index_folder(
        self,
        folder_path: str,
        recursive: bool = True,
        force: bool = False,
        on_progress: Optional[Callable[[str, "IndexFileResult"], None]] = None,
        cancel_event: threading.Event | None = None,
    ) -> IndexFolderResult:
        """Index all supported documents in a folder.

        Args:
            folder_path: Path to the folder to scan.
            recursive: If True, scan subdirectories.
            force: If True, re-index all files regardless of hash.
            on_progress: Optional callback invoked after each file with
                (file_path, IndexFileResult). Used by CLI for progress bars.
            cancel_event: Optional threading.Event. When set, the loop stops
                processing further files and returns accumulated counts.

        Returns:
            IndexFolderResult with counts and per-file results.
        """
        folder = Path(folder_path)
        results = []
        indexed = 0
        skipped = 0
        failed = 0

        # Collect files first so callers can know the total count.
        files = discover_files(folder, self._config.supported_extensions, recursive)
        _logger.info("Discovered %d supported files in %s", len(files), folder_path)

        for path in files:
            if cancel_event is not None and cancel_event.is_set():
                break
            result = self.index_file(str(path), force=force)
            results.append(result)
            if result.status == "indexed":
                indexed += 1
                # Reclaim MarkItDown/ONNX buffers every 2 files to keep
                # peak RSS below ~2 GB during large batch indexing (B53).
                if indexed % 2 == 0:
                    gc.collect()
            elif result.status == "skipped":
                skipped += 1
            else:
                failed += 1
                gc.collect()
            if on_progress is not None:
                on_progress(str(path), result)

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
