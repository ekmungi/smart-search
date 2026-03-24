# Tests for model import (copy local files to HF cache).

"""Tests for model_importer: copy_model_to_cache and _detect_embedding_dims."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from smart_search.model_importer import copy_model_to_cache, _detect_embedding_dims


def test_copy_model_to_cache(tmp_path):
    """copy_model_to_cache should copy model files to HF cache structure."""
    source = tmp_path / "source_model"
    source.mkdir()
    (source / "onnx").mkdir()
    (source / "onnx" / "model_quantized.onnx").write_bytes(b"fake_model")
    (source / "tokenizer.json").write_text('{"test": true}')
    (source / "config.json").write_text('{"model_type": "bert"}')

    cache_dir = tmp_path / "hf_cache"
    cache_dir.mkdir()

    with patch.dict(os.environ, {"HF_HOME": str(cache_dir)}):
        result = copy_model_to_cache(
            str(source), "Snowflake/snowflake-arctic-embed-m-v2.0",
        )

    assert result["success"] is True
    assert result["files_copied"] >= 3
    assert "native_dims" in result
    assert "cache_path" in result

    # Verify refs/main was created
    safe_name = "Snowflake--snowflake-arctic-embed-m-v2.0"
    refs_main = cache_dir / "hub" / f"models--{safe_name}" / "refs" / "main"
    assert refs_main.exists()
    assert refs_main.read_text() == "imported"


def test_copy_model_validates_onnx_present(tmp_path):
    """Should fail if no ONNX file found in source directory."""
    source = tmp_path / "empty_model"
    source.mkdir()
    (source / "tokenizer.json").write_text("{}")

    result = copy_model_to_cache(str(source), "test/model")
    assert result["success"] is False
    assert "onnx" in result["error"].lower()


def test_copy_model_validates_source_exists():
    """Should fail if source directory doesn't exist."""
    result = copy_model_to_cache("/nonexistent/path", "test/model")
    assert result["success"] is False


def test_detect_embedding_dims_returns_none_for_missing_onnx(tmp_path):
    """Should return None when no ONNX file found."""
    result = _detect_embedding_dims(tmp_path)
    assert result is None


def test_detect_embedding_dims_returns_none_for_invalid_onnx(tmp_path):
    """Should return None for invalid ONNX file."""
    (tmp_path / "onnx").mkdir()
    (tmp_path / "onnx" / "model.onnx").write_bytes(b"not a real model")
    result = _detect_embedding_dims(tmp_path)
    assert result is None
