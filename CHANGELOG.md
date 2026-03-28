# Changelog

All notable changes to Smart Search are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.15.0] - 2026-03-28

Visual refresh with light/dark theme support and polish. Zero functional changes.

### Added
- Light/dark theme system with CSS custom property overrides
- Theme toggle (segmented control) in Appearance settings with Sun/Moon icons
- Theme persists across app restarts via localStorage

### Changed
- Dark theme text contrast improved: `text-muted` #606058 -> #7A7A72, `text-secondary` #909088 -> #A0A098
- Typography hierarchy: StatsCard labels larger, IndexingLog filenames use monospace, FolderManager paths use monospace
- Spacing polish: tighter folder cards, consistent stats card heights, increased settings section gaps
- Sidebar active indicator: added subtle blue ring for stronger visual feedback
- Sidebar hover states: added background highlight on hover
- Title bar: frosted glass effect with `backdrop-blur-sm`
- IndexingBanner progress bar: subtle gradient for depth
- Dashboard section headings: increased bottom margin for breathing room
- Smooth 200ms CSS transition on theme change

---

## [0.14.2] - 2026-03-28

### Added
- Inline file actions in IndexingLog: retry, open file, show in folder (hover-revealed icons)
- Folder total count display in FolderManager status text
- `show_in_folder` Tauri command for opening file location in OS explorer

---

## [0.14.1] - 2026-03-28

### Fixed
- B69: NSIS installer now cleans up HuggingFace cache directory on uninstall
- B70: Per-file progress tracking during indexing (indexed/failed counts from SQLite)
- B71: ModelDownloadBanner race condition -- poll continues after cache, transition detection fires correctly

---

## [0.14.0] - 2026-03-28

### Changed
- Replaced subprocess-based ConversionWorker with in-process architecture
- MarkItDown calls run directly in the indexing thread (no IPC overhead)
- Added subprocess fallback via `SMART_SEARCH_SUBPROCESS_CONVERTER` env var
- Retry logic and detailed error reporting in markitdown_parser

---

## [0.13.8] - 2026-03-27

### Changed
- Model management redesign: model selector with cache checkmarks and auto-download
- ModelDownloadBanner on Dashboard showing real-time download progress
- Default to no model on fresh install (user selects preferred model)
- Download progress tracking via backend polling
- SHA-based snapshot directories for imported models
- Windows symlink privilege error handling in HF model download

---

## [0.13.7] - 2026-03-27

### Fixed
- Enterprise SSL certificate handling for HuggingFace model downloads
- Quick Search window no longer opens on app startup
- Installer prompts to close running Smart Search before upgrading
- NSIS uninstaller deletes actual data directory

---

## [0.13.5] - 2026-03-26

### Added
- Model readiness gate: blocks vector indexing until embedding model is cached
- Download timeout wrapper with configurable limit (default 15 min)
- ModelDownloadTimeoutError with recovery info (HF URL + cache path)
- Pause/resume indexing controls on Dashboard
- Model import endpoint: copy local model files to HF cache
- Auto-retry failed files when embedding model becomes available
- Timeout dialog with continue-keyword-only option

---

## [0.13.1] - 2026-03-25

### Added
- Persistent indexing: background task manager with per-folder cancellation
- Graceful shutdown: stop indexing tasks cleanly on app exit
- Persistent conversion worker (single subprocess for all binary files)

---

## [0.13.0] - 2026-03-25

### Added
- GPU acceleration support (CUDA/DirectML execution providers)
- Backend dropdown with GPU detection chip in Embedding settings
- Reranking and MMR diversity toggles in Search settings
- GPU status in model status API and gpu_required flag in model registry
- GPU provider detection module with automatic fallback chain

---

## [0.12.0] - 2026-03-24

### Added
- Cross-encoder reranker (TinyBERT-L-2, ~50MB, lazy ONNX with idle unload)
- Maximum Marginal Relevance (MMR) diversity selection (lambda=0.8)
- Query preprocessing: stopword removal for FTS5, whitespace normalization for embeddings

---

## [0.11.5] - 2026-03-23

### Added
- Expanded to 14 supported file formats

---

## [0.11.4] - 2026-03-23

### Changed
- UI overhaul with motion animations, typography improvements, and visual polish

---

## [0.11.3] - 2026-03-22

### Added
- Failed file tracking in SQLite (skip on restart until file changes)
- Mtime backfill for pre-migration indexed rows
- True-state pre-scan: categorize files as indexed/failed/needs-OCR before indexing

---

## [0.11.1] - 2026-03-22

### Fixed
- Dashboard stats showing "--" instead of values
- Search query normalization for better matching
- Hybrid search RRF threshold calculation

---

## [0.9.0] - 2026-03-21

Search quality overhaul. Fixes YouTube transcript not appearing in search despite
21 mentions of query terms. Root cause: oversized chunks truncated by embedder,
undersized PDF chunks, no filename in FTS5, insufficient over-fetching, and
misleading RRF score display.

### Added
- Size-enforced chunk splitting: oversized chunks (>200 words) split on sentence
  boundaries with 40-word overlap between sub-chunks
- Chunk merging: undersized chunks (<50 words) merged with next sibling
- Title prepend: every chunk gets `Title: {name}\n---\n` prefix before embedding
  (Anthropic Contextual Retrieval: +49% recall improvement)
- Configurable `rrf_k` in SmartSearchConfig (default 60, tunable for mixed content)
- `chunk_max_words`, `chunk_min_words`, `chunk_overlap_words` config params
- `OVERFETCH_MULTIPLIER` constant (5x) extracted to constants.py
- Auto re-index detection: startup detects chunk config changes and clears file
  hashes so next ingest re-processes all files
- FTS5 schema migration: startup auto-detects old schema and rebuilds FTS5 with
  source_path indexed
- `clear_all_file_hashes()` method on ChunkStore for forced re-indexing

### Changed
- Hybrid search over-fetches `limit * 5` from each source (was `limit * 2`)
- FTS5 `source_path` is now indexed (was UNINDEXED), enabling filename keyword search
- RRF fusion scores normalized to 0-1 range (top result = 100%, was raw 0-3.3%)
- Quick Search requests `MAX_RESULTS * 4` results (was `* 3`) for better dedup headroom
- `chunk_max_tokens: int = 512` replaced with `chunk_max_words: int = 200`

### Upgrade Notes
- Phase 1 changes (over-fetch, RRF normalization, FTS5 filename) work immediately
  without re-indexing. FTS5 auto-migrates on first startup.
- Phase 2 changes (chunk splitting, title prepend) require a re-index to take effect.
  Trigger via Dashboard "Re-index" button or `POST /api/ingest`.

---

## [0.8.5] - 2026-03-20

### Changed
- Split large source files into focused modules (30+ modules, 200-line target)
- Extracted shared constants to `constants.py`
- Improved error handling across indexer and store modules

---

## [0.8.4] - 2026-03-17

### Fixed
- B53: Memory peaks 4.8GB during indexing (now ~2.1GB via gc every 2 files,
  del embeddings after use, max 1 concurrent batch)
- B48: File count mismatch 94 vs 93 (discover_files with resolve + dedup)
- B54: Index size reported from SQLite only, missing LanceDB (cached combined
  size with 60s TTL)
- B47: POST requests fail in dev mode (Vite proxy for /api)
- B55: MarkItDown hangs on certain PDFs (_convert_with_timeout 120s)

### Added
- Indexing Log UI: per-file green/red status in desktop app
- Configurable log level via `SMART_SEARCH_LOG_LEVEL` env var

---

## [0.8.3] - 2026-03-17

### Fixed
- B44: AbortController breaks POST requests (fetchWithTimeout GET-only)
- B45: RLock deadlock on singleton getters during concurrent startup
- B46: Dashboard Promise.all fails if one endpoint errors
- B49: Stats queries blocked by indexing writes (WAL mode + read-only conn)
- B50: Empty-output PDFs crash indexer (graceful handling + needs_ocr flag)
- B51: Zero-chunk files not recorded in indexed_files
- B52: Folder failed count display incorrect

### Changed
- Non-blocking server startup: heavy init runs in background daemon thread
- Sidecar dedup: kill orphan backend processes before spawning new one

---

## [0.8.2] - 2026-03-16

### Changed
- ONNX Runtime arena allocator disabled (lower idle memory)
- Standalone tokenizers (no HuggingFace Hub dependency)
- Close-to-tray behavior for desktop window

---

## [0.8.1] - 2026-03-16

### Added
- Manual repair index button in Settings UI
- FTS5 forced rebuild during repair (drop + recreate + backfill)
- LanceDB compaction during repair to reclaim disk space

---

## [0.8.0] - 2026-03-16

### Added
- Hybrid search: FTS5 keyword search + vector search combined via Reciprocal
  Rank Fusion (RRF, k=60)
- Three search modes: `semantic`, `keyword`, `hybrid` (default)
- FTS5 virtual table with porter stemming for keyword matching
- One-time FTS5 backfill migration for pre-v0.8 indexes on startup
- BM25 scoring for keyword results

---

## [0.7.2] - 2026-03-16

### Fixed
- 42 bugs fixed across phases A-H (B1-B43)
- MCP HTTP proxy for ephemeral tools
- LanceDB compaction errors on empty tables
- Global shortcut unregister on config change
- URL encoding for source_path in API calls
- Quick Search deduplication by file
- Paragraph-based fallback chunking for headingless documents (B17)

### Added
- Resource-aware concurrent indexing with semaphore throttle
- Auto-resume indexing for watched folders on server startup

---

## [0.7.0] - 2026-03-16

### Changed
- Switched embedding model from nomic-embed-text-v1.5 to
  Snowflake/snowflake-arctic-embed-m-v2.0 (int8, 256-dim Matryoshka)
- Eliminated PyTorch dependency (ONNX Runtime only)
- Lazy embedder lifecycle: load on first use, unload after idle timeout
- Peak memory reduced from ~4GB to ~2.1GB during indexing

---

## [0.6.0] - 2026-03-16

### Added
- Single NSIS installer: PyInstaller sidecar bundled inside Tauri app
- Windows autostart via registry
- MCP auto-registration in Claude Desktop config on install

---

## [0.5.2] - 2026-03-16

### Added
- NSIS installer for Windows distribution
- Autostart on login
- MCP server registration in Claude Desktop config.json

---

## [0.5.1] - 2026-03-15

### Added
- Quick Search overlay: global hotkey (Ctrl+Space) opens floating search bar
- Debounced search-as-you-type with keyboard navigation
- ESC to dismiss, Enter to open file, arrow keys to navigate

---

## [0.5.0] - 2026-03-15

### Added
- Folder manager UI: add/remove watched folders from desktop app
- Settings panel: appearance, embedding model, search defaults, system info
- Dialog plugin integration for native folder picker

---

## [0.4.1] - 2026-03-15

### Added
- Tauri v2 desktop shell with system tray icon
- Dashboard view: index stats, health status, folder overview
- Dark theme (custom Tailwind palette)

---

## [0.4.0] - 2026-03-14

### Added
- FastAPI HTTP REST API server (15 endpoints)
- Health, stats, search, folders, files, ingest, config endpoints
- PyInstaller one-file bundle with unified CLI entry point
- `smart-search serve` command for HTTP server

---

## [0.3.2] - 2026-03-13

### Changed
- Lazy imports in MCP server for fast startup (~100ms vs ~3s)

---

## [0.3.1] - 2026-03-11

### Added
- tqdm progress bars for CLI indexing commands

---

## [0.3.0] - 2026-03-11

### Changed
- Replaced Docling with MarkItDown for document parsing
- Single pipeline: all files -> MarkItDown (non-.md) -> MarkdownChunker -> Chunks
- Added PPTX, XLSX, HTML support alongside existing PDF, DOCX, MD

---

## [0.2.7] - 2026-03-10

### Added
- Ephemeral (temporary) folder-local indexes
- `knowledge_temp_index` and `knowledge_temp_cleanup` MCP tools
- Ephemeral registry with CRUD and stale pruning

---

## [0.2.6] - 2026-03-10

### Added
- CLI interface with subcommands: stats, config, watch, index, search, model
- ConfigManager for persistent config.json
- Folder filter on search queries
- Runtime add/remove of watch directories

---

## [0.2.5] - 2026-03-10

### Added
- OS-convention data directory (~/.local/share/smart-search or %LOCALAPPDATA%)
- Index metadata tracking for model mismatch detection
- `find_related` MCP tool: find notes similar to a given note
- `read_note` MCP tool: read note content
- Folder management MCP tools: add, remove, list folders
- `list_indexed_files` MCP tool
- Protocol definitions for extensible pipeline stages

---

## [0.2.0] - 2026-03-06

### Added
- Heading-based Markdown chunker (ATX headings # / ## / ###)
- YAML frontmatter extraction (title, date)
- File watcher with debounced re-indexing
- `knowledge_ingest` MCP tool for file and folder ingestion
- Indexer routing by file extension

---

## [0.1.0] - 2026-03-06

### Added
- Initial MCP server with `knowledge_search` and `knowledge_stats` tools
- PDF and DOCX document indexing
- LanceDB vector storage with cosine similarity search
- SQLite metadata tracking (indexed files, content hashes)
- Pydantic configuration with environment variable overrides
