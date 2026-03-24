# Tests for embedding model download timeout and model_download module.

"""Tests for embedding model download timeout."""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from smart_search.model_download import (
    ModelDownloadTimeoutError,
    get_download_status,
    set_download_status,
    get_hf_model_url,
    get_hf_cache_path,
    download_with_timeout,
)


@pytest.fixture(autouse=True)
def _reset_download_status():
    """Reset class-level download status between tests to avoid state leaks."""
    set_download_status("idle")
    yield
    set_download_status("idle")


def test_model_download_timeout_error_exists():
    """ModelDownloadTimeoutError should be importable."""
    assert issubclass(ModelDownloadTimeoutError, Exception)


def test_model_download_timeout_error_has_model_info():
    """Error should carry model_name, timeout, download URL, and cache path."""
    err = ModelDownloadTimeoutError(
        model_name="test/model",
        timeout_seconds=900,
        download_url="https://huggingface.co/test/model",
        cache_path="/home/user/.cache/huggingface/hub",
    )
    assert err.model_name == "test/model"
    assert err.timeout_seconds == 900
    assert "test/model" in str(err)
    assert err.download_url == "https://huggingface.co/test/model"
    assert err.cache_path == "/home/user/.cache/huggingface/hub"


def test_download_with_timeout_raises_on_timeout():
    """download_with_timeout should raise ModelDownloadTimeoutError when download hangs."""
    def slow_download(*args, **kwargs):
        time.sleep(10)
        return "/fake/path"

    with patch("smart_search.model_download.snapshot_download", slow_download):
        with pytest.raises(ModelDownloadTimeoutError) as exc_info:
            download_with_timeout("test/model", timeout_seconds=1)
        assert exc_info.value.timeout_seconds == 1
        assert get_download_status() == "timeout"


def test_download_with_timeout_succeeds_within_timeout():
    """download_with_timeout should return path when download completes in time."""
    with patch("smart_search.model_download.snapshot_download", return_value="/fake/path"):
        result = download_with_timeout("test/model", timeout_seconds=30)
        # Use as_posix() for cross-platform comparison (Windows uses backslashes)
        assert result.as_posix() == "/fake/path"
        assert get_download_status() == "cached"


def test_download_with_timeout_no_timeout():
    """When timeout_seconds=0, should download without timeout."""
    with patch("smart_search.model_download.snapshot_download", return_value="/fake/path"):
        result = download_with_timeout("test/model", timeout_seconds=0)
        # Use as_posix() for cross-platform comparison (Windows uses backslashes)
        assert result.as_posix() == "/fake/path"


def test_download_status_default_is_idle():
    """Default download status should be idle."""
    assert get_download_status() == "idle"


def test_get_hf_model_url():
    """get_hf_model_url should return correct HuggingFace URL."""
    url = get_hf_model_url("Snowflake/snowflake-arctic-embed-m-v2.0")
    assert url == "https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0"


def test_get_hf_cache_path_default():
    """get_hf_cache_path should return default HF cache directory."""
    path = get_hf_cache_path()
    assert "huggingface" in str(path).lower() or ".cache" in str(path).lower()


def test_get_hf_cache_path_custom(monkeypatch):
    """get_hf_cache_path should respect HF_HOME env var."""
    monkeypatch.setenv("HF_HOME", "/custom/hf")
    path = get_hf_cache_path()
    # Normalize to forward slashes for cross-platform comparison
    assert "/custom/hf" in path.replace("\\", "/")
