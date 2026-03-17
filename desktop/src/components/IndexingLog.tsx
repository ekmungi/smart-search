// Real-time indexing log showing per-file status with success/failure icons.
// Session-only: cleared on app restart, maintained while the app is open.

import { useState, useEffect, useRef } from "react";
import { CheckCircle, XCircle, ScrollText } from "lucide-react";
import { fetchIndexingStatus, type ProcessedFile, type IndexingTask } from "../lib/api";

export default function IndexingLog() {
  const [files, setFiles] = useState<ProcessedFile[]>([]);
  const [filter, setFilter] = useState<"all" | "failed">("all");
  const bottomRef = useRef<HTMLDivElement>(null);
  const prevCount = useRef(0);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const status = await fetchIndexingStatus();
        if (cancelled) return;
        // Flatten all processed files from all tasks
        const allFiles: ProcessedFile[] = [];
        for (const task of status.tasks) {
          for (const f of task.processed_files ?? []) {
            allFiles.push(f);
          }
        }
        setFiles(allFiles);
        // Auto-scroll when new files arrive
        if (allFiles.length > prevCount.current) {
          prevCount.current = allFiles.length;
          setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
        }
      } catch {
        // Server not ready
      }
    };

    poll();
    const id = setInterval(poll, 2000);
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
            className={`px-2 py-1 rounded ${
              filter === "all"
                ? "bg-bg-elevated text-text-primary"
                : "text-text-muted hover:text-text-primary"
            }`}
          >
            All ({indexedCount + failedCount})
          </button>
          <button
            onClick={() => setFilter("failed")}
            className={`px-2 py-1 rounded ${
              filter === "failed"
                ? "bg-accent-red/20 text-accent-red"
                : "text-text-muted hover:text-accent-red"
            }`}
          >
            Failed ({failedCount})
          </button>
        </div>
      </div>

      {displayed.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-text-muted">
          <ScrollText size={32} className="mb-2 opacity-50" />
          <p className="text-sm">
            {files.length === 0
              ? "No files processed yet"
              : "No failed files"}
          </p>
        </div>
      ) : (
        <div className="space-y-1 max-h-[calc(100vh-12rem)] overflow-y-auto">
          {displayed.map((file, idx) => (
            <div
              key={`${file.path}-${idx}`}
              className="flex items-start gap-2 px-3 py-2 rounded bg-bg-surface hover:bg-bg-elevated transition-colors"
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
                  <p className="text-xs text-text-muted">
                    {file.chunks} chunks
                  </p>
                )}
                {file.status === "failed" && file.error && (
                  <p className="text-xs text-accent-red truncate" title={file.error}>
                    {file.error}
                  </p>
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
