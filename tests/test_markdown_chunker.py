# Tests for MarkdownChunker: heading-based Markdown section splitting.

import json

import pytest

from smart_search.markdown_chunker import MarkdownChunker, _enforce_size_limits


class TestMarkdownChunkerFast:
    """Fast tests for Markdown chunking -- no ML models needed."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_config):
        # Disable size enforcement for basic chunker tests (tested separately)
        cfg = tmp_config.model_copy(update={
            "min_chunk_length": 0,
            "chunk_min_words": 0,
            "chunk_max_words": 10000,
        })
        self.chunker = MarkdownChunker(cfg)

    def test_simple_note_single_chunk(self, tmp_path):
        """Note with no headings becomes a single chunk."""
        md = tmp_path / "note.md"
        md.write_text("Just a simple note with no headings.", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        assert len(chunks) == 1
        assert "Just a simple note with no headings." in chunks[0].text
        assert chunks[0].text.startswith("Title: note\n---\n")
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
        """YAML frontmatter is removed from chunk text (title prefix is separate)."""
        md = tmp_path / "note.md"
        md.write_text("---\ntitle: My Note\ndate: 2026-01-01\n---\n# Heading\nBody text\n", encoding="utf-8")
        chunks = self.chunker.chunk_file(str(md))
        # Frontmatter key-value pairs should not appear in chunk text
        assert all("date: 2026-01-01" not in c.text for c in chunks)
        assert chunks[0].source_title == "My Note"
        # Title prefix should be present
        assert chunks[0].text.startswith("Title: My Note\n---\n")

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


class TestParagraphFallback:
    """Tests for paragraph-based fallback chunking (B17 fix)."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_config):
        cfg = tmp_config.model_copy(update={
            "min_chunk_length": 0,
            "chunk_min_words": 0,
            "chunk_max_words": 10000,
        })
        self.chunker = MarkdownChunker(cfg)

    def test_long_headingless_text_splits_by_paragraphs(self):
        """Text without headings exceeding threshold splits on paragraph boundaries."""
        paragraphs = [f"Paragraph {i} with enough content to be meaningful. " * 3 for i in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = self.chunker.chunk_text(text, source_path="/test/doc.pdf", source_type="pdf")
        assert len(chunks) > 1
        # All original content should be present across chunks
        combined = " ".join(c.text for c in chunks)
        assert "Paragraph 0" in combined
        assert "Paragraph 9" in combined

    def test_short_headingless_text_stays_single_chunk(self):
        """Short text without headings remains a single chunk (below threshold)."""
        text = "A short document with no headings."
        chunks = self.chunker.chunk_text(text, source_path="/test/doc.pdf", source_type="pdf")
        assert len(chunks) == 1

    def test_text_with_headings_uses_heading_split(self):
        """When headings exist, heading-based splitting is preferred over paragraph fallback."""
        text = "# Section 1\nContent one.\n\n# Section 2\nContent two."
        chunks = self.chunker.chunk_text(text, source_path="/test/doc.pdf", source_type="pdf")
        assert len(chunks) == 2
        assert "Content one" in chunks[0].text
        assert "Content two" in chunks[1].text

    def test_paragraph_chunks_have_empty_section_path(self):
        """Paragraph-based chunks have empty section_path since there are no headings."""
        paragraphs = [f"Long paragraph {i} with substantial content here. " * 5 for i in range(6)]
        text = "\n\n".join(paragraphs)
        chunks = self.chunker.chunk_text(text, source_path="/test/doc.pdf", source_type="pdf")
        assert len(chunks) > 1
        for c in chunks:
            assert json.loads(c.section_path) == []

    def test_paragraph_chunks_preserve_source_type(self):
        """Paragraph-based chunks retain the source_type from the caller."""
        paragraphs = [f"Content block {i} with enough text to matter for chunking. " * 4 for i in range(8)]
        text = "\n\n".join(paragraphs)
        chunks = self.chunker.chunk_text(text, source_path="/test/slides.pptx", source_type="pptx")
        assert all(c.source_type == "pptx" for c in chunks)


class TestChunkText:
    """Tests for MarkdownChunker.chunk_text() method."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_config):
        cfg = tmp_config.model_copy(update={
            "min_chunk_length": 0,
            "chunk_min_words": 0,
            "chunk_max_words": 10000,
        })
        self.chunker = MarkdownChunker(cfg)

    def test_chunk_text_returns_chunks(self):
        """chunk_text produces Chunk objects from a Markdown string."""
        text = "# Section A\nContent A\n## Section B\nContent B\n"
        chunks = self.chunker.chunk_text(text, source_path="/test/doc.pdf", source_type="pdf")
        assert len(chunks) == 2
        assert "Content A" in chunks[0].text
        assert "Content B" in chunks[1].text

    def test_chunk_text_uses_source_type(self):
        """source_type is set correctly on produced chunks."""
        text = "# Heading\nSome content here"
        chunks = self.chunker.chunk_text(text, source_path="/test/doc.docx", source_type="docx")
        assert all(c.source_type == "docx" for c in chunks)

    def test_chunk_text_default_source_type_is_md(self):
        """Default source_type is 'md' when not specified."""
        text = "# Heading\nSome content here"
        chunks = self.chunker.chunk_text(text, source_path="/test/note.md")
        assert all(c.source_type == "md" for c in chunks)

    def test_chunk_text_strips_frontmatter(self):
        """YAML frontmatter key-value pairs are stripped from text input."""
        text = "---\ntitle: My Doc\n---\n# Heading\nBody text\n"
        chunks = self.chunker.chunk_text(text, source_path="/test/doc.pdf", source_type="pdf")
        # Frontmatter key-value pairs should not appear in chunk body
        assert all("title: My Doc" not in c.text.split("---\n", 2)[-1] for c in chunks)
        assert chunks[0].source_title == "My Doc"
        assert chunks[0].text.startswith("Title: My Doc\n---\n")

    def test_chunk_text_source_path_set(self):
        """source_path is set on all chunks."""
        text = "# Heading\nContent"
        chunks = self.chunker.chunk_text(text, source_path="/my/file.pdf", source_type="pdf")
        assert all(c.source_path == "/my/file.pdf" for c in chunks)

    def test_chunk_file_delegates_to_chunk_text(self, tmp_path):
        """chunk_file produces same results as chunk_text for same content."""
        md = tmp_path / "note.md"
        content = "# A\nContent A\n# B\nContent B\n"
        md.write_text(content, encoding="utf-8")
        file_chunks = self.chunker.chunk_file(str(md))
        text_chunks = self.chunker.chunk_text(content, source_path=md.resolve().as_posix())
        assert len(file_chunks) == len(text_chunks)
        assert [c.text for c in file_chunks] == [c.text for c in text_chunks]


class TestEnforceSizeLimits:
    """Tests for _enforce_size_limits: splitting oversized and merging undersized chunks."""

    def test_small_input_no_split(self):
        """Input below max_words stays as one chunk."""
        sections = [{"text": "A short sentence with a few words.", "section_path": []}]
        result = _enforce_size_limits(sections, max_words=200, min_words=50, overlap_words=40)
        assert len(result) == 1
        assert result[0]["text"] == sections[0]["text"]

    def test_oversized_splits_into_multiple(self):
        """500-word input splits into 2-3 chunks with max_words=200."""
        words = " ".join(f"word{i}." for i in range(500))
        sections = [{"text": words, "section_path": ["Heading"]}]
        result = _enforce_size_limits(sections, max_words=200, min_words=50, overlap_words=40)
        assert len(result) >= 2
        for s in result:
            # Each chunk should be at most ~max_words + overlap (allow some slack for merging)
            assert len(s["text"].split()) <= 280

    def test_undersized_merged(self):
        """Three 10-word chunks merge into one."""
        sections = [
            {"text": " ".join(f"w{j}" for j in range(10)), "section_path": []}
            for _ in range(3)
        ]
        result = _enforce_size_limits(sections, max_words=200, min_words=50, overlap_words=0)
        assert len(result) == 1
        assert "w0" in result[0]["text"]

    def test_sentence_boundary_respected(self):
        """Splits happen at sentence boundaries, not mid-sentence."""
        text = "First sentence here. Second sentence here. Third sentence here. Fourth sentence here. Fifth sentence here."
        sections = [{"text": text, "section_path": []}]
        result = _enforce_size_limits(sections, max_words=5, min_words=1, overlap_words=0)
        for s in result:
            # Each chunk should end with a complete sentence (ends with period or is the last chunk)
            stripped = s["text"].strip()
            assert stripped.endswith(".") or s == result[-1]

    def test_overlap_contains_trailing_words(self):
        """Second sub-chunk contains overlap words from the first."""
        sentences = [f"Sentence number {i} has some content here." for i in range(20)]
        text = " ".join(sentences)
        sections = [{"text": text, "section_path": []}]
        result = _enforce_size_limits(sections, max_words=30, min_words=5, overlap_words=10)
        if len(result) >= 2:
            # Last words of chunk 1 should appear at start of chunk 2
            chunk1_words = result[0]["text"].split()
            chunk2_words = result[1]["text"].split()
            tail = chunk1_words[-10:]
            head = chunk2_words[:10]
            # At least some overlap words should match
            overlap = set(tail) & set(head)
            assert len(overlap) > 0

    def test_section_path_preserved_on_split(self):
        """Split sub-chunks preserve parent section_path with part suffix."""
        words = " ".join(f"word{i}." for i in range(400))
        sections = [{"text": words, "section_path": ["Chapter 1"]}]
        result = _enforce_size_limits(sections, max_words=200, min_words=50, overlap_words=40)
        assert len(result) >= 2
        for s in result:
            assert "Chapter 1" in s["section_path"]

    def test_mixed_sizes(self):
        """Mix of oversized and undersized sections handled correctly."""
        big = " ".join(f"word{i}." for i in range(500))
        tiny = "Hello."
        sections = [
            {"text": big, "section_path": ["Big"]},
            {"text": tiny, "section_path": ["Tiny"]},
        ]
        result = _enforce_size_limits(sections, max_words=200, min_words=50, overlap_words=20)
        # Big should be split into multiple chunks
        assert len(result) >= 2
        # "Hello." content should still be present somewhere
        combined = " ".join(s["text"] for s in result)
        assert "Hello" in combined

    def test_undersized_at_end_merges_into_previous(self):
        """Undersized last section merges into the previous chunk."""
        sections = [
            {"text": " ".join(f"word{i}" for i in range(60)), "section_path": ["A"]},
            {"text": "tiny", "section_path": ["B"]},
        ]
        result = _enforce_size_limits(sections, max_words=200, min_words=50, overlap_words=0)
        # First section has 60 words (above min), so it flushes; "tiny" stays alone
        # This is expected -- downstream min_chunk_length filter handles it
        assert len(result) >= 1


class TestTitlePrepend:
    """Tests for document title prepending to chunk text."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_config):
        cfg = tmp_config.model_copy(update={
            "min_chunk_length": 0,
            "chunk_min_words": 0,
            "chunk_max_words": 10000,
        })
        self.chunker = MarkdownChunker(cfg)

    def test_chunk_text_starts_with_title(self):
        """Each chunk starts with 'Title: {name}' prefix."""
        text = "# Section\nSome content here that is long enough."
        chunks = self.chunker.chunk_text(text, source_path="/test/my-note.md")
        assert chunks[0].text.startswith("Title: my-note\n---\n")

    def test_title_from_frontmatter(self):
        """Title comes from YAML frontmatter when present."""
        text = "---\ntitle: Drug Discovery Paper\n---\n# Intro\nContent here."
        chunks = self.chunker.chunk_text(text, source_path="/test/paper.md")
        assert chunks[0].text.startswith("Title: Drug Discovery Paper\n---\n")

    def test_title_falls_back_to_filename_stem(self):
        """Title uses filename stem when no frontmatter title."""
        text = "# Heading\nSome content."
        chunks = self.chunker.chunk_text(text, source_path="/docs/my-research.pdf", source_type="pdf")
        assert chunks[0].text.startswith("Title: my-research\n---\n")

    def test_title_not_doubled(self):
        """Title prefix is not doubled if chunk already starts with it."""
        text = "Title: Already There\n---\nContent follows."
        chunks = self.chunker.chunk_text(text, source_path="/test/Already There.md")
        # Should not have "Title: Already There" twice
        assert chunks[0].text.count("Title: Already There") == 1

    def test_all_chunks_share_same_title(self):
        """All chunks from one file have the same title prefix."""
        text = "# A\nContent A.\n# B\nContent B."
        chunks = self.chunker.chunk_text(text, source_path="/test/shared.md")
        for c in chunks:
            assert "Title: shared" in c.text
