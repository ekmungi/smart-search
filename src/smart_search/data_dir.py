"""Resolve the smart-search data directory using OS conventions."""

import os
import platform
from pathlib import Path


def get_data_dir() -> Path:
    """Return the data directory path, resolved per OS convention.

    Priority:
    1. SMART_SEARCH_DATA_DIR env var (explicit override)
    2. OS convention:
       - Windows: %LOCALAPPDATA%/smart-search
       - Linux/Mac: ~/.local/share/smart-search

    Returns:
        Absolute Path to the data directory.
    """
    env_override = os.environ.get("SMART_SEARCH_DATA_DIR")
    if env_override:
        return Path(env_override)

    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA", "")
        if base:
            return Path(base) / "smart-search"
        return Path.home() / "AppData" / "Local" / "smart-search"

    return Path.home() / ".local" / "share" / "smart-search"
