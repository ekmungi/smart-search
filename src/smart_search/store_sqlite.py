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

    def record_file_indexed(
        self, source_path: str, file_hash: str, chunk_count: int,
        needs_ocr: bool = False,
    ) -> None:
        """Record that a file has been indexed.

        Args:
            source_path: Path to the document file.
            file_hash: SHA-256 hash of the file contents.
            chunk_count: Number of chunks produced from this file.
            needs_ocr: True if the file produced no text and needs OCR
                to be indexed properly. These files are skipped on restart
                but can be retried when OCR support is added.
        """
        now = datetime.now(timezone.utc).isoformat()
        self._sqlite_conn.execute(
            """INSERT OR REPLACE INTO indexed_files
               (source_path, file_hash, chunk_count, indexed_at, needs_ocr)
               VALUES (?, ?, ?, ?, ?)""",
            (source_path, file_hash, chunk_count, now, int(needs_ocr)),
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
