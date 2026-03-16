# FTS5 keyword search and backfill utilities for hybrid search.

"""Provides keyword search via SQLite FTS5, chunk retrieval from LanceDB
by ID, and one-time backfill migration for existing indexes upgrading
to hybrid search (v0.8)."""

import logging
import sqlite3
from typing import Dict, List

from smart_search.models import Chunk

logger = logging.getLogger(__name__)


def keyword_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
) -> List[dict]:
    """Search the FTS5 index for chunks matching a keyword query.

    Uses SQLite FTS5 MATCH syntax with porter stemming. Returns results
    ranked by BM25 relevance (lower rank = more relevant).

    Args:
        conn: SQLite connection with chunks_fts table.
        query: Search query string (FTS5 MATCH syntax).
        limit: Maximum number of results.

    Returns:
        List of dicts with id, source_path, source_type, text, bm25_score.
    """
    # Escape double quotes in query to prevent FTS5 syntax errors
    safe_query = query.replace('"', '""')

    try:
        cursor = conn.execute(
            """SELECT id, source_path, source_type, text,
                      bm25(chunks_fts) AS bm25_score
               FROM chunks_fts
               WHERE chunks_fts MATCH ?
               ORDER BY bm25_score ASC
               LIMIT ?""",
            (f'"{safe_query}"', limit),
        )
    except Exception:
        # Fallback: try individual terms joined with OR
        terms = query.split()
        if not terms:
            return []
        or_query = " OR ".join(f'"{t.replace(chr(34), "")}"' for t in terms)
        try:
            cursor = conn.execute(
                """SELECT id, source_path, source_type, text,
                          bm25(chunks_fts) AS bm25_score
                   FROM chunks_fts
                   WHERE chunks_fts MATCH ?
                   ORDER BY bm25_score ASC
                   LIMIT ?""",
                (or_query, limit),
            )
        except Exception:
            return []

    return [
        {
            "id": row[0],
            "source_path": row[1],
            "source_type": row[2],
            "text": row[3],
            "bm25_score": row[4],
        }
        for row in cursor.fetchall()
    ]


def fts_count(conn: sqlite3.Connection) -> int:
    """Count the number of rows in the FTS5 index.

    Args:
        conn: SQLite connection with chunks_fts table.

    Returns:
        Number of rows in chunks_fts.
    """
    row = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()
    return row[0] if row else 0


def backfill_fts(conn: sqlite3.Connection, table, batch_size: int = 1000) -> int:
    """Populate FTS5 from existing LanceDB chunks.

    One-time migration for indexes created before hybrid search.
    Reads chunks in batches from LanceDB and inserts into FTS5.

    Args:
        conn: SQLite connection with chunks_fts table.
        table: LanceDB table object with .search() method.
        batch_size: Number of chunks per batch.

    Returns:
        Number of chunks backfilled.
    """
    try:
        total_rows = table.count_rows()
    except Exception:
        return 0

    if total_rows == 0:
        return 0

    inserted = 0
    offset = 0

    while offset < total_rows:
        try:
            rows = (
                table.search()
                .limit(batch_size)
                .offset(offset)
                .to_list()
            )
        except Exception:
            break

        if not rows:
            break

        for row in rows:
            conn.execute(
                "INSERT OR IGNORE INTO chunks_fts (text, id, source_path, source_type) "
                "VALUES (?, ?, ?, ?)",
                (
                    row.get("text", ""),
                    row.get("id", ""),
                    row.get("source_path", ""),
                    row.get("source_type", ""),
                ),
            )
            inserted += 1

        conn.commit()
        offset += batch_size

    logger.info("FTS5 backfill complete: %d chunks inserted", inserted)
    return inserted


def get_chunks_by_ids(table, chunk_ids: List[str]) -> Dict[str, Chunk]:
    """Fetch full Chunk data from LanceDB for a list of chunk IDs.

    Used after FTS5 keyword search returns IDs to hydrate full Chunk
    objects with embeddings and all metadata.

    Args:
        table: LanceDB table object.
        chunk_ids: List of chunk ID strings.

    Returns:
        Dict mapping chunk ID to Chunk object.
    """
    if not chunk_ids:
        return {}

    result = {}
    for cid in chunk_ids:
        try:
            rows = (
                table.search()
                .where(f'id = "{cid}"')
                .limit(1)
                .to_list()
            )
            if rows:
                row = rows[0]
                result[cid] = Chunk(
                    id=row["id"],
                    source_path=row["source_path"],
                    source_type=row["source_type"],
                    content_type=row["content_type"],
                    text=row["text"],
                    page_number=row.get("page_number") or None,
                    section_path=row["section_path"],
                    embedding=list(row["embedding"]),
                    has_image=row.get("has_image", False),
                    image_path=row.get("image_path") or None,
                    entity_tags=row.get("entity_tags") or None,
                    source_title=row.get("source_title") or None,
                    source_date=row.get("source_date") or None,
                    indexed_at=row["indexed_at"],
                    model_name=row["model_name"],
                )
        except Exception:
            pass  # Skip chunks that can't be retrieved

    return result
