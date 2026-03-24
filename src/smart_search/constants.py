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

# Reranking settings
DEFAULT_RERANK_TOP_N = 20  # Number of fusion results to pass through cross-encoder

# Keyword-only extensions: indexed in FTS5 for keyword search but skipped
# from the embedding pipeline. Structured data (spreadsheets, data files)
# doesn't benefit from semantic search but should be findable by content.
KEYWORD_ONLY_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".jsonl"}

# Model download timeout (seconds). If download takes longer than this,
# abort and offer manual download instructions to the user.
DEFAULT_MODEL_DOWNLOAD_TIMEOUT = 900  # 15 minutes

# Application metadata
APP_VERSION = "0.13.1"
