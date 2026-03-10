# smart-search

Local-first MCP server for semantic search over Markdown, PDF, DOCX, PPTX, XLSX, and HTML documents. Runs entirely on CPU with no cloud dependencies, no GPU required. Designed to make your personal knowledge base searchable from Claude Code.

**Version:** 0.3.1

---

## What It Does

- Indexes Markdown notes, PDFs, DOCX, PPTX, XLSX, and HTML files into a searchable knowledge base
- Single pipeline: all non-Markdown files converted to Markdown via MarkItDown, then chunked by headings
- Generates embeddings with nomic-embed-text-v1.5 (ONNX, CPU-optimized)
- Stores vectors in LanceDB and metadata in SQLite -- both file-based, no server needed
- Watches directories for changes and re-indexes automatically
- Exposes MCP tools to Claude Code: search, stats, ingest, folder management, related notes
- CLI for config, watch directories, model management, and index operations with tqdm progress bars
- Persistent config.json with OS-convention data directory

---

## Prerequisites

- Python 3.11 or later
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`

The embedding model (`nomic-ai/nomic-embed-text-v1.5`) downloads from Hugging Face on first run and caches locally. No internet connection is required after that.

---

## Installation

### Option A: Install from GitHub (recommended)

Install directly from the repository -- no PyPI account needed:

```bash
uv pip install git+https://github.com/ekmungi/smart-search.git
```

Or with pip:

```bash
pip install git+https://github.com/ekmungi/smart-search.git
```

This creates the `smart-search` command on your PATH.

### Option B: Install from PyPI (when published)

```bash
uv pip install smart-search
```

### Option C: Local development install

Clone and install in editable mode:

```bash
git clone https://github.com/ekmungi/smart-search.git
cd smart-search
uv pip install -e ".[dev]"
```

### Verify installation

```bash
which smart-search    # Unix/Git Bash
where smart-search    # Windows CMD
```

Should print a path like `.../Scripts/smart-search` (Windows) or `.../bin/smart-search` (Unix).

---

## MCP Server Setup

After installation, register smart-search as an MCP server with Claude Code. Choose one method:

### Method 1: `claude mcp add` (recommended)

If you installed via Option A or B (smart-search is on your PATH):

```bash
claude mcp add smart-search -- smart-search
```

If using a virtual environment where smart-search is installed:

```bash
claude mcp add smart-search -- /path/to/venv/Scripts/smart-search
```

### Method 2: `.mcp.json` file

Create or edit `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "smart-search": {
      "command": "smart-search"
    }
  }
}
```

If smart-search is not on your global PATH, use the full path:

```json
{
  "mcpServers": {
    "smart-search": {
      "command": "/path/to/venv/Scripts/smart-search"
    }
  }
}
```

### Method 3: Python module (no install)

If you prefer not to install the package:

```json
{
  "mcpServers": {
    "smart-search": {
      "command": "/path/to/python",
      "args": ["-m", "smart_search.server"],
      "cwd": "/path/to/smart-search"
    }
  }
}
```

> **Note:** On Windows, use forward slashes in JSON paths or escape backslashes.

---

## Quick Start

1. Install: `uv pip install git+https://github.com/ekmungi/smart-search.git`
2. Register: `claude mcp add smart-search -- smart-search`
3. In Claude Code, ingest your documents:
   - "Use knowledge_ingest to index `C:/Users/me/Documents/notes`"
4. Search:
   - "Search my knowledge base for transformer architecture"

---

## Cheatsheet

### CLI Commands

```bash
smart-search stats                           # Index stats and data directory
smart-search config show                     # Show current configuration
smart-search watch list                      # List watched directories
smart-search watch add /path/to/dir          # Add a watch directory
smart-search watch remove /path/to/dir       # Remove a watch directory
smart-search index list                      # List all indexed files
smart-search index ingest /path              # Index a file or folder
smart-search index ingest /path --ephemeral  # Create a local .smart-search/ index
smart-search index rebuild                   # Re-index all watched directories
smart-search index remove /path              # Remove files from index
smart-search search "query"                  # Search the knowledge base
smart-search search "query" --folder /path   # Search within a folder
smart-search search "query" --limit 5        # Limit results
smart-search search "query" --ephemeral /path # Search a local index
smart-search temp list                       # List ephemeral indexes
smart-search temp cleanup /path              # Remove an ephemeral index
smart-search model show                      # Show current embedding model
smart-search model set model-name --dim 256  # Change embedding model
```

### Claude Code Prompts

| Task | Prompt |
|------|--------|
| Index a folder | "Index my notes in C:/Users/me/vault" |
| Search | "Search my knowledge base for regulatory compliance" |
| Add watch folder | "Add C:/Users/me/papers to the watch list" |
| Remove watch folder | "Stop watching C:/Users/me/old-notes" |
| Check stats | "Show knowledge base statistics" |
| List indexed files | "List all indexed files" |
| Find related notes | "Find notes related to meeting-notes/2026-03-10.md" |
| Read a note | "Read the note at projects/smart-search.md" |
| Force re-index | "Re-index C:/Users/me/vault with force=true" |
| Temp index a folder | "Create a temporary index of C:/Users/me/Downloads/papers" |
| Search temp index | "Search the temp index at C:/Users/me/Downloads/papers for transformers" |
| Clean up temp index | "Clean up the temporary index at C:/Users/me/Downloads/papers" |
| List temp indexes | "List all ephemeral indexes" |

---

## MCP Tools

The server exposes the following tools to Claude Code.

### `knowledge_search`

Search the knowledge base for document chunks matching a natural language query.

| Parameter  | Type            | Required | Default    | Description                                              |
|------------|-----------------|----------|------------|----------------------------------------------------------|
| `query`    | string          | Yes      | -          | Natural language search query                            |
| `limit`    | integer         | No       | `10`       | Maximum number of chunks to return                       |
| `mode`     | string          | No       | `"hybrid"` | Search mode: `semantic`, `keyword`, or `hybrid`          |
| `doc_types`| list of strings | No       | `null`     | Filter by file type, e.g. `["pdf"]` or `["pdf", "md"]`  |
| `folder`   | string          | No       | `null`     | Restrict results to a folder path prefix                 |

Returns formatted results with source file path, page number, section heading, chunk text, and relevance score.

> **Note (v0.2):** All three mode values currently execute semantic search. Keyword and hybrid modes using SQLite FTS5 + Reciprocal Rank Fusion are planned for v0.3.

### `knowledge_stats`

Returns statistics about the indexed knowledge base: document count, chunk count, index size, last indexed timestamp, and formats present.

No parameters.

### `knowledge_ingest`

Index a file or folder into the knowledge base.

| Parameter | Type    | Required | Default | Description                                    |
|-----------|---------|----------|---------|------------------------------------------------|
| `path`    | string  | Yes      | -       | Absolute path to a file or folder to ingest    |
| `force`   | boolean | No       | `false` | Re-index even if file hash is unchanged        |

Supports `.md`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, and `.html` files. Uses hash-based change detection to skip unchanged files.

### `knowledge_add_folder`

Add a folder to the watch list and trigger initial indexing.

| Parameter     | Type   | Required | Description                        |
|---------------|--------|----------|------------------------------------|
| `folder_path` | string | Yes      | Absolute path to the folder        |

### `knowledge_remove_folder`

Stop watching a folder. Optionally remove its indexed data.

| Parameter     | Type    | Required | Default | Description                              |
|---------------|---------|----------|---------|------------------------------------------|
| `folder_path` | string  | Yes      | -       | Path to the folder                       |
| `remove_data` | boolean | No       | `false` | Also delete indexed chunks from this folder |

### `knowledge_list_folders`

List all watched directories and their status. No parameters.

### `knowledge_list_files`

List all indexed files with chunk counts and timestamps. No parameters.

### `find_related`

Find notes similar to a given note by averaging its embeddings.

| Parameter   | Type    | Required | Default | Description                       |
|-------------|---------|----------|---------|-----------------------------------|
| `note_path` | string  | Yes      | -       | Path to the source note           |
| `limit`     | integer | No       | `10`    | Maximum number of related notes   |

### `read_note`

Read a note's content by path, with safety validation against path traversal.

| Parameter   | Type   | Required | Description                        |
|-------------|--------|----------|------------------------------------|
| `note_path` | string | Yes      | Relative path to the note          |

---

## File Watching

smart-search can watch directories and automatically re-index files when they change. Configure via environment variable:

```bash
SMART_SEARCH_WATCH_DIRECTORIES='["C:/Users/me/notes", "C:/Users/me/papers"]'
```

The watcher monitors all subdirectories recursively. Files matching exclude patterns (`.git`, `.obsidian`, `node_modules`, etc.) are ignored. Deleted files are automatically removed from the index.

---

## Configuration

### Data Directory

smart-search stores its data (vectors, metadata, config.json) in an OS-convention directory:

| OS      | Default Path                              |
|---------|-------------------------------------------|
| Windows | `%LOCALAPPDATA%\smart-search`             |
| Linux   | `~/.local/share/smart-search`             |
| macOS   | `~/.local/share/smart-search`             |

Override with: `SMART_SEARCH_DATA_DIR=/custom/path`

### config.json

Persistent configuration is stored in `config.json` in the data directory. Managed via CLI (`smart-search config show`, `smart-search watch add`) or MCP tools (`knowledge_add_folder`, `knowledge_remove_folder`).

### Environment Variables

All settings can be overridden with environment variables prefixed `SMART_SEARCH_`.

| Environment Variable                  | Default                            | Description                                      |
|---------------------------------------|------------------------------------|--------------------------------------------------|
| `SMART_SEARCH_EMBEDDING_MODEL`        | `nomic-ai/nomic-embed-text-v1.5`   | Hugging Face model identifier                    |
| `SMART_SEARCH_EMBEDDING_DIMENSIONS`   | `768`                              | Output vector dimensions                         |
| `SMART_SEARCH_EMBEDDING_BACKEND`      | `onnx`                             | Backend: `onnx` or `pytorch`                     |
| `SMART_SEARCH_CHUNK_MAX_TOKENS`       | `512`                              | Maximum tokens per chunk                         |
| `SMART_SEARCH_LANCEDB_PATH`           | `<data_dir>/vectors`               | Directory for LanceDB vector store               |
| `SMART_SEARCH_SQLITE_PATH`            | `<data_dir>/metadata.db`           | Path to SQLite metadata database                 |
| `SMART_SEARCH_LANCEDB_TABLE_NAME`     | `chunks`                           | LanceDB table name                               |
| `SMART_SEARCH_SUPPORTED_EXTENSIONS`   | `[".pdf", ".docx", ".md", ".pptx", ".xlsx", ".html"]` | File types to index                              |
| `SMART_SEARCH_WATCH_DIRECTORIES`      | `[]`                               | Directories to watch for changes                 |
| `SMART_SEARCH_EXCLUDE_PATTERNS`       | `[".git", ".obsidian", ...]`       | Path components to exclude from indexing         |
| `SMART_SEARCH_BLOCK_CHUNKING_ENABLED` | `true`                             | Enable heading-based Markdown chunking           |
| `SMART_SEARCH_MIN_CHUNK_LENGTH`       | `50`                               | Minimum chunk length in characters               |
| `SMART_SEARCH_WATCHER_DEBOUNCE_SECONDS` | `2.0`                            | Debounce window for file watcher                 |
| `SMART_SEARCH_SEARCH_DEFAULT_LIMIT`   | `10`                               | Default result count                             |
| `SMART_SEARCH_SEARCH_DEFAULT_MODE`    | `hybrid`                           | Default search mode                              |
| `SMART_SEARCH_NOMIC_DOCUMENT_PREFIX`  | `search_document: `                | Task prefix for document text at index time      |
| `SMART_SEARCH_NOMIC_QUERY_PREFIX`     | `search_query: `                   | Task prefix for queries at search time           |

Paths are resolved to absolute at startup relative to the working directory.

---

## Indexing Documents

### Via MCP (recommended)

In Claude Code, ask to ingest files:

```
"Ingest all documents in C:/Users/me/papers"
"Index this file: C:/Users/me/notes/meeting.md"
"Re-index C:/Users/me/papers with force=true"
```

### Via Python API

```python
from smart_search.config import get_config
from smart_search.embedder import Embedder
from smart_search.markdown_chunker import MarkdownChunker
from smart_search.store import ChunkStore
from smart_search.indexer import DocumentIndexer

config = get_config()
store = ChunkStore(config)
store.initialize()

indexer = DocumentIndexer(
    config=config,
    embedder=Embedder(config),
    store=store,
    markdown_chunker=MarkdownChunker(config),
)

# Index a single file
result = indexer.index_file("/path/to/document.pdf")
print(result.status, result.chunk_count)

# Index a folder (recursively finds .md, .pdf, .docx, .pptx, .xlsx, .html)
result = indexer.index_folder("/path/to/documents")
print(f"Indexed: {result.indexed}, Skipped: {result.skipped}, Failed: {result.failed}")
```

Files already indexed at the same content hash are skipped automatically. Pass `force=True` to re-index regardless.

---

## Running Tests

```bash
# Fast tests only (default, no ML model loading)
pytest

# All tests including slow integration tests
pytest -m ""

# With coverage
pytest --cov=smart_search --cov-report=term-missing
```

Slow tests are marked with `@pytest.mark.slow` and require ML models to be downloaded.

---

## Project Structure

```
src/smart_search/
  server.py            - FastMCP entry point; MCP tool definitions
  cli.py               - CLI with subcommands (stats, config, watch, index, search, model)
  indexer.py            - Document ingestion pipeline (chunk, embed, store, dedup)
  markitdown_parser.py  - MarkItDown wrapper: converts any file to Markdown
  markdown_chunker.py   - Heading-based Markdown section splitter
  watcher.py            - Watchdog file watcher with debounce and runtime add/remove
  embedder.py           - nomic-embed-text-v1.5 ONNX embedding generation
  store.py              - LanceDB vector store + SQLite metadata store
  search.py             - Semantic search with Smart Context formatting and folder filter
  models.py             - Pydantic models: Chunk, SearchResult, IndexStats
  config.py             - Settings with SMART_SEARCH_ env var overrides
  config_manager.py     - Persistent config.json with atomic writes
  data_dir.py           - OS-convention data directory resolution
  protocols.py          - Extension point protocols (Embedder, Chunker, Enricher, Retriever)
  index_metadata.py     - Index metadata tracking in SQLite
  reader.py             - Note reader with path traversal safety

tests/
  test_server.py             - MCP tool registration, dispatch, folder tools
  test_cli.py                - CLI subcommand tests
  test_indexer.py            - Indexer pipeline and routing
  test_markitdown_parser.py  - MarkItDown document conversion
  test_markdown_chunker.py   - Markdown heading-based chunking
  test_watcher.py            - File watcher, debounce, runtime management
  test_store.py              - LanceDB, SQLite, file listing, folder removal
  test_search.py             - Search formatting, filtering, folder filter
  test_config.py             - Config fields, env vars, data dir defaults
  test_config_manager.py     - Config manager CRUD and persistence
  test_data_dir.py           - Data directory resolution
  test_protocols.py          - Protocol compliance tests
  test_index_metadata.py     - Index metadata tracking
  test_models.py             - Pydantic model validation
  test_embedder.py           - Embedder (slow: loads ONNX model)
```

---

## Tech Stack

| Component        | Library / Model                                        |
|------------------|--------------------------------------------------------|
| MCP server       | FastMCP                                                |
| Document parsing | MarkItDown (PDF, DOCX, PPTX, XLSX, HTML)               |
| Markdown parsing | Custom heading-based splitter (no dependencies)        |
| Pipeline         | All files -> MarkItDown -> MarkdownChunker (single path) |
| Embeddings       | nomic-ai/nomic-embed-text-v1.5 via sentence-transformers + ONNX |
| Vector store     | LanceDB (file-based, no server)                        |
| Metadata store   | SQLite (Python stdlib)                                 |
| File watching    | Watchdog                                               |
| Config           | pydantic-settings                                      |
| Build            | Hatchling                                              |

---

## License

MIT
