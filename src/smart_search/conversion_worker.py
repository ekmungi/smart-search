# Persistent conversion worker subprocess for binary file processing.

"""Long-lived subprocess that imports MarkItDown once and converts files
on demand via IPC queues. Eliminates per-file subprocess spawn overhead
on Windows, where multiprocessing.Process with 'spawn' start method is
non-deterministic due to Defender scanning and process creation cost.

Usage:
    worker = ConversionWorker()
    worker.start()
    text = worker.convert("path/to/file.pdf", timeout=300)
    worker.stop()
"""

import logging
import multiprocessing
import os
import queue
import time
from dataclasses import dataclass
from typing import Optional

_logger = logging.getLogger(__name__)

# Restart the worker if its RSS exceeds this threshold (bytes).
# MarkItDown can leak memory on complex PDFs; restarting reclaims it.
_RSS_RESTART_THRESHOLD_MB = 1024


@dataclass(frozen=True)
class ConversionResult:
    """Result from the worker subprocess.

    Attributes:
        ok: True if conversion succeeded.
        text: Converted markdown text (empty on failure).
        error: Error message (empty on success).
        rss_mb: Worker process RSS in MB after conversion.
    """

    ok: bool
    text: str = ""
    error: str = ""
    rss_mb: int = 0


def _worker_loop(
    request_q: multiprocessing.Queue,
    response_q: multiprocessing.Queue,
) -> None:
    """Main loop for the persistent conversion worker subprocess.

    Imports MarkItDown once, then processes file paths from request_q
    until a None sentinel is received. Results are sent back via response_q.

    Args:
        request_q: Queue receiving file path strings (None = shutdown).
        response_q: Queue sending ConversionResult tuples back.
    """
    # Import MarkItDown once in the subprocess -- this is the expensive part
    # that was previously repeated per file.
    from smart_search.markitdown_parser import convert_to_markdown

    while True:
        file_path = request_q.get()
        if file_path is None:
            # Sentinel: clean shutdown
            break

        try:
            text = convert_to_markdown(file_path)
            rss = _get_rss_mb()
            # Send as tuple for pickling simplicity (dataclass pickling
            # requires the class to be importable in the subprocess).
            response_q.put((True, text, "", rss))
        except Exception as e:
            rss = _get_rss_mb()
            response_q.put((False, "", str(e), rss))


def _get_rss_mb() -> int:
    """Get current process RSS in megabytes.

    Returns:
        RSS in MB, or 0 if unavailable.
    """
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

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
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if os.uname().sysname == "Darwin":
                return int(usage / (1024 * 1024))
            return int(usage / 1024)
    except (OSError, AttributeError, ImportError):
        return 0


class ConversionWorker:
    """Persistent subprocess for converting binary files to markdown.

    Spawns a single long-lived worker process that imports MarkItDown
    once and handles all conversion requests via IPC queues. Auto-restarts
    the worker if it crashes or exceeds the RSS memory threshold.
    """

    def __init__(self, rss_threshold_mb: int = _RSS_RESTART_THRESHOLD_MB) -> None:
        """Initialize the worker (does not start the subprocess yet).

        Args:
            rss_threshold_mb: Restart worker if RSS exceeds this (MB).
        """
        self._rss_threshold_mb = rss_threshold_mb
        self._request_q: Optional[multiprocessing.Queue] = None
        self._response_q: Optional[multiprocessing.Queue] = None
        self._process: Optional[multiprocessing.Process] = None

    def start(self) -> None:
        """Start the worker subprocess.

        Safe to call multiple times -- restarts if already stopped.
        """
        if self._process is not None and self._process.is_alive():
            return
        self._request_q = multiprocessing.Queue()
        self._response_q = multiprocessing.Queue()
        self._process = multiprocessing.Process(
            target=_worker_loop,
            args=(self._request_q, self._response_q),
            daemon=True,
        )
        self._process.start()
        _logger.info(
            "Conversion worker started (PID %d)", self._process.pid,
        )

    def stop(self) -> None:
        """Gracefully stop the worker subprocess.

        Sends a sentinel value and waits up to 5s for clean exit.
        Force-kills if the worker doesn't respond.
        """
        if self._process is None or not self._process.is_alive():
            self._process = None
            return

        try:
            self._request_q.put(None)  # Sentinel for clean shutdown
            self._process.join(timeout=5)
        except (OSError, ValueError):
            pass

        if self._process.is_alive():
            _logger.warning("Conversion worker did not exit cleanly, killing")
            self._process.kill()
            self._process.join(timeout=5)

        _logger.info("Conversion worker stopped")
        self._process = None

    def _restart(self) -> None:
        """Kill and restart the worker subprocess."""
        _logger.info("Restarting conversion worker")
        self.stop()
        self.start()

    def _ensure_alive(self) -> None:
        """Ensure the worker is running, restarting if needed."""
        if self._process is None or not self._process.is_alive():
            _logger.warning("Conversion worker not alive, restarting")
            self.start()

    def convert(self, file_path: str, timeout: int = 300) -> str:
        """Convert a binary file to markdown via the worker subprocess.

        Sends the file path to the worker and waits for the result.
        If the worker crashes or times out, it is restarted automatically.

        Args:
            file_path: Path to the file to convert.
            timeout: Max seconds to wait for conversion.

        Returns:
            Converted markdown text.

        Raises:
            TimeoutError: If conversion exceeds the timeout.
            RuntimeError: If conversion fails in the worker.
        """
        self._ensure_alive()

        # Drain any stale responses from a previous crash/timeout
        self._drain_response_queue()

        self._request_q.put(file_path)

        try:
            result_tuple = self._response_q.get(timeout=timeout)
        except queue.Empty:
            # Worker hung -- kill and restart for next call
            _logger.warning(
                "Conversion timed out after %ds: %s", timeout, file_path,
            )
            self._restart()
            raise TimeoutError(
                f"File conversion timed out after {timeout}s: {file_path}"
            )

        ok, text, error, rss_mb = result_tuple

        # Check RSS and restart if over threshold (non-blocking for caller)
        if rss_mb > self._rss_threshold_mb:
            _logger.info(
                "Worker RSS %d MB exceeds %d MB threshold, scheduling restart",
                rss_mb, self._rss_threshold_mb,
            )
            self._restart()

        if not ok:
            raise RuntimeError(f"Conversion failed: {error}")

        return text

    def _drain_response_queue(self) -> None:
        """Discard any stale messages in the response queue.

        After a timeout/crash, the response queue may have leftover
        results from previous requests. Drain them before sending a
        new request to keep request/response pairs in sync.
        """
        while True:
            try:
                self._response_q.get_nowait()
            except queue.Empty:
                break
