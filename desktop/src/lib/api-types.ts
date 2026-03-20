// Type declarations for the smart-search backend REST API responses.

/** Health check response from GET /api/health. */
export interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
}

/** Index statistics from GET /api/stats. */
export interface StatsResponse {
  document_count: number;
  chunk_count: number;
  index_size_bytes: number;
  index_size_mb: number;
  total_files: number;
  last_indexed_at: string | null;
  formats_indexed: string[];
}

/** Single folder entry in the watch list. */
export interface FolderInfo {
  path: string;
  exists: boolean;
  status: string;
}

/** Response from GET /api/folders. */
export interface FoldersResponse {
  total: number;
  folders: FolderInfo[];
}

/** Response from POST /api/folders (add folder + trigger indexing). */
export interface AddFolderResponse {
  path: string;
  task_id: string;
  status: string;
}

/** Per-file status entry in an indexing task. */
export interface ProcessedFile {
  name: string;
  path: string;
  status: string; // "indexed" | "skipped" | "failed"
  chunks?: string;
  error?: string;
}

/** Single background indexing task. */
export interface IndexingTask {
  task_id: string;
  folder: string;
  state: string;
  total: number;
  indexed: number;
  skipped: number;
  failed: number;
  error: string | null;
  processed_files: ProcessedFile[];
}

/** Response from GET /api/indexing/status. */
export interface IndexingStatusResponse {
  active: number;
  tasks: IndexingTask[];
}

/** Backend configuration as key-value pairs. */
export interface SmartSearchConfig {
  embedding_model?: string;
  embedding_dimensions?: number;
  shortcut_key?: string;
  relevance_threshold?: number;
  search_default_limit?: number;
  exclude_patterns?: string[];
  watch_directories?: string[];
  [key: string]: unknown;
}

/** Response from GET /api/config. */
export interface ConfigResponse {
  config: SmartSearchConfig;
}

/** Response from PUT /api/config. */
export interface ConfigUpdateResponse {
  config: SmartSearchConfig;
  requires_reindex: boolean;
}

/** Embedding model cache status from GET /api/model/status. */
export interface ModelStatusResponse {
  cached: boolean;
  model_name: string;
}

/** Whether the embedding model is loaded in memory, from GET /api/model/loaded. */
export interface ModelLoadedResponse {
  loaded: boolean;
}

/** Available embedding model metadata. */
export interface ModelInfo {
  model_id: string;
  display_name: string;
  size_mb: number;
  mteb_retrieval: number;
  native_dims: number;
  mrl_dims: number[];
  default_dims: number;
  modalities: string[];
  description: string;
}

/** Response from GET /api/models. */
export interface ModelsResponse {
  models: ModelInfo[];
}

/** Single search result hit. */
export interface SearchHit {
  rank: number;
  score: number;
  source_path: string;
  source_type: string;
  text: string;
  page_number: number | null;
}

/** Response from GET /api/search. */
export interface SearchResponse {
  query: string;
  mode: string;
  total: number;
  results: SearchHit[];
}

/** Response from POST /api/repair. */
export interface RepairResponse {
  orphans_removed: number;
  orphan_files: string[];
  fts_rebuilt: boolean;
  fts_rows: number;
  compacted: boolean;
  compatible: boolean;
  mismatches: Record<string, unknown>;
}
