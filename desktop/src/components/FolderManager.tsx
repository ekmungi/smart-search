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
  fetchIndexingStatus,
  type FolderInfo,
  type StatsResponse,
  type IndexingTask,
} from "../lib/api";

export default function FolderManager() {
  const [folders, setFolders] = useState<FolderInfo[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // indexingTasks from the backend /indexing/status endpoint (source of truth for per-folder state)
  const [indexingTasks, setIndexingTasks] = useState<IndexingTask[]>([]);

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
    // Poll stats every 5s for document count updates
    const statsInterval = setInterval(async () => {
      try {
        const s = await fetchStats();
        setStats(s);
      } catch {
        // Ignore poll errors
      }
    }, 5000);
    return () => clearInterval(statsInterval);
  }, [refresh]);

  // Poll indexing status every 2s while tasks are active, slow down when idle
  useEffect(() => {
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const checkIndexing = async () => {
      try {
        const status = await fetchIndexingStatus();
        if (!cancelled) {
          setIndexingTasks(status.tasks);
          // Refresh folder list when tasks complete so status badges update
          if (status.active === 0 && indexingTasks.some((t) => t.state === "running")) {
            refresh();
          }
          // Slow down when no active tasks
          const nextDelay = status.active > 0 ? 2000 : 10000;
          if (intervalId !== null) clearInterval(intervalId);
          if (!cancelled) {
            intervalId = setInterval(checkIndexing, nextDelay);
          }
        }
      } catch {
        // Ignore -- backend may not support endpoint yet
      }
    };

    checkIndexing();
    intervalId = setInterval(checkIndexing, 2000);

    return () => {
      cancelled = true;
      if (intervalId !== null) clearInterval(intervalId);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /** Whether indexing is currently active according to the backend task queue. */
  const isIndexing = indexingTasks.some((t) => t.state === "running" || t.state === "pending");

  /** Return the active indexing task for a given folder path, if any. */
  const taskForFolder = (path: string): IndexingTask | undefined =>
    indexingTasks.find(
      (t) => (t.state === "running" || t.state === "pending") && t.folder === path,
    );

  /** Return the most recent completed/failed task for a given folder path. */
  const completedTaskForFolder = (path: string): IndexingTask | undefined =>
    indexingTasks.find(
      (t) => (t.state === "done" || t.state === "failed") && t.folder === path,
    );

  const handleAdd = async () => {
    const selected = await open({ directory: true, multiple: false });
    if (!selected) return;

    setError(null);
    const folderPath = selected as string;

    // Fire-and-forget: POST /folders returns 202 immediately; indexing runs in background
    addFolder(folderPath)
      .then(async (result) => {
        await refresh();
        setError(`Added ${result.path} -- indexing started (task ${result.task_id})`);
        setTimeout(() => setError(null), 4000);
      })
      .catch((e) => {
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
                Indexing in progress &mdash;{" "}
                {indexingTasks
                  .filter((t) => t.state === "running" || t.state === "pending")
                  .reduce((sum, t) => sum + t.indexed, 0)}{" "}
                documents indexed so far ({stats.chunk_count} chunks)
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
              ) : taskForFolder(folder.path) ? (
                <Loader size={16} className="text-accent-blue animate-spin shrink-0" />
              ) : completedTaskForFolder(folder.path)?.state === "failed" ? (
                <AlertCircle size={16} className="text-accent-red shrink-0" />
              ) : (
                <CheckCircle size={16} className="text-accent-green shrink-0" />
              )}
              <div className="min-w-0">
                <p className="text-sm truncate">{folder.path}</p>
                <p className="text-xs text-text-muted">
                  {!folder.exists
                    ? "Missing"
                    : taskForFolder(folder.path)
                      ? `Indexing... ${taskForFolder(folder.path)!.indexed} indexed`
                      : completedTaskForFolder(folder.path)?.state === "failed"
                        ? `Failed: ${completedTaskForFolder(folder.path)!.error ?? "unknown error"}`
                        : completedTaskForFolder(folder.path)
                          ? `Done -- ${completedTaskForFolder(folder.path)!.indexed} indexed, ${completedTaskForFolder(folder.path)!.skipped} skipped`
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
