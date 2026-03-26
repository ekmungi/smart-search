# Tests for conversion_worker.py -- in-process conversion with memory guard.

"""Tests for the in-process ConversionWorker: timeout handling,
memory guard (RSS threshold + periodic GC), and API compatibility."""

from unittest.mock import patch, MagicMock

import pytest

from smart_search.conversion_worker import ConversionWorker


class TestConversionWorker:
    """Tests for the in-process ConversionWorker."""

    def test_convert_returns_markdown(self, tmp_path):
        """Converts a real markdown file successfully."""
        md = tmp_path / "test.md"
        md.write_text("# Hello\nWorld")
        worker = ConversionWorker()
        result = worker.convert(str(md))
        assert "Hello" in result

    def test_convert_raises_on_timeout(self):
        """Raises TimeoutError when conversion exceeds timeout."""
        import time
        worker = ConversionWorker()
        with patch("smart_search.conversion_worker.convert_to_markdown",
                    side_effect=lambda p: time.sleep(10)):
            with pytest.raises(TimeoutError):
                worker.convert("/fake.pdf", timeout=1)

    def test_reset_on_high_rss(self):
        """Resets converter when RSS exceeds threshold."""
        worker = ConversionWorker(rss_threshold_mb=1)
        with patch("smart_search.conversion_worker.convert_to_markdown",
                    return_value="# Content"), \
             patch("smart_search.conversion_worker._get_rss_mb", return_value=2000):
            result = worker.convert("/fake.pdf")
            assert result == "# Content"
        assert worker._converter_reset_count > 0

    def test_stop_releases_converter(self):
        """stop() releases converter and runs GC."""
        worker = ConversionWorker()
        worker.start()
        worker.stop()
        # Should not raise on double-stop
        worker.stop()

    def test_gc_runs_periodically(self):
        """GC triggers after every N conversions."""
        worker = ConversionWorker()
        worker._gc_interval = 2
        with patch("smart_search.conversion_worker.convert_to_markdown",
                    return_value="# Content"), \
             patch("smart_search.conversion_worker.gc") as mock_gc:
            worker.convert("/f1.pdf")
            worker.convert("/f2.pdf")
            assert mock_gc.collect.called

    def test_start_is_noop(self):
        """start() is a no-op for API compatibility."""
        worker = ConversionWorker()
        worker.start()  # Should not raise

    def test_convert_propagates_value_error(self):
        """ValueError from convert_to_markdown propagates to caller."""
        worker = ConversionWorker()
        with patch("smart_search.conversion_worker.convert_to_markdown",
                    side_effect=ValueError("empty output")):
            with pytest.raises(ValueError, match="empty output"):
                worker.convert("/fake.pdf")

    def test_convert_propagates_runtime_error(self):
        """RuntimeError from convert_to_markdown propagates to caller."""
        worker = ConversionWorker()
        with patch("smart_search.conversion_worker.convert_to_markdown",
                    side_effect=RuntimeError("conversion failed")):
            with pytest.raises(RuntimeError, match="conversion failed"):
                worker.convert("/fake.pdf")


class TestConversionWorkerIntegration:
    """Integration tests with real file conversions."""

    def test_converts_real_md_file(self, tmp_path):
        """End-to-end: .md file -> convert -> returns content."""
        from smart_search.conversion_worker import ConversionWorker
        md = tmp_path / "doc.md"
        md.write_text("# Title\n\nParagraph here.\n\n## Section\n\nMore text.")
        worker = ConversionWorker()
        result = worker.convert(str(md))
        assert "Title" in result
        assert "Section" in result

    def test_converts_real_pdf_file(self, sample_pdf_path):
        """End-to-end: PDF file -> convert -> returns content."""
        from smart_search.conversion_worker import ConversionWorker
        worker = ConversionWorker()
        result = worker.convert(str(sample_pdf_path))
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_converts_real_docx_file(self, sample_docx_path):
        """End-to-end: DOCX file -> convert -> returns content."""
        from smart_search.conversion_worker import ConversionWorker
        worker = ConversionWorker()
        result = worker.convert(str(sample_docx_path))
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_multiple_files_sequentially(self, tmp_path):
        """Worker handles multiple files in sequence without errors."""
        from smart_search.conversion_worker import ConversionWorker
        worker = ConversionWorker()
        for i in range(5):
            md = tmp_path / f"doc{i}.md"
            md.write_text(f"# Document {i}\n\nContent for doc {i}.")
            result = worker.convert(str(md))
            assert f"Document {i}" in result
        worker.stop()
