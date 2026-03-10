"""Tests for OS-convention data directory resolution."""

import os
from pathlib import Path
from unittest.mock import patch

from smart_search.data_dir import get_data_dir


def test_returns_localappdata_on_windows():
    """On Windows, uses %LOCALAPPDATA%/smart-search."""
    with patch("smart_search.data_dir.platform.system", return_value="Windows"):
        with patch.dict(os.environ, {"LOCALAPPDATA": "C:/Users/test/AppData/Local", "SMART_SEARCH_DATA_DIR": ""}, clear=False):
            result = get_data_dir()
            assert result.as_posix().endswith("smart-search")
            assert "AppData/Local" in result.as_posix()


def test_returns_xdg_on_linux():
    """On Linux/Mac, uses ~/.local/share/smart-search."""
    with patch("smart_search.data_dir.platform.system", return_value="Linux"):
        with patch.dict(os.environ, {"SMART_SEARCH_DATA_DIR": ""}, clear=False):
            with patch("smart_search.data_dir.Path.home", return_value=Path("/home/testuser")):
                result = get_data_dir()
                assert result.as_posix() == "/home/testuser/.local/share/smart-search"


def test_env_override_takes_precedence():
    """SMART_SEARCH_DATA_DIR env var overrides OS convention."""
    with patch.dict(os.environ, {"SMART_SEARCH_DATA_DIR": "/custom/path"}, clear=False):
        result = get_data_dir()
        assert result.as_posix() == "/custom/path"


def test_returns_path_object():
    """Return type is always a Path."""
    result = get_data_dir()
    assert isinstance(result, Path)
