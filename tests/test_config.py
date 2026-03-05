# Tests for SmartSearchConfig: defaults, env overrides, path resolution, singleton.

import os
from pathlib import Path

import pytest

from smart_search.config import SmartSearchConfig, get_config


class TestConfigDefaults:
    """Tests for default configuration values."""

    def test_default_embedding_model(self):
        """Default model is nomic-ai/nomic-embed-text-v1.5."""
        config = SmartSearchConfig()
        assert config.embedding_model == "nomic-ai/nomic-embed-text-v1.5"

    def test_default_dimensions(self):
        """Default embedding dimensions is 768."""
        config = SmartSearchConfig()
        assert config.embedding_dimensions == 768

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
