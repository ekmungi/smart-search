# Tests for model_importer.py -- manual model import and SHA snapshot naming.

"""Tests for copy_model_to_cache: verifies that imported model snapshot
directories use a 40-char hex SHA (not the literal string 'imported'),
and that refs/main contains the same SHA."""

from pathlib import Path


def test_import_creates_sha_snapshot(tmp_path, monkeypatch):
    """Imported model snapshot dir should be a 40-char hex SHA, not 'imported'."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "onnx").mkdir()
    (source / "onnx" / "model_quantized.onnx").write_bytes(b"fake")
    (source / "tokenizer.json").write_text("{}")

    cache = tmp_path / "cache"
    monkeypatch.setenv("HF_HOME", str(cache))

    from smart_search.model_importer import copy_model_to_cache
    result = copy_model_to_cache(str(source), "test/model")

    assert result["success"]
    # Snapshot dir should be a 40-char hex, not "imported"
    snapshot_path = Path(result["cache_path"])
    assert len(snapshot_path.name) == 40
    assert all(c in "0123456789abcdef" for c in snapshot_path.name)

    # refs/main should contain the same SHA
    refs_main = snapshot_path.parent.parent / "refs" / "main"
    assert refs_main.read_text() == snapshot_path.name


def test_import_fails_when_source_missing(tmp_path, monkeypatch):
    """Returns error dict when source path does not exist."""
    monkeypatch.setenv("HF_HOME", str(tmp_path / "cache"))

    from smart_search.model_importer import copy_model_to_cache
    result = copy_model_to_cache(str(tmp_path / "nonexistent"), "test/model")

    assert not result["success"]
    assert "error" in result


def test_import_fails_when_no_onnx(tmp_path, monkeypatch):
    """Returns error dict when source directory contains no ONNX file."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "tokenizer.json").write_text("{}")
    monkeypatch.setenv("HF_HOME", str(tmp_path / "cache"))

    from smart_search.model_importer import copy_model_to_cache
    result = copy_model_to_cache(str(source), "test/model")

    assert not result["success"]
    assert "error" in result


def test_import_copies_all_files(tmp_path, monkeypatch):
    """All files in source tree are copied to the snapshot directory."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "onnx").mkdir()
    (source / "onnx" / "model_quantized.onnx").write_bytes(b"fake")
    (source / "tokenizer.json").write_text("{}")
    (source / "config.json").write_text("{}")

    monkeypatch.setenv("HF_HOME", str(tmp_path / "cache"))

    from smart_search.model_importer import copy_model_to_cache
    result = copy_model_to_cache(str(source), "test/model")

    assert result["success"]
    assert result["files_copied"] == 3


def test_sha_is_deterministic(tmp_path, monkeypatch):
    """Same model_name always produces the same SHA snapshot directory name."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "onnx").mkdir()
    (source / "onnx" / "model_quantized.onnx").write_bytes(b"fake")

    monkeypatch.setenv("HF_HOME", str(tmp_path / "cache"))

    from smart_search.model_importer import copy_model_to_cache
    result1 = copy_model_to_cache(str(source), "vendor/my-model")

    import hashlib
    expected_sha = hashlib.sha1("imported-vendor/my-model".encode("utf-8")).hexdigest()
    assert Path(result1["cache_path"]).name == expected_sha
