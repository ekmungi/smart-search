# Tests for MarkdownChunker: heading-based Markdown section splitting.

import json

import pytest

from smart_search.markdown_chunker import MarkdownChunker


class TestMarkdownChunkerFast:
    """Fast tests for Markdown chunking -- no ML models needed."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_config):
        cfg = tmp_config.model_copy(update={"min_chunk_length": 0})
        self.chunker = MarkdownChunker(cfg)

    def test_simple_note_single_chunk(self, tmp_path):
        """Note with no headings becomes a single chunk."""
        md = tmp_path / "note.md"
        md.write_text("Just a simple note with no headings.", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        assert len(chunks) == 1
        assert chunks[0].text == "Just a simple note with no headings."
        assert chunks[0].source_type == "md"
        assert chunks[0].content_type == "text"

    def test_headings_split_into_chunks(self, tmp_path):
        """Each heading starts a new chunk."""
        md = tmp_path / "note.md"
        md.write_text("# Section A\nContent A\n## Section B\nContent B\n", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        assert len(chunks) == 2
        assert "Content A" in chunks[0].text
        assert "Content B" in chunks[1].text

    def test_section_path_hierarchy(self, tmp_path):
        """section_path tracks heading hierarchy."""
        md = tmp_path / "note.md"
        md.write_text("# Top\nIntro\n## Sub\nDetail\n", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        paths = [json.loads(c.section_path) for c in chunks]
        assert paths[0] == ["Top"]
        assert paths[1] == ["Top", "Sub"]

    def test_frontmatter_stripped(self, tmp_path):
        """YAML frontmatter is removed from chunk text."""
        md = tmp_path / "note.md"
        md.write_text("---\ntitle: My Note\ndate: 2026-01-01\n---\n# Heading\nBody text\n", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        assert all("---" not in c.text for c in chunks)
        assert chunks[0].source_title == "My Note"

    def test_frontmatter_date_extracted(self, tmp_path):
        """Date from frontmatter stored in source_date."""
        md = tmp_path / "note.md"
        md.write_text("---\ndate: 2026-01-15\n---\nSome content\n", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        assert chunks[0].source_date == "2026-01-15"

    def test_empty_sections_skipped(self, tmp_path):
        """Sections with only whitespace are not included."""
        md = tmp_path / "note.md"
        md.write_text("# Empty\n\n# Has Content\nSomething here\n", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        assert len(chunks) == 1
        assert "Something" in chunks[0].text

    def test_min_chunk_length_filters_short(self, tmp_config, tmp_path):
        """Chunks shorter than min_chunk_length are filtered out."""
        cfg = tmp_config.model_copy(update={"min_chunk_length": 100})
        chunker = MarkdownChunker(cfg)
        md = tmp_path / "note.md"
        md.write_text("# Heading\nShort.\n# Other\n" + "Long content. " * 20 + "\n", encoding="utf-8")
        chunks = chunker.chunk_file(str(md))
        assert all(len(c.text) >= 100 for c in chunks)

    def test_block_chunking_disabled_returns_single_chunk(self, tmp_config, tmp_path):
        """block_chunking_enabled=False returns whole note as one chunk."""
        cfg = tmp_config.model_copy(update={"block_chunking_enabled": False})
        chunker = MarkdownChunker(cfg)
        md = tmp_path / "note.md"
        md.write_text("# A\nContent A\n# B\nContent B\n", encoding="utf-8")
        chunks = chunker.chunk_file(str(md))
        assert len(chunks) == 1

    def test_chunk_ids_unique(self, tmp_path):
        """All chunk IDs within a file are unique."""
        md = tmp_path / "note.md"
        md.write_text("# A\nContent\n# B\nMore content\n", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_ids_deterministic(self, tmp_path):
        """Same file chunked twice produces same IDs."""
        md = tmp_path / "note.md"
        md.write_text("# A\nContent\n# B\nMore\n", encoding="utf-8")
        a = [c.id for c in self.chunker.chunk_file(str(md))]
        b = [c.id for c in self.chunker.chunk_file(str(md))]
        assert a == b

    def test_file_not_found_raises(self):
        """FileNotFoundError for non-existent file."""
        with pytest.raises(FileNotFoundError):
            self.chunker.chunk_file("/nonexistent/note.md")

    def test_unsupported_extension_raises(self, tmp_path):
        """ValueError for non-.md extension."""
        txt = tmp_path / "note.txt"
        txt.write_text("hello", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            self.chunker.chunk_file(str(txt))

    def test_embedding_empty(self, tmp_path):
        """Embeddings are empty at chunking stage."""
        md = tmp_path / "note.md"
        md.write_text("Some content", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        assert all(c.embedding == [] for c in chunks)

    def test_h3_creates_deeper_section_path(self, tmp_path):
        """H3 under H2 under H1 produces 3-level section path."""
        md = tmp_path / "note.md"
        md.write_text("# L1\nA\n## L2\nB\n### L3\nC\n", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        paths = [json.loads(c.section_path) for c in chunks]
        assert paths[2] == ["L1", "L2", "L3"]

    def test_content_before_first_heading(self, tmp_path):
        """Content before first heading becomes its own chunk."""
        md = tmp_path / "note.md"
        md.write_text("Preamble text here with enough words to be a real chunk.\n\n# First Heading\nBody of this section with enough content to matter.\n", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        assert len(chunks) == 2
        assert "Preamble" in chunks[0].text
        assert json.loads(chunks[0].section_path) == []
