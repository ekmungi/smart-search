# Shared constants used across the smart-search codebase.

"""Centralizes magic numbers and configuration defaults to avoid
scattered hardcoded values in multiple modules."""

# Byte conversion factors
BYTES_PER_KB = 1024
BYTES_PER_MB = 1024 * 1024

# Network defaults
DEFAULT_HTTP_PORT = 9742
DEFAULT_HOST = "127.0.0.1"

# Browser origins allowed to call the API: the Tauri webview on macOS/Linux
# (tauri://) and Windows (http/https://tauri.localhost), plus the Vite dev server.
ALLOWED_ORIGINS = (
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:5173",
)
# Loopback bind addresses; also the only Host header values accepted when
# bound to one (blocks DNS rebinding).
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
# Cloud embedding settings read only from SMART_SEARCH_ env vars, never from
# config.json or the HTTP API, so no web page can redirect the API key.
ENV_ONLY_CONFIG_KEYS = frozenset({
    "embedding_api_key",
    "embedding_api_base_url",
    "embedding_cloud_model",
})

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
APP_VERSION = "0.15.1"

# Cloud embedding model dimensions (OpenAI-compatible model ids via OpenRouter).
# Used to size the LanceDB vector column before the first embedding call.
CLOUD_MODEL_DIMS = {
    "openai/text-embedding-3-small": 1536,
    "openai/text-embedding-3-large": 3072,
    "cohere/embed-english-v3.0": 1024,
    "voyageai/voyage-3": 1024,
    "google/gemini-embedding-001": 3072,
}

# Approximate USD price per 1M input tokens, for pre-indexing cost estimates.
CLOUD_MODEL_PRICE_PER_1M = {
    "openai/text-embedding-3-small": 0.02,
    "openai/text-embedding-3-large": 0.13,
    "cohere/embed-english-v3.0": 0.10,
    "voyageai/voyage-3": 0.06,
    "google/gemini-embedding-001": 0.20,
}
