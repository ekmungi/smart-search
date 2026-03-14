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
