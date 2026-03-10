# smart-search

Local-first MCP server for semantic search over Markdown, PDF, and DOCX documents. Runs entirely on CPU with no cloud dependencies, no GPU required. Designed to make your personal knowledge base searchable from Claude Code.

**Version:** 0.2.0

---

## What It Does

- Indexes Markdown notes, PDFs, and DOCX files into a searchable knowledge base
- Heading-based chunking for Markdown, structure-aware hierarchical chunking for documents
- Generates embeddings with nomic-embed-text-v1.5 (ONNX, CPU-optimized)
- Stores vectors in LanceDB and metadata in SQLite -- both file-based, no server needed
- Watches directories for changes and re-indexes automatically
- Exposes three MCP tools to Claude Code: search, stats, and ingest

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

## MCP Tools

The server exposes three tools to Claude Code.

### `knowledge_search`

Search the knowledge base for document chunks matching a natural language query.

| Parameter  | Type            | Required | Default    | Description                                              |
|------------|-----------------|----------|------------|----------------------------------------------------------|
| `query`    | string          | Yes      | -          | Natural language search query                            |
| `limit`    | integer         | No       | `10`       | Maximum number of chunks to return                       |
| `mode`     | string          | No       | `"hybrid"` | Search mode: `semantic`, `keyword`, or `hybrid`          |
| `doc_types`| list of strings | No       | `null`     | Filter by file type, e.g. `["pdf"]` or `["pdf", "md"]`  |

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

Supports `.md`, `.pdf`, and `.docx` files. Uses hash-based change detection to skip unchanged files.

---

## File Watching

smart-search can watch directories and automatically re-index files when they change. Configure via environment variable:

```bash
SMART_SEARCH_WATCH_DIRECTORIES='["C:/Users/me/notes", "C:/Users/me/papers"]'
```

The watcher monitors all subdirectories recursively. Files matching exclude patterns (`.git`, `.obsidian`, `node_modules`, etc.) are ignored. Deleted files are automatically removed from the index.

---

## Configuration

All settings are overridden with environment variables prefixed `SMART_SEARCH_`.

| Environment Variable                  | Default                            | Description                                      |
|---------------------------------------|------------------------------------|--------------------------------------------------|
| `SMART_SEARCH_EMBEDDING_MODEL`        | `nomic-ai/nomic-embed-text-v1.5`   | Hugging Face model identifier                    |
| `SMART_SEARCH_EMBEDDING_DIMENSIONS`   | `768`                              | Output vector dimensions                         |
| `SMART_SEARCH_EMBEDDING_BACKEND`      | `onnx`                             | Backend: `onnx` or `pytorch`                     |
| `SMART_SEARCH_CHUNK_MAX_TOKENS`       | `512`                              | Maximum tokens per chunk                         |
| `SMART_SEARCH_LANCEDB_PATH`           | `./data/vectors`                   | Directory for LanceDB vector store               |
| `SMART_SEARCH_SQLITE_PATH`            | `./data/metadata.db`               | Path to SQLite metadata database                 |
| `SMART_SEARCH_LANCEDB_TABLE_NAME`     | `chunks`                           | LanceDB table name                               |
| `SMART_SEARCH_SUPPORTED_EXTENSIONS`   | `[".pdf", ".docx", ".md"]`         | File types to index                              |
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
from smart_search.chunker import DocumentChunker
from smart_search.embedder import Embedder
from smart_search.markdown_chunker import MarkdownChunker
from smart_search.store import ChunkStore
from smart_search.indexer import DocumentIndexer

config = get_config()
store = ChunkStore(config)
store.initialize()

indexer = DocumentIndexer(
    config=config,
    chunker=DocumentChunker(config),
    embedder=Embedder(config),
    store=store,
    markdown_chunker=MarkdownChunker(config),
)

# Index a single file
result = indexer.index_file("/path/to/document.pdf")
print(result.status, result.chunk_count)

# Index a folder (recursively finds .md, .pdf, .docx)
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
  server.py           - FastMCP entry point; MCP tool definitions
  indexer.py           - Document ingestion pipeline (chunk, embed, store, dedup)
  chunker.py           - Docling HierarchicalChunker for PDF/DOCX
  markdown_chunker.py  - Heading-based Markdown section splitter
  watcher.py           - Watchdog file watcher with debounce
  embedder.py          - nomic-embed-text-v1.5 ONNX embedding generation
  store.py             - LanceDB vector store + SQLite metadata store
  search.py            - Semantic search with Smart Context formatting
  models.py            - Pydantic models: Chunk, SearchResult, IndexStats
  config.py            - Settings with SMART_SEARCH_ env var overrides

tests/
  test_server.py             - MCP tool registration and dispatch
  test_indexer.py            - Indexer pipeline and routing
  test_markdown_chunker.py   - Markdown heading-based chunking
  test_watcher.py            - File watcher and debounce
  test_store.py              - LanceDB and SQLite operations
  test_search.py             - Search formatting and filtering
  test_config.py             - Config fields and env var overrides
  test_models.py             - Pydantic model validation
  test_chunker.py            - DocumentChunker (slow: requires Docling)
  test_embedder.py           - Embedder (slow: loads ONNX model)
```

---

## Tech Stack

| Component        | Library / Model                                        |
|------------------|--------------------------------------------------------|
| MCP server       | FastMCP                                                |
| Document parsing | Docling (DocumentConverter, HierarchicalChunker)       |
| Markdown parsing | Custom heading-based splitter (no dependencies)        |
| Embeddings       | nomic-ai/nomic-embed-text-v1.5 via sentence-transformers + ONNX |
| Vector store     | LanceDB (file-based, no server)                        |
| Metadata store   | SQLite (Python stdlib)                                 |
| File watching    | Watchdog                                               |
| Config           | pydantic-settings                                      |
| Build            | Hatchling                                              |

---

## License

MIT
