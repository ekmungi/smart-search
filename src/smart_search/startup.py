# Startup checks: index compatibility and orphan reconciliation.

"""Startup checks run when the HTTP server starts.

Validates that the current config matches the stored index metadata
and removes orphan chunks for files deleted while the app was offline."""

import logging
from typing import Dict

from smart_search.config import SmartSearchConfig
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
