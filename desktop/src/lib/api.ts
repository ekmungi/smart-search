// HTTP client for the smart-search backend REST API.

const BASE_URL = "http://127.0.0.1:9742/api";

export interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
}

export interface StatsResponse {
  document_count: number;
  chunk_count: number;
  index_size_bytes: number;
  index_size_mb: number;
  total_files: number;
  last_indexed_at: string | null;
  formats_indexed: string[];
}

export interface FolderInfo {
  path: string;
  exists: boolean;
  status: string;
}

export interface FoldersResponse {
  total: number;
  folders: FolderInfo[];
}

export interface AddFolderResponse {
  path: string;
  task_id: string;
  status: string;
}

export interface IndexingTask {
  task_id: string;
  folder: string;
  state: string;
  total: number;
  indexed: number;
  skipped: number;
  failed: number;
  error: string | null;
}

export interface IndexingStatusResponse {
  active: number;
  tasks: IndexingTask[];
}

export interface ConfigResponse {
  config: Record<string, unknown>;
}

export interface ModelStatusResponse {
  cached: boolean;
  model_name: string;
}

export interface ModelLoadedResponse {
  loaded: boolean;
}

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

export interface ModelsResponse {
  models: ModelInfo[];
}

export interface ConfigUpdateResponse {
  config: Record<string, unknown>;
  requires_reindex: boolean;
}

export interface SearchHit {
  rank: number;
  score: number;
  source_path: string;
  source_type: string;
  text: string;
  page_number: number | null;
}

export interface SearchResponse {
  query: string;
  mode: string;
  total: number;
  results: SearchHit[];
}

/** Fetch server health status. */
export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BASE_URL}/health`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Fetch index statistics. */
export async function fetchStats(): Promise<StatsResponse> {
  const res = await fetch(`${BASE_URL}/stats`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Fetch watched folder list. */
export async function fetchFolders(): Promise<FoldersResponse> {
  const res = await fetch(`${BASE_URL}/folders`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Add a folder to the watch list and trigger indexing. */
export async function addFolder(path: string): Promise<AddFolderResponse> {
  const res = await fetch(`${BASE_URL}/folders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/** Remove a folder from the watch list. */
export async function removeFolder(
  path: string,
  removeData = false,
): Promise<void> {
  const params = new URLSearchParams({ path, remove_data: String(removeData) });
  const res = await fetch(`${BASE_URL}/folders?${params}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

/** Trigger re-indexing of a folder. */
export async function reindexFolder(path: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, force: true }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

/** Fetch current configuration. */
export async function fetchConfig(): Promise<ConfigResponse> {
  const res = await fetch(`${BASE_URL}/config`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Search indexed documents with optional folder filter. */
export async function searchDocuments(
  query: string,
  limit = 10,
  folder?: string,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (folder) params.set("folder", folder);
  const res = await fetch(`${BASE_URL}/search?${params}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Check if the embedding model is cached locally. */
export async function fetchModelStatus(): Promise<ModelStatusResponse> {
  const res = await fetch(`${BASE_URL}/model/status`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Update configuration keys. Returns whether re-indexing is needed. */
export async function updateConfig(
  config: Record<string, unknown>,
): Promise<ConfigUpdateResponse> {
  const res = await fetch(`${BASE_URL}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Check if the embedding model is currently loaded in memory. */
export async function fetchModelLoaded(): Promise<ModelLoadedResponse> {
  const res = await fetch(`${BASE_URL}/model/loaded`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Fetch the list of available embedding models. */
export async function fetchModels(): Promise<ModelsResponse> {
  const res = await fetch(`${BASE_URL}/models`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Fetch the current background indexing task status. */
export async function fetchIndexingStatus(): Promise<IndexingStatusResponse> {
  const res = await fetch(`${BASE_URL}/indexing/status`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export interface RepairResponse {
  orphans_removed: number;
  orphan_files: string[];
  fts_rebuilt: boolean;
  fts_rows: number;
  compacted: boolean;
  compatible: boolean;
  mismatches: Record<string, unknown>;
}

/** Run all index maintenance operations: orphan removal, FTS5 rebuild, compaction. */
export async function repairIndex(): Promise<RepairResponse> {
  const res = await fetch(`${BASE_URL}/repair`, { method: "POST" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
