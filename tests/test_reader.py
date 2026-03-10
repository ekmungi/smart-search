# tests/test_reader.py
# Tests for the read_note file reader with path safety validation.

from pathlib import Path
from unittest.mock import patch

import pytest

from smart_search.reader import read_note, resolve_note_path


class TestResolveNotePath:
    """Tests for path resolution against watch directories."""

    def test_resolves_relative_path_against_watch_dir(self, tmp_path):
        """Relative path resolves to absolute within watch directory."""
        note = tmp_path / "notes" / "test.md"
        note.parent.mkdir(parents=True)
        note.write_text("hello")
        result = resolve_note_path("notes/test.md", [str(tmp_path)])
        assert result == note

    def test_rejects_path_traversal(self, tmp_path):
        """Paths with .. are rejected."""
        with pytest.raises(ValueError, match="traversal"):
            resolve_note_path("../etc/passwd", [str(tmp_path)])

    def test_rejects_absolute_path(self, tmp_path):
        """Absolute paths are rejected."""
        with pytest.raises(ValueError, match="Relative"):
            resolve_note_path("/etc/passwd", [str(tmp_path)])

    def test_rejects_path_exceeding_max_length(self, tmp_path):
        """Paths longer than 500 chars are rejected."""
        long_path = "a" * 501 + ".md"
        with pytest.raises(ValueError, match="500"):
            resolve_note_path(long_path, [str(tmp_path)])

    def test_returns_none_when_file_not_found(self, tmp_path):
        """Returns None when file does not exist in any watch directory."""
        result = resolve_note_path("nonexistent.md", [str(tmp_path)])
        assert result is None

    def test_searches_multiple_watch_directories(self, tmp_path):
        """Finds file in second watch directory when not in first."""
        dir_a = tmp_path / "vault_a"
        dir_b = tmp_path / "vault_b"
        dir_a.mkdir()
        dir_b.mkdir()
        note = dir_b / "found.md"
        note.write_text("content")
        result = resolve_note_path("found.md", [str(dir_a), str(dir_b)])
        assert result == note


class TestReadNote:
    """Tests for the read_note function."""

    def test_reads_note_content(self, tmp_path):
        """Returns full content of a small note."""
        note = tmp_path / "test.md"
        note.write_text("# Hello\n\nWorld")
        result = read_note("test.md", [str(tmp_path)])
        assert "# Hello" in result
        assert "World" in result

    def test_truncates_large_files(self, tmp_path):
        """Files exceeding 50KB are truncated with a notice."""
        note = tmp_path / "large.md"
        note.write_text("x" * 60_000)
        result = read_note("large.md", [str(tmp_path)])
        assert len(result) <= 52_000  # 50KB + truncation notice
        assert "truncated" in result.lower()

    def test_returns_error_for_missing_file(self, tmp_path):
        """Returns error message when file not found."""
        result = read_note("missing.md", [str(tmp_path)])
        assert "not found" in result.lower()

    def test_returns_error_for_traversal(self, tmp_path):
        """Returns error message for path traversal attempt."""
        result = read_note("../../etc/passwd", [str(tmp_path)])
        assert "error" in result.lower() or "invalid" in result.lower()
