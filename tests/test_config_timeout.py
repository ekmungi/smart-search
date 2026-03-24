"""Tests for model_download_timeout configuration key."""

from smart_search.config import SmartSearchConfig
from smart_search.constants import DEFAULT_MODEL_DOWNLOAD_TIMEOUT


def test_default_timeout_is_900_seconds():
    """Default model download timeout should be 15 minutes (900s)."""
    config = SmartSearchConfig()
    assert config.model_download_timeout == 900


def test_constant_matches_default():
    """Constant and config default should agree."""
    assert DEFAULT_MODEL_DOWNLOAD_TIMEOUT == 900


def test_timeout_overridable_via_env(monkeypatch):
    """model_download_timeout should be overridable via env var."""
    monkeypatch.setenv("SMART_SEARCH_MODEL_DOWNLOAD_TIMEOUT", "300")
    config = SmartSearchConfig()
    assert config.model_download_timeout == 300


def test_config_manager_includes_timeout(tmp_path):
    """ConfigManager defaults should include model_download_timeout."""
    from smart_search.config_manager import ConfigManager
    mgr = ConfigManager(tmp_path)
    loaded = mgr.load()
    assert "model_download_timeout" in loaded
    assert loaded["model_download_timeout"] == 900
