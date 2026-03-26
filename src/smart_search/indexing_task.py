# Background indexing task manager with cancellation support.

"""Runs indexing in worker threads so HTTP handlers return immediately.
Supports cancellation via threading.Event and progress tracking.
Each folder gets at most one active task — resubmitting cancels the old one."""

import ctypes
import gc
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from smart_search.constants import KEYWORD_ONLY_EXTENSIONS

_logger = logging.getLogger(__name__)


def _get_available_ram_gb() -> float:
    """Get available system RAM in GB using OS-native APIs.

    Returns:
        Available RAM in GB, or 4.0 as a safe fallback.
    """
    try:
        # Windows: use kernel32.GlobalMemoryStatusEx
        if os.name == "nt":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return stat.ullAvailPhys / (1024 ** 3)
        # Linux/macOS: parse /proc/meminfo or use sysctl
        else:
            import shutil
            total, used, free = shutil.disk_usage("/")  # fallback
            # Try /proc/meminfo on Linux
            meminfo = Path("/proc/meminfo")
            if meminfo.exists():
                for line in meminfo.read_text().splitlines():
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) / (1024 ** 2)
            return 4.0
    except (OSError, ImportError, AttributeError):
        _logger.debug("Failed to get available RAM", exc_info=True)
        return 4.0


def _compute_max_concurrent() -> int:
    """Determine max concurrent indexing tasks based on available resources.

    Checks CPU cores and available RAM. Each indexing task needs roughly
    1.5 GB of headroom (ONNX model + tokenizer + buffers). Caps at 1
    to halve peak memory — sequential folder indexing is acceptable for
    background work (B53).

    Returns:
        Max concurrent tasks (always at least 1).
    """
    try:
        cpu_cores = os.cpu_count() or 2
        available_gb = _get_available_ram_gb()

        # Each task needs ~1.5 GB; reserve 2 GB for OS + app overhead
        usable_gb = max(0, available_gb - 2.0)
        by_ram = max(1, int(usable_gb / 1.5))

        # Allow one task per 2 cores
        by_cpu = max(1, cpu_cores // 2)

        limit = min(by_ram, by_cpu, 1)
        _logger.info(
            "Resource check: %.1f GB available, %d cores -> max %d concurrent tasks",
            available_gb, cpu_cores, limit,
        )
        return limit
    except (OSError, ImportError, AttributeError):
        _logger.debug("Failed to compute max concurrent tasks", exc_info=True)
        return 1  # Safe fallback

if TYPE_CHECKING:
    from smart_search.indexer import DocumentIndexer


@dataclass
class IndexingStatus:
    """Status of a single indexing task.

    Attributes:
        task_id: Unique task identifier.
        folder: Absolute path of the folder being indexed.
        state: One of 'running', 'completed', 'failed', 'cancelled'.
        indexed: Number of files successfully indexed so far.
        skipped: Number of files skipped (already indexed).
        failed: Number of files that failed.
        error: Error message if state is 'failed'.
        started_at: Epoch timestamp when task started.
        finished_at: Epoch timestamp when task finished (None while running).
    """

    task_id: str
    folder: str
    state: str  # "running", "completed", "failed", "cancelled"
    total: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    error: Optional[str] = None
    failed_files: List[Dict[str, str]] = field(default_factory=list)
    processed_files: List[Dict[str, str]] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None


class IndexingTaskManager:
    """Manages background indexing tasks with cancellation.

    Each folder gets at most one active task. Submitting the same folder
    again cancels the previous task. Thread-safe via a lock.
    """

    def __init__(self) -> None:
        """Initialize with empty task registry and resource-aware semaphore."""
        self._tasks: Dict[str, IndexingStatus] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._folder_to_task: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._max_concurrent = _compute_max_concurrent()
        self._semaphore = threading.Semaphore(self._max_concurrent)
        # Global pause control: set = running, clear = paused.
        self._pause_event = threading.Event()
        self._pause_event.set()  # Start in non-paused (running) state
        # Model availability watcher state
        self._model_watcher_active = False
        self._model_watcher_cancel = threading.Event()

    def submit(
        self, folder: str, indexer: "DocumentIndexer", force: bool = False,
    ) -> str:
        """Submit a folder for background indexing.

        Cancels any existing task for the same folder before starting.

        Args:
            folder: Absolute path to the folder to index.
            indexer: DocumentIndexer instance to use.
            force: Skip mtime pre-scan and re-index all files.

        Returns:
            Task ID string for status tracking.
        """
        # Normalize to forward slashes so paths match the folder list API
        folder = Path(folder).as_posix()
        with self._lock:
            # Cancel and remove existing task for this folder
            if folder in self._folder_to_task:
                old_id = self._folder_to_task[folder]
                if old_id in self._cancel_events:
                    self._cancel_events[old_id].set()
                    del self._cancel_events[old_id]
                self._tasks.pop(old_id, None)

            task_id = str(uuid.uuid4())[:8]
            cancel_event = threading.Event()
            status = IndexingStatus(
                task_id=task_id, folder=folder, state="running"
            )
            self._tasks[task_id] = status
            self._cancel_events[task_id] = cancel_event
            self._folder_to_task[folder] = task_id

        thread = threading.Thread(
            target=self._run_indexing,
            args=(task_id, folder, indexer, cancel_event, force),
            daemon=True,
        )
        thread.start()
        with self._lock:
            self._threads[task_id] = thread
        return task_id

    def cancel_folder(self, folder: str) -> bool:
        """Cancel any active indexing task for a folder (non-blocking).

        Sets the cancellation flag but does not wait for the thread to stop.
        Use cancel_folder_and_wait() when you need the thread fully stopped
        before proceeding (e.g., before deleting indexed data).

        Args:
            folder: Folder path to cancel indexing for.

        Returns:
            True if a task was found and cancelled, False otherwise.
        """
        folder = Path(folder).as_posix()
        with self._lock:
            task_id = self._folder_to_task.get(folder)
            if task_id and task_id in self._cancel_events:
                self._cancel_events[task_id].set()
                return True

    def cancel_folder_and_wait(self, folder: str, timeout: float = 10.0) -> bool:
        """Cancel indexing for a folder and wait for the thread to finish.

        Ensures no more chunks are written after this method returns,
        making it safe to delete indexed data immediately afterward.

        Args:
            folder: Folder path to cancel indexing for.
            timeout: Max seconds to wait for the thread to stop.

        Returns:
            True if a task was found, cancelled, and stopped within timeout.
        """
        folder = Path(folder).as_posix()
        with self._lock:
            task_id = self._folder_to_task.get(folder)
            if not task_id:
                return False
            event = self._cancel_events.get(task_id)
            thread = self._threads.get(task_id)
            if event:
                event.set()

        # Wait outside the lock so the indexing thread can acquire it to clean up
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
            return not thread.is_alive()
        return True
        return False

    def get_status(self, task_id: str) -> Optional[IndexingStatus]:
        """Get the status of a specific task.

        Args:
            task_id: Task ID returned by submit().

        Returns:
            IndexingStatus or None if not found.
        """
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[IndexingStatus]:
        """Get all tracked tasks (any state).

        Returns:
            List of all IndexingStatus objects.
        """
        return list(self._tasks.values())

    def get_all_active(self) -> List[IndexingStatus]:
        """Get all tasks that are currently running.

        Returns:
            List of IndexingStatus for running tasks.
        """
        return [s for s in self._tasks.values() if s.state == "running"]

    def get_folder_status(self, folder: str) -> Optional[IndexingStatus]:
        """Get the latest task status for a folder.

        Args:
            folder: Folder path to check.

        Returns:
            IndexingStatus or None if no task exists for this folder.
        """
        folder = Path(folder).as_posix()
        task_id = self._folder_to_task.get(folder)
        if task_id:
            return self._tasks.get(task_id)
        return None

    def start_model_watcher(
        self,
        model_name: str,
        store,
        config_mgr,
        indexer: "DocumentIndexer",
        check_interval: float = 30.0,
    ) -> None:
        """Start watching for model availability to auto-retry failed files.

        If model is already cached, does nothing. Otherwise, starts a daemon
        thread that periodically checks is_model_cached(). When model becomes
        available, clears all failed files and resubmits indexing.

        Args:
            model_name: HuggingFace model identifier.
            store: ChunkStore for clearing failed status.
            config_mgr: ConfigManager for listing watch directories.
            indexer: DocumentIndexer for resubmission.
            check_interval: Seconds between availability checks.
        """
        from smart_search.embedder import Embedder

        if Embedder.is_model_cached(model_name):
            self._model_watcher_active = False
            return

        self._model_watcher_active = True
        self._model_watcher_cancel.clear()

        def _watch() -> None:
            while not self._model_watcher_cancel.is_set():
                self._model_watcher_cancel.wait(timeout=check_interval)
                if self._model_watcher_cancel.is_set():
                    break
                try:
                    if Embedder.is_model_cached(model_name):
                        _logger.info(
                            "Model %s now available -- clearing failed files "
                            "and resubmitting indexing", model_name,
                        )
                        store.clear_failed_status()
                        for folder in config_mgr.list_watch_dirs():
                            self.submit(folder, indexer)
                        self._model_watcher_active = False
                        return
                except Exception:
                    _logger.debug("Model watcher check failed", exc_info=True)
            self._model_watcher_active = False

        thread = threading.Thread(target=_watch, daemon=True, name="model-watcher")
        thread.start()

    def stop_model_watcher(self) -> None:
        """Stop the model availability watcher thread."""
        self._model_watcher_cancel.set()
        self._model_watcher_active = False

    def shutdown(self) -> None:
        """Cancel all running tasks and stop the model watcher."""
        self.stop_model_watcher()
        with self._lock:
            for event in self._cancel_events.values():
                event.set()

    def pause(self) -> None:
        """Pause all active indexing tasks.

        Tasks block after finishing the current file until resume() is called.
        """
        self._pause_event.clear()
        _logger.info("Indexing paused")

    def resume(self) -> None:
        """Resume all paused indexing tasks."""
        self._pause_event.set()
        _logger.info("Indexing resumed")

    @property
    def is_paused(self) -> bool:
        """Whether indexing is currently paused."""
        return not self._pause_event.is_set()

    def _run_indexing(
        self,
        task_id: str,
        folder: str,
        indexer: "DocumentIndexer",
        cancel_event: threading.Event,
        force: bool = False,
    ) -> None:
        """Worker function that runs indexing in a background thread.

        Args:
            task_id: Unique task identifier.
            folder: Folder path to index.
            indexer: DocumentIndexer instance.
            cancel_event: Event to signal cancellation.
            force: Skip mtime pre-scan and re-index all files.
        """
        status = self._tasks[task_id]

        def _on_progress(_file_path: str, file_result: "IndexFileResult") -> None:
            """Update status counters and per-file log in real-time."""
            normalized = _file_path.replace("\\", "/")

            file_name = normalized.split("/")[-1]
            if file_result.status == "indexed":
                status.indexed += 1
                status.processed_files.append({
                    "name": file_name,
                    "path": _file_path,
                    "status": "indexed",
                    "chunks": str(file_result.chunk_count),
                })
            elif file_result.status == "skipped":
                status.skipped += 1
                status.processed_files.append({
                    "name": file_name,
                    "path": _file_path,
                    "status": "skipped",
                })
            else:
                status.failed += 1
                status.failed_files.append({
                    "path": _file_path,
                    "error": file_result.error or "unknown",
                })
                status.processed_files.append({
                    "name": file_name,
                    "path": _file_path,
                    "status": "failed",
                    "error": file_result.error or "unknown",
                })
                _logger.warning(
                    "Task %s: FAILED %s -- %s",
                    task_id, _file_path, file_result.error,
                )

        try:
            # Phase 1: Lightweight pre-scan WITHOUT semaphore.
            # Check mtime+size for each file. Files that haven't changed
            # are reported as skipped immediately so progress bars update
            # across all folders concurrently, even while one folder holds
            # the semaphore for heavy embedding work.
            from smart_search.indexer import IndexFileResult, discover_files

            folder_p = Path(folder)
            config = indexer._config
            discovered = discover_files(folder_p, config.supported_extensions)
            status.total = len(discovered)

            # Each pre-scan thread gets its own SQLite connection.
            # Python's sqlite3 module is not safe for concurrent use of a
            # single connection object, even with check_same_thread=False.
            import sqlite3
            prescan_conn = sqlite3.connect(
                indexer._store._config.sqlite_path, check_same_thread=False,
            )
            prescan_conn.execute("PRAGMA journal_mode=WAL")

            files_needing_work: list[Path] = []
            try:
                for f in discovered:
                    if cancel_event.is_set():
                        status.state = "cancelled"
                        return
                    try:
                        stat_info = f.stat()
                        source_path = f.resolve().as_posix()
                        row = prescan_conn.execute(
                            "SELECT file_mtime, file_size, "
                            "COALESCE(status, 'indexed'), error, needs_ocr "
                            "FROM indexed_files WHERE source_path = ?",
                            (source_path,),
                        ).fetchone()
                        if (
                            not force
                            and row is not None
                            and row[0] is not None
                            and row[1] is not None
                            and row[0] == stat_info.st_mtime
                            and row[1] == stat_info.st_size
                        ):
                            # File unchanged -- report true stored state.
                            stored_status = row[2]
                            stored_error = row[3]
                            stored_needs_ocr = row[4]
                            if stored_status == "failed":
                                _on_progress(
                                    str(f),
                                    IndexFileResult(
                                        file_path=str(f), status="failed",
                                        error=stored_error or "previous failure",
                                    ),
                                )
                            elif stored_needs_ocr:
                                _on_progress(
                                    str(f),
                                    IndexFileResult(
                                        file_path=str(f), status="skipped",
                                        error="needs OCR",
                                    ),
                                )
                            else:
                                _on_progress(
                                    str(f),
                                    IndexFileResult(
                                        file_path=str(f), status="skipped",
                                    ),
                                )
                            continue
                    except OSError:
                        pass  # File may have been deleted; let index_file handle it
                    files_needing_work.append(f)
            finally:
                prescan_conn.close()

            # Model readiness gate: check if embedding model is cached.
            # If not, filter out files that need vector embeddings and only
            # process keyword-only files (CSV, XLSX, JSON, etc.).
            from smart_search.embedder import Embedder
            model_name = config.embedding_model
            if not model_name:
                model_ready = False
            else:
                model_ready = Embedder.is_model_cached(model_name)

            if not model_ready:
                keyword_only_files = [
                    f for f in files_needing_work
                    if f.suffix.lower() in KEYWORD_ONLY_EXTENSIONS
                ]
                skipped_for_model = len(files_needing_work) - len(keyword_only_files)
                if skipped_for_model > 0:
                    _logger.warning(
                        "Task %s: embedding model not cached -- skipping %d files "
                        "that need vector embeddings, processing %d keyword-only files",
                        task_id, skipped_for_model, len(keyword_only_files),
                    )
                files_needing_work = keyword_only_files

            # Phase 2: If all files were pre-skipped, no heavy work needed.
            if not files_needing_work:
                status.state = "completed"
                _logger.info("Task %s: all %d files unchanged, skipping",
                             task_id, status.total)
                return

            # Phase 3: Acquire semaphore for heavy work (embedding/conversion).
            # Only files identified by pre-scan are processed — no re-discovery.
            _logger.info("Task %s: %d/%d files need processing, waiting for slot",
                         task_id, len(files_needing_work), status.total)
            self._semaphore.acquire()
            _logger.info("Task %s: acquired slot, indexing %s (%d files to process)",
                         task_id, folder, len(files_needing_work))
            try:
                for f in files_needing_work:
                    if cancel_event.is_set():
                        status.state = "cancelled"
                        return
                    result = indexer.index_file(str(f))
                    _on_progress(str(f), result)
                    # Per-file GC to prevent memory accumulation during
                    # heavy embedding/conversion work.
                    if result.status in ("indexed", "failed"):
                        gc.collect()
                    # Pause gate: block until resumed or cancelled.
                    while not self._pause_event.is_set():
                        if cancel_event.is_set():
                            break
                        self._pause_event.wait(timeout=1.0)
                if cancel_event.is_set():
                    status.state = "cancelled"
                else:
                    status.state = "completed"
            finally:
                self._semaphore.release()
        except Exception as e:
            status.state = "failed"
            status.error = str(e)
        finally:
            status.finished_at = time.time()
            # Clean up thread reference so join() callers don't wait on dead threads
            with self._lock:
                self._threads.pop(task_id, None)
