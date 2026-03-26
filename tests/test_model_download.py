# Tests for model_download.py: timeout wrapper, status/progress tracking, HF helpers.

"""Unit tests for model_download module.

Tests cover: status tracking, progress tracking, URL helpers, model ID parsing,
and download_with_timeout behavior (mocked).
"""

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import smart_search.model_download as md
from smart_search.model_download import (
    ModelDownloadTimeoutError,
    download_with_timeout,
    get_download_progress,
    get_download_status,
    get_hf_cache_path,
    get_hf_model_url,
    parse_model_id,
    set_download_progress,
    set_download_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level status and progress state before each test."""
    set_download_status("idle")
    set_download_progress(0.0)
    yield
    set_download_status("idle")
    set_download_progress(0.0)


# ---------------------------------------------------------------------------
# Status tracking (existing behaviour, regression guard)
# ---------------------------------------------------------------------------


def test_get_download_status_default_is_idle():
    """get_download_status returns 'idle' by default."""
    assert get_download_status() == "idle"


def test_set_download_status_updates_value():
    """set_download_status persists the new status."""
    set_download_status("downloading")
    assert get_download_status() == "downloading"


def test_set_download_status_is_thread_safe():
    """Concurrent status updates do not raise or corrupt state."""
    errors = []

    def _worker(status):
        try:
            set_download_status(status)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(s,)) for s in ["downloading", "cached", "idle"] * 10]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert get_download_status() in {"idle", "downloading", "cached"}


# ---------------------------------------------------------------------------
# Progress tracking (new behaviour)
# ---------------------------------------------------------------------------


def test_get_download_progress_returns_zero_initially():
    """get_download_progress returns 0.0 before any download starts."""
    assert get_download_progress() == 0.0


def test_set_download_progress_updates_value():
    """set_download_progress persists the new progress value."""
    set_download_progress(0.5)
    assert get_download_progress() == 0.5


def test_set_download_progress_to_one():
    """set_download_progress accepts 1.0 (completion marker)."""
    set_download_progress(1.0)
    assert get_download_progress() == 1.0


def test_set_download_progress_is_thread_safe():
    """Concurrent progress updates do not raise or corrupt state."""
    errors = []

    def _worker(value):
        try:
            set_download_progress(value)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(v,)) for v in [0.0, 0.25, 0.5, 0.75, 1.0] * 10]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert 0.0 <= get_download_progress() <= 1.0


# ---------------------------------------------------------------------------
# Progress reset at download start
# ---------------------------------------------------------------------------


def test_download_with_timeout_resets_progress_at_start():
    """download_with_timeout resets progress to 0.0 before downloading."""
    set_download_progress(0.9)  # simulate leftover from a previous run

    captured = []

    def _fake_snapshot(model_name, ignore_patterns=None):
        # Capture progress at the point snapshot_download is first called
        captured.append(get_download_progress())
        return "/tmp/fake-model"

    with patch("smart_search.model_download.snapshot_download", side_effect=_fake_snapshot):
        download_with_timeout("org/model", timeout_seconds=0)

    assert captured[0] == 0.0, "Progress must be reset before snapshot_download is called"


def test_download_with_timeout_sets_progress_to_one_on_success():
    """download_with_timeout sets progress to 1.0 after a successful download."""
    with patch("smart_search.model_download.snapshot_download", return_value="/tmp/fake-model"):
        download_with_timeout("org/model", timeout_seconds=0)

    assert get_download_progress() == 1.0


def test_download_with_timeout_sets_status_downloading_then_cached():
    """download_with_timeout transitions status: idle -> downloading -> cached."""
    statuses = []

    def _fake_snapshot(model_name, ignore_patterns=None):
        statuses.append(get_download_status())
        return "/tmp/fake-model"

    with patch("smart_search.model_download.snapshot_download", side_effect=_fake_snapshot):
        download_with_timeout("org/model", timeout_seconds=0)

    assert "downloading" in statuses
    assert get_download_status() == "cached"


def test_download_with_timeout_resets_status_on_failure():
    """download_with_timeout resets status to 'idle' when download fails."""
    with patch("smart_search.model_download.snapshot_download", side_effect=RuntimeError("network error")):
        with pytest.raises(RuntimeError):
            download_with_timeout("org/model", timeout_seconds=0)

    assert get_download_status() == "idle"


def test_download_with_timeout_sets_timeout_status_on_timeout():
    """download_with_timeout sets status to 'timeout' when timeout is exceeded."""
    import time
    from concurrent.futures import TimeoutError as FutureTimeoutError

    def _slow_snapshot(model_name, ignore_patterns=None):
        time.sleep(60)
        return "/tmp/fake-model"

    with patch("smart_search.model_download.snapshot_download", side_effect=_slow_snapshot):
        with pytest.raises(ModelDownloadTimeoutError):
            download_with_timeout("org/model", timeout_seconds=1)

    assert get_download_status() == "timeout"


# ---------------------------------------------------------------------------
# HF helpers
# ---------------------------------------------------------------------------


def test_get_hf_model_url_format():
    """get_hf_model_url returns a correctly formatted HuggingFace URL."""
    url = get_hf_model_url("Snowflake/snowflake-arctic-embed-m-v2.0")
    assert url == "https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0"


def test_get_hf_cache_path_uses_hf_home_env(monkeypatch):
    """get_hf_cache_path uses HF_HOME env var when set."""
    monkeypatch.setenv("HF_HOME", "/custom/hf")
    path = get_hf_cache_path()
    assert path == str(Path("/custom/hf") / "hub")


def test_get_hf_cache_path_default(monkeypatch):
    """get_hf_cache_path falls back to ~/.cache/huggingface/hub."""
    monkeypatch.delenv("HF_HOME", raising=False)
    path = get_hf_cache_path()
    assert path == str(Path.home() / ".cache" / "huggingface" / "hub")


# ---------------------------------------------------------------------------
# parse_model_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("org/model-name", "org/model-name"),
    ("https://huggingface.co/org/model-name", "org/model-name"),
    ("https://huggingface.co/org/model-name/", "org/model-name"),
    ("Snowflake/snowflake-arctic-embed-m-v2.0", "Snowflake/snowflake-arctic-embed-m-v2.0"),
])
def test_parse_model_id_valid(raw, expected):
    """parse_model_id extracts the model ID from valid inputs."""
    assert parse_model_id(raw) == expected


@pytest.mark.parametrize("bad_input", [
    "not-a-valid-id",
    "https://example.com/org/model",
    "",
    "org",
])
def test_parse_model_id_invalid_raises(bad_input):
    """parse_model_id raises ValueError for invalid inputs."""
    with pytest.raises(ValueError):
        parse_model_id(bad_input)


# ---------------------------------------------------------------------------
# ModelDownloadTimeoutError
# ---------------------------------------------------------------------------


def test_model_download_timeout_error_message():
    """ModelDownloadTimeoutError includes timeout and model in message."""
    err = ModelDownloadTimeoutError(
        model_name="org/m",
        timeout_seconds=30,
        download_url="https://huggingface.co/org/m",
        cache_path="/tmp/cache",
    )
    assert "30s" in str(err)
    assert "org/m" in str(err)


# ---------------------------------------------------------------------------
# list_cached_models
# ---------------------------------------------------------------------------


def test_list_cached_models_empty(tmp_path, monkeypatch):
    """list_cached_models returns [] when cache directory does not exist."""
    monkeypatch.setenv("HF_HOME", str(tmp_path / "nonexistent"))
    from smart_search.model_download import list_cached_models
    result = list_cached_models()
    assert result == []


def test_list_cached_models_finds_onnx(tmp_path, monkeypatch):
    """list_cached_models returns model IDs for dirs containing ONNX files."""
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    hub = tmp_path / "hub"
    snapshot = hub / "models--Snowflake--snowflake-arctic-embed-m-v2.0" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "model.onnx").write_text("fake onnx", encoding="utf-8")

    from smart_search.model_download import list_cached_models
    result = list_cached_models()
    assert result == ["Snowflake/snowflake-arctic-embed-m-v2.0"]


def test_list_cached_models_skips_non_onnx(tmp_path, monkeypatch):
    """list_cached_models excludes model dirs that contain no .onnx files."""
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    hub = tmp_path / "hub"
    snapshot = hub / "models--org--some-model" / "snapshots" / "def456"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")

    from smart_search.model_download import list_cached_models
    result = list_cached_models()
    assert result == []
