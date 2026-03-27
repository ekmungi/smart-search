# Tests for markitdown_parser: MarkItDown document-to-Markdown conversion.

from unittest.mock import MagicMock, patch

import pytest

from smart_search.markitdown_parser import convert_to_markdown, reset_converter


class TestConvertToMarkdown:
    """Tests for the convert_to_markdown function."""

    def test_returns_markdown_string(self, tmp_path):
        """Successful conversion returns a non-empty string."""
        md_file = tmp_path / "note.md"
        md_file.write_text("# Hello\nWorld")
        result = convert_to_markdown(str(md_file))
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    @patch("smart_search.markitdown_parser.Path")
    @patch("smart_search.markitdown_parser._converter", None)
    @patch("smart_search.markitdown_parser.MarkItDown")
    def test_lazy_init_creates_converter_once(self, mock_cls, mock_path):
        """MarkItDown instance is created lazily on first call."""
        mock_path.return_value.stat.return_value.st_size = 100
        mock_instance = MagicMock()
        mock_instance.convert.return_value = MagicMock(
            text_content="# Result\nContent"
        )
        mock_cls.return_value = mock_instance

        convert_to_markdown("/fake/path.pdf")
        mock_cls.assert_called_once()

    @patch("smart_search.markitdown_parser.Path")
    @patch("smart_search.markitdown_parser._converter")
    def test_empty_output_raises_value_error(self, mock_converter, mock_path):
        """ValueError raised when MarkItDown returns empty text."""
        mock_path.return_value.stat.return_value.st_size = 100
        mock_converter.convert.return_value = MagicMock(text_content="")
        with pytest.raises(ValueError, match="empty output"):
            convert_to_markdown("/fake/path.pdf")

    @patch("smart_search.markitdown_parser.Path")
    @patch("smart_search.markitdown_parser._converter")
    def test_whitespace_only_output_raises_value_error(self, mock_converter, mock_path):
        """ValueError raised when MarkItDown returns whitespace-only text."""
        mock_path.return_value.stat.return_value.st_size = 100
        mock_converter.convert.return_value = MagicMock(text_content="   \n  ")
        with pytest.raises(ValueError, match="empty output"):
            convert_to_markdown("/fake/path.pdf")

    @patch("smart_search.markitdown_parser.Path")
    @patch("smart_search.markitdown_parser._converter")
    def test_none_output_raises_value_error(self, mock_converter, mock_path):
        """ValueError raised when MarkItDown returns None text_content."""
        mock_path.return_value.stat.return_value.st_size = 100
        mock_converter.convert.return_value = MagicMock(text_content=None)
        with pytest.raises(ValueError, match="empty output"):
            convert_to_markdown("/fake/path.pdf")

    @patch("smart_search.markitdown_parser.Path")
    @patch("smart_search.markitdown_parser._converter")
    def test_passes_file_path_to_converter(self, mock_converter, mock_path):
        """File path is forwarded to MarkItDown.convert()."""
        mock_path.return_value.stat.return_value.st_size = 100
        mock_converter.convert.return_value = MagicMock(
            text_content="# Content"
        )
        convert_to_markdown("/my/doc.pdf")
        mock_converter.convert.assert_called_once_with("/my/doc.pdf")

    def test_converts_pdf_file(self, sample_pdf_path):
        """Real PDF file is converted to non-empty Markdown."""
        result = convert_to_markdown(str(sample_pdf_path))
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_converts_docx_file(self, sample_docx_path):
        """Real DOCX file is converted to non-empty Markdown."""
        result = convert_to_markdown(str(sample_docx_path))
        assert isinstance(result, str)
        assert len(result.strip()) > 0


def test_retries_on_permission_error(monkeypatch):
    """Retries up to 3 times on PermissionError before succeeding."""
    import smart_search.markitdown_parser as mod

    monkeypatch.setattr(mod, "_converter", None)
    monkeypatch.setattr(mod, "_RETRY_DELAY_S", 0.01)  # fast for tests

    # Patch Path so stat() doesn't fail on the fake path.
    fake_stat = MagicMock()
    fake_stat.st_size = 100
    fake_path = MagicMock()
    fake_path.stat.return_value = fake_stat
    monkeypatch.setattr(mod, "Path", lambda p: fake_path)

    call_count = 0

    class FakeConverter:
        """Fake MarkItDown that fails twice then succeeds."""

        def convert(self, path):
            """Raise PermissionError on first two calls, succeed on third."""
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise PermissionError("file locked by antivirus")
            return MagicMock(text_content="# Content")

    monkeypatch.setattr(mod, "MarkItDown", lambda: FakeConverter())
    result = mod.convert_to_markdown("/fake/file.pdf")
    assert call_count == 3
    assert "Content" in result


def test_reset_converter_clears_singleton():
    """reset_converter sets _converter to None."""
    import smart_search.markitdown_parser as mod

    mod._converter = "something"
    reset_converter()
    assert mod._converter is None
