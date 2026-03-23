# Smart Search

A personal, local-first knowledge management system. Index your documents, notes, spreadsheets, and more into a searchable knowledge base that connects with everything running locally -- Claude Code (MCP), a desktop app, REST API, or CLI. Runs entirely on your machine: no cloud, no GPU, no subscriptions.

**Version:** 0.12.0 | **License:** MIT

---

## Why Smart Search?

Your knowledge is scattered across notes, PDFs, slide decks, and spreadsheets. Smart Search brings it together:

- **Search everything locally.** 14 document formats indexed into one knowledge base with hybrid search (semantic + keyword + reranking). Find what you need whether you remember the exact phrase or just the concept.
- **Connect with your tools.** MCP server for Claude Code, REST API for scripts and automation, CLI for power users, desktop app for visual management. One index, many interfaces.
- **Stay responsive.** All heavy lifting runs in an out-of-process Python server. Your editor, your Obsidian vault, your desktop -- nothing freezes during indexing.
- **Own your data.** Everything stays on disk -- LanceDB vectors and SQLite metadata in a local directory. No cloud sync, no telemetry, no accounts. MIT licensed.
- **Keep it lightweight.** CPU-only ONNX embeddings with lazy loading. The model loads when you search, unloads after 60 seconds idle. Steady-state RAM under 200MB.

---

## Features

### Search

- **Hybrid search** (default): combines vector similarity with FTS5 keyword matching via Reciprocal Rank Fusion, cross-encoder reranking, and MMR diversity selection
- **Cross-encoder reranking**: jointly scores (query, document) pairs with TinyBERT-L-2 for higher precision than bi-encoder similarity alone (+5-15 nDCG@10 in benchmarks)
- **MMR diversity**: eliminates redundant chunks from the same document, ensuring results cover distinct information
- **Semantic mode**: pure vector search with configurable relevance threshold
- **Keyword mode**: BM25 ranking via SQLite FTS5 with porter stemming and stopword removal
- **Folder filtering**: restrict results to specific directories
- **Find related**: discover similar documents by averaging chunk embeddings
- **[Search pipeline architecture](https://ekmungi.github.io/smart-search/search-pipeline.html)**: interactive visual diagram of the full retrieval pipeline

### Supported Files

| Category | Formats |
|----------|---------|
| Documents | `.pdf`, `.docx`, `.epub` |
| Spreadsheets | `.xlsx`, `.xls`, `.csv` |
| Presentations | `.pptx` |
| Email | `.msg` |
| Text | `.md`, `.txt` |
| Web | `.html`, `.htm` |
| Data | `.json`, `.jsonl` |
| Notebooks | `.ipynb` |

### Indexing

- **14 formats**: all non-Markdown files converted via MarkItDown, then chunked by headings
- **Background indexing**: non-blocking with per-folder progress, cancellation, and auto-resume on restart
- **Hash-based dedup**: unchanged files are skipped automatically
- **Ephemeral indexes**: create temporary `.smart-search/` indexes inside any folder

### Desktop App

- **Tauri v2 + React** desktop application with warm dark theme
- **Quick Search**: `Ctrl+Space` global hotkey opens a floating search overlay (configurable shortcut)
- **Dashboard**: index stats, per-folder status, model download progress
- **Folder Manager**: add/remove watch directories with drag-and-drop
- **Settings**: font scaling, embedding model selection, Matryoshka dimension picker, relevance threshold, autostart, MCP registration
- **Repair Index**: one-click maintenance (orphan removal, FTS5 rebuild, LanceDB compaction, compatibility check)
- **System tray**: background operation with tray icon

### Embedding

- **Default model**: snowflake-arctic-embed-m-v2.0 (int8 ONNX, 297MB, 0.554 MTEB retrieval)
- **Matryoshka truncation**: 256-dim default, configurable per model
- **Lazy loading**: model loads on demand, unloads after 60s idle to free RAM
- **Curated registry**: switchable models with quality/size metadata
- **CPU-only**: ONNX Runtime, no GPU required

### Architecture

- **Out-of-process**: all heavy lifting in Python, Obsidian/desktop stays responsive
- **MCP server**: 11 tools for Claude Code integration
- **REST API**: 20 endpoints on `localhost:9742`
- **CLI**: `smart-search` command with subcommands for all operations
- **File-based storage**: LanceDB (vectors) + SQLite (metadata + FTS5), no database server

### System Requirements

| | Requirement |
|--|-------------|
| OS | Windows 10/11 (x64) |
| RAM | 2 GB minimum (~200 MB idle) |
| Storage | ~300 MB (with AI model) |
| Runtime | Python 3.11+ (bundled in desktop installer) |
| Network | Not required |

---

## Quick Start

### Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`

### Install

```bash
uv pip install git+https://github.com/ekmungi/smart-search.git
```

### Register with Claude Code

```bash
claude mcp add smart-search -- smart-search
```

### Use

In Claude Code:
```
"Add C:/Users/me/vault to the knowledge base"
"Search my knowledge base for transformer architecture"
"Find notes related to meeting-notes/2026-03-10.md"
```

---

## Installation Options

### Option A: Install from GitHub (recommended)

```bash
uv pip install git+https://github.com/ekmungi/smart-search.git
```

Or with pip:

```bash
pip install git+https://github.com/ekmungi/smart-search.git
```

This creates the `smart-search` command on your PATH.

### Option B: Local development install

```bash
git clone https://github.com/ekmungi/smart-search.git
cd smart-search
uv pip install -e ".[dev]"
```

### Option C: Desktop app

Download the installer from the Releases page. The desktop app bundles the Python backend as a sidecar -- no Python installation required.

### Verify installation

```bash
smart-search stats
```

---

## MCP Server Setup

Register smart-search as an MCP server with Claude Code:

### Method 1: `claude mcp add` (recommended)

```bash
claude mcp add smart-search -- smart-search
```

With a virtual environment:

```bash
claude mcp add smart-search -- /path/to/venv/Scripts/smart-search
```

### Method 2: `.mcp.json` file

```json
{
  "mcpServers": {
    "smart-search": {
      "command": "smart-search"
    }
  }
}
```

### Method 3: Python module

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

## CLI Cheatsheet

```bash
# Index management
smart-search stats                           # Index stats and data directory
smart-search index ingest /path              # Index a file or folder
smart-search index ingest /path --ephemeral  # Create a local .smart-search/ index
smart-search index list                      # List all indexed files
smart-search index rebuild                   # Re-index all watched directories
smart-search index remove /path              # Remove files from index

# Search
smart-search search "query"                  # Hybrid search (default)
smart-search search "query" --mode semantic  # Vector-only search
smart-search search "query" --mode keyword   # FTS5 keyword search
smart-search search "query" --folder /path   # Search within a folder
smart-search search "query" --limit 5        # Limit results

# Watch directories
smart-search watch list                      # List watched directories
smart-search watch add /path/to/dir          # Add a watch directory
smart-search watch remove /path/to/dir       # Remove a watch directory

# Configuration
smart-search config show                     # Show current configuration
smart-search model show                      # Show current embedding model
smart-search model set model-name --dim 256  # Change embedding model

# Server
smart-search serve                           # Start HTTP server (port 9742)
smart-search mcp                             # Start MCP server (stdio)

# Ephemeral indexes
smart-search temp list                       # List ephemeral indexes
smart-search temp cleanup /path              # Remove an ephemeral index
```

---

## Claude Code Prompts

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
| Temp index | "Create a temporary index of C:/Users/me/Downloads/papers" |
| Search temp index | "Search the temp index at C:/Users/me/Downloads/papers for transformers" |
| Clean up temp index | "Clean up the temporary index at C:/Users/me/Downloads/papers" |

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `knowledge_search` | Search with query, mode (semantic/keyword/hybrid), folder filter, doc type filter |
| `knowledge_stats` | Index statistics: documents, chunks, size, formats |
| `knowledge_ingest` | Index a file or folder (background for directories) |
| `knowledge_add_folder` | Add a folder to the watch list and trigger indexing |
| `knowledge_remove_folder` | Stop watching a folder, optionally delete data |
| `knowledge_list_folders` | List watched directories and their status |
| `knowledge_list_files` | List indexed files with chunk counts |
| `find_related` | Find documents similar to a given note |
| `read_note` | Read a note's content (supports PDF, DOCX via MarkItDown) |
| `knowledge_temp_index` | Create an ephemeral index inside a folder |
| `knowledge_temp_cleanup` | Delete an ephemeral index |

---

## REST API

The HTTP server runs on `localhost:9742` with 21 endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Server health, version, uptime |
| GET | `/api/stats` | Index statistics |
| GET | `/api/search?q=...&mode=hybrid` | Search with mode, folder filter |
| GET | `/api/folders` | List watched folders |
| POST | `/api/folders` | Add folder (returns 202, background indexing) |
| DELETE | `/api/folders?path=...` | Remove folder |
| GET | `/api/files` | List indexed files |
| POST | `/api/ingest` | Index file (sync) or folder (202 async) |
| GET | `/api/indexing/status` | Background indexing progress |
| GET | `/api/config` | Current configuration |
| PUT | `/api/config` | Update configuration |
| GET | `/api/models` | Available embedding models |
| GET | `/api/model/status` | Model cache status |
| GET | `/api/model/loaded` | Model memory status |
| GET | `/api/find-related?note_path=...` | Find related documents |
| POST | `/api/repair` | Run index maintenance (orphans, FTS5, compaction) |
| POST | `/api/ephemeral/index` | Create ephemeral index |
| GET | `/api/ephemeral` | List ephemeral indexes |
| DELETE | `/api/ephemeral?folder_path=...` | Delete ephemeral index |

---

## Configuration

### Data Directory

| OS | Default Path |
|----|--------------|
| Windows | `%LOCALAPPDATA%\smart-search` |
| Linux | `~/.local/share/smart-search` |
| macOS | `~/.local/share/smart-search` |

Override with: `SMART_SEARCH_DATA_DIR=/custom/path`

### config.json

Persistent configuration stored in the data directory. Managed via CLI, REST API, or desktop Settings panel.

### Environment Variables

All settings can be overridden with `SMART_SEARCH_` prefixed variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SMART_SEARCH_EMBEDDING_MODEL` | `Snowflake/snowflake-arctic-embed-m-v2.0` | Embedding model |
| `SMART_SEARCH_EMBEDDING_DIMENSIONS` | `256` | Vector dimensions (Matryoshka) |
| `SMART_SEARCH_WATCH_DIRECTORIES` | `[]` | Directories to watch |
| `SMART_SEARCH_SEARCH_DEFAULT_MODE` | `hybrid` | Default search mode |
| `SMART_SEARCH_RELEVANCE_THRESHOLD` | `0.30` | Minimum similarity score (semantic mode) |
| `SMART_SEARCH_CHUNK_MAX_TOKENS` | `512` | Maximum tokens per chunk |
| `SMART_SEARCH_SUPPORTED_EXTENSIONS` | `[".md", ".txt", ".pdf", ".docx", ".epub", ".xlsx", ".xls", ".csv", ".pptx", ".html", ".htm", ".json", ".jsonl", ".msg", ".ipynb"]` | File types to index |
| `SMART_SEARCH_EXCLUDE_PATTERNS` | `[".git", ".obsidian", "node_modules", ...]` | Excluded directories |
| `SMART_SEARCH_WATCHER_DEBOUNCE_SECONDS` | `2.0` | File watcher debounce |
| `SMART_SEARCH_SEARCH_DEFAULT_LIMIT` | `10` | Default result count |

---

## Architecture

All clients connect to the **same HTTP server** on port 9742. The server is the single source of truth -- there is only one backend process.

```
                         ┌─────────────────────────┐
                         │   HTTP Server (:9742)    │
                         │   smart-search serve     │
                         │   (FastAPI, 20 endpoints)│
                         └──────┬──┬──┬────────────┘
                                │  │  │
                 ┌──────────────┘  │  └──────────────┐
                 │                 │                  │
          ┌──────┴──────┐  ┌──────┴──────┐   ┌──────┴──────┐
          │  Desktop UI │  │  MCP Server │   │     CLI     │
          │  (Tauri v2) │  │  (proxy)    │   │  smart-search│
          │  fetch()    │  │  → :9742    │   │  search/etc │
          └─────────────┘  └─────────────┘   └─────────────┘
          Started by user   Started by         Run manually
          (or autostart)    Claude Code        in terminal
```

**Who starts the HTTP server?**

- **Desktop app running**: the Tauri app starts the server as a sidecar process. When you quit from the system tray, it kills the server.
- **No desktop app**: run `smart-search serve` manually, or the MCP tools will fail.

**Key point**: the MCP server does NOT run its own backend. It is a thin translator -- MCP protocol in, HTTP request to `:9742`, response back as MCP result. If the HTTP server is not running, MCP tools will return errors.

### Component Details

```
Backend (Python, all share the HTTP server)
  http.py / http_routes.py       FastAPI app, 20 endpoints
  server.py / mcp_client.py      MCP server, proxies to HTTP
  search.py                      Hybrid search: vector + FTS5 + RRF + rerank + MMR
  fts.py                         FTS5 keyword search, BM25 ranking
  fusion.py                      Reciprocal Rank Fusion (k=60)
  reranker.py                    Cross-encoder reranking (TinyBERT, lazy-load)
  mmr.py                         Maximum Marginal Relevance diversity selection
  query_preprocessor.py          Stopword removal (FTS5), query normalization
  indexer.py                     Document ingestion pipeline
  markitdown_parser.py           File -> Markdown conversion
  markdown_chunker.py            Heading-based section splitting
  embedder.py                    ONNX embedding with lazy load/unload
  store.py                       LanceDB vectors + SQLite metadata + FTS5
  startup.py                     Orphan reconciliation, FTS5 backfill, repair
  watcher.py                     Watchdog file watcher with debounce
  indexing_task.py               Background task manager with cancellation
  config_manager.py              Persistent config.json

Storage (file-based, no database server)
  LanceDB      vectors/ directory (columnar, sub-50ms search)
  SQLite       metadata.db (indexed_files + chunks_fts virtual table)

Desktop (Tauri v2)
  Rust         System tray, sidecar manager, global shortcut
  React        Dashboard, Folder Manager, Settings, Quick Search
```

### Data Flow

```
File -> MarkItDown (non-.md) -> Markdown -> MarkdownChunker -> Chunks
     -> Embedder -> LanceDB + SQLite FTS5
```

### Search Flow (hybrid mode)

```
Query -> Preprocess (stopwords / normalization)
      -> Vector search (LanceDB)    ─┐
      -> Keyword search (FTS5 BM25) ─┼─> RRF Fusion
                                          -> Cross-Encoder Rerank (TinyBERT, 30-60ms)
                                              -> MMR Diversity (lambda=0.8, <1ms)
                                                  -> Final Results
```

For the full pipeline architecture with resource budgets and configuration reference, see [docs/search-architecture.md](docs/search-architecture.md) or the [interactive visual diagram](https://ekmungi.github.io/smart-search/search-pipeline.html).

---

## Running Tests

```bash
# Fast tests only (default)
pytest

# All tests including slow integration tests
pytest -m ""

# With coverage
pytest --cov=smart_search --cov-report=term-missing
```

425+ tests covering all modules. Slow tests (marked `@pytest.mark.slow`) require ML models to be downloaded.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| MCP server | FastMCP |
| HTTP server | FastAPI + Uvicorn |
| Document parsing | MarkItDown (14 formats: PDF, DOCX, XLSX, PPTX, EPUB, CSV, MSG, HTML, TXT, JSON, IPYNB) |
| Markdown parsing | Custom heading-based splitter |
| Embeddings | snowflake-arctic-embed-m-v2.0 via ONNX Runtime |
| Vector store | LanceDB (file-based, columnar) |
| Metadata + FTS | SQLite (FTS5 with porter stemming) |
| Search fusion | Reciprocal Rank Fusion (RRF, k=60) |
| Reranking | cross-encoder/ms-marco-TinyBERT-L-2-v2 via ONNX Runtime |
| Diversity | Maximum Marginal Relevance (MMR, lambda=0.8) |
| File watching | Watchdog |
| Desktop | Tauri v2 + React + Tailwind CSS v4 + Motion |
| Build | Hatchling (Python), PyInstaller (sidecar), NSIS (installer) |

---

## License

MIT
