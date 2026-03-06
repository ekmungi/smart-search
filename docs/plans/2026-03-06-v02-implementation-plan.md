# v0.2 Daily Use + Markdown Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Markdown support with heading-based chunking, file watcher for auto-indexing, exclusion patterns, config controls, and a knowledge_ingest MCP tool.

**Architecture:** Strategy pattern -- MarkdownChunker alongside DocumentChunker, indexer routes by extension. Watchdog monitors configured directories. All config via pydantic-settings with env var overrides.

**Tech Stack:** Python 3.12, watchdog, pydantic-settings, FastMCP, LanceDB, pytest

---

### Task 1: Update config with v0.2 fields

**Files:**
- Modify: `src/smart_search/config.py`
- Test: `tests/test_config.py`

**Step 1: Write failing tests for new config fields**

Add tests to `tests/test_config.py`:

```python
def test_default_supported_extensions_includes_md():
    config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
    assert ".md" in config.supported_extensions

def test_default_watch_directories_empty():
    config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
    assert config.watch_directories == []

def test_default_exclude_patterns():
    config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
    assert ".git" in config.exclude_patterns
    assert ".obsidian" in config.exclude_patterns

def test_default_block_chunking_enabled():
    config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
    assert config.block_chunking_enabled is True

def test_default_min_chunk_length():
    config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
    assert config.min_chunk_length == 50

def test_default_watcher_debounce():
    config = SmartSearchConfig(lancedb_path="./x", sqlite_path="./y")
    assert config.watcher_debounce_seconds == 2.0
```

**Step 2: Run tests -- expect FAIL**

Run: `pytest tests/test_config.py -v`

**Step 3: Add fields to config.py**

Add to `SmartSearchConfig`:
- `watch_directories: List[str] = []`
- `exclude_patterns: List[str] = [".git", ".obsidian", ".trash", "node_modules", ".smart-search"]`
- `block_chunking_enabled: bool = True`
- `min_chunk_length: int = 50`
- `watcher_debounce_seconds: float = 2.0`
- Update `supported_extensions` default to include `".md"`
- Resolve `watch_directories` paths in `resolve_paths` validator

**Step 4: Run tests -- expect PASS**

Run: `pytest tests/test_config.py -v`

**Step 5: Commit**

`feat: add v0.2 config fields (watch dirs, exclusions, chunking controls)`

---

### Task 2: MarkdownChunker -- core parsing

**Files:**
- Create: `src/smart_search/markdown_chunker.py`
- Test: `tests/test_markdown_chunker.py`

**Step 1: Write failing tests for MarkdownChunker**

Create `tests/test_markdown_chunker.py`:

```python
import json
import pytest
from smart_search.markdown_chunker import MarkdownChunker

class TestMarkdownChunkerFast:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_config):
        self.chunker = MarkdownChunker(tmp_config)

    def test_simple_note_single_chunk(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("Just a simple note with no headings.")
        chunks = self.chunker.chunk_file(str(md))
        assert len(chunks) == 1
        assert chunks[0].text == "Just a simple note with no headings."
        assert chunks[0].source_type == "md"

    def test_headings_split_into_chunks(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("# Section A\nContent A\n## Section B\nContent B\n")
        chunks = self.chunker.chunk_file(str(md))
        assert len(chunks) == 2

    def test_section_path_hierarchy(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("# Top\nIntro\n## Sub\nDetail\n")
        chunks = self.chunker.chunk_file(str(md))
        paths = [json.loads(c.section_path) for c in chunks]
        assert paths[0] == ["Top"]
        assert paths[1] == ["Top", "Sub"]

    def test_frontmatter_stripped(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("---\ntitle: My Note\ndate: 2026-01-01\n---\n# Heading\nBody text\n")
        chunks = self.chunker.chunk_file(str(md))
        assert all("---" not in c.text for c in chunks)
        assert chunks[0].source_title == "My Note"

    def test_frontmatter_date_extracted(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("---\ndate: 2026-01-15\n---\nSome content\n")
        chunks = self.chunker.chunk_file(str(md))
        assert chunks[0].source_date == "2026-01-15"

    def test_empty_sections_skipped(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("# Empty\n\n# Has Content\nSomething here\n")
        chunks = self.chunker.chunk_file(str(md))
        assert len(chunks) == 1
        assert "Something" in chunks[0].text

    def test_min_chunk_length_filters_short(self, tmp_config, tmp_path):
        tmp_config_obj = tmp_config.model_copy(update={"min_chunk_length": 100})
        chunker = MarkdownChunker(tmp_config_obj)
        md = tmp_path / "note.md"
        md.write_text("# Heading\nShort.\n# Other\n" + "Long content. " * 20 + "\n")
        chunks = chunker.chunk_file(str(md))
        assert all(len(c.text) >= 100 for c in chunks)

    def test_block_chunking_disabled_returns_single_chunk(self, tmp_config, tmp_path):
        cfg = tmp_config.model_copy(update={"block_chunking_enabled": False})
        chunker = MarkdownChunker(cfg)
        md = tmp_path / "note.md"
        md.write_text("# A\nContent A\n# B\nContent B\n")
        chunks = chunker.chunk_file(str(md))
        assert len(chunks) == 1

    def test_chunk_ids_unique(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("# A\nContent\n# B\nMore content\n")
        chunks = self.chunker.chunk_file(str(md))
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_ids_deterministic(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("# A\nContent\n# B\nMore\n")
        a = [c.id for c in self.chunker.chunk_file(str(md))]
        b = [c.id for c in self.chunker.chunk_file(str(md))]
        assert a == b

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            self.chunker.chunk_file("/nonexistent/note.md")

    def test_unsupported_extension_raises(self, tmp_path):
        txt = tmp_path / "note.txt"
        txt.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported"):
            self.chunker.chunk_file(str(txt))

    def test_embedding_empty(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("Some content")
        chunks = self.chunker.chunk_file(str(md))
        assert all(c.embedding == [] for c in chunks)
```

**Step 2: Run tests -- expect FAIL (module not found)**

Run: `pytest tests/test_markdown_chunker.py -v`

**Step 3: Implement MarkdownChunker**

Create `src/smart_search/markdown_chunker.py` with:
- `__init__(self, config)` storing config
- `chunk_file(self, file_path) -> List[Chunk]` that:
  1. Validates file exists and extension
  2. Reads file text
  3. Calls `_strip_frontmatter()` to extract YAML metadata and body
  4. If `block_chunking_enabled` is False, return whole body as one chunk
  5. Calls `_split_by_headings()` to get sections with heading hierarchy
  6. Filters by `min_chunk_length`
  7. Creates Chunk objects with proper metadata
- `_strip_frontmatter(text) -> (metadata_dict, body_text)`
- `_split_by_headings(body) -> List[dict]` each with keys: text, section_path, level

**Step 4: Run tests -- expect PASS**

Run: `pytest tests/test_markdown_chunker.py -v`

**Step 5: Commit**

`feat: add MarkdownChunker with heading-based section splitting`

---

### Task 3: Indexer router -- support both chunkers

**Files:**
- Modify: `src/smart_search/indexer.py`
- Modify: `tests/test_indexer.py`

**Step 1: Write failing tests for Markdown routing**

Add to `tests/test_indexer.py`:

```python
@pytest.fixture
def mock_md_chunker():
    chunker = MagicMock()
    chunker.chunk_file.side_effect = lambda path: _make_fake_chunks(path, source_type="md")
    return chunker

def test_md_file_routes_to_markdown_chunker(tmp_config, mock_md_chunker, mock_chunker, mock_embedder, tmp_path):
    store = ChunkStore(tmp_config)
    store.initialize()
    indexer = DocumentIndexer(
        config=tmp_config, chunker=mock_chunker,
        embedder=mock_embedder, store=store,
        markdown_chunker=mock_md_chunker,
    )
    md = tmp_path / "note.md"
    md.write_text("# Test\nContent")
    result = indexer.index_file(str(md))
    assert result.status == "indexed"
    mock_md_chunker.chunk_file.assert_called_once()
    mock_chunker.chunk_file.assert_not_called()
```

**Step 2: Run test -- expect FAIL (unexpected keyword markdown_chunker)**

**Step 3: Modify indexer.py**

- Add `markdown_chunker` parameter to `__init__` (optional, defaults to None)
- In `index_file`, route `.md` to `self._markdown_chunker`, others to `self._chunker`

**Step 4: Run all tests -- expect PASS**

Run: `pytest tests/test_indexer.py -v`

**Step 5: Commit**

`feat: indexer routes .md files to MarkdownChunker`

---

### Task 4: Store -- add remove_file_record

**Files:**
- Modify: `src/smart_search/store.py`
- Modify: `tests/test_store.py`

**Step 1: Write failing test**

```python
def test_remove_file_record(self, store):
    store.record_file_indexed("/tmp/test.md", "abc123", 5)
    assert store.is_file_indexed("/tmp/test.md", "abc123")
    store.remove_file_record("/tmp/test.md")
    assert not store.is_file_indexed("/tmp/test.md", "abc123")
```

**Step 2: Run -- expect FAIL (method not found)**

**Step 3: Implement remove_file_record in store.py**

```python
def remove_file_record(self, source_path: str) -> None:
    self._sqlite_conn.execute(
        "DELETE FROM indexed_files WHERE source_path = ?", (source_path,)
    )
    self._sqlite_conn.commit()
```

**Step 4: Run -- expect PASS**

**Step 5: Commit**

`feat: add remove_file_record to ChunkStore`

---

### Task 5: File watcher

**Files:**
- Create: `src/smart_search/watcher.py`
- Create: `tests/test_watcher.py`
- Modify: `pyproject.toml` (add watchdog)

**Step 1: Add watchdog to pyproject.toml**

**Step 2: Write failing tests for FileWatcher**

Tests covering:
- Watcher calls indexer on file create
- Watcher calls indexer on file modify
- Watcher calls store.delete_chunks_for_file + remove_file_record on delete
- Watcher ignores excluded directories
- Watcher ignores unsupported extensions
- Debounce: rapid writes produce single index call

**Step 3: Implement FileWatcher**

- `__init__(config, indexer, store)` -- stores deps
- `start()` -- creates watchdog Observer for each watch_directory
- `stop()` -- stops all observers
- `_is_excluded(path)` -- checks against exclude_patterns
- `_on_event(event)` -- debounced handler calling indexer/store
- Uses threading.Timer for debounce

**Step 4: Run tests -- expect PASS**

**Step 5: Commit**

`feat: add FileWatcher with debounced indexing and exclusion patterns`

---

### Task 6: knowledge_ingest MCP tool + server watcher startup

**Files:**
- Modify: `src/smart_search/server.py`
- Modify: `tests/test_server.py`

**Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_knowledge_ingest_tool_exists(server):
    tools = await server.list_tools()
    assert "knowledge_ingest" in [t.name for t in tools]

@pytest.mark.asyncio
async def test_knowledge_ingest_single_file(server):
    result = await server.call_tool("knowledge_ingest", {"path": "/tmp/test.pdf"})
    text = _get_text(result)
    assert isinstance(text, str)
```

**Step 2: Run -- expect FAIL**

**Step 3: Implement**

- Add `knowledge_ingest` tool to `create_server()`
- Accepts `path: str` and `force: bool = False`
- Detects file vs folder, calls indexer accordingly
- Returns formatted result string
- Add watcher startup logic: if config.watch_directories is non-empty, start FileWatcher

**Step 4: Run all tests -- expect PASS**

Run: `pytest tests/ -v`

**Step 5: Commit**

`feat: add knowledge_ingest MCP tool and watcher startup`

---

### Task 7: Integration test -- end-to-end Markdown indexing

**Files:**
- Modify: `tests/test_indexer.py`

**Step 1: Write end-to-end test**

```python
@pytest.mark.slow
def test_end_to_end_markdown_indexing(tmp_config, tmp_path):
    from smart_search.markdown_chunker import MarkdownChunker
    from smart_search.chunker import DocumentChunker
    from smart_search.embedder import Embedder

    md = tmp_path / "test_note.md"
    md.write_text("---\ntitle: Test Note\n---\n# Section 1\nContent A\n## Section 2\nContent B\n")

    store = ChunkStore(tmp_config)
    store.initialize()
    indexer = DocumentIndexer(
        config=tmp_config,
        chunker=DocumentChunker(tmp_config),
        embedder=Embedder(tmp_config),
        store=store,
        markdown_chunker=MarkdownChunker(tmp_config),
    )
    result = indexer.index_file(str(md))
    assert result.status == "indexed"
    assert result.chunk_count == 2
    chunks = store.get_chunks_for_file(md.resolve().as_posix())
    assert all(len(c.embedding) == 768 for c in chunks)
```

**Step 2: Run -- expect PASS**

Run: `pytest tests/test_indexer.py -m slow -v`

**Step 3: Commit**

`test: add end-to-end Markdown indexing integration test`

---

### Task 8: Final -- run full suite, verify coverage, update pyproject version

**Step 1:** Run `pytest tests/ -m "" -v --cov=smart_search --cov-report=term-missing`
**Step 2:** Verify 80%+ coverage
**Step 3:** Update pyproject.toml version to 0.2.0
**Step 4:** Commit: `chore: bump version to v0.2.0`
