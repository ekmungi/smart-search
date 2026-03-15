// Folder manager: list, add, remove, and re-index watched folders.

import { useState, useEffect, useCallback } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  FolderPlus,
  Trash2,
  RefreshCw,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import {
  fetchFolders,
  addFolder,
  removeFolder,
  reindexFolder,
  type FolderInfo,
} from "../lib/api";

export default function FolderManager() {
  const [folders, setFolders] = useState<FolderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetchFolders();
      setFolders(res.folders);
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

  const handleAdd = async () => {
    const selected = await open({ directory: true, multiple: false });
    if (!selected) return;

    setError(null);
    // Fire-and-forget: start indexing in background, don't block the UI
    addFolder(selected as string)
      .then(async (result) => {
        await refresh();
        setError(
          `Added ${result.path} -- ${result.indexed} indexed, ${result.skipped} skipped`,
        );
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
              {folder.exists ? (
                <CheckCircle size={16} className="text-accent-green shrink-0" />
              ) : (
                <AlertCircle size={16} className="text-accent-red shrink-0" />
              )}
              <div className="min-w-0">
                <p className="text-sm truncate">{folder.path}</p>
                <p className="text-xs text-text-muted">
                  {folder.exists ? "Active" : "Missing"}
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
