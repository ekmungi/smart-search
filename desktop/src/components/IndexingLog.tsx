// Real-time indexing log showing per-file status with success/failure icons.
// Session-only: cleared on app restart, maintained while the app is open.

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircle, XCircle, ScrollText, ChevronDown } from "lucide-react";
import { fetchIndexingStatus, type ProcessedFile } from "../lib/api";
import { POLL_INDEXING_ACTIVE_MS } from "../lib/constants";
import { staggerContainer, slideUp } from "../lib/animations";
import Skeleton from "./Skeleton";
import EmptyState from "./EmptyState";

export default function IndexingLog() {
  const [files, setFiles] = useState<ProcessedFile[]>([]);
  const [filter, setFilter] = useState<"all" | "failed">("all");
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [isPolling, setIsPolling] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const prevCount = useRef(0);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const status = await fetchIndexingStatus();
        if (cancelled) return;
        const allFiles: ProcessedFile[] = [];
        for (const task of status.tasks) {
          for (const f of task.processed_files ?? []) {
            allFiles.push(f);
          }
        }
        setFiles(allFiles);
        setIsPolling(status.active > 0);
        if (allFiles.length > prevCount.current) {
          prevCount.current = allFiles.length;
          setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
        }
      } catch {
        // Server not ready
      }
    };

    poll();
    const id = setInterval(poll, POLL_INDEXING_ACTIVE_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const displayed = filter === "all"
    ? files.filter((f) => f.status !== "skipped")
    : files.filter((f) => f.status === "failed");

  const failedCount = files.filter((f) => f.status === "failed").length;
  const indexedCount = files.filter((f) => f.status === "indexed").length;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Indexing Log</h2>
        <div className="flex gap-2 text-xs">
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
        </div>
      </div>

      <AnimatePresence mode="wait">
        {displayed.length === 0 ? (
          <motion.div
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            {/* Skeleton rows while actively indexing but no results yet */}
            {files.length === 0 && isPolling ? (
              <div className="space-y-1">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div key={i} className="flex items-start gap-2 px-3 py-2 rounded bg-bg-surface">
                    <Skeleton width="w-4" height="h-4" className="rounded shrink-0 mt-0.5" />
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
                heading={files.length === 0 ? "No files processed yet" : "No failed files"}
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
            key={filter}
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
              {displayed.map((file, idx) => (
                <FileRow
                  key={`${file.path}-${idx}`}
                  file={file}
                  expanded={expandedIdx === idx}
                  onToggleExpand={() =>
                    setExpandedIdx(expandedIdx === idx ? null : idx)
                  }
                />
              ))}
            </motion.div>
            <div ref={bottomRef} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Props for a single file entry in the log. */
interface FileRowProps {
  file: ProcessedFile;
  expanded: boolean;
  onToggleExpand: () => void;
}

/** Single file row with status icon, name, timestamp, and expandable error. */
function FileRow({ file, expanded, onToggleExpand }: FileRowProps) {
  const isFailed = file.status === "failed";
  const hasError = isFailed && file.error;

  return (
    <motion.div
      variants={slideUp}
      className="px-3 py-2 rounded bg-bg-surface hover:bg-bg-elevated transition-colors"
    >
      <div
        className={`flex items-start gap-2 ${hasError ? "cursor-pointer" : ""}`}
        onClick={hasError ? onToggleExpand : undefined}
      >
        {file.status === "indexed" ? (
          <CheckCircle size={16} className="text-accent-green shrink-0 mt-0.5" />
        ) : (
          <XCircle size={16} className="text-accent-red shrink-0 mt-0.5" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm truncate" title={file.path}>
            {file.name}
          </p>
          {file.status === "indexed" && file.chunks && (
            <p className="text-xs text-text-muted">{file.chunks} chunks</p>
          )}
          {isFailed && file.error && !expanded && (
            <p className="text-xs text-accent-red truncate" title={file.error}>
              {file.error}
            </p>
          )}
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
      {/* Expanded error detail */}
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
