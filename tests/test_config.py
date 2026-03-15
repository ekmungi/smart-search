# Tests for SmartSearchConfig: defaults, env overrides, path resolution, singleton.

import os
from pathlib import Path

import pytest

from smart_search.config import SmartSearchConfig, get_config


class TestConfigDefaults:
    """Tests for default configuration values."""

    def test_default_embedding_model(self):
        """Default model is Snowflake/snowflake-arctic-embed-m-v2.0."""
        config = SmartSearchConfig()
        assert config.embedding_model == "Snowflake/snowflake-arctic-embed-m-v2.0"

    def test_default_dimensions(self):
        """Default embedding dimensions is 256 (Matryoshka truncation)."""
        config = SmartSearchConfig()
        assert config.embedding_dimensions == 256

    def test_supported_extensions_is_list(self):
        """supported_extensions is a list, not a string."""
        config = SmartSearchConfig()
        assert isinstance(config.supported_extensions, list)
        assert ".pdf" in config.supported_extensions
        assert ".docx" in config.supported_extensions

    def test_paths_are_resolved(self):
        """lancedb_path and sqlite_path are absolute after init."""
        config = SmartSearchConfig()
        assert Path(config.lancedb_path).is_absolute()
        assert Path(config.sqlite_path).is_absolute()

    def test_default_paths_use_data_dir(self):
        """Default paths point to OS-convention data directory."""
        config = SmartSearchConfig()
        assert "smart-search" in config.lancedb_path
        assert "vectors" in config.lancedb_path
        assert "smart-search" in config.sqlite_path
        assert "metadata.db" in config.sqlite_path


class TestConfigOverrides:
    """Tests for environment variable overrides."""

    def test_env_override(self, monkeypatch):
        """Environment variable overrides default value."""
        monkeypatch.setenv("SMART_SEARCH_EMBEDDING_DIMENSIONS", "256")
        config = SmartSearchConfig()
        assert config.embedding_dimensions == 256

    def test_custom_paths(self, tmp_path):
        """Custom paths are resolved to absolute."""
        config = SmartSearchConfig(
            lancedb_path=str(tmp_path / "vectors"),
            sqlite_path=str(tmp_path / "meta.db"),
        )
        assert Path(config.lancedb_path).is_absolute()
        assert Path(config.sqlite_path).is_absolute()


class TestGetConfig:
    """Tests for the get_config singleton function."""

    def test_get_config_returns_config(self):
        """get_config returns a SmartSearchConfig instance."""
        config = get_config()
        assert isinstance(config, SmartSearchConfig)


class TestConfigV02Fields:
    """Tests for v0.2 fields: watch_directories, exclude_patterns, chunking controls."""

    def test_default_supported_extensions_includes_md(self):
        """supported_extensions default includes .md for Markdown notes."""
        config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
        assert ".md" in config.supported_extensions

    def test_default_watch_directories_empty(self):
        """watch_directories defaults to an empty list."""
        config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
        assert config.watch_directories == []

    def test_default_exclude_patterns(self):
        """exclude_patterns defaults include .git and .obsidian."""
        config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
        assert ".git" in config.exclude_patterns
        assert ".obsidian" in config.exclude_patterns

    def test_default_block_chunking_enabled(self):
        """block_chunking_enabled defaults to True."""
        config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
        assert config.block_chunking_enabled is True

    def test_default_min_chunk_length(self):
        """min_chunk_length defaults to 50 characters."""
        config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
        assert config.min_chunk_length == 50

    def test_default_watcher_debounce(self):
        """watcher_debounce_seconds defaults to 2.0."""
        config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
        assert config.watcher_debounce_seconds == 2.0

    def test_watch_directories_resolved_to_absolute(self):
        """watch_directories entries are resolved to absolute paths at init."""
        config = SmartSearchConfig(
            lancedb_path="./x", sqlite_path="./y",
            watch_directories=["./my_vault"]
        )
        for d in config.watch_directories:
            assert Path(d).is_absolute()
