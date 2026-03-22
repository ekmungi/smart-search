# Index statistics and size calculation for ChunkStore.

"""Mixin class providing stats and index size methods for ChunkStore.
Includes time-cached index size to avoid blocking during active indexing."""

import logging
import time
from pathlib import Path

from smart_search.models import IndexStats

_logger = logging.getLogger(__name__)


class StatsStoreMixin:
    """Mixin providing index statistics methods for ChunkStore.

    Expects the host class to have:
        - self._sqlite_read_conn: sqlite3.Connection (read-only)
        - self._config: SmartSearchConfig
        - self._cached_index_size: int
        - self._cached_index_size_at: float
    """

    def _init_size_cache(self) -> None:
        """Trigger an immediate index size calculation on startup.

        The 5s deadline in _calculate_index_size() prevents blocking, so we
        can safely compute the real size instead of returning 0 MB for the
        first 120 seconds. Falls back to 0 on any error.
        """
        try:
            self._cached_index_size = self._calculate_index_size()
        except OSError:
            self._cached_index_size = 0
        self._cached_index_size_at = time.monotonic()

    def get_stats(self, watch_directories: list[str] | None = None) -> IndexStats:
        """Get statistics about the indexed knowledge base.

        Uses count_rows() and SQLite queries instead of loading all data
        into memory, keeping RAM usage constant regardless of index size.

        Args:
            watch_directories: Optional override for watch dirs. When provided,
                uses these instead of the startup config dirs. Enables live
                config (B22) -- stats reflect current ConfigManager state.

        Returns:
            IndexStats with document count, chunk count, size, formats.
        """
        # All stats from the read-only SQLite connection -- avoids blocking
        # on the write connection used by indexing threads. WAL mode enables
        # concurrent reads on separate connections.
        doc_count = 0
        chunk_count = 0
        formats: list[str] = []
        last_indexed = None
        total_files = 0
        conn = self._sqlite_read_conn
        if conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(chunk_count), 0) FROM indexed_files"
            ).fetchone()
            doc_count = row[0] if row else 0
            chunk_count = row[1] if row else 0

            # Derive formats from file extensions in source_path
            path_rows = conn.execute(
                "SELECT DISTINCT source_path FROM indexed_files"
            ).fetchall()
            ext_set = set()
            for r in path_rows:
                ext = Path(r[0]).suffix.lower()
                if ext:
                    ext_set.add(ext)
            formats = sorted(ext_set)

            ts_row = conn.execute(
                "SELECT MAX(indexed_at) FROM indexed_files"
            ).fetchone()
            if ts_row and ts_row[0]:
                last_indexed = ts_row[0]

        # Index size: LanceDB + SQLite with 60s cache to avoid blocking
        # during active indexing (B54). Falls back to stale cache on error.
        index_size = self._get_cached_index_size()

        # Total files: use SQLite doc_count (already indexed) as the baseline.
        # This avoids expensive rglob scans on OneDrive folders during polling.
        total_files = doc_count

        return IndexStats(
            document_count=doc_count,
            chunk_count=chunk_count,
            index_size_bytes=index_size,
            total_files=total_files,
            last_indexed_at=last_indexed,
            formats_indexed=formats,
        )

    def invalidate_size_cache(self) -> None:
        """Reset the cached index size so the next stats call recalculates.

        Called after rebuild_table() wipes the LanceDB directory (B58).
        """
        self._cached_index_size = 0
        self._cached_index_size_at = 0.0

    def _get_cached_index_size(self) -> int:
        """Return total index size with a 120-second time-based cache.

        Avoids blocking the stats endpoint during active writes while
        still reporting the full LanceDB + SQLite size (B54). Uses 120s TTL
        since index size is informational and not worth blocking for.

        Returns:
            Total size in bytes (may be up to 120s stale).
        """
        now = time.monotonic()
        if now - self._cached_index_size_at < 120.0:
            return self._cached_index_size
        try:
            size = self._calculate_index_size()
            self._cached_index_size = size
            self._cached_index_size_at = now
            return size
        except OSError:
            # Return stale cache on any error (file locks, etc.)
            _logger.debug("Index size calculation failed, using stale cache", exc_info=True)
            return self._cached_index_size

    # Maximum time (seconds) to spend scanning LanceDB files before
    # returning a partial count. Prevents rglob from blocking the stats
    # endpoint when hundreds of fragment files exist during active indexing.
    _INDEX_SIZE_SCAN_DEADLINE_S = 5.0

    def _calculate_index_size(self) -> int:
        """Calculate total size of LanceDB and SQLite files on disk.

        Best-effort: returns partial count if the scan exceeds 5s, and
        returns 0 if files are locked during active indexing rather than
        blocking the stats endpoint.

        Returns:
            Total size in bytes (may be partial if scan was time-capped).
        """
        total = 0
        deadline = time.monotonic() + self._INDEX_SIZE_SCAN_DEADLINE_S
        try:
            lance_path = Path(self._config.lancedb_path)
            if lance_path.exists():
                for f in lance_path.rglob("*"):
                    if time.monotonic() > deadline:
                        _logger.debug("Index size scan hit 5s deadline, returning partial count")
                        break
                    try:
                        if f.is_file():
                            total += f.stat().st_size
                    except OSError:
                        pass

            sqlite_path = Path(self._config.sqlite_path)
            if sqlite_path.exists():
                total += sqlite_path.stat().st_size
        except OSError:
            pass

        return total
