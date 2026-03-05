# Document chunking using Docling's HierarchicalChunker on DoclingDocument JSON.

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from docling.chunking import HierarchicalChunker
from docling.document_converter import DocumentConverter

from smart_search.config import SmartSearchConfig
from smart_search.models import Chunk, generate_chunk_id


# Map Docling label names to our content_type values
_LABEL_MAP = {
    "text": "text",
    "table": "table",
    "picture": "figure_caption",
    "section_header": "heading",
    "title": "heading",
    "caption": "figure_caption",
    "list_item": "text",
    "formula": "text",
    "page_header": "text",
    "page_footer": "text",
}


class DocumentChunker:
    """Wraps Docling DocumentConverter and HierarchicalChunker.

    Converts PDF/DOCX files to DoclingDocument JSON, then chunks them
    using structure-aware hierarchical chunking. No Markdown conversion.
    """

    def __init__(self, config: SmartSearchConfig) -> None:
        """Initialize converter and chunker with config settings.

        Args:
            config: SmartSearchConfig with chunk and extension settings.
        """
        self._config = config
        self._converter = DocumentConverter()
        self._chunker = HierarchicalChunker(
            max_tokens=config.chunk_max_tokens,
        )

    def chunk_file(self, file_path: str) -> List[Chunk]:
        """Extract and chunk a document file.

        Args:
            file_path: Path to a PDF or DOCX file.

        Returns:
            List of Chunk objects with empty embeddings.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file extension is not supported.
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = path.suffix.lower()
        if suffix not in self._config.supported_extensions:
            raise ValueError(
                f"Unsupported file extension: {suffix}. "
                f"Supported: {self._config.supported_extensions}"
            )

        # Convert document to DoclingDocument (no Markdown)
        result = self._converter.convert(str(path))
        doc = result.document

        # Extract metadata
        source_path = path.resolve().as_posix()
        source_type = suffix.lstrip(".")
        source_title = getattr(doc, "title", None) or path.stem
        now = datetime.now(timezone.utc).isoformat()

        # Apply hierarchical chunking
        docling_chunks = list(self._chunker.chunk(doc))

        chunks = []
        for idx, dc in enumerate(docling_chunks):
            content_type = self._resolve_content_type(dc)
            section_path = self._extract_section_path(dc)
            page_number = self._extract_page_number(dc)

            chunk = Chunk(
                id=generate_chunk_id(source_path, idx),
                source_path=source_path,
                source_type=source_type,
                content_type=content_type,
                text=dc.text,
                page_number=page_number,
                section_path=json.dumps(section_path),
                embedding=[],
                has_image=False,
                image_path=None,
                entity_tags=None,
                source_title=source_title,
                source_date=None,
                indexed_at=now,
                model_name=self._config.embedding_model,
            )
            chunks.append(chunk)

        return chunks

    def _resolve_content_type(self, dc) -> str:
        """Map a Docling chunk's label to our content_type enum.

        Args:
            dc: A Docling chunk object with meta.doc_items.

        Returns:
            Content type string: text, table, figure_caption, or heading.
        """
        if hasattr(dc, "meta") and hasattr(dc.meta, "doc_items"):
            for item in dc.meta.doc_items:
                label = getattr(item, "label", None)
                if label is not None:
                    label_str = str(label).lower().split(".")[-1]
                    return _LABEL_MAP.get(label_str, "text")
        return "text"

    def _extract_section_path(self, dc) -> List[str]:
        """Extract section heading path from a Docling chunk.

        Args:
            dc: A Docling chunk object with meta.headings.

        Returns:
            List of section heading strings (may be empty).
        """
        if hasattr(dc, "meta") and hasattr(dc.meta, "headings"):
            return [str(h) for h in dc.meta.headings if h]
        return []

    def _extract_page_number(self, dc) -> int | None:
        """Extract page number from a Docling chunk's provenance.

        Args:
            dc: A Docling chunk object with meta.doc_items.

        Returns:
            1-based page number, or None if unavailable.
        """
        if hasattr(dc, "meta") and hasattr(dc.meta, "doc_items"):
            for item in dc.meta.doc_items:
                prov = getattr(item, "prov", None)
                if prov:
                    for p in prov:
                        page = getattr(p, "page_no", None)
                        if page is not None:
                            return page
        return None
