# Convert documents to Markdown using the MarkItDown library.

from markitdown import MarkItDown

_converter = None


def convert_to_markdown(file_path: str) -> str:
    """Convert any supported file to Markdown text.

    Uses a module-level MarkItDown singleton to avoid repeated init.
    Supports PDF, DOCX, PPTX, XLSX, HTML, and other formats that
    MarkItDown handles natively.

    Args:
        file_path: Path to the file to convert.

    Returns:
        Markdown text content.

    Raises:
        ValueError: If conversion fails or produces empty output.
    """
    global _converter
    if _converter is None:
        _converter = MarkItDown()
    result = _converter.convert(file_path)
    if not result.text_content or not result.text_content.strip():
        raise ValueError(f"MarkItDown produced empty output for {file_path}")
    return result.text_content
