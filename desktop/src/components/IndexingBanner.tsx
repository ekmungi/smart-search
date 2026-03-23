// Compact multi-folder indexing progress banner for the dashboard.

import type { IndexingTask } from "../lib/api-types";

interface IndexingBannerProps {
  tasks: IndexingTask[];
}

/** Per-folder progress row inside the indexing banner. */
function FolderProgress({ task }: { task: IndexingTask }) {
  const done = task.indexed + task.skipped + task.failed;
  const pct = task.total > 0 ? (done / task.total) * 100 : 0;
  const failPct = task.total > 0 ? (task.failed / task.total) * 100 : 0;
  const folderName = task.folder.split(/[\\/]/).pop() ?? task.folder;

  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="text-xs text-text-primary truncate min-w-0 w-32 shrink-0">
        {folderName}
      </span>
      <div className="flex-1 bg-bg-elevated rounded-full h-1.5 relative overflow-hidden">
        {/* Blue: indexed+skipped portion */}
        <div
          className="absolute inset-y-0 left-0 bg-accent-blue rounded-full transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
        {/* Amber overlay: failed portion */}
        {failPct > 0 && (
          <div
            className="absolute inset-y-0 bg-accent-amber rounded-full transition-all duration-300"
            style={{ left: `${pct - failPct}%`, width: `${failPct}%` }}
          />
        )}
      </div>
      <span className="text-xs text-text-muted tabular-nums shrink-0 w-20 text-right">
        {done}/{task.total}
        {task.failed > 0 && (
          <span className="text-accent-amber ml-1">({task.failed} err)</span>
        )}
      </span>
    </div>
  );
}

/** Dashboard banner showing per-folder indexing progress. */
export default function IndexingBanner({ tasks }: IndexingBannerProps) {
  const activeTasks = tasks.filter(
    (t) => t.state === "running" || t.state === "pending",
  );
  const failedTasks = tasks.filter((t) => t.state === "failed");

  if (activeTasks.length === 0 && failedTasks.length === 0) return null;

  return (
    <>
      {/* Active indexing */}
      {activeTasks.length > 0 && (
        <div className="bg-bg-surface border border-accent-blue/30 rounded-lg p-4 mb-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-4 h-4 border-2 border-accent-blue border-t-transparent rounded-full animate-spin shrink-0" />
            <span className="text-sm font-medium text-text-primary">
              Indexing {activeTasks.length} folder{activeTasks.length > 1 ? "s" : ""}
            </span>
          </div>
          <div className="pl-7">
            {activeTasks.map((task) => (
              <FolderProgress key={task.task_id} task={task} />
            ))}
          </div>
        </div>
      )}

      {/* Failed tasks */}
      {failedTasks.length > 0 && (
        <div className="bg-bg-surface border border-accent-red/30 rounded-lg p-4 mb-6 text-sm text-accent-red">
          Indexing failed for:{" "}
          {failedTasks.map((t) => t.folder.split(/[\\/]/).pop()).join(", ")}
        </div>
      )}
    </>
  );
}
