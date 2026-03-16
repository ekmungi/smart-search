# src/smart_search/reader.py
# Note reader: path resolution, safety validation, and file reading.

from pathlib import Path
from typing import List, Optional

MAX_NOTE_PATH_LENGTH = 500
MAX_CONTENT_BYTES = 50_000  # ~50KB cap to prevent context flooding

# Extensions that require MarkItDown conversion instead of plain text read
BINARY_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}


def resolve_note_path(
    note_path: str, watch_directories: List[str]
) -> Optional[Path]:
    """Resolve a relative note path against watch directories.

    Validates the path is safe (no traversal, not absolute, within length
    limit) and returns the first matching file found across watch dirs.

    Args:
        note_path: Relative path to the note file.
        watch_directories: List of absolute directory paths to search.

    Returns:
        Resolved absolute Path if found, None if file does not exist.

    Raises:
        ValueError: If the path is unsafe (traversal, absolute, too long).
    """
    if len(note_path) > MAX_NOTE_PATH_LENGTH:
        raise ValueError(
            f"Note path exceeds {MAX_NOTE_PATH_LENGTH} characters."
        )

    normalized = Path(note_path).as_posix()

    # On Windows, Path("/foo").is_absolute() is False; check leading / too
    if Path(note_path).is_absolute() or note_path.startswith("/"):
        raise ValueError("Relative path required, got absolute path.")

    if ".." in normalized.split("/"):
        raise ValueError("Path traversal (..) is not allowed.")

    for directory in watch_directories:
        candidate = Path(directory) / note_path
        resolved = candidate.resolve()

        # Double-check resolved path is within the watch directory
        if not str(resolved).startswith(str(Path(directory).resolve())):
            raise ValueError("Path traversal detected after resolution.")

        if resolved.is_file():
            return resolved

    # Fallback: search by filename across all watch directories.
    # Handles cases where the user provides a path relative to a parent
    # of the watch dir (e.g. "Drug Discovery/file.pdf" when the watch
    # dir is already ".../Drug Discovery").
    filename = Path(note_path).name
    for directory in watch_directories:
        for match in Path(directory).rglob(filename):
            resolved = match.resolve()
            if not str(resolved).startswith(str(Path(directory).resolve())):
                continue
            if resolved.is_file():
                return resolved

    return None


def read_note(note_path: str, watch_directories: List[str]) -> str:
    """Read a note's content by relative path with safety validation.

    Resolves the path against watch directories, validates safety,
    reads the file, and truncates if too large.

    Args:
        note_path: Relative path to the note file (max 500 chars).
        watch_directories: List of absolute directory paths to search.

    Returns:
        Note content as a string, or an error message.
    """
    try:
        resolved = resolve_note_path(note_path, watch_directories)
    except ValueError as exc:
        return f"Error: Invalid path -- {exc}"

    if resolved is None:
        return f"Error: Note not found -- '{note_path}'"

    content = _read_file_content(resolved)

    if len(content) > MAX_CONTENT_BYTES:
        return (
            content[:MAX_CONTENT_BYTES]
            + f"\n\n[Truncated: file exceeds {MAX_CONTENT_BYTES // 1000}KB]"
        )

    return content


def _read_file_content(path: Path) -> str:
    """Read file content, using MarkItDown for binary formats.

    Args:
        path: Resolved absolute path to the file.

    Returns:
        File content as a string.
    """
    if path.suffix.lower() in BINARY_EXTENSIONS:
        from smart_search.markitdown_parser import convert_to_markdown
        return convert_to_markdown(str(path))

    return path.read_text(encoding="utf-8")
