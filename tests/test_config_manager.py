"""Tests for persistent config manager."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from smart_search.config_manager import ConfigManager


@pytest.fixture
def data_dir(tmp_path):
    """Return a temporary data directory."""
    return tmp_path


@pytest.fixture
def manager(data_dir):
    """Create a ConfigManager with a temporary data dir."""
    return ConfigManager(data_dir)


def test_load_returns_defaults_when_no_file(manager):
    """Loading with no config.json returns default config."""
    config = manager.load()
    assert config["watch_directories"] == []
    assert "embedding_model" in config


def test_save_creates_config_file(manager, data_dir):
    """save() writes config.json to data directory."""
    manager.save({"watch_directories": ["/test/path"]})
    config_path = data_dir / "config.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text())
    assert data["watch_directories"] == ["/test/path"]


def test_load_reads_saved_config(manager):
    """load() returns previously saved config."""
    manager.save({"watch_directories": ["/a", "/b"]})
    config = manager.load()
    assert config["watch_directories"] == ["/a", "/b"]


def test_add_watch_directory(manager):
    """add_watch_dir adds a directory and persists it."""
    manager.add_watch_dir("/new/dir")
    config = manager.load()
    assert len(config["watch_directories"]) == 1


def test_add_watch_directory_no_duplicates(manager):
    """Adding the same directory twice does not duplicate it."""
    manager.add_watch_dir("/same/dir")
    manager.add_watch_dir("/same/dir")
    config = manager.load()
    count = len(config["watch_directories"])
    assert count == 1


def test_remove_watch_directory(manager):
    """remove_watch_dir removes a directory and persists it."""
    manager.add_watch_dir("/dir/a")
    manager.add_watch_dir("/dir/b")
    # Remove first dir
    dirs_before = manager.list_watch_dirs()
    manager.remove_watch_dir(dirs_before[0])
    dirs_after = manager.list_watch_dirs()
    assert len(dirs_after) == 1


def test_remove_nonexistent_directory_is_noop(manager):
    """Removing a directory that doesn't exist does not raise."""
    manager.remove_watch_dir("/does/not/exist")


def test_list_watch_dirs(manager):
    """list_watch_dirs returns current watch directories."""
    manager.add_watch_dir("/x")
    manager.add_watch_dir("/y")
    dirs = manager.list_watch_dirs()
    assert len(dirs) == 2


def test_config_path_property(manager, data_dir):
    """config_path points to config.json in data dir."""
    assert manager.config_path == data_dir / "config.json"


def test_env_vars_override_config(manager):
    """Environment variables take precedence over config.json."""
    manager.save({"embedding_dimensions": "256"})
    with patch.dict("os.environ", {"SMART_SEARCH_EMBEDDING_DIMENSIONS": "768"}):
        config = manager.load()
        assert config["embedding_dimensions"] == "768"
