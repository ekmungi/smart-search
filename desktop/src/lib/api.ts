// HTTP client for the smart-search backend REST API.

import { BACKEND_PORT, API_TIMEOUT_MS } from "./constants";
import type {
  HealthResponse,
  StatsResponse,
  FoldersResponse,
  AddFolderResponse,
  IndexingStatusResponse,
  ConfigResponse,
  ConfigUpdateResponse,
  ModelStatusResponse,
  ModelLoadedResponse,
  ModelsResponse,
  SearchResponse,
  RepairResponse,
  SmartSearchConfig,
} from "./api-types";

// Re-export all types so existing imports like `import { type FolderInfo } from "../lib/api"` keep working.
export type {
  HealthResponse,
  StatsResponse,
  FolderInfo,
  FoldersResponse,
  AddFolderResponse,
  ProcessedFile,
  IndexingTask,
  IndexingStatusResponse,
  ConfigResponse,
  ConfigUpdateResponse,
  ModelStatusResponse,
  ModelLoadedResponse,
  ModelInfo,
  ModelsResponse,
  SearchHit,
  SearchResponse,
  RepairResponse,
  SmartSearchConfig,
  GpuInfo,
} from "./api-types";

/** In dev mode, Vite proxies /api to the backend so all requests are
 *  same-origin -- avoids WebView2 cross-origin POST failures (B47). */
const BASE_URL = import.meta.env.DEV
  ? "/api"
  : `http://127.0.0.1:${BACKEND_PORT}/api`;

/** Fetch with timeout using AbortController. Throws on timeout. */
async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit,
  timeoutMs = API_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}

/** Parse a response as JSON, throwing a descriptive error on failure. */
async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(body || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

/** Fetch server health status. */
export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetchWithTimeout(`${BASE_URL}/health`);
  return handleResponse<HealthResponse>(res);
}

/** Fetch index statistics. */
export async function fetchStats(): Promise<StatsResponse> {
  const res = await fetchWithTimeout(`${BASE_URL}/stats`);
  return handleResponse<StatsResponse>(res);
}

/** Fetch watched folder list. */
export async function fetchFolders(): Promise<FoldersResponse> {
  const res = await fetchWithTimeout(`${BASE_URL}/folders`);
  return handleResponse<FoldersResponse>(res);
}

/** Add a folder to the watch list and trigger indexing. */
export async function addFolder(path: string): Promise<AddFolderResponse> {
  const res = await fetch(`${BASE_URL}/folders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  return handleResponse<AddFolderResponse>(res);
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
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(body || `HTTP ${res.status}`);
  }
}

/** Trigger re-indexing of a folder. */
export async function reindexFolder(path: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, force: true }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(body || `HTTP ${res.status}`);
  }
}

/** Fetch current configuration. */
export async function fetchConfig(): Promise<ConfigResponse> {
  const res = await fetchWithTimeout(`${BASE_URL}/config`);
  return handleResponse<ConfigResponse>(res);
}

/** Search indexed documents with optional folder filter. */
export async function searchDocuments(
  query: string,
  limit = 10,
  folder?: string,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (folder) params.set("folder", folder);
  const res = await fetchWithTimeout(`${BASE_URL}/search?${params}`);
  return handleResponse<SearchResponse>(res);
}

/** Check if the embedding model is cached locally. */
export async function fetchModelStatus(): Promise<ModelStatusResponse> {
  const res = await fetchWithTimeout(`${BASE_URL}/model/status`);
  return handleResponse<ModelStatusResponse>(res);
}

/** Update configuration keys. Returns whether re-indexing is needed. */
export async function updateConfig(
  config: Partial<SmartSearchConfig>,
): Promise<ConfigUpdateResponse> {
  const res = await fetch(`${BASE_URL}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
  return handleResponse<ConfigUpdateResponse>(res);
}

/** Check if the embedding model is currently loaded in memory. */
export async function fetchModelLoaded(): Promise<ModelLoadedResponse> {
  const res = await fetchWithTimeout(`${BASE_URL}/model/loaded`);
  return handleResponse<ModelLoadedResponse>(res);
}

/** Fetch the list of available embedding models. */
export async function fetchModels(): Promise<ModelsResponse> {
  const res = await fetchWithTimeout(`${BASE_URL}/models`);
  return handleResponse<ModelsResponse>(res);
}

/** Fetch the current background indexing task status. */
export async function fetchIndexingStatus(): Promise<IndexingStatusResponse> {
  const res = await fetchWithTimeout(`${BASE_URL}/indexing/status`);
  return handleResponse<IndexingStatusResponse>(res);
}

/** Run all index maintenance operations: orphan removal, FTS5 rebuild, compaction. */
export async function repairIndex(): Promise<RepairResponse> {
  const res = await fetch(`${BASE_URL}/repair`, { method: "POST" });
  return handleResponse<RepairResponse>(res);
}

/** Clear all file hashes and re-index every watched folder. */
export async function rebuildIndex(): Promise<{ folders_queued: number; hashes_cleared: number }> {
  const res = await fetch(`${BASE_URL}/rebuild`, { method: "POST" });
  return handleResponse(res);
}
