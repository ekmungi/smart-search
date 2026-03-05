# smart-search

A local-first MCP server that makes PDF and DOCX files searchable from Claude Code via semantic search. Documents are extracted with Docling, chunked using structure-aware hierarchical chunking, embedded with nomic-embed-text-v1.5 (ONNX), and stored in LanceDB. Everything runs on CPU with no cloud dependencies and no GPU required.

**Version:** 0.1.0 (Foundation)

---

## MCP Tools

The server exposes two tools to Claude Code.

### `knowledge_search`

Search the knowledge base for document chunks matching a natural language query.

| Parameter  | Type            | Required | Default    | Description                                              |
|------------|-----------------|----------|------------|----------------------------------------------------------|
| `query`    | string          | Yes      | -          | Natural language search query                            |
| `limit`    | integer         | No       | `10`       | Maximum number of chunks to return                       |
| `mode`     | string          | No       | `"hybrid"` | Search mode: `semantic`, `keyword`, or `hybrid`          |
| `doc_types`| list of strings | No       | `null`     | Filter by file type, e.g. `["pdf"]` or `["pdf", "docx"]`|

Returns a formatted block with source file name, page number, section heading path, chunk text, and relevance score for each result.

> **Note (v0.1):** All three mode values currently execute semantic search. Keyword and hybrid modes using SQLite FTS5 + Reciprocal Rank Fusion are planned for v0.3.

### `knowledge_stats`

Returns counts and metadata about the indexed knowledge base: document count, chunk count, index size in MB, last indexed timestamp, and file formats present.

No parameters.

---

## Prerequisites

- Python 3.11 or later
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`

The embedding model (`nomic-ai/nomic-embed-text-v1.5`) is downloaded from Hugging Face on first run and cached locally. No GPU or internet connection is required after that initial download.

---

## Installation

Clone the repository and install in editable mode with development dependencies:

```bash
git clone <repository-url>
cd smart-search
uv pip install -e ".[dev]"
```

To install without development dependencies:

```bash
uv pip install -e .
```

---

## Indexing Documents

Documents must be indexed before they can be searched. Use `DocumentIndexer` directly from Python, or integrate it into a CLI or script.

**Index a single file:**

```python
from smart_search.config import get_config
from smart_search.chunker import DocumentChunker
from smart_search.embedder import Embedder
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
)

result = indexer.index_file("/path/to/document.pdf")
print(result.status, result.chunk_count)
```

**Index a folder:**

```python
result = indexer.index_folder("/path/to/documents", recursive=True)
print(f"Indexed: {result.indexed}, Skipped: {result.skipped}, Failed: {result.failed}")
```

Files already indexed at the same content hash are skipped automatically. Pass `force=True` to re-index regardless.

---

## MCP Server Setup

### Configure Claude Code

Add an entry to your `.mcp.json` pointing to the Python interpreter in your virtual environment:

```json
{
  "mcpServers": {
    "smart-search": {
      "command": "/path/to/your/venv/bin/python",
      "args": ["-m", "smart_search.server"],
      "cwd": "/path/to/smart-search"
    }
  }
}
```

On Windows, use the full path to `python.exe` inside your virtual environment's `Scripts` directory.

### Run the server manually

```bash
python -m smart_search.server
```

The server communicates over stdio (MCP standard transport).

---

## Configuration

All settings can be overridden with environment variables prefixed `SMART_SEARCH_`. The defaults are suitable for local use out of the box.

| Environment Variable                  | Default                            | Description                                      |
|---------------------------------------|------------------------------------|--------------------------------------------------|
| `SMART_SEARCH_EMBEDDING_MODEL`        | `nomic-ai/nomic-embed-text-v1.5`   | Hugging Face model identifier                    |
| `SMART_SEARCH_EMBEDDING_DIMENSIONS`   | `768`                              | Output vector dimensions                         |
| `SMART_SEARCH_EMBEDDING_BACKEND`      | `onnx`                             | Backend: `onnx` (default) or `pytorch`           |
| `SMART_SEARCH_CHUNK_MAX_TOKENS`       | `512`                              | Maximum tokens per chunk                         |
| `SMART_SEARCH_LANCEDB_PATH`           | `./data/vectors`                   | Directory for LanceDB vector store               |
| `SMART_SEARCH_SQLITE_PATH`            | `./data/metadata.db`               | Path to SQLite metadata database                 |
| `SMART_SEARCH_LANCEDB_TABLE_NAME`     | `chunks`                           | LanceDB table name                               |
| `SMART_SEARCH_SEARCH_DEFAULT_LIMIT`   | `10`                               | Default result count for `knowledge_search`      |
| `SMART_SEARCH_SEARCH_DEFAULT_MODE`    | `hybrid`                           | Default search mode for `knowledge_search`       |
| `SMART_SEARCH_NOMIC_DOCUMENT_PREFIX`  | `search_document: `                | Task prefix applied to document text at index time |
| `SMART_SEARCH_NOMIC_QUERY_PREFIX`     | `search_query: `                   | Task prefix applied to queries at search time    |

Paths are resolved to absolute paths at startup, so relative values are interpreted relative to the working directory where the server process starts.

---

## Running Tests

The test suite uses `pytest`. Tests are split into fast unit tests and slow integration tests that load ML models or process real files.

**Run fast tests only (default):**

```bash
pytest
```

**Run all tests including slow ones:**

```bash
pytest --override-ini="addopts="
```

**Run with coverage:**

```bash
pytest --cov=smart_search --cov-report=term-missing
```

Slow tests are marked with `@pytest.mark.slow`. The default `pytest` invocation excludes them so the suite completes quickly without loading ML models.

---

## Project Structure

```
src/smart_search/
  server.py    - FastMCP entry point; registers knowledge_search and knowledge_stats
  indexer.py   - Document ingestion pipeline (chunk, embed, store, dedup)
  chunker.py   - Docling DocumentConverter and HierarchicalChunker wrapper
  embedder.py  - nomic-embed-text-v1.5 ONNX embedding generation
  store.py     - LanceDB vector store and SQLite metadata store
  search.py    - Semantic search with Smart Context result formatting
  models.py    - Pydantic models: Chunk, SearchResult, IndexStats
  config.py    - Settings with SMART_SEARCH_ environment variable overrides

tests/
  test_models.py   - Chunk, SearchResult, IndexStats validation
  test_config.py   - Environment variable override and path resolution
  test_chunker.py  - DocumentChunker (slow: requires Docling)
  test_embedder.py - Embedder (slow: loads ONNX model)
  test_store.py    - ChunkStore LanceDB and SQLite operations
  test_indexer.py  - DocumentIndexer pipeline integration
  test_search.py   - SearchEngine formatting and filtering
  test_server.py   - FastMCP tool registration and dispatch
```

---

## Tech Stack

| Component       | Library / Model                        |
|-----------------|----------------------------------------|
| MCP server      | FastMCP                                |
| Document parsing| Docling (DocumentConverter, HierarchicalChunker) |
| Embeddings      | nomic-ai/nomic-embed-text-v1.5 via sentence-transformers + ONNX |
| Vector store    | LanceDB                                |
| Metadata store  | SQLite                                 |
| Config          | pydantic-settings                      |
| Build           | Hatchling                              |

