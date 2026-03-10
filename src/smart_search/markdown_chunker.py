# Heading-based Markdown chunker for .md files -- no Docling dependency.

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from smart_search.config import SmartSearchConfig
from smart_search.models import Chunk, generate_chunk_id

# Regex matching ATX headings at levels 1-3: "# ", "## ", "### "
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


class MarkdownChunker:
    """Splits Markdown files into Chunk objects by heading structure.

    Uses ATX headings (# / ## / ###) as section boundaries. Strips YAML
    frontmatter and extracts title/date metadata. Pure Python -- no ML or
    Docling dependency.
    """

    def __init__(self, config: SmartSearchConfig) -> None:
        """Store config settings for chunking behaviour.

        Args:
            config: SmartSearchConfig with block_chunking_enabled,
                    min_chunk_length, and embedding_model settings.
        """
        self._config = config

    def chunk_file(self, file_path: str) -> List[Chunk]:
        """Read a Markdown file and return heading-delimited Chunk objects.

        Thin wrapper around chunk_text() that reads from disk first.

        Args:
            file_path: Absolute or relative path to a .md file.

        Returns:
            List of Chunk objects with empty embeddings, ready for embedding.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file extension is not ".md".
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Only accept .md -- check directly rather than via config.supported_extensions
        # so this class stays independent of config extension list ordering.
        if path.suffix.lower() != ".md":
            raise ValueError(
                f"Unsupported file extension: {path.suffix}. "
                f"MarkdownChunker only handles .md files."
            )

        raw_text = path.read_text(encoding="utf-8")
        source_path = path.resolve().as_posix()
        return self.chunk_text(raw_text, source_path=source_path)

    def chunk_text(
        self, text: str, source_path: str, source_type: str = "md"
    ) -> List[Chunk]:
        """Chunk a Markdown string into heading-delimited Chunk objects.

        Core chunking method that operates on text directly. Used by
        chunk_file() for .md files and by the indexer for MarkItDown-
        converted documents (PDF, DOCX, PPTX, etc.).

        Args:
            text: Markdown text content (may include YAML frontmatter).
            source_path: Resolved posix path to attribute chunks to.
            source_type: File type identifier (e.g., "md", "pdf", "docx").

        Returns:
            List of Chunk objects with empty embeddings, ready for embedding.
        """
        frontmatter, body = _strip_frontmatter(text)

        source_title = frontmatter.get("title") or Path(source_path).stem
        source_date = frontmatter.get("date") or None
        now = datetime.now(timezone.utc).isoformat()

        if not self._config.block_chunking_enabled:
            # Return the whole body as a single chunk (no heading splits)
            return self._build_chunks(
                sections=[{"text": body.strip(), "section_path": []}],
                source_path=source_path,
                source_title=source_title,
                source_date=source_date,
                source_type=source_type,
                now=now,
            )

        sections = _split_by_headings(body)
        # Filter empty sections and those below minimum length threshold
        min_len = max(self._config.min_chunk_length, 1)
        sections = [
            s for s in sections
            if len(s["text"].strip()) >= min_len
        ]

        return self._build_chunks(
            sections=sections,
            source_path=source_path,
            source_title=source_title,
            source_date=source_date,
            source_type=source_type,
            now=now,
        )

    def _build_chunks(
        self,
        sections: List[Dict],
        source_path: str,
        source_title: Optional[str],
        source_date: Optional[str],
        now: str,
        source_type: str = "md",
    ) -> List[Chunk]:
        """Construct Chunk objects from a list of section dicts.

        Args:
            sections: List of dicts with "text" and "section_path" keys.
            source_path: Resolved posix path to the source file.
            source_title: Title extracted from frontmatter or filename stem.
            source_date: Date string extracted from frontmatter, or None.
            now: UTC ISO timestamp string for indexed_at.
            source_type: File type identifier (e.g., "md", "pdf", "docx").

        Returns:
            List of Chunk objects, one per section.
        """
        chunks = []
        for idx, section in enumerate(sections):
            chunk = Chunk(
                id=generate_chunk_id(source_path, idx),
                source_path=source_path,
                source_type=source_type,
                content_type="text",
                text=section["text"].strip(),
                page_number=None,
                section_path=json.dumps(section["section_path"]),
                embedding=[],
                has_image=False,
                image_path=None,
                entity_tags=None,
                source_title=source_title,
                source_date=source_date,
                indexed_at=now,
                model_name=self._config.embedding_model,
            )
            chunks.append(chunk)
        return chunks


def _strip_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """Remove YAML frontmatter from Markdown text and parse key-value pairs.

    Frontmatter is a block delimited by "---" on its own line at the start
    of the file. Only simple "key: value" pairs are parsed (no nested YAML).

    Args:
        text: Raw Markdown file content.

    Returns:
        Tuple of (metadata dict, body text without frontmatter).
    """
    if not text.startswith("---\n"):
        return {}, text

    # Find the closing "---" delimiter
    close_idx = text.find("\n---\n", 4)
    if close_idx == -1:
        # Malformed frontmatter -- treat whole text as body
        return {}, text

    frontmatter_block = text[4:close_idx]
    body = text[close_idx + 5:]  # Skip "\n---\n"

    metadata: Dict[str, str] = {}
    for line in frontmatter_block.splitlines():
        if ": " in line:
            key, _, value = line.partition(": ")
            metadata[key.strip()] = value.strip()

    return metadata, body


def _split_by_headings(body: str) -> List[Dict]:
    """Split Markdown body text into sections delimited by ATX headings.

    Handles heading levels 1-3 (# / ## / ###). Tracks a heading stack to
    build nested section_path arrays. Content before the first heading is
    returned as a section with an empty section_path.

    Args:
        body: Markdown text with frontmatter already stripped.

    Returns:
        List of dicts: {"text": str, "section_path": List[str]}.
        Each dict represents one section's content and its heading ancestry.
    """
    sections = []
    # heading_stack maps level (1-3) -> heading text; tracks current hierarchy
    heading_stack: Dict[int, str] = {}

    # Find all heading positions in the body
    matches = list(_HEADING_RE.finditer(body))

    if not matches:
        # No headings -- whole body is one section
        return [{"text": body, "section_path": []}]

    # Capture content that appears before the first heading
    preamble = body[: matches[0].start()].strip()
    if preamble:
        sections.append({"text": preamble, "section_path": []})

    for i, match in enumerate(matches):
        level = len(match.group(1))   # Number of "#" characters
        heading_text = match.group(2).strip()

        # Update the heading stack: this heading replaces its level and
        # clears all deeper levels (they are no longer active ancestors).
        heading_stack[level] = heading_text
        for deeper_level in list(heading_stack.keys()):
            if deeper_level > level:
                del heading_stack[deeper_level]

        # Build section_path from levels 1..level in order
        section_path = [
            heading_stack[lvl]
            for lvl in sorted(heading_stack.keys())
            if lvl <= level
        ]

        # Section text is everything between this heading line and the next
        content_start = match.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_text = body[content_start:content_end].strip()

        sections.append({"text": section_text, "section_path": section_path})

    return sections
