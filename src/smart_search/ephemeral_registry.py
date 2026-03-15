# EphemeralRegistry: manages ephemeral index metadata in SQLite with CRUD and stale pruning.
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


def _utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EphemeralEntry:
    """Immutable record for a single ephemeral index entry."""

    folder_path: str
    created_at: str
    last_accessed: str
    chunk_count: int
    size_bytes: int


class EphemeralRegistry:
    """Manages the ephemeral_indexes table in a SQLite database.

    Tracks which folders have been indexed ephemerally, including metadata
    such as chunk count, size, and access timestamps. Supports stale pruning
    based on the presence of a .smart-search/ directory on disk.
    """

    def __init__(self, sqlite_path: str) -> None:
        """Store the path to the SQLite database; connection is deferred.

        Args:
            sqlite_path: Absolute path to the SQLite file.
        """
        self._sqlite_path = sqlite_path

    def _connect(self) -> sqlite3.Connection:
        """Open and return a new SQLite connection with row_factory set.

        Returns:
            A sqlite3.Connection configured to return Row objects.
        """
        conn = sqlite3.connect(self._sqlite_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        """Create the ephemeral_indexes table if it does not already exist."""
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ephemeral_indexes (
                    folder_path   TEXT PRIMARY KEY,
                    created_at    TEXT NOT NULL,
                    last_accessed TEXT NOT NULL,
                    chunk_count   INTEGER NOT NULL,
                    size_bytes    INTEGER NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def register(self, folder_path: str, chunk_count: int, size_bytes: int) -> None:
        """Insert or replace an ephemeral index entry with current UTC timestamps.

        Args:
            folder_path: Absolute path to the indexed folder.
            chunk_count: Number of chunks stored for this folder.
            size_bytes:  Total byte size of the index data.
        """
        now = _utc_now()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO ephemeral_indexes
                    (folder_path, created_at, last_accessed, chunk_count, size_bytes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (folder_path, now, now, chunk_count, size_bytes),
            )
            conn.commit()
        finally:
            conn.close()

    def deregister(self, folder_path: str) -> bool:
        """Delete an ephemeral index entry by folder path.

        Args:
            folder_path: Absolute path to the folder to remove.

        Returns:
            True if a row was deleted, False if the path was not found.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM ephemeral_indexes WHERE folder_path = ?",
                (folder_path,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def touch(self, folder_path: str) -> None:
        """Update last_accessed to the current UTC time for the given folder.

        Args:
            folder_path: Absolute path to the folder to update.
        """
        now = _utc_now()
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE ephemeral_indexes SET last_accessed = ? WHERE folder_path = ?",
                (now, folder_path),
            )
            conn.commit()
        finally:
            conn.close()

    def list_all(self) -> List[EphemeralEntry]:
        """Return all ephemeral index entries ordered by created_at descending.

        Returns:
            A list of EphemeralEntry dataclasses, newest first.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM ephemeral_indexes ORDER BY created_at DESC"
            )
            return [_row_to_entry(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get(self, folder_path: str) -> Optional[EphemeralEntry]:
        """Retrieve a single ephemeral index entry by folder path.

        Args:
            folder_path: Absolute path to the folder to look up.

        Returns:
            An EphemeralEntry if found, or None.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM ephemeral_indexes WHERE folder_path = ?",
                (folder_path,),
            )
            row = cursor.fetchone()
            return _row_to_entry(row) if row is not None else None
        finally:
            conn.close()

    def prune_stale(self) -> List[str]:
        """Remove entries whose folder no longer contains a .smart-search/ directory.

        An ephemeral index is considered stale when the .smart-search/ subdirectory
        inside the registered folder_path does not exist on disk.

        Returns:
            A list of folder_path strings that were pruned.
        """
        entries = self.list_all()
        pruned: List[str] = []
        for entry in entries:
            smart_search_dir = Path(entry.folder_path) / ".smart-search"
            if not smart_search_dir.is_dir():
                self.deregister(entry.folder_path)
                pruned.append(entry.folder_path)
        return pruned


def _row_to_entry(row: sqlite3.Row) -> EphemeralEntry:
    """Convert a sqlite3.Row to an immutable EphemeralEntry.

    Args:
        row: A sqlite3.Row from the ephemeral_indexes table.

    Returns:
        An EphemeralEntry populated from the row.
    """
    return EphemeralEntry(
        folder_path=row["folder_path"],
        created_at=row["created_at"],
        last_accessed=row["last_accessed"],
        chunk_count=row["chunk_count"],
        size_bytes=row["size_bytes"],
    )
