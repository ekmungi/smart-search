# Tests for shortcut_key configuration in SmartSearchConfig and ConfigManager.

import json
import os
from pathlib import Path

import pytest

from smart_search.config import SmartSearchConfig
from smart_search.config_manager import ConfigManager, _DEFAULTS, _ENV_OVERRIDABLE


class TestShortcutConfigDefaults:
    """Verify shortcut_key has the correct default in SmartSearchConfig."""

    def test_default_shortcut_key(self):
        """SmartSearchConfig should default shortcut_key to Ctrl+Space."""
        config = SmartSearchConfig()
        assert config.shortcut_key == "Ctrl+Space"

    def test_shortcut_key_override_via_env(self, monkeypatch):
        """shortcut_key should be overridable via SMART_SEARCH_SHORTCUT_KEY."""
        monkeypatch.setenv("SMART_SEARCH_SHORTCUT_KEY", "Ctrl+Shift+K")
        config = SmartSearchConfig()
        assert config.shortcut_key == "Ctrl+Shift+K"

    def test_shortcut_key_custom_value(self):
        """SmartSearchConfig should accept a custom shortcut_key."""
        config = SmartSearchConfig(shortcut_key="Alt+Space")
        assert config.shortcut_key == "Alt+Space"


class TestShortcutConfigManager:
    """Verify shortcut_key in ConfigManager defaults and env override."""

    def test_shortcut_key_in_defaults(self):
        """_DEFAULTS should contain shortcut_key with value Ctrl+Space."""
        assert "shortcut_key" in _DEFAULTS
        assert _DEFAULTS["shortcut_key"] == "Ctrl+Space"

    def test_shortcut_key_is_env_overridable(self):
        """shortcut_key should be in the _ENV_OVERRIDABLE list."""
        assert "shortcut_key" in _ENV_OVERRIDABLE

    def test_load_returns_default_shortcut(self, tmp_path):
        """ConfigManager.load() should return default shortcut_key when no config file."""
        mgr = ConfigManager(tmp_path)
        config = mgr.load()
        assert config["shortcut_key"] == "Ctrl+Space"

    def test_load_returns_saved_shortcut(self, tmp_path):
        """ConfigManager.load() should return the shortcut_key from config.json."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"shortcut_key": "Ctrl+Shift+S"}))
        mgr = ConfigManager(tmp_path)
        config = mgr.load()
        assert config["shortcut_key"] == "Ctrl+Shift+S"

    def test_save_and_load_shortcut(self, tmp_path):
        """Round-trip: save shortcut_key then load it back."""
        mgr = ConfigManager(tmp_path)
        mgr.save({"shortcut_key": "Alt+K"})
        config = mgr.load()
        assert config["shortcut_key"] == "Alt+K"

    def test_env_override_shortcut(self, tmp_path, monkeypatch):
        """Env var SMART_SEARCH_SHORTCUT_KEY should override config.json value."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"shortcut_key": "Ctrl+Shift+S"}))
        monkeypatch.setenv("SMART_SEARCH_SHORTCUT_KEY", "Ctrl+Alt+P")
        mgr = ConfigManager(tmp_path)
        config = mgr.load()
        assert config["shortcut_key"] == "Ctrl+Alt+P"
