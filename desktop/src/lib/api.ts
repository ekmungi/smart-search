// HTTP client for the smart-search backend REST API.

const BASE_URL = "http://localhost:9742/api";

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
  indexed: number;
  skipped: number;
  failed: number;
}

export interface ConfigResponse {
  config: Record<string, unknown>;
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

/** Update configuration keys. */
export async function updateConfig(
  config: Record<string, unknown>,
): Promise<ConfigResponse> {
  const res = await fetch(`${BASE_URL}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
