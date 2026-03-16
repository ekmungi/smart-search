# Startup checks: index compatibility, orphan reconciliation, FTS5 backfill.

"""Startup checks run when the HTTP server starts.

Validates that the current config matches the stored index metadata,
removes orphan chunks for files deleted while the app was offline,
and backfills the FTS5 index for hybrid search migration."""

import logging
import sqlite3
from typing import Dict

from smart_search.config import SmartSearchConfig
from smart_search.fts import backfill_fts, fts_count
from smart_search.index_metadata import IndexMetadata
from smart_search.store import ChunkStore

logger = logging.getLogger(__name__)


def check_index_compatibility(config: SmartSearchConfig, db_path: str) -> Dict:
    """Check if the current config matches the index metadata.

    Args:
        config: Current SmartSearchConfig.
        db_path: Path to SQLite database.

    Returns:
        Dict with 'compatible' (bool) and 'mismatches' (dict).
    """
    metadata = IndexMetadata(db_path)
    metadata.initialize()

    current = {
        "embedding_model": config.embedding_model,
        "embedding_dimensions": str(config.embedding_dimensions),
    }
    mismatches = metadata.check_mismatch(current)

    if mismatches:
        for key, (stored, current_val) in mismatches.items():
            logger.warning(
                "Index mismatch: %s changed from '%s' to '%s'. "
                "Re-indexing recommended.",
                key, stored, current_val,
            )

    return {"compatible": len(mismatches) == 0, "mismatches": mismatches}


def reconcile_orphans(store: ChunkStore) -> Dict:
    """Remove orphan chunks for files that no longer exist.

    Args:
        store: Initialized ChunkStore instance.

    Returns:
        Dict with 'removed_count' and 'removed_files'.
    """
    result = store.reconcile()
    if result["removed_count"] > 0:
        logger.info(
            "Reconciled %d orphan files: %s",
            result["removed_count"],
            result["removed_files"],
        )
    return result


def backfill_fts_if_needed(store: ChunkStore) -> Dict:
    """Backfill FTS5 index from LanceDB if FTS5 is empty but chunks exist.

    One-time migration for indexes created before hybrid search (v0.8).
    Checks if FTS5 is empty and LanceDB has chunks, then backfills.

    Args:
        store: Initialized ChunkStore instance.

    Returns:
        Dict with 'backfilled' (bool) and 'count' (int).
    """
    conn = store._sqlite_conn
    table = store._table

    if conn is None or table is None:
        return {"backfilled": False, "count": 0}

    existing_fts = fts_count(conn)
    if existing_fts > 0:
        logger.info("FTS5 index already populated (%d rows), skipping backfill", existing_fts)
        return {"backfilled": False, "count": existing_fts}

    try:
        lance_count = table.count_rows()
    except Exception:
        lance_count = 0

    if lance_count == 0:
        return {"backfilled": False, "count": 0}

    logger.info("FTS5 backfill starting: %d LanceDB chunks to migrate", lance_count)
    count = backfill_fts(conn, table)
    logger.info("FTS5 backfill complete: %d chunks indexed", count)
    return {"backfilled": True, "count": count}


def repair_index(store: ChunkStore, config: SmartSearchConfig, db_path: str) -> Dict:
    """Run all maintenance: orphan removal, FTS5 rebuild, compaction, compatibility check.

    Unlike startup checks, FTS5 is always dropped and rebuilt (not conditional).
    This is the manual repair path triggered by the user.

    Args:
        store: Initialized ChunkStore instance.
        config: Current SmartSearchConfig.
        db_path: Path to SQLite database.

    Returns:
        Dict with orphans_removed, orphan_files, fts_rebuilt, fts_rows,
        compacted, compatible, mismatches.
    """
    # Step 1: Remove orphan chunks for deleted files
    orphan_result = reconcile_orphans(store)

    # Step 2: Drop and rebuild FTS5 from LanceDB (always, not conditional)
    conn = store._sqlite_conn
    table = store._table
    fts_rows = 0
    if conn is not None and table is not None:
        conn.execute("DROP TABLE IF EXISTS chunks_fts")
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text,
                id UNINDEXED,
                source_path UNINDEXED,
                source_type UNINDEXED,
                tokenize='porter unicode61'
            )"""
        )
        conn.commit()
        fts_rows = backfill_fts(conn, table)
        logger.info("FTS5 repair: rebuilt with %d rows", fts_rows)

    # Step 3: Compact LanceDB to reclaim disk space
    compacted = True
    try:
        store._compact_and_cleanup()
    except Exception:
        compacted = False

    # Step 4: Check index compatibility (model/dimension mismatches)
    compat_result = check_index_compatibility(config, db_path)

    return {
        "orphans_removed": orphan_result["removed_count"],
        "orphan_files": orphan_result["removed_files"],
        "fts_rebuilt": True,
        "fts_rows": fts_rows,
        "compacted": compacted,
        "compatible": compat_result["compatible"],
        "mismatches": compat_result["mismatches"],
    }
