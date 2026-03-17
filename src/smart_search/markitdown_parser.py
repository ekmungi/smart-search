# Convert documents to Markdown using the MarkItDown library.

import logging
from pathlib import Path

from markitdown import MarkItDown

_converter = None
_logger = logging.getLogger(__name__)

# Files larger than this are skipped to avoid excessive memory usage.
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


def convert_to_markdown(file_path: str) -> str:
    """Convert any supported file to Markdown text.

    Uses a module-level MarkItDown singleton to avoid repeated init.
    Supports PDF, DOCX, PPTX, XLSX, HTML, and other formats that
    MarkItDown handles natively. Files exceeding MAX_FILE_SIZE_BYTES are
    skipped with a warning and an empty string is returned.

    Args:
        file_path: Path to the file to convert.

    Returns:
        Markdown text content, or empty string if conversion produces no text
        (e.g. scanned PDFs without OCR text layer) or file exceeds size limit.
    """
    file_size = Path(file_path).stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        _logger.warning(
            "Skipping %s: file size %d MB exceeds 100 MB limit",
            file_path,
            file_size // (1024 * 1024),
        )
        return ""

    global _converter
    if _converter is None:
        _converter = MarkItDown()
    result = _converter.convert(file_path)
    # Extract text before releasing the result object to free MarkItDown's
    # internal buffers immediately (important for large PDFs).
    text_content = result.text_content
    del result
    if not text_content or not text_content.strip():
        _logger.warning(
            "No extractable text in %s (may need OCR)", file_path,
        )
        return ""
    return text_content
