"""SQLite table tracking what model/config built the index."""

import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional


class IndexMetadata:
    """Stores and retrieves index build metadata in SQLite.

    Tracks which embedding model, dimensions, and backend were used
    to build the current index. Detects mismatches when config changes.
    """

    def __init__(self, db_path: str) -> None:
        """Initialize with SQLite database path.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Create the index_metadata table if it does not exist."""
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS index_metadata (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def set(self, key: str, value: str) -> None:
        """Store or update a metadata key-value pair.

        Args:
            key: Metadata key (e.g., 'embedding_model').
            value: Metadata value.
        """
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO index_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
        self._conn.commit()

    def get(self, key: str) -> Optional[str]:
        """Retrieve a metadata value by key.

        Args:
            key: Metadata key to look up.

        Returns:
            The value, or None if the key does not exist.
        """
        cursor = self._conn.execute(
            "SELECT value FROM index_metadata WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def get_all(self) -> Dict[str, str]:
        """Retrieve all metadata as a dictionary.

        Returns:
            Dict of all key-value pairs.
        """
        cursor = self._conn.execute("SELECT key, value FROM index_metadata")
        return dict(cursor.fetchall())

    def check_mismatch(self, current_config: Dict[str, str]) -> Dict[str, tuple]:
        """Compare stored metadata against current config.

        Args:
            current_config: Dict of current config key-value pairs.

        Returns:
            Dict of mismatched keys: {key: (stored_value, config_value)}.
            Empty dict means no mismatches.
        """
        stored = self.get_all()
        mismatches = {}
        for key, config_val in current_config.items():
            stored_val = stored.get(key)
            if stored_val is not None and stored_val != config_val:
                mismatches[key] = (stored_val, config_val)
        return mismatches

    def clear(self) -> None:
        """Remove all metadata entries (used during index rebuild)."""
        self._conn.execute("DELETE FROM index_metadata")
        self._conn.commit()
