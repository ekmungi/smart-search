# File watcher: monitors directories for changes and triggers indexing.

import logging
import threading
from pathlib import Path
from typing import Dict

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from smart_search.config import SmartSearchConfig

logger = logging.getLogger(__name__)


class FileWatcher:
    """Monitors directories for file changes and triggers indexing.

    Uses watchdog to watch configured directories recursively. Debounces
    rapid changes to avoid redundant re-indexing. Filters by supported
    extensions and exclude patterns.
    """

    def __init__(self, config: SmartSearchConfig, indexer, store) -> None:
        """Initialize with config, indexer, and store.

        Args:
            config: SmartSearchConfig with watch_directories, exclude_patterns,
                    watcher_debounce_seconds, supported_extensions.
            indexer: DocumentIndexer for indexing new/changed files.
            store: ChunkStore for deleting chunks on file removal.
        """
        self._config = config
        self._indexer = indexer
        self._store = store
        self._observers: list = []
        self._dir_observer_map: Dict[str, Observer] = {}
        self._running = False
        self._debounce_timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """Whether the watcher is currently monitoring directories."""
        return self._running

    def start(self) -> None:
        """Start watching all configured directories.

        Safe to call if watch_directories is empty (no-op observers).
        Idempotent -- calling start() on an already-running watcher does nothing.
        """
        if self._running:
            return

        handler = _WatcherHandler(self)
        for dir_path in self._config.watch_directories:
            path = Path(dir_path)
            if not path.is_dir():
                logger.warning("Watch directory does not exist: %s", dir_path)
                continue
            observer = Observer()
            observer.schedule(handler, str(path), recursive=True)
            observer.daemon = True
            observer.start()
            self._observers.append(observer)
            self._dir_observer_map[str(path)] = observer

        self._running = True

    def stop(self) -> None:
        """Stop all directory observers and cancel pending debounce timers.

        Idempotent -- safe to call if watcher is already stopped.
        """
        if not self._running:
            return

        with self._lock:
            for timer in self._debounce_timers.values():
                timer.cancel()
            self._debounce_timers.clear()

        for observer in self._observers:
            observer.stop()
        for observer in self._observers:
            observer.join(timeout=5)
        self._observers.clear()
        self._running = False

    @property
    def watched_directories(self) -> list:
        """Return list of currently watched directory paths."""
        return list(self._dir_observer_map.keys())

    def add_directory(self, dir_path: str) -> None:
        """Start watching a new directory at runtime.

        Args:
            dir_path: Absolute path to the directory to watch.
        """
        path = Path(dir_path).resolve()
        path_str = str(path)
        if path_str in self._dir_observer_map:
            return
        if not path.is_dir():
            logger.warning("Watch directory does not exist: %s", path_str)
            return
        handler = _WatcherHandler(self)
        observer = Observer()
        observer.schedule(handler, path_str, recursive=True)
        observer.daemon = True
        observer.start()
        self._dir_observer_map[path_str] = observer
        self._observers.append(observer)

    def remove_directory(self, dir_path: str) -> None:
        """Stop watching a directory at runtime.

        Args:
            dir_path: Path to the directory to stop watching.
        """
        path_str = str(Path(dir_path).resolve())
        observer = self._dir_observer_map.pop(path_str, None)
        if observer:
            observer.stop()
            observer.join(timeout=5)
            if observer in self._observers:
                self._observers.remove(observer)

    def _is_excluded(self, file_path: str) -> bool:
        """Check if a file path matches any exclusion pattern.

        Matches against each path component (directory or file name).
        Uses exact equality against the exclude_patterns list, so ".git"
        excludes any path that has ".git" as a component.

        Args:
            file_path: Absolute path to check.

        Returns:
            True if the file should be excluded from indexing.
        """
        parts = Path(file_path).parts
        for pattern in self._config.exclude_patterns:
            if any(part == pattern for part in parts):
                return True
        return False

    def _is_supported(self, file_path: str) -> bool:
        """Check if a file has a supported extension.

        Args:
            file_path: Path to check.

        Returns:
            True if the extension is in config.supported_extensions.
        """
        return Path(file_path).suffix.lower() in self._config.supported_extensions

    def _handle_create_or_modify(self, file_path: str) -> None:
        """Schedule debounced indexing for a created or modified file.

        Cancels any pending timer for this path and starts a fresh one.
        This prevents rapid successive edits from triggering multiple
        index operations.

        Args:
            file_path: Absolute path to the changed file.
        """
        with self._lock:
            existing = self._debounce_timers.pop(file_path, None)
            if existing:
                existing.cancel()

            timer = threading.Timer(
                self._config.watcher_debounce_seconds,
                self._do_index,
                args=[file_path],
            )
            timer.daemon = True
            timer.start()
            self._debounce_timers[file_path] = timer

    def _handle_delete(self, file_path: str) -> None:
        """Remove chunks and metadata for a deleted file.

        Cancels any pending debounce timer for the file before removing
        so a rapid create-then-delete sequence does not re-index.

        Args:
            file_path: Absolute path to the deleted file.
        """
        # Cancel any pending indexing for this file
        with self._lock:
            existing = self._debounce_timers.pop(file_path, None)
            if existing:
                existing.cancel()

        source_path = Path(file_path).resolve().as_posix()
        try:
            self._store.delete_chunks_for_file(source_path)
            self._store.remove_file_record(source_path)
            logger.info("Removed index for deleted file: %s", source_path)
        except Exception as exc:
            logger.error("Error removing index for %s: %s", source_path, exc)

    def _do_index(self, file_path: str) -> None:
        """Index a file after the debounce timer fires.

        Args:
            file_path: Absolute path to the file to index.
        """
        with self._lock:
            self._debounce_timers.pop(file_path, None)

        try:
            result = self._indexer.index_file(file_path)
            logger.info(
                "Indexed %s: %s (%d chunks)",
                file_path,
                result.status,
                result.chunk_count,
            )
        except Exception as exc:
            logger.error("Error indexing %s: %s", file_path, exc)


class _WatcherHandler(FileSystemEventHandler):
    """Watchdog event handler that delegates to FileWatcher.

    Filters events by extension and exclusion patterns before
    forwarding to the watcher's debounced handlers.
    """

    def __init__(self, watcher: FileWatcher) -> None:
        """Store reference to parent watcher.

        Args:
            watcher: FileWatcher instance to delegate to.
        """
        super().__init__()
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events by scheduling indexing."""
        if event.is_directory:
            return
        self._handle_file_event(event.src_path, is_delete=False)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events by scheduling re-indexing."""
        if event.is_directory:
            return
        self._handle_file_event(event.src_path, is_delete=False)

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events by removing stored chunks."""
        if event.is_directory:
            return
        self._handle_file_event(event.src_path, is_delete=True)

    def _handle_file_event(self, file_path: str, is_delete: bool) -> None:
        """Filter and route a file event to the appropriate handler.

        Skips excluded paths and unsupported extensions before delegating.

        Args:
            file_path: Path to the affected file.
            is_delete: True if this is a deletion event.
        """
        if self._watcher._is_excluded(file_path):
            return
        if not self._watcher._is_supported(file_path):
            return

        if is_delete:
            self._watcher._handle_delete(file_path)
        else:
            self._watcher._handle_create_or_modify(file_path)
