"""Persistent configuration manager with atomic JSON writes."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List


# Default config values
_DEFAULTS: Dict[str, Any] = {
    "watch_directories": [],
    "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
    "embedding_dimensions": "256",
    "embedding_backend": "onnx",
    "exclude_patterns": [".git", ".obsidian", ".trash", "node_modules", ".smart-search"],
}

# Keys that can be overridden by SMART_SEARCH_ env vars
_ENV_OVERRIDABLE = [
    "embedding_model",
    "embedding_dimensions",
    "embedding_backend",
    "watch_directories",
]


class ConfigManager:
    """Manages persistent config.json with runtime updates.

    Reads/writes config.json in the data directory. Merges with
    environment variables (env vars take precedence). Supports
    runtime add/remove of watch directories.
    """

    def __init__(self, data_dir: Path) -> None:
        """Initialize with the data directory path.

        Args:
            data_dir: Path to the smart-search data directory.
        """
        self._data_dir = Path(data_dir)
        self._config_path = self._data_dir / "config.json"

    @property
    def config_path(self) -> Path:
        """Path to the config.json file."""
        return self._config_path

    def load(self) -> Dict[str, Any]:
        """Load config from file, merge with env vars and defaults.

        Priority: env vars > config.json > defaults.

        Returns:
            Merged configuration dictionary.
        """
        config = dict(_DEFAULTS)

        # Layer 2: config.json overrides defaults
        if self._config_path.exists():
            try:
                file_config = json.loads(
                    self._config_path.read_text(encoding="utf-8")
                )
                config.update(file_config)
            except (json.JSONDecodeError, OSError):
                pass

        # Layer 3: env vars override everything
        for key in _ENV_OVERRIDABLE:
            env_key = f"SMART_SEARCH_{key.upper()}"
            env_val = os.environ.get(env_key)
            if env_val is not None:
                config[key] = env_val

        return config

    def save(self, config: Dict[str, Any]) -> None:
        """Save config to JSON file atomically.

        Writes to a temporary file then renames, preventing corruption
        from partial writes or crashes.

        Args:
            config: Configuration dictionary to persist.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp, then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._data_dir), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            # On Windows, remove target before rename
            if self._config_path.exists():
                self._config_path.unlink()
            Path(tmp_path).rename(self._config_path)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def add_watch_dir(self, path: str) -> None:
        """Add a watch directory and persist to config.

        No-op if the directory is already in the list.

        Args:
            path: Directory path to add.
        """
        config = self.load()
        dirs = list(config.get("watch_directories", []))
        normalized = str(Path(path).resolve().as_posix())
        if normalized not in dirs:
            dirs.append(normalized)
        config["watch_directories"] = dirs
        self.save(config)

    def remove_watch_dir(self, path: str) -> None:
        """Remove a watch directory and persist to config.

        No-op if the directory is not in the list.

        Args:
            path: Directory path to remove.
        """
        config = self.load()
        dirs = list(config.get("watch_directories", []))
        normalized = str(Path(path).resolve().as_posix())
        dirs = [d for d in dirs if d != normalized]
        config["watch_directories"] = dirs
        self.save(config)

    def list_watch_dirs(self) -> List[str]:
        """Return the current list of watch directories.

        Returns:
            List of directory paths.
        """
        config = self.load()
        return list(config.get("watch_directories", []))
