# Convert documents to Markdown using the MarkItDown library.

"""Wraps MarkItDown with retry logic for enterprise file locks,
detailed error logging, and lazy singleton initialization."""

import logging
import time
import traceback
from pathlib import Path

from markitdown import MarkItDown

_converter = None
_logger = logging.getLogger(__name__)

# Files larger than this are skipped to avoid excessive memory usage.
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB

# Retry config for file access errors (antivirus locks, sharing violations).
_MAX_RETRIES = 3
_RETRY_DELAY_S = 1.0


def _get_converter() -> MarkItDown:
    """Return the module-level MarkItDown singleton, creating on first call."""
    global _converter
    if _converter is None:
        _converter = MarkItDown()
        _logger.info("MarkItDown initialized (version: %s)",
                      getattr(MarkItDown, "__version__", "unknown"))
    return _converter


def reset_converter() -> None:
    """Release the MarkItDown singleton to free memory."""
    global _converter
    _converter = None


def convert_to_markdown(file_path: str) -> str:
    """Convert any supported file to Markdown text.

    Retries up to _MAX_RETRIES times on PermissionError or OSError
    with errno 32 (Windows sharing violation from antivirus scans).

    Args:
        file_path: Path to the file to convert.

    Returns:
        Markdown text content.

    Raises:
        ValueError: If conversion produces no extractable text.
        PermissionError: If file remains locked after all retries.
        RuntimeError: If conversion fails for other reasons.
    """
    file_size = Path(file_path).stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        _logger.warning(
            "Skipping %s: file size %d MB exceeds 100 MB limit",
            file_path, file_size // (1024 * 1024),
        )
        return ""

    converter = _get_converter()
    last_error = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = converter.convert(file_path)
            # Extract text before releasing result to free internal buffers.
            text_content = result.text_content
            del result
            if not text_content or not text_content.strip():
                raise ValueError(
                    f"MarkItDown returned empty output for {file_path}"
                )
            return text_content
        except PermissionError as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                _logger.warning(
                    "File locked (attempt %d/%d): %s -- retrying in %.1fs",
                    attempt, _MAX_RETRIES, file_path, _RETRY_DELAY_S,
                )
                time.sleep(_RETRY_DELAY_S)
            else:
                _logger.error("File locked after %d attempts: %s",
                              _MAX_RETRIES, file_path)
        except OSError as e:
            if getattr(e, "errno", None) == 32 and attempt < _MAX_RETRIES:
                last_error = e
                _logger.warning(
                    "Sharing violation (attempt %d/%d): %s -- retrying",
                    attempt, _MAX_RETRIES, file_path,
                )
                time.sleep(_RETRY_DELAY_S)
            else:
                _logger.error(
                    "Conversion failed for %s:\n%s",
                    file_path, traceback.format_exc(),
                )
                raise RuntimeError(
                    f"Conversion failed for {file_path}: {e}"
                ) from e
        except ValueError:
            raise
        except Exception as e:
            _logger.error(
                "Conversion failed for %s:\n%s",
                file_path, traceback.format_exc(),
            )
            raise RuntimeError(
                f"Conversion failed for {file_path}: {e}"
            ) from e

    raise last_error
