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
        Markdown text content, or empty string if file exceeds size limit.

    Raises:
        ValueError: If conversion fails or produces empty output.
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
    if not result.text_content or not result.text_content.strip():
        raise ValueError(f"MarkItDown produced empty output for {file_path}")
    return result.text_content
