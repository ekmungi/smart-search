// Persistent indexing log sourced from SQLite, with retry for failed files.

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { invoke } from "@tauri-apps/api/core";
import {
  CheckCircle,
  XCircle,
  ScrollText,
  ChevronDown,
  RotateCcw,
  ExternalLink,
  FolderOpen,
  Loader,
} from "lucide-react";
import {
  fetchFiles,
  fetchIndexingStatus,
  retryFailed,
  type IndexedFileInfo,
} from "../lib/api";
import { POLL_INDEXING_IDLE_MS, POLL_INDEXING_ACTIVE_MS } from "../lib/constants";
import { staggerContainer, slideUp } from "../lib/animations";
import Skeleton from "./Skeleton";
import EmptyState from "./EmptyState";

/** Extract filename from a POSIX source_path. */
function fileName(sourcePath: string): string {
  const parts = sourcePath.split("/");
  return parts[parts.length - 1] ?? sourcePath;
}

export default function IndexingLog() {
  const [files, setFiles] = useState<IndexedFileInfo[]>([]);
  const [filter, setFilter] = useState<"all" | "failed">("all");
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(false);
  const [currentFile, setCurrentFile] = useState<string | null>(null);

  const loadFiles = useCallback(async () => {
    try {
      const resp = await fetchFiles();
      setFiles(resp.files);
    } catch {
      // Server not ready
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFiles();
    const id = setInterval(loadFiles, POLL_INDEXING_IDLE_MS);
    return () => clearInterval(id);
  }, [loadFiles]);

  // Poll indexing status for "currently indexing" indicator
  useEffect(() => {
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const checkIndexing = async () => {
      try {
        const status = await fetchIndexingStatus();
        if (!cancelled) {
          // Find the first running task with a current_file
          const active = status.tasks.find((t) => t.state === "running" && t.current_file);
          setCurrentFile(active?.current_file ?? null);
          const isActive = status.tasks.some((t) => t.state === "running");
          const delay = isActive ? POLL_INDEXING_ACTIVE_MS : POLL_INDEXING_IDLE_MS;
          if (intervalId !== null) clearInterval(intervalId);
          if (!cancelled) intervalId = setInterval(checkIndexing, delay);
        }
      } catch { /* ignore */ }
    };
    checkIndexing();
    intervalId = setInterval(checkIndexing, POLL_INDEXING_ACTIVE_MS);
    return () => { cancelled = true; if (intervalId !== null) clearInterval(intervalId); };
  }, []);

  const handleRetryAll = async () => {
    setRetrying(true);
    try {
      await retryFailed();
      // Refresh after a short delay to let indexing start
      setTimeout(loadFiles, 1000);
    } catch {
      // ignore
    } finally {
      setRetrying(false);
    }
  };

  const handleRetrySingle = async (sourcePath: string) => {
    try {
      await retryFailed([sourcePath]);
      setTimeout(loadFiles, 1000);
    } catch {
      // ignore
    }
  };

  const displayed =
    filter === "all"
      ? files
      : files.filter((f) => f.status === "failed");

  const failedCount = files.filter((f) => f.status === "failed").length;
  const indexedCount = files.filter((f) => f.status === "indexed").length;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Indexing Log</h2>
        <div className="flex items-center gap-2 text-xs">
          <button
            onClick={() => setFilter("all")}
            className={`px-2 py-1 rounded transition-colors ${
              filter === "all"
                ? "bg-bg-elevated text-text-primary"
                : "text-text-muted hover:text-text-primary"
            }`}
          >
            All ({indexedCount + failedCount})
          </button>
          <button
            onClick={() => setFilter("failed")}
            className={`px-2 py-1 rounded transition-colors ${
              filter === "failed"
                ? "bg-accent-red/20 text-accent-red"
                : "text-text-muted hover:text-accent-red"
            }`}
          >
            Failed ({failedCount})
          </button>
          {failedCount > 0 && (
            <button
              onClick={handleRetryAll}
              disabled={retrying}
              className="flex items-center gap-1 px-2 py-1 rounded bg-accent-blue/20 text-accent-blue hover:bg-accent-blue/30 transition-colors disabled:opacity-50"
              title="Retry all failed files"
            >
              <RotateCcw
                size={12}
                className={retrying ? "animate-spin" : ""}
              />
              Retry All
            </button>
          )}
        </div>
      </div>

      <AnimatePresence mode="wait">
        {displayed.length === 0 && !currentFile ? (
          <motion.div
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            {loading ? (
              <div className="space-y-1">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 px-3 py-2 rounded bg-bg-surface"
                  >
                    <Skeleton
                      width="w-4"
                      height="h-4"
                      className="rounded shrink-0 mt-0.5"
                    />
                    <div className="flex-1 space-y-1">
                      <Skeleton width="w-48" height="h-4" />
                      <Skeleton width="w-16" height="h-3" />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={ScrollText}
                heading={
                  files.length === 0 ? "No files indexed yet" : "No failed files"
                }
                description={
                  files.length === 0
                    ? "Files will appear here as they are indexed."
                    : undefined
                }
              />
            )}
          </motion.div>
        ) : (
          <motion.div
            key={`${filter}-${currentFile ? "active" : "idle"}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="max-h-[calc(100vh-12rem)] overflow-y-auto"
          >
            <motion.div
              className="space-y-1"
              variants={staggerContainer}
              initial="hidden"
              animate="visible"
            >
              {/* Currently indexing file appears as first row with spinner */}
              {currentFile && filter === "all" && (
                <motion.div
                  key="current-indexing"
                  variants={slideUp}
                  className="px-3 py-2 rounded bg-bg-surface border border-accent-blue/20"
                >
                  <div className="flex items-start gap-2">
                    <Loader size={16} className="text-accent-blue animate-spin shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-mono truncate" title={currentFile}>
                        {fileName(currentFile)}
                      </p>
                      <p className="text-xs text-accent-blue">indexing...</p>
                    </div>
                  </div>
                </motion.div>
              )}
              {displayed.map((file, idx) => (
                <FileRow
                  key={file.source_path}
                  file={file}
                  expanded={expandedIdx === idx}
                  onToggleExpand={() =>
                    setExpandedIdx(expandedIdx === idx ? null : idx)
                  }
                  onRetry={() => handleRetrySingle(file.source_path)}
                  onOpen={() => invoke("open_file", { path: file.source_path })}
                  onShowInFolder={() => invoke("show_in_folder", { path: file.source_path })}
                />
              ))}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Props for a single file entry in the log. */
interface FileRowProps {
  file: IndexedFileInfo;
  expanded: boolean;
  onToggleExpand: () => void;
  onRetry: () => void;
  onOpen: () => void;
  onShowInFolder: () => void;
}

/** Single file row with status icon, name, date, and inline action icons. */
function FileRow({ file, expanded, onToggleExpand, onRetry, onOpen, onShowInFolder }: FileRowProps) {
  const isFailed = file.status === "failed";
  const hasError = isFailed && file.error;
  const name = fileName(file.source_path);

  return (
    <motion.div
      variants={slideUp}
      className="group/row px-3 py-2 rounded bg-bg-surface hover:bg-bg-elevated transition-colors"
    >
      <div
        className={`flex items-start gap-2 ${hasError ? "cursor-pointer" : ""}`}
        onClick={hasError ? onToggleExpand : undefined}
      >
        {isFailed ? (
          <XCircle size={16} className="text-accent-red shrink-0 mt-0.5" />
        ) : (
          <CheckCircle size={16} className="text-accent-green shrink-0 mt-0.5" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-mono truncate" title={file.source_path}>
            {name}
          </p>
          {!isFailed && (
            <p className="text-xs text-text-muted">{file.chunk_count} chunks</p>
          )}
          {isFailed && file.error && !expanded && (
            <p
              className="text-xs text-accent-red truncate"
              title={file.error}
            >
              {file.error}
            </p>
          )}
        </div>
        <span className="text-xs text-text-muted shrink-0 mt-0.5">
          {file.indexed_at?.slice(0, 10) ?? ""}
        </span>
        {/* Inline action icons: visible on hover, always visible for failed rows */}
        <div
          className={`flex items-center gap-1 shrink-0 mt-0.5 transition-opacity ${
            isFailed ? "opacity-100" : "opacity-0 group-hover/row:opacity-100"
          }`}
        >
          <button
            onClick={(e) => { e.stopPropagation(); onRetry(); }}
            className="p-1 rounded text-text-muted hover:text-accent-blue hover:bg-accent-blue/10 transition-colors"
            title="Retry indexing"
          >
            <RotateCcw size={13} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onOpen(); }}
            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
            title="Open file"
          >
            <ExternalLink size={13} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onShowInFolder(); }}
            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
            title="Open file location"
          >
            <FolderOpen size={13} />
          </button>
        </div>
        {hasError && (
          <ChevronDown
            size={14}
            className={`text-text-muted shrink-0 mt-0.5 transition-transform ${
              expanded ? "rotate-180" : ""
            }`}
          />
        )}
      </div>
      {/* Expanded error detail (error text only, actions are inline now) */}
      <AnimatePresence>
        {expanded && hasError && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <p className="text-xs text-accent-red mt-2 pl-6 whitespace-pre-wrap break-all">
              {file.error}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
