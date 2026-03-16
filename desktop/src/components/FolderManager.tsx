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
  addFolder,
  removeFolder,
  reindexFolder,
  fetchIndexingStatus,
  type FolderInfo,
  type IndexingTask,
} from "../lib/api";

export default function FolderManager() {
  const [folders, setFolders] = useState<FolderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // indexingTasks from the backend /indexing/status endpoint (source of truth for per-folder state)
  const [indexingTasks, setIndexingTasks] = useState<IndexingTask[]>([]);

  const refresh = useCallback(async () => {
    try {
      const fRes = await fetchFolders();
      setFolders(fRes.folders);
      setError(null);
    } catch {
      setError("Could not load folders");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll indexing status every 2s while tasks are active, slow down when idle
  useEffect(() => {
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const checkIndexing = async () => {
      try {
        const [status, foldersRes] = await Promise.all([
          fetchIndexingStatus(),
          fetchFolders(),
        ]);
        if (!cancelled) {
          setIndexingTasks(status.tasks);
          // Always sync folder list to pick up external changes (MCP, API)
          setFolders(foldersRes.folders);

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

  /** Return the active indexing task for a given folder path, if any. */
  const taskForFolder = (path: string): IndexingTask | undefined =>
    indexingTasks.find(
      (t) => (t.state === "running" || t.state === "pending") && t.folder === path,
    );

  /** Return the most recent completed/failed task for a given folder path. */
  const completedTaskForFolder = (path: string): IndexingTask | undefined =>
    indexingTasks.find(
      (t) => (t.state === "completed" || t.state === "failed") && t.folder === path,
    );

  const handleAdd = async () => {
    const selected = await open({ directory: true, multiple: false });
    if (!selected) return;

    setError(null);
    const folderPath = selected as string;

    // Fire-and-forget: POST /folders returns 202 immediately; indexing runs in background
    addFolder(folderPath)
      .then(async (result) => {
        // Fetch both folder list and indexing status together so the task
        // appears at the same time as the folder row (prevents the race where
        // the row renders as "Indexed" before the poll picks up the new task).
        const [, status] = await Promise.all([
          refresh(),
          fetchIndexingStatus(),
        ]);
        setIndexingTasks(status.tasks);
        setError(`Added ${result.path} -- indexing started (task ${result.task_id})`);
        setTimeout(() => setError(null), 4000);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed to add folder");
      });
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

      {/* Top-level banner removed -- per-folder status is sufficient */}

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
              ) : completedTaskForFolder(folder.path)?.state === "completed" ? (
                <CheckCircle size={16} className="text-accent-green shrink-0" />
              ) : (
                <Loader size={16} className="text-text-muted animate-spin shrink-0" />
              )}
              <div className="min-w-0">
                <p className="text-sm truncate">{folder.path}</p>
                <p className="text-xs text-text-muted">
                  {!folder.exists
                    ? "Missing"
                    : taskForFolder(folder.path)
                      ? (() => {
                          const t = taskForFolder(folder.path)!;
                          const done = t.indexed + t.skipped + t.failed;
                          return t.total > 0
                            ? `Indexing... ${done} of ${t.total} files`
                            : `Indexing... ${done} files`;
                        })()
                      : completedTaskForFolder(folder.path)?.state === "failed"
                        ? `Failed: ${completedTaskForFolder(folder.path)!.error ?? "unknown error"}`
                        : completedTaskForFolder(folder.path)?.state === "completed"
                          ? `Indexed -- ${completedTaskForFolder(folder.path)!.indexed + completedTaskForFolder(folder.path)!.skipped} files`
                          : "Pending"}
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
