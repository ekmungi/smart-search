# Background indexing task manager with cancellation support.

"""Runs indexing in worker threads so HTTP handlers return immediately.
Supports cancellation via threading.Event and progress tracking.
Each folder gets at most one active task — resubmitting cancels the old one."""

import ctypes
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

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
    except Exception:
        return 4.0


def _compute_max_concurrent() -> int:
    """Determine max concurrent indexing tasks based on available resources.

    Checks CPU cores and available RAM. Each indexing task needs roughly
    1.5 GB of headroom (ONNX model + tokenizer + buffers). Caps at 2
    to avoid overwhelming the system.

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

        limit = min(by_ram, by_cpu, 2)
        _logger.info(
            "Resource check: %.1f GB available, %d cores -> max %d concurrent tasks",
            available_gb, cpu_cores, limit,
        )
        return limit
    except Exception:
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
        self._folder_to_task: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._max_concurrent = _compute_max_concurrent()
        self._semaphore = threading.Semaphore(self._max_concurrent)

    def submit(self, folder: str, indexer: "DocumentIndexer") -> str:
        """Submit a folder for background indexing.

        Cancels any existing task for the same folder before starting.

        Args:
            folder: Absolute path to the folder to index.
            indexer: DocumentIndexer instance to use.

        Returns:
            Task ID string for status tracking.
        """
        # Normalize to forward slashes so paths match the folder list API
        folder = Path(folder).as_posix()
        with self._lock:
            # Cancel existing task for this folder
            if folder in self._folder_to_task:
                old_id = self._folder_to_task[folder]
                if old_id in self._cancel_events:
                    self._cancel_events[old_id].set()

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
            args=(task_id, folder, indexer, cancel_event),
            daemon=True,
        )
        thread.start()
        return task_id

    def cancel_folder(self, folder: str) -> bool:
        """Cancel any active indexing task for a folder.

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

    def shutdown(self) -> None:
        """Cancel all running tasks."""
        with self._lock:
            for event in self._cancel_events.values():
                event.set()

    def _run_indexing(
        self,
        task_id: str,
        folder: str,
        indexer: "DocumentIndexer",
        cancel_event: threading.Event,
    ) -> None:
        """Worker function that runs indexing in a background thread.

        Args:
            task_id: Unique task identifier.
            folder: Folder path to index.
            indexer: DocumentIndexer instance.
            cancel_event: Event to signal cancellation.
        """
        status = self._tasks[task_id]

        def _on_progress(_file_path: str, file_result: "IndexFileResult") -> None:
            """Update status counters in real-time as each file completes."""
            if file_result.status == "indexed":
                status.indexed += 1
            elif file_result.status == "skipped":
                status.skipped += 1
            else:
                status.failed += 1
                status.failed_files.append({
                    "path": _file_path,
                    "error": file_result.error or "unknown",
                })
                _logger.warning(
                    "Task %s: FAILED %s -- %s",
                    task_id, _file_path, file_result.error,
                )

        try:
            # Discover total file count before waiting for semaphore (lightweight)
            folder_p = Path(folder)
            config = indexer._config
            file_count = sum(
                1 for p in folder_p.glob("**/*")
                if p.is_file() and p.suffix.lower() in config.supported_extensions
            )
            status.total = file_count

            # Wait for resource slot before starting heavy work
            _logger.info("Task %s: waiting for resource slot (%d max concurrent)",
                         task_id, self._max_concurrent)
            self._semaphore.acquire()
            _logger.info("Task %s: acquired slot, indexing %s (%d files)",
                         task_id, folder, file_count)
            try:
                if cancel_event.is_set():
                    status.state = "cancelled"
                    return

                indexer.index_folder(
                    folder,
                    cancel_event=cancel_event,
                    on_progress=_on_progress,
                )
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
