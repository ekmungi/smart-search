# Startup checks: index compatibility, orphan reconciliation, FTS5 backfill, SSL.

"""Startup checks run when the HTTP server starts.

Validates that the current config matches the stored index metadata,
removes orphan chunks for files deleted while the app was offline,
backfills the FTS5 index for hybrid search migration, and injects
OS certificate store for enterprise SSL compatibility."""

import logging
import sqlite3
from typing import Dict

from smart_search.config import SmartSearchConfig
from smart_search.fts import backfill_fts, fts_count
from smart_search.index_metadata import IndexMetadata
from smart_search.store import ChunkStore

logger = logging.getLogger(__name__)


def inject_ssl_truststore() -> bool:
    """Inject OS certificate store into Python's SSL context.

    Uses truststore (PEP 543) so that huggingface_hub and other HTTPS
    clients trust the same CA certificates as the system browser. Fixes
    model downloads on enterprise networks with SSL inspection proxies.

    Returns:
        True if injection succeeded, False if truststore is unavailable.
    """
    try:
        import truststore
        truststore.inject_into_ssl()
        logger.info("truststore: using OS certificate store for SSL")
        return True
    except ImportError:
        logger.debug("truststore not installed, using default certifi CA bundle")
        return False
    except Exception:
        logger.warning("truststore injection failed, falling back to certifi", exc_info=True)
        return False


def check_index_compatibility(config: SmartSearchConfig, db_path: str) -> Dict:
    """Check if the current config matches the index metadata.

    Compares embedding model/dimensions and chunk config (max_words,
    min_words, overlap_words). If chunk config changed, clears file
    hashes to force a full re-index on next ingest.

    Args:
        config: Current SmartSearchConfig.
        db_path: Path to SQLite database.

    Returns:
        Dict with 'compatible' (bool), 'mismatches' (dict),
        and 'chunk_config_changed' (bool).
    """
    metadata = IndexMetadata(db_path)
    metadata.initialize()

    current = {
        "embedding_model": config.embedding_model,
        "embedding_dimensions": str(config.embedding_dimensions),
        "chunk_max_words": str(config.chunk_max_words),
        "chunk_min_words": str(config.chunk_min_words),
        "chunk_overlap_words": str(config.chunk_overlap_words),
    }
    mismatches = metadata.check_mismatch(current)

    # Detect chunk-config-only changes (don't require table rebuild,
    # just re-indexing of files via hash cache clear)
    chunk_keys = {"chunk_max_words", "chunk_min_words", "chunk_overlap_words"}
    chunk_changed = bool(chunk_keys & set(mismatches.keys()))

    if mismatches:
        for key, (stored, current_val) in mismatches.items():
            logger.warning(
                "Index mismatch: %s changed from '%s' to '%s'. "
                "Re-indexing recommended.",
                key, stored, current_val,
            )

    # Update stored metadata to current values so the check only fires once
    for key, val in current.items():
        metadata.set(key, val)

    return {
        "compatible": len(mismatches) == 0,
        "mismatches": mismatches,
        "chunk_config_changed": chunk_changed,
    }


def backfill_mtime_if_needed(store: ChunkStore) -> Dict:
    """Backfill NULL file_mtime/file_size from disk for pre-migration rows.

    Files indexed before the mtime+size feature have NULL values, causing
    the pre-scan to treat them as needing work on every restart. This
    one-time migration reads stat info from disk and fills in the gaps.

    Args:
        store: Initialized ChunkStore instance.

    Returns:
        Dict with 'backfilled' (int) count of rows updated.
    """
    conn = store._sqlite_conn
    if conn is None:
        return {"backfilled": 0}

    rows = conn.execute(
        "SELECT source_path FROM indexed_files "
        "WHERE file_mtime IS NULL OR file_size IS NULL"
    ).fetchall()

    if not rows:
        return {"backfilled": 0}

    from pathlib import Path

    updated = 0
    for (source_path,) in rows:
        try:
            stat_info = Path(source_path).stat()
            conn.execute(
                "UPDATE indexed_files SET file_mtime = ?, file_size = ? "
                "WHERE source_path = ?",
                (stat_info.st_mtime, stat_info.st_size, source_path),
            )
            updated += 1
        except OSError:
            pass  # File deleted — reconcile_orphans will clean it up

    if updated:
        conn.commit()
        logger.info("Backfilled mtime+size for %d pre-migration files", updated)

    return {"backfilled": updated}


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


def migrate_fts_schema_if_needed(store: ChunkStore) -> Dict:
    """Rebuild FTS5 if source_path is UNINDEXED (pre-v0.9 schema).

    Checks the FTS5 table definition for 'source_path UNINDEXED'. If found,
    drops and recreates with source_path indexed, then backfills from LanceDB.

    Args:
        store: Initialized ChunkStore instance.

    Returns:
        Dict with 'migrated' (bool) and 'count' (int rows rebuilt).
    """
    conn = store._sqlite_conn
    table = store._table
    if conn is None or table is None:
        return {"migrated": False, "count": 0}

    # Check if source_path is UNINDEXED in the current FTS5 schema
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
        ).fetchone()
    except sqlite3.OperationalError:
        return {"migrated": False, "count": 0}

    if row is None:
        return {"migrated": False, "count": 0}

    schema_sql = row[0] or ""
    if "source_path UNINDEXED" not in schema_sql.lower():
        return {"migrated": False, "count": 0}

    logger.info("FTS5 schema migration: rebuilding with source_path indexed")
    conn.execute("DROP TABLE IF EXISTS chunks_fts")
    conn.execute(
        """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text,
            id UNINDEXED,
            source_path,
            source_type UNINDEXED,
            tokenize='porter unicode61'
        )"""
    )
    conn.commit()

    count = backfill_fts(conn, table)
    logger.info("FTS5 schema migration complete: %d chunks re-indexed", count)
    return {"migrated": True, "count": count}


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
    except (OSError, ValueError):
        logger.debug("Failed to count LanceDB rows during FTS backfill check", exc_info=True)
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
                source_path,
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
    except (ImportError, OSError, ValueError):
        logger.debug("LanceDB compaction failed during repair", exc_info=True)
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
