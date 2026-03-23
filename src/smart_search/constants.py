# Shared constants used across the smart-search codebase.

"""Centralizes magic numbers and configuration defaults to avoid
scattered hardcoded values in multiple modules."""

# Byte conversion factors
BYTES_PER_KB = 1024
BYTES_PER_MB = 1024 * 1024

# Network defaults
DEFAULT_HTTP_PORT = 9742
DEFAULT_HOST = "127.0.0.1"

# Search retrieval settings
OVERFETCH_MULTIPLIER = 5  # Fetch limit*N from each source before fusion

# Memory management
UPSERT_BATCH_SIZE = 200     # Max chunks per LanceDB insert batch
MAX_CHUNKS_PER_FILE = 5000  # Safety cap: truncate files producing more chunks

# Application metadata
APP_VERSION = "0.11.4"
