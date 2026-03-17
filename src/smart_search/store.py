# LanceDB vector storage + SQLite metadata for chunk persistence and search.

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import lancedb
import pyarrow as pa

from datetime import timedelta

from smart_search.config import SmartSearchConfig
from smart_search.models import Chunk, IndexStats, SearchResult


class ChunkStore:
    """Stores and retrieves document chunks using LanceDB (vectors) and SQLite (metadata).

    LanceDB handles vector storage and similarity search.
    SQLite tracks which files have been indexed and their content hashes.
    """

    def __init__(self, config: SmartSearchConfig) -> None:
        """Initialize store with paths from config.

        Args:
            config: SmartSearchConfig with lancedb_path, sqlite_path, table name.
        """
        self._config = config
        self._db = None
        self._table = None
        self._sqlite_conn = None

    def initialize(self) -> None:
        """Create LanceDB database/table and SQLite schema.

        Safe to call multiple times (idempotent).
        """
        # LanceDB setup
        Path(self._config.lancedb_path).mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(self._config.lancedb_path)

        existing_tables = self._db.list_tables().tables
        if self._config.lancedb_table_name in existing_tables:
            self._table = self._db.open_table(self._config.lancedb_table_name)
        else:
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("source_path", pa.string()),
                pa.field("source_type", pa.string()),
                pa.field("content_type", pa.string()),
                pa.field("text", pa.string()),
                pa.field("page_number", pa.int32()),
                pa.field("section_path", pa.string()),
                pa.field("embedding", pa.list_(pa.float32(), self._config.embedding_dimensions)),
                pa.field("has_image", pa.bool_()),
                pa.field("image_path", pa.string()),
                pa.field("entity_tags", pa.string()),
                pa.field("source_title", pa.string()),
                pa.field("source_date", pa.string()),
                pa.field("indexed_at", pa.string()),
                pa.field("model_name", pa.string()),
            ])
            self._table = self._db.create_table(
                self._config.lancedb_table_name, schema=schema
            )

        # SQLite setup
        Path(self._config.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self._sqlite_conn = sqlite3.connect(
            self._config.sqlite_path, check_same_thread=False
        )
        # WAL mode allows concurrent reads during writes so stats/search
        # queries aren't blocked while indexing threads write to the DB.
        self._sqlite_conn.execute("PRAGMA journal_mode=WAL")
        # Separate read-only connection for stats queries. WAL only enables
        # concurrent reads on *different* connections; the write connection
        # serializes all operations including reads.
        self._sqlite_read_conn = sqlite3.connect(
            self._config.sqlite_path, check_same_thread=False
        )
        self._sqlite_read_conn.execute("PRAGMA journal_mode=WAL")
        self._sqlite_conn.execute(
            """CREATE TABLE IF NOT EXISTS indexed_files (
                source_path TEXT PRIMARY KEY,
                file_hash   TEXT NOT NULL,
                chunk_count INTEGER NOT NULL,
                indexed_at  TEXT NOT NULL
            )"""
        )

        # FTS5 virtual table for keyword search (hybrid search v0.8)
        self._sqlite_conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text,
                id UNINDEXED,
                source_path UNINDEXED,
                source_type UNINDEXED,
                tokenize='porter unicode61'
            )"""
        )
        self._sqlite_conn.commit()

    def close(self) -> None:
        """Close the SQLite connection.

        Call before deleting the backing directory (e.g. ephemeral
        indexes on Windows) to release file locks.
        """
        if self._sqlite_read_conn:
            self._sqlite_read_conn.close()
            self._sqlite_read_conn = None
        if self._sqlite_conn:
            self._sqlite_conn.close()
            self._sqlite_conn = None

    def upsert_chunks(self, chunks: List[Chunk]) -> None:
        """Insert or replace chunks in LanceDB and FTS5.

        Deletes existing chunks with matching IDs before inserting,
        ensuring idempotent upsert behavior.

        Args:
            chunks: List of Chunk objects with populated embeddings.
        """
        if not chunks:
            return

        # Delete existing chunks with same IDs
        chunk_ids = [c.id for c in chunks]
        for cid in chunk_ids:
            try:
                self._table.delete(f'id = "{cid}"')
            except Exception:
                pass  # Row may not exist

        # Remove old FTS5 entries for these chunk IDs
        for cid in chunk_ids:
            self._sqlite_conn.execute(
                "DELETE FROM chunks_fts WHERE id = ?", (cid,)
            )

        # Insert new chunks into LanceDB
        records = [self._chunk_to_record(c) for c in chunks]
        self._table.add(records)

        # Insert into FTS5 for keyword search
        for c in chunks:
            self._sqlite_conn.execute(
                "INSERT INTO chunks_fts (text, id, source_path, source_type) "
                "VALUES (?, ?, ?, ?)",
                (c.text, c.id, c.source_path, c.source_type),
            )
        self._sqlite_conn.commit()

    def delete_chunks_for_file(self, source_path: str) -> int:
        """Remove all chunks for a given source file from LanceDB and FTS5.

        Args:
            source_path: The source_path value stored in chunks.

        Returns:
            Number of chunks deleted.
        """
        existing = self.get_chunks_for_file(source_path)
        count = len(existing)
        if count > 0:
            # Escape single quotes in path
            escaped = source_path.replace("'", "''")
            self._table.delete(f"source_path = '{escaped}'")

            # Remove from FTS5
            self._sqlite_conn.execute(
                "DELETE FROM chunks_fts WHERE source_path = ?",
                (source_path,),
            )
            self._sqlite_conn.commit()
        return count

    def get_chunks_for_file(self, source_path: str) -> List[Chunk]:
        """Retrieve all chunks for a specific source file.

        Args:
            source_path: Path to the source document.

        Returns:
            List of Chunk objects for that file.
        """
        try:
            escaped = source_path.replace("'", "''")
            results = (
                self._table.search()
                .where(f"source_path = '{escaped}'")
                .limit(10000)
                .to_list()
            )
            return [self._record_to_chunk(r) for r in results]
        except Exception:
            return []

    def vector_search(
        self, query_embedding: List[float], limit: int = 10
    ) -> List[SearchResult]:
        """Search for chunks most similar to the query embedding.

        Args:
            query_embedding: 768-dim query vector.
            limit: Maximum number of results to return.

        Returns:
            List of SearchResult objects ranked by similarity (highest first).
        """
        results = (
            self._table.search(query_embedding)
            .metric("cosine")
            .limit(limit)
            .to_list()
        )

        search_results = []
        for rank, row in enumerate(results, start=1):
            chunk = self._record_to_chunk(row)
            # LanceDB cosine distance ranges 0..2; convert to 0..1 similarity
            distance = row.get("_distance", 0.0)
            score = max(0.0, 1.0 - distance)
            search_results.append(
                SearchResult(rank=rank, score=score, chunk=chunk)
            )

        return search_results

    def get_stats(self, watch_directories: list[str] | None = None) -> IndexStats:
        """Get statistics about the indexed knowledge base.

        Uses count_rows() and SQLite queries instead of loading all data
        into memory, keeping RAM usage constant regardless of index size.

        Args:
            watch_directories: Optional override for watch dirs. When provided,
                uses these instead of the startup config dirs. Enables live
                config (B22) — stats reflect current ConfigManager state.

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

        # Index size: use SQLite file size only (fast). LanceDB dir walk
        # can block during active indexing due to file locks.
        sqlite_path = Path(self._config.sqlite_path)
        index_size = sqlite_path.stat().st_size if sqlite_path.exists() else 0

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
        self, source_path: str, file_hash: str, chunk_count: int
    ) -> None:
        """Record that a file has been indexed.

        Args:
            source_path: Path to the document file.
            file_hash: SHA-256 hash of the file contents.
            chunk_count: Number of chunks produced from this file.
        """
        now = datetime.now(timezone.utc).isoformat()
        self._sqlite_conn.execute(
            """INSERT OR REPLACE INTO indexed_files
               (source_path, file_hash, chunk_count, indexed_at)
               VALUES (?, ?, ?, ?)""",
            (source_path, file_hash, chunk_count, now),
        )
        self._sqlite_conn.commit()

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

    def remove_files_for_folder(self, folder_path: str) -> int:
        """Remove all indexed files under a folder prefix.

        Removes both chunks (LanceDB) and file records (SQLite).

        Args:
            folder_path: Folder path prefix to match.

        Returns:
            Number of files removed.
        """
        normalized = folder_path.replace("\\", "/")
        if not normalized.endswith("/"):
            normalized += "/"
        cursor = self._sqlite_conn.execute(
            "SELECT source_path FROM indexed_files WHERE source_path LIKE ?",
            (normalized + "%",),
        )
        files = [row[0] for row in cursor.fetchall()]
        for source_path in files:
            self.delete_chunks_for_file(source_path)
            self.remove_file_record(source_path)

        # Compact LanceDB and purge old versions to reclaim disk space
        if files:
            self._compact_and_cleanup()

        return len(files)

    def rebuild_table(self) -> None:
        """Drop and recreate the LanceDB table with current config schema.

        Also clears all indexed_files records from SQLite since the
        embeddings are no longer valid after a model or dimension change.
        """
        # Drop existing LanceDB table
        try:
            self._db.drop_table(self._config.lancedb_table_name)
        except Exception:
            pass

        # Recreate with current config dimensions
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("source_path", pa.string()),
            pa.field("source_type", pa.string()),
            pa.field("content_type", pa.string()),
            pa.field("text", pa.string()),
            pa.field("page_number", pa.int32()),
            pa.field("section_path", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), self._config.embedding_dimensions)),
            pa.field("has_image", pa.bool_()),
            pa.field("image_path", pa.string()),
            pa.field("entity_tags", pa.string()),
            pa.field("source_title", pa.string()),
            pa.field("source_date", pa.string()),
            pa.field("indexed_at", pa.string()),
            pa.field("model_name", pa.string()),
        ])
        self._table = self._db.create_table(
            self._config.lancedb_table_name, schema=schema
        )

        # Clear SQLite records -- old embeddings are invalid
        self._sqlite_conn.execute("DELETE FROM indexed_files")

        # Rebuild FTS5 table (drop and recreate to clear all entries)
        self._sqlite_conn.execute("DROP TABLE IF EXISTS chunks_fts")
        self._sqlite_conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text,
                id UNINDEXED,
                source_path UNINDEXED,
                source_type UNINDEXED,
                tokenize='porter unicode61'
            )"""
        )
        self._sqlite_conn.commit()

    def reconcile(self) -> dict:
        """Remove chunks for files that no longer exist on disk.

        Queries all unique source_path values from SQLite indexed_files,
        checks if each file still exists via Path.exists(), removes
        missing files' chunks from LanceDB and records from SQLite,
        then compacts LanceDB.

        Returns:
            Dict with 'removed_count' (int) and 'removed_files' (list of paths).
        """
        cursor = self._sqlite_conn.execute(
            "SELECT source_path FROM indexed_files"
        )
        all_paths = [row[0] for row in cursor.fetchall()]

        removed_files = [p for p in all_paths if not Path(p).exists()]

        for source_path in removed_files:
            self.delete_chunks_for_file(source_path)
            self.remove_file_record(source_path)

        if removed_files:
            self._compact_and_cleanup()

        return {"removed_count": len(removed_files), "removed_files": list(removed_files)}

    def _compact_and_cleanup(self) -> None:
        """Compact LanceDB fragments and purge old versions to reclaim disk space.

        Requires pylance for actual compaction. Falls back silently if unavailable.
        """
        try:
            self._table.compact_files()
            self._table.cleanup_old_versions(older_than=timedelta(0))
        except (ImportError, Exception):
            pass  # pylance not installed or compaction failed

    def _chunk_to_record(self, chunk: Chunk) -> dict:
        """Convert a Chunk to a dict suitable for LanceDB insertion.

        Args:
            chunk: Chunk Pydantic model.

        Returns:
            Dictionary with all chunk fields.
        """
        return {
            "id": chunk.id,
            "source_path": chunk.source_path,
            "source_type": chunk.source_type,
            "content_type": chunk.content_type,
            "text": chunk.text,
            "page_number": chunk.page_number if chunk.page_number is not None else 0,
            "section_path": chunk.section_path,
            "embedding": chunk.embedding,
            "has_image": chunk.has_image,
            "image_path": chunk.image_path or "",
            "entity_tags": chunk.entity_tags or "",
            "source_title": chunk.source_title or "",
            "source_date": chunk.source_date or "",
            "indexed_at": chunk.indexed_at,
            "model_name": chunk.model_name,
        }

    def _record_to_chunk(self, record: dict) -> Chunk:
        """Convert a LanceDB record back to a Chunk model.

        Args:
            record: Dictionary from LanceDB query result.

        Returns:
            Chunk Pydantic model.
        """
        return Chunk(
            id=record["id"],
            source_path=record["source_path"],
            source_type=record["source_type"],
            content_type=record["content_type"],
            text=record["text"],
            page_number=record.get("page_number") or None,
            section_path=record["section_path"],
            embedding=list(record["embedding"]),
            has_image=record.get("has_image", False),
            image_path=record.get("image_path") or None,
            entity_tags=record.get("entity_tags") or None,
            source_title=record.get("source_title") or None,
            source_date=record.get("source_date") or None,
            indexed_at=record["indexed_at"],
            model_name=record["model_name"],
        )

    def _calculate_index_size(self) -> int:
        """Calculate total size of LanceDB and SQLite files on disk.

        Best-effort: returns 0 if files are locked during active indexing
        rather than blocking the stats endpoint.

        Returns:
            Total size in bytes.
        """
        total = 0
        try:
            lance_path = Path(self._config.lancedb_path)
            if lance_path.exists():
                for f in lance_path.rglob("*"):
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
