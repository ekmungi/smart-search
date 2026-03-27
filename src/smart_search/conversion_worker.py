# In-process file converter with memory leak protection.

"""Converts binary files to Markdown directly in-process (no subprocess).
Matches the proven MarkItDown MCP server architecture. Memory leaks are
handled by RSS monitoring + converter reset + periodic GC.

The old subprocess-based worker is available as SubprocessConversionWorker
via SMART_SEARCH_SUBPROCESS_CONVERTER=1 environment variable."""

import gc
import logging
import os
import threading
from typing import Optional

from smart_search.markitdown_parser import convert_to_markdown, reset_converter

_logger = logging.getLogger(__name__)

# Restart threshold for RSS (megabytes).
_RSS_RESTART_THRESHOLD_MB = 1024

# GC interval: run gc.collect() every N conversions.
_GC_INTERVAL = 5


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
    """In-process file converter with memory leak protection.

    Converts files directly (no subprocess) like the MarkItDown MCP server.
    Monitors RSS after each conversion and resets the converter when memory
    grows beyond the threshold.
    """

    def __init__(self, rss_threshold_mb: int = _RSS_RESTART_THRESHOLD_MB) -> None:
        """Initialize the worker.

        Args:
            rss_threshold_mb: Reset converter if RSS exceeds this (MB).
        """
        self._rss_threshold_mb = rss_threshold_mb
        self._conversions_since_gc = 0
        self._gc_interval = _GC_INTERVAL
        self._converter_reset_count = 0

    def start(self) -> None:
        """No-op for API compatibility. In-process needs no startup."""
        _logger.info("ConversionWorker ready (in-process mode)")

    def stop(self) -> None:
        """Release the MarkItDown converter and force GC."""
        reset_converter()
        gc.collect()
        _logger.info("ConversionWorker stopped, converter released")

    def convert(self, file_path: str, timeout: int = 300) -> str:
        """Convert a binary file to markdown in-process.

        Uses a daemon thread with join(timeout) as a safety net for
        hung conversions. The thread is abandoned if it exceeds timeout.

        Args:
            file_path: Path to the file to convert.
            timeout: Max seconds to wait for conversion.

        Returns:
            Converted markdown text.

        Raises:
            TimeoutError: If conversion exceeds the timeout.
            RuntimeError: If conversion fails.
            ValueError: If conversion produces empty output.
        """
        result_box: dict = {}

        def _do_convert():
            try:
                result_box["text"] = convert_to_markdown(file_path)
            except Exception as e:
                result_box["error"] = e

        thread = threading.Thread(target=_do_convert, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            _logger.error(
                "Conversion timed out after %ds: %s", timeout, file_path,
            )
            raise TimeoutError(
                f"File conversion timed out after {timeout}s: {file_path}"
            )

        if "error" in result_box:
            raise result_box["error"]

        text = result_box.get("text", "")

        # Memory management: periodic GC
        self._conversions_since_gc += 1
        if self._conversions_since_gc >= self._gc_interval:
            gc.collect()
            self._conversions_since_gc = 0

        # Memory management: RSS check + converter reset
        rss = _get_rss_mb()
        if rss > self._rss_threshold_mb:
            _logger.warning(
                "RSS %d MB exceeds %d MB threshold, resetting converter",
                rss, self._rss_threshold_mb,
            )
            reset_converter()
            gc.collect()
            self._converter_reset_count += 1

        return text


def create_conversion_worker(**kwargs) -> "ConversionWorker":
    """Create the appropriate ConversionWorker based on environment.

    Set SMART_SEARCH_SUBPROCESS_CONVERTER=1 to use the old subprocess-based
    worker as a fallback.

    Args:
        **kwargs: Passed to the worker constructor (e.g. rss_threshold_mb).

    Returns:
        ConversionWorker instance (in-process default, or subprocess fallback).
    """
    if os.environ.get("SMART_SEARCH_SUBPROCESS_CONVERTER"):
        from smart_search.subprocess_conversion_worker import SubprocessConversionWorker
        _logger.info("Using subprocess conversion worker (env override)")
        worker = SubprocessConversionWorker(**kwargs)
        worker.start()
        return worker  # type: ignore[return-value]
    return ConversionWorker(**kwargs)
