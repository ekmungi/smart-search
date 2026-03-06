# v0.2 Design: Daily Use + Markdown

Date: 2026-03-06
Status: Approved

## Scope

Lean v0.2 (Option C): 7 milestones. Entity tagging (spaCy/GLiNER) deferred.

| # | Milestone | Priority |
|---|-----------|----------|
| M2.1 | Markdown file support | Must |
| M2.2 | Block-level heading chunking | Must |
| M2.3 | File watcher (watchdog) | Must |
| M2.4 | Incremental indexing (watcher integration) | Must |
| M2.5 | File exclusion patterns | Must |
| M2.6 | Indexing config controls | Should |
| M2.9 | knowledge_ingest MCP tool | Must |

## Design Decisions

- Approach A: Strategy pattern -- MarkdownChunker alongside DocumentChunker, indexer routes by extension
- Watch paths: Config-based (`watch_directories`), recursive, any folder (not Obsidian-specific)
- Delete sync: Auto-remove chunks when watched file is deleted
- Index storage: Project data dir (`./data/`), unchanged from v0.1
- No-headings Markdown: Whole note = one chunk
- Images: Deferred to v0.7, schema placeholders remain

## Architecture

### MarkdownChunker (new: `markdown_chunker.py`)

- Reads `.md` files as plain text
- Strips YAML frontmatter (`---` delimiters), parses for title/date/tags
- Splits on heading boundaries (`#`, `##`, `###`)
- Tracks section_path hierarchy (e.g., `["Architecture", "Data Flow"]`)
- No headings -> whole note = one chunk
- Sets source_type="md", content_type="text"
- No sub-splitting for long sections in v0.2
- Pure Python, no Docling dependency

### Indexer Router (modified: `indexer.py`)

- Receives both MarkdownChunker and DocumentChunker in constructor
- Routes by extension: .md -> MarkdownChunker, .pdf/.docx -> DocumentChunker
- Rest of pipeline unchanged: embed -> store

### Config Changes (modified: `config.py`)

New fields:
- `watch_directories: List[str] = []` -- folders to monitor
- `exclude_patterns: List[str] = [".git", ".obsidian", ".trash", "node_modules", ".smart-search"]`
- `block_chunking_enabled: bool = True` -- False = whole-file chunks only
- `min_chunk_length: int = 50` -- skip chunks shorter than this (chars)
- `watcher_debounce_seconds: float = 2.0`
- `supported_extensions` updated to include `.md`

### File Watcher (new: `watcher.py`)

- Uses watchdog library
- Monitors all watch_directories recursively
- Reacts to create/modify/delete for supported extensions
- Debounces rapid changes (configurable, default 2s)
- Exclusion filtering: skips paths matching exclude_patterns (component-level match)
- On create/modify: calls indexer.index_file() (hash-based skip if unchanged)
- On delete: calls store.delete_chunks_for_file() + store.remove_file_record()
- start()/stop() lifecycle, background thread, non-blocking
- Not started if watch_directories is empty

### knowledge_ingest Tool (modified: `server.py`)

- Accepts path (file or folder) and optional force (bool)
- Routes to indexer.index_file() or index_folder()
- Returns formatted result string

### Delete Sync (modified: `store.py`)

- New method: remove_file_record(source_path) -- deletes SQLite indexed_files row
- Watcher calls delete_chunks_for_file() + remove_file_record() on delete events

## Dependencies

New: `watchdog`
No other new dependencies.

## Files Changed

| File | Action |
|------|--------|
| `src/smart_search/markdown_chunker.py` | New |
| `src/smart_search/watcher.py` | New |
| `src/smart_search/config.py` | Modified |
| `src/smart_search/indexer.py` | Modified |
| `src/smart_search/server.py` | Modified |
| `src/smart_search/store.py` | Modified |
| `pyproject.toml` | Modified (add watchdog) |
| `tests/test_markdown_chunker.py` | New |
| `tests/test_watcher.py` | New |
