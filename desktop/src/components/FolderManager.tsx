// Folder manager: list, add, remove, and re-index watched folders.

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  FolderPlus,
  Trash2,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  AlertTriangle,
  Loader,
  Loader2,
  FileCheck,
  FileWarning,
} from "lucide-react";
import {
  fetchFolders,
  addFolder,
  removeFolder,
  fetchIndexingStatus,
  type FolderInfo,
  type IndexingTask,
} from "../lib/api";
import { POLL_INDEXING_ACTIVE_MS, POLL_INDEXING_IDLE_MS } from "../lib/constants";
import { staggerContainer, slideUp } from "../lib/animations";
import { truncatePath } from "../lib/format";
import Skeleton from "./Skeleton";
import EmptyState from "./EmptyState";

export default function FolderManager() {
  const [folders, setFolders] = useState<FolderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [indexingTasks, setIndexingTasks] = useState<IndexingTask[]>([]);
  const [confirmReindex, setConfirmReindex] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const fRes = await fetchFolders();
      setFolders(fRes.folders);
      setError(null);
    } catch {
      setError("Could not load folders -- showing last known state");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Poll indexing status
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
          setFolders(foldersRes.folders);
          const nextDelay = status.active > 0 ? POLL_INDEXING_ACTIVE_MS : POLL_INDEXING_IDLE_MS;
          if (intervalId !== null) clearInterval(intervalId);
          if (!cancelled) intervalId = setInterval(checkIndexing, nextDelay);
        }
      } catch { /* ignore */ }
    };
    checkIndexing();
    intervalId = setInterval(checkIndexing, POLL_INDEXING_ACTIVE_MS);
    return () => { cancelled = true; if (intervalId !== null) clearInterval(intervalId); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /** Active indexing task for a folder. */
  const taskForFolder = (path: string): IndexingTask | undefined =>
    indexingTasks.find(
      (t) => (t.state === "running" || t.state === "pending") && t.folder === path,
    );

  /** Most recent completed/failed task for a folder. */
  const completedTaskForFolder = (path: string): IndexingTask | undefined =>
    indexingTasks.find(
      (t) => (t.state === "completed" || t.state === "failed") && t.folder === path,
    );

  const handleAdd = async () => {
    const selected = await open({ directory: true, multiple: false });
    if (!selected) return;
    setError(null);
    const folderPath = selected as string;
    addFolder(folderPath)
      .then(async (result) => {
        const [, status] = await Promise.all([refresh(), fetchIndexingStatus()]);
        setIndexingTasks(status.tasks);
        setError(`Added ${result.path} -- indexing started (task ${result.task_id})`);
        setTimeout(() => setError(null), 4000);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed to add folder");
      });
  };

  /** Show confirmation dialog before removing. */
  const promptRemove = (path: string) => setConfirmRemove(path);

  /** Execute removal after user confirms. */
  const handleRemove = async () => {
    const path = confirmRemove;
    if (!path) return;
    setConfirmRemove(null);
    setBusy(path);
    try { await removeFolder(path, true); await refresh(); }
    catch { setError("Failed to remove folder"); }
    finally { setBusy(null); }
  };

  /** Show confirmation dialog before re-indexing. */
  const promptReindex = (path: string) => setConfirmReindex(path);

  /** Execute re-index after user confirms: delete all data, then re-add. */
  const handleReindex = async () => {
    const path = confirmReindex;
    if (!path) return;
    setConfirmReindex(null);
    setBusy(path);
    setError(null);
    try {
      // Step 1: Remove folder and wipe all indexed data
      await removeFolder(path, true);
      // Step 2: Re-add folder -- triggers fresh indexing from scratch
      await addFolder(path);
      // Small delay to let the backend task register before polling
      await new Promise((r) => setTimeout(r, 500));
      const [, status] = await Promise.all([refresh(), fetchIndexingStatus()]);
      setIndexingTasks(status.tasks);
      const folderName = path.split(/[\\/]/).pop() ?? path;
      setError(`Re-indexing ${folderName}...`);
      setTimeout(() => setError(null), 3000);
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

      {error && (
        <div className="bg-bg-surface border border-border rounded-lg p-3 mb-4 text-sm text-text-secondary">
          {error}
        </div>
      )}

      {/* Skeleton loading */}
      {loading && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="bg-bg-surface rounded-lg p-4 flex items-center gap-3">
              <Skeleton width="w-4" height="h-4" className="rounded shrink-0" />
              <div className="flex-1 space-y-2">
                <Skeleton width="w-48" height="h-4" />
                <Skeleton width="w-24" height="h-3" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && folders.length === 0 && !error && (
        <EmptyState
          icon={FolderPlus}
          heading="No folders configured"
          description="Add a folder to start indexing your documents for semantic search."
          action={
            <button
              onClick={handleAdd}
              className="px-4 py-2 bg-accent-blue text-white rounded-lg text-sm hover:opacity-90 transition-opacity"
            >
              Add Folder
            </button>
          }
        />
      )}

      {/* Folder list with staggered animation */}
      {!loading && folders.length > 0 && (
        <motion.div
          className="space-y-2"
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
        >
          {folders.map((folder) => (
            <FolderRow
              key={folder.path}
              folder={folder}
              task={taskForFolder(folder.path)}
              completedTask={completedTaskForFolder(folder.path)}
              busy={busy === folder.path}
              onReindex={() => promptReindex(folder.path)}
              onRemove={() => promptRemove(folder.path)}
            />
          ))}
        </motion.div>
      )}

      {/* Remove confirmation dialog */}
      <AnimatePresence>
        {confirmRemove && (
          <motion.div
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <motion.div
              className="bg-bg-surface border border-border rounded-lg p-6 max-w-md mx-4"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.15 }}
            >
              <div className="flex items-center gap-2 mb-3 text-accent-red">
                <AlertTriangle size={20} />
                <h3 className="font-semibold">Remove folder?</h3>
              </div>
              <p className="text-sm text-text-secondary mb-1">
                This will remove the folder and delete all indexed data for:
              </p>
              <p className="text-sm text-text-primary font-mono mb-4 break-all">
                {confirmRemove.split(/[\\/]/).slice(-2).join("/")}
              </p>
              <p className="text-xs text-text-muted mb-4">
                The original files on disk will not be affected.
              </p>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setConfirmRemove(null)}
                  className="px-3 py-1.5 text-sm rounded bg-bg-elevated text-text-secondary hover:bg-border"
                >
                  Cancel
                </button>
                <button
                  onClick={handleRemove}
                  className="px-3 py-1.5 text-sm rounded bg-accent-red text-text-primary hover:opacity-90"
                >
                  Remove
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Re-index confirmation dialog */}
      <AnimatePresence>
        {confirmReindex && (
          <motion.div
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <motion.div
              className="bg-bg-surface border border-border rounded-lg p-6 max-w-md mx-4"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.15 }}
            >
              <div className="flex items-center gap-2 mb-3 text-accent-amber">
                <AlertTriangle size={20} />
                <h3 className="font-semibold">Re-index folder?</h3>
              </div>
              <p className="text-sm text-text-secondary mb-1">
                This will re-process all files in:
              </p>
              <p className="text-sm text-text-primary font-mono mb-4 break-all">
                {confirmReindex.split(/[\\/]/).slice(-2).join("/")}
              </p>
              <p className="text-xs text-text-muted mb-4">
                All documents will be re-embedded. This may take several minutes for large folders.
              </p>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setConfirmReindex(null)}
                  className="px-3 py-1.5 text-sm rounded bg-bg-elevated text-text-secondary hover:bg-border"
                >
                  Cancel
                </button>
                <button
                  onClick={handleReindex}
                  disabled={busy !== null}
                  className="px-3 py-1.5 text-sm rounded bg-accent-blue text-text-primary hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
                >
                  {busy && <Loader2 size={14} className="animate-spin" />}
                  Re-index
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Props for a single folder row. */
interface FolderRowProps {
  folder: FolderInfo;
  task?: IndexingTask;
  completedTask?: IndexingTask;
  busy: boolean;
  onReindex: () => void;
  onRemove: () => void;
}

/** Single folder row with status, progress, and actions. */
function FolderRow({ folder, task, completedTask, busy, onReindex, onRemove }: FolderRowProps) {
  return (
    <motion.div
      variants={slideUp}
      className="bg-bg-surface rounded-lg p-4 flex items-center justify-between hover:-translate-y-px hover:shadow-lg hover:shadow-black/10 transition-all duration-150"
    >
      <div className="flex items-center gap-3 min-w-0">
        <FolderStatusIcon folder={folder} task={task} completedTask={completedTask} />
        <div className="min-w-0">
          <p className="text-sm truncate" title={folder.path}>
            {truncatePath(folder.path)}
          </p>
          <FolderStatusText folder={folder} task={task} completedTask={completedTask} />
        </div>
      </div>

      <div className="flex items-center gap-1 shrink-0">
        <button
          onClick={onReindex}
          disabled={busy}
          title="Re-index"
          className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors disabled:opacity-50"
        >
          <RefreshCw size={16} className={busy ? "animate-spin" : ""} />
        </button>
        <button
          onClick={onRemove}
          disabled={busy}
          title="Remove"
          className="p-2 rounded-lg text-text-secondary hover:text-accent-red hover:bg-bg-elevated transition-colors disabled:opacity-50"
        >
          <Trash2 size={16} />
        </button>
      </div>
    </motion.div>
  );
}

/** Status icon for a folder row. */
function FolderStatusIcon({
  folder,
  task,
  completedTask,
}: {
  folder: FolderInfo;
  task?: IndexingTask;
  completedTask?: IndexingTask;
}) {
  if (!folder.exists) return <AlertCircle size={16} className="text-accent-red shrink-0" />;
  if (task) return <Loader size={16} className="text-accent-blue animate-spin shrink-0" />;
  if (completedTask?.state === "failed") return <AlertCircle size={16} className="text-accent-red shrink-0" />;
  if (completedTask?.state === "completed") return <CheckCircle size={16} className="text-accent-green shrink-0" />;
  // No active task -- use SQLite counts to determine icon
  if (folder.indexed_count > 0 || folder.failed_count > 0) return <CheckCircle size={16} className="text-accent-green shrink-0" />;
  return <Loader size={16} className="text-text-muted animate-spin shrink-0" />;
}

/** Status text and progress bar for a folder row. */
function FolderStatusText({
  folder,
  task,
  completedTask,
}: {
  folder: FolderInfo;
  task?: IndexingTask;
  completedTask?: IndexingTask;
}) {
  if (!folder.exists) {
    return <p className="text-xs text-text-muted">Missing</p>;
  }

  if (task) {
    const done = task.indexed + task.skipped + task.failed;
    const pct = task.total > 0 ? (done / task.total) * 100 : 0;
    const failPct = task.total > 0 ? (task.failed / task.total) * 100 : 0;
    // Use SQLite counts as source of truth, with progress bar showing session progress
    const indexed = folder.indexed_count;
    const failed = folder.failed_count;
    return (
      <div className="text-xs text-text-muted">
        <div className="w-full bg-bg-elevated rounded-full h-1.5 mt-0.5 relative overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-accent-blue h-1.5 rounded-full transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
          {failPct > 0 && (
            <div
              className="absolute inset-y-0 bg-accent-amber h-1.5 rounded-full transition-all duration-300"
              style={{ left: `${pct - failPct}%`, width: `${failPct}%` }}
            />
          )}
        </div>
        <span className="flex items-center gap-2 mt-0.5">
          {indexed > 0 && (
            <span className="flex items-center gap-1">
              <FileCheck size={11} className="text-accent-green" />
              {indexed} indexed
            </span>
          )}
          {failed > 0 && (
            <span className="flex items-center gap-1">
              <FileWarning size={11} className="text-accent-amber" />
              {failed} failed
            </span>
          )}
          {indexed === 0 && failed === 0 && (
            <span>{done} of {task.total}</span>
          )}
        </span>
      </div>
    );
  }

  if (completedTask?.state === "failed") {
    return (
      <p className="text-xs text-text-muted">
        Failed: {completedTask.error ?? "unknown error"}
      </p>
    );
  }

  if (completedTask?.state === "completed" || (!task && (folder.indexed_count > 0 || folder.failed_count > 0))) {
    // Use SQLite counts as source of truth -- persists across restarts
    const indexed = folder.indexed_count;
    const failed = folder.failed_count;
    return (
      <p className="text-xs text-text-muted">
        <span className="flex items-center gap-2">
          {indexed > 0 && (
            <span className="flex items-center gap-1">
              <FileCheck size={11} className="text-accent-green" />
              {indexed} indexed
            </span>
          )}
          {failed > 0 && (
            <span className="flex items-center gap-1">
              <FileWarning size={11} className="text-accent-amber" />
              {failed} failed
            </span>
          )}
        </span>
      </p>
    );
  }

  return <p className="text-xs text-text-muted">Pending</p>;
}
