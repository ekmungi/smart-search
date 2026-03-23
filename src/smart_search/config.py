# Configuration for smart-search: all settings with env var overrides.

from pathlib import Path
from typing import List, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from smart_search.data_dir import get_data_dir


class SmartSearchConfig(BaseSettings):
    """Configuration for the smart-search MCP server.

    All settings can be overridden via environment variables prefixed
    with SMART_SEARCH_ (e.g., SMART_SEARCH_EMBEDDING_DIMENSIONS=256).
    Paths are resolved to absolute at instantiation.
    """

    model_config = SettingsConfigDict(env_prefix="SMART_SEARCH_")

    # Embedding settings
    embedding_model: str = "Snowflake/snowflake-arctic-embed-m-v2.0"
    embedding_dimensions: int = 256
    embedding_backend: str = "auto"
    embedder_idle_timeout: float = 60.0

    # Chunking settings -- word-based limits for size-enforced splitting
    chunk_max_words: int = 200   # Max words per chunk (Chroma Research: 200 optimal)
    chunk_min_words: int = 50    # Merge undersized chunks below this threshold
    chunk_overlap_words: int = 40  # Overlap between split sub-chunks for context

    # Storage paths -- sentinel defaults replaced by data_dir in validator
    lancedb_path: str = ""
    sqlite_path: str = ""
    lancedb_table_name: str = "chunks"

    # Document settings -- expanded in v0.3.0 with MarkItDown, v0.11.5 with full format list
    supported_extensions: List[str] = [
        ".md", ".txt",                          # Text
        ".pdf", ".docx", ".epub",               # Documents
        ".xlsx", ".xls", ".csv",                # Spreadsheets
        ".pptx",                                # Presentations
        ".html", ".htm",                        # Web
        ".json", ".jsonl",                      # Data
        ".msg",                                 # Email
        ".ipynb",                               # Notebooks
    ]

    # Watch directories for file watcher (resolved to absolute in validator)
    watch_directories: List[str] = []

    # File exclusion patterns matched against path components
    exclude_patterns: List[str] = [
        ".git", ".obsidian", ".trash", "node_modules", ".smart-search"
    ]

    # Markdown block-level chunking controls (v0.2)
    block_chunking_enabled: bool = True
    min_chunk_length: int = 50  # Minimum characters; shorter chunks are discarded

    # File watcher debounce window in seconds to avoid redundant re-indexing
    watcher_debounce_seconds: float = 2.0

    # Search settings
    search_default_limit: int = 10
    search_default_mode: str = "hybrid"
    relevance_threshold: float = 0.30
    rrf_k: int = 60  # RRF constant; lower values (20-30) boost top-ranked results

    # Cross-encoder reranking settings (Phase 2: search quality improvements)
    reranking_enabled: bool = True
    reranker_model: str = "cross-encoder/ms-marco-TinyBERT-L-2-v2"
    reranker_idle_timeout: float = 60.0
    rerank_top_n: int = 20  # How many fusion results to rerank

    # MMR diversity settings (Phase 3: eliminate redundant chunks)
    mmr_enabled: bool = True
    mmr_lambda: float = 0.8  # 0-1: higher = more relevance, lower = more diversity

    # GPU acceleration settings
    gpu_device_id: int = 0               # CUDA/DirectML device index
    gpu_mem_limit_mb: int = 2048         # Max VRAM allocation in MB (CUDA only)

    # Global shortcut for Quick Search overlay
    shortcut_key: str = "Ctrl+Space"

    # nomic-embed task prefixes
    nomic_document_prefix: str = "search_document: "
    nomic_query_prefix: str = "search_query: "

    @model_validator(mode="after")
    def resolve_paths(self) -> "SmartSearchConfig":
        """Resolve storage paths and watch_directories to absolute paths.

        Empty lancedb_path/sqlite_path are replaced with OS-convention
        data directory defaults. Runs after all field assignments so
        relative paths provided by callers or env vars are normalised.
        """
        data_dir = get_data_dir()

        # Replace empty sentinel defaults with data_dir-based paths
        lancedb = self.lancedb_path if self.lancedb_path else str(data_dir / "vectors")
        sqlite = self.sqlite_path if self.sqlite_path else str(data_dir / "metadata.db")

        object.__setattr__(
            self, "lancedb_path", str(Path(lancedb).resolve())
        )
        object.__setattr__(
            self, "sqlite_path", str(Path(sqlite).resolve())
        )
        object.__setattr__(
            self,
            "watch_directories",
            [str(Path(d).resolve()) for d in self.watch_directories],
        )
        return self


# Module-level singleton
_config_instance: Optional[SmartSearchConfig] = None


def get_config() -> SmartSearchConfig:
    """Return a singleton SmartSearchConfig instance.

    Returns:
        The shared configuration instance, created on first call.
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = SmartSearchConfig()
    return _config_instance
