// Folder manager: list, add, remove, and re-index watched folders.

import { useState, useEffect, useCallback } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  FolderPlus,
  Trash2,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Loader,
} from "lucide-react";
import {
  fetchFolders,
  fetchStats,
  addFolder,
  removeFolder,
  reindexFolder,
  type FolderInfo,
  type StatsResponse,
} from "../lib/api";

export default function FolderManager() {
  const [folders, setFolders] = useState<FolderInfo[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [indexingPaths, setIndexingPaths] = useState<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    try {
      const [fRes, sRes] = await Promise.all([fetchFolders(), fetchStats()]);
      setFolders(fRes.folders);
      setStats(sRes);
      setError(null);
    } catch {
      setError("Could not load folders");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    // Poll stats every 5s to update indexing progress
    const interval = setInterval(async () => {
      try {
        const s = await fetchStats();
        setStats(s);
      } catch {
        // Ignore poll errors
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  /** Whether indexing is currently active (fewer docs indexed than files on disk). */
  const isIndexing = stats !== null && stats.total_files > 0 && stats.document_count < stats.total_files;

  const handleAdd = async () => {
    const selected = await open({ directory: true, multiple: false });
    if (!selected) return;

    setError(null);
    const folderPath = selected as string;

    // Mark this folder as indexing immediately
    setIndexingPaths((prev) => new Set([...prev, folderPath]));

    // Fire-and-forget: start indexing in background, don't block the UI
    addFolder(folderPath)
      .then(async (result) => {
        setIndexingPaths((prev) => {
          const next = new Set(prev);
          next.delete(folderPath);
          return next;
        });
        await refresh();
        setError(
          `Added ${result.path} -- ${result.indexed} indexed, ${result.skipped} skipped`,
        );
        setTimeout(() => setError(null), 4000);
      })
      .catch((e) => {
        setIndexingPaths((prev) => {
          const next = new Set(prev);
          next.delete(folderPath);
          return next;
        });
        setError(e instanceof Error ? e.message : "Failed to add folder");
      });

    // Optimistically refresh folder list (folder appears before indexing completes)
    setTimeout(() => refresh(), 500);
  };

  const handleRemove = async (path: string) => {
    setBusy(path);
    try {
      await removeFolder(path, true);
      await refresh();
    } catch {
      setError("Failed to remove folder");
    } finally {
      setBusy(null);
    }
  };

  const handleReindex = async (path: string) => {
    setBusy(path);
    try {
      await reindexFolder(path);
      await refresh();
    } catch {
      setError("Failed to re-index folder");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Folders</h1>
        <button
          onClick={handleAdd}
          className="flex items-center gap-2 px-3 py-2 bg-accent-blue text-white rounded-lg text-sm hover:opacity-90 transition-opacity"
        >
          <FolderPlus size={16} />
          Add Folder
        </button>
      </div>

      {/* Indexing progress summary */}
      {stats && stats.total_files > 0 && (
        <div className="bg-bg-surface rounded-lg p-3 mb-4 flex items-center gap-3">
          {isIndexing ? (
            <>
              <Loader size={14} className="text-accent-blue animate-spin shrink-0" />
              <span className="text-sm text-text-secondary">
                Indexing {stats.document_count} of {stats.total_files} files ({stats.chunk_count} chunks)
              </span>
            </>
          ) : (
            <>
              <CheckCircle size={14} className="text-accent-green shrink-0" />
              <span className="text-sm text-text-secondary">
                {stats.document_count} files indexed ({stats.chunk_count} chunks)
              </span>
            </>
          )}
        </div>
      )}

      {error && (
        <div className="bg-bg-surface border border-border rounded-lg p-3 mb-4 text-sm text-text-secondary">
          {error}
        </div>
      )}

      {loading && (
        <p className="text-text-secondary text-sm">Loading folders...</p>
      )}

      {!loading && folders.length === 0 && (
        <div className="bg-bg-surface rounded-lg p-8 text-center">
          <p className="text-text-secondary mb-2">No folders configured</p>
          <p className="text-text-muted text-sm">
            Add a folder to start indexing your documents
          </p>
        </div>
      )}

      <div className="space-y-2">
        {folders.map((folder) => (
          <div
            key={folder.path}
            className="bg-bg-surface rounded-lg p-4 flex items-center justify-between"
          >
            <div className="flex items-center gap-3 min-w-0">
              {!folder.exists ? (
                <AlertCircle size={16} className="text-accent-red shrink-0" />
              ) : indexingPaths.has(folder.path) ? (
                <Loader size={16} className="text-accent-blue animate-spin shrink-0" />
              ) : (
                <CheckCircle size={16} className="text-accent-green shrink-0" />
              )}
              <div className="min-w-0">
                <p className="text-sm truncate">{folder.path}</p>
                <p className="text-xs text-text-muted">
                  {!folder.exists
                    ? "Missing"
                    : indexingPaths.has(folder.path)
                      ? "Indexing..."
                      : "Indexed"}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => handleReindex(folder.path)}
                disabled={busy === folder.path}
                title="Re-index"
                className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors disabled:opacity-50"
              >
                <RefreshCw
                  size={16}
                  className={busy === folder.path ? "animate-spin" : ""}
                />
              </button>
              <button
                onClick={() => handleRemove(folder.path)}
                disabled={busy === folder.path}
                title="Remove"
                className="p-2 rounded-lg text-text-secondary hover:text-accent-red hover:bg-bg-elevated transition-colors disabled:opacity-50"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
