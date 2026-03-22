# SQLite metadata operations for indexed file tracking.

"""Mixin class providing SQLite-backed file metadata methods for ChunkStore.
Handles indexed file records, OCR flags, and file listing queries."""

import sqlite3
from datetime import datetime, timezone


class SqliteMetadataStore:
    """Mixin providing SQLite metadata operations for file indexing state.

    Expects the host class to have:
        - self._sqlite_conn: sqlite3.Connection (read-write)
    """

    def is_file_indexed(self, source_path: str, file_hash: str) -> bool:
        """Check if a file is already indexed with the given hash.

        Args:
            source_path: Path to the document file.
            file_hash: SHA-256 hash of the file contents.

        Returns:
            True if the file is indexed at exactly this hash.
        """
        cursor = self._sqlite_conn.execute(
            "SELECT file_hash FROM indexed_files WHERE source_path = ?",
            (source_path,),
        )
        row = cursor.fetchone()
        return row is not None and row[0] == file_hash

    def remove_file_record(self, source_path: str) -> None:
        """Remove the indexed_files record for a source file.

        Called when a watched file is deleted. Does nothing if the
        record does not exist.

        Args:
            source_path: Path to the document file.
        """
        self._sqlite_conn.execute(
            "DELETE FROM indexed_files WHERE source_path = ?",
            (source_path,),
        )
        self._sqlite_conn.commit()

    def is_file_unchanged(self, source_path: str, file_mtime: float, file_size: int) -> bool:
        """Fast check: file unchanged if mtime and size match stored values.

        Returns False (triggers hash check) when:
        - File not in index
        - Stored mtime/size are NULL (pre-migration rows)
        - mtime or size differ

        Args:
            source_path: POSIX-normalized path to the document file.
            file_mtime: Current file modification time (seconds since epoch).
            file_size: Current file size in bytes.

        Returns:
            True if mtime and size both match stored values.
        """
        cursor = self._sqlite_conn.execute(
            "SELECT file_mtime, file_size FROM indexed_files WHERE source_path = ?",
            (source_path,),
        )
        row = cursor.fetchone()
        if row is None or row[0] is None or row[1] is None:
            return False
        return row[0] == file_mtime and row[1] == file_size

    def record_file_indexed(
        self, source_path: str, file_hash: str, chunk_count: int,
        needs_ocr: bool = False,
        file_mtime: float | None = None,
        file_size: int | None = None,
    ) -> None:
        """Record that a file has been indexed.

        Args:
            source_path: Path to the document file.
            file_hash: SHA-256 hash of the file contents.
            chunk_count: Number of chunks produced from this file.
            needs_ocr: True if the file produced no text and needs OCR
                to be indexed properly. These files are skipped on restart
                but can be retried when OCR support is added.
            file_mtime: File modification time for fast change detection.
            file_size: File size in bytes for fast change detection.
        """
        now = datetime.now(timezone.utc).isoformat()
        self._sqlite_conn.execute(
            """INSERT OR REPLACE INTO indexed_files
               (source_path, file_hash, chunk_count, indexed_at, needs_ocr,
                file_mtime, file_size)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source_path, file_hash, chunk_count, now, int(needs_ocr),
             file_mtime, file_size),
        )
        self._sqlite_conn.commit()

    def record_file_failed(
        self, source_path: str, file_hash: str, error: str,
        file_mtime: float | None = None,
        file_size: int | None = None,
    ) -> None:
        """Record that a file failed to index.

        Stores the failure with mtime/size so the file is not retried on
        restart unless it changes. Useful for scanned PDFs, timeout errors,
        and other persistent failures.

        Args:
            source_path: Path to the document file.
            file_hash: SHA-256 hash of the file contents.
            error: Error message describing the failure.
            file_mtime: File modification time for change detection.
            file_size: File size in bytes for change detection.
        """
        now = datetime.now(timezone.utc).isoformat()
        self._sqlite_conn.execute(
            """INSERT OR REPLACE INTO indexed_files
               (source_path, file_hash, chunk_count, indexed_at, needs_ocr,
                file_mtime, file_size, status, error)
               VALUES (?, ?, 0, ?, 0, ?, ?, 'failed', ?)""",
            (source_path, file_hash, now, file_mtime, file_size, error),
        )
        self._sqlite_conn.commit()

    def update_file_metadata(
        self, source_path: str, file_mtime: float, file_size: int,
    ) -> None:
        """Update mtime + size without changing hash or chunk data.

        Used when mtime changed but content hash is the same (e.g. touch,
        OneDrive sync, file copy). Prevents re-hashing on next startup.

        Args:
            source_path: POSIX-normalized path to the document file.
            file_mtime: New file modification time.
            file_size: New file size in bytes.
        """
        self._sqlite_conn.execute(
            "UPDATE indexed_files SET file_mtime = ?, file_size = ? WHERE source_path = ?",
            (file_mtime, file_size, source_path),
        )
        self._sqlite_conn.commit()

    def get_needs_ocr_files(self) -> list[dict]:
        """List files that need OCR to be indexed properly.

        Returns:
            List of dicts with source_path and indexed_at.
        """
        cursor = self._sqlite_conn.execute(
            "SELECT source_path, indexed_at FROM indexed_files WHERE needs_ocr = 1"
        )
        return [
            {"source_path": row[0], "indexed_at": row[1]}
            for row in cursor.fetchall()
        ]

    def clear_needs_ocr(self, source_paths: list[str] | None = None) -> int:
        """Clear needs_ocr flag and hash so files are re-indexed on next run.

        Args:
            source_paths: Specific files to clear. If None, clears all.

        Returns:
            Number of files cleared.
        """
        if source_paths:
            placeholders = ",".join("?" for _ in source_paths)
            cursor = self._sqlite_conn.execute(
                f"DELETE FROM indexed_files WHERE needs_ocr = 1 AND source_path IN ({placeholders})",
                source_paths,
            )
        else:
            cursor = self._sqlite_conn.execute(
                "DELETE FROM indexed_files WHERE needs_ocr = 1"
            )
        self._sqlite_conn.commit()
        return cursor.rowcount

    def clear_all_file_hashes(self) -> int:
        """Clear all file hashes to force re-indexing on next ingest.

        Deletes all indexed_files records so hash-based skip no longer
        applies. Called when chunk config changes require a full re-index.

        Returns:
            Number of file records cleared.
        """
        cursor = self._sqlite_conn.execute("DELETE FROM indexed_files")
        self._sqlite_conn.commit()
        return cursor.rowcount

    def list_indexed_files(self) -> list:
        """List all indexed files with metadata.

        Returns:
            List of dicts with source_path, file_hash, chunk_count, indexed_at.
        """
        cursor = self._sqlite_conn.execute(
            "SELECT source_path, file_hash, chunk_count, indexed_at "
            "FROM indexed_files ORDER BY indexed_at DESC"
        )
        return [
            {
                "source_path": row[0],
                "file_hash": row[1],
                "chunk_count": row[2],
                "indexed_at": row[3],
            }
            for row in cursor.fetchall()
        ]
