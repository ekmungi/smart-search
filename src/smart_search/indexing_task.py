# Background indexing task manager with cancellation support.

"""Runs indexing in worker threads so HTTP handlers return immediately.
Supports cancellation via threading.Event and progress tracking.
Each folder gets at most one active task — resubmitting cancels the old one."""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

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
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None


class IndexingTaskManager:
    """Manages background indexing tasks with cancellation.

    Each folder gets at most one active task. Submitting the same folder
    again cancels the previous task. Thread-safe via a lock.
    """

    def __init__(self) -> None:
        """Initialize with empty task registry."""
        self._tasks: Dict[str, IndexingStatus] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._folder_to_task: Dict[str, str] = {}
        self._lock = threading.Lock()

    def submit(self, folder: str, indexer: "DocumentIndexer") -> str:
        """Submit a folder for background indexing.

        Cancels any existing task for the same folder before starting.

        Args:
            folder: Absolute path to the folder to index.
            indexer: DocumentIndexer instance to use.

        Returns:
            Task ID string for status tracking.
        """
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
        try:
            result = indexer.index_folder(folder, cancel_event=cancel_event)
            if cancel_event.is_set():
                status.state = "cancelled"
            else:
                status.state = "completed"
                status.indexed = result.indexed
                status.skipped = result.skipped
                status.failed = result.failed
        except Exception as e:
            status.state = "failed"
            status.error = str(e)
        finally:
            status.finished_at = time.time()
