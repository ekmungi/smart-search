# Configuration for smart-search: all settings with env var overrides.

from pathlib import Path
from typing import List, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SmartSearchConfig(BaseSettings):
    """Configuration for the smart-search MCP server.

    All settings can be overridden via environment variables prefixed
    with SMART_SEARCH_ (e.g., SMART_SEARCH_EMBEDDING_DIMENSIONS=256).
    Paths are resolved to absolute at instantiation.
    """

    model_config = SettingsConfigDict(env_prefix="SMART_SEARCH_")

    # Embedding settings
    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"
    embedding_dimensions: int = 768
    embedding_backend: str = "onnx"

    # Chunking settings
    chunk_max_tokens: int = 512

    # Storage paths (resolved to absolute in validator)
    lancedb_path: str = "./data/vectors"
    sqlite_path: str = "./data/metadata.db"
    lancedb_table_name: str = "chunks"

    # Document settings -- .md added in v0.2 for Markdown note indexing
    supported_extensions: List[str] = [".pdf", ".docx", ".md"]

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

    # nomic-embed task prefixes
    nomic_document_prefix: str = "search_document: "
    nomic_query_prefix: str = "search_query: "

    @model_validator(mode="after")
    def resolve_paths(self) -> "SmartSearchConfig":
        """Resolve storage paths and watch_directories to absolute paths.

        Runs after all field assignments so relative paths provided by
        callers or env vars are normalised before any code reads them.
        """
        object.__setattr__(
            self, "lancedb_path", str(Path(self.lancedb_path).resolve())
        )
        object.__setattr__(
            self, "sqlite_path", str(Path(self.sqlite_path).resolve())
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
