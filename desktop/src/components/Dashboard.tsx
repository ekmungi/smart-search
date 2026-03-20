// Index dashboard with stats cards, server status, and format badges.

import { useState, useEffect, useRef } from "react";
import { FileText, Layers, HardDrive, Clock } from "lucide-react";
import {
  fetchHealth,
  fetchStats,
  fetchModelStatus,
  fetchIndexingStatus,
  type HealthResponse,
  type StatsResponse,
  type IndexingTask,
} from "../lib/api";
import {
  POLL_STATS_MS,
  POLL_INDEXING_ACTIVE_MS,
  POLL_INDEXING_IDLE_MS,
  POLL_MODEL_MS,
} from "../lib/constants";
import StatsCard from "./StatsCard";

/** Format seconds into human-readable duration (e.g. "2h 15m", "3d 4h"). */
function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  const remainMins = mins % 60;
  if (hours < 24) return remainMins > 0 ? `${hours}h ${remainMins}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  const remainHours = hours % 24;
  return remainHours > 0 ? `${days}d ${remainHours}h` : `${days}d`;
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modelCached, setModelCached] = useState<boolean | null>(null);
  const [modelName, setModelName] = useState<string | null>(null);
  const [activeTasks, setActiveTasks] = useState<IndexingTask[]>([]);
  // True on first load: assume backend is starting up, not offline.
  // Stays true until health succeeds OR 30s of continuous failure elapses.
  const [startingUp, setStartingUp] = useState<boolean>(true);
  // Tracks the timestamp of the first consecutive health failure (null when healthy).
  const failingSince = useRef<number | null>(null);

  useEffect(() => {
    const poll = async () => {
      // Health and stats are independent: stats may fail during indexing
      // (DB contention) but health should still update the status dot.
      try {
        const h = await fetchHealth();
        setHealth(h);
        setError(null);
        setStartingUp(false);
        failingSince.current = null;
      } catch {
        setHealth(null);
        setError("Backend not reachable");
        if (failingSince.current === null) {
          failingSince.current = Date.now();
        }
        const elapsed = Date.now() - failingSince.current;
        if (elapsed >= 30_000) {
          setStartingUp(false);
        }
      }
      // Stats fetch is best-effort; failure does not affect health status.
      try {
        const s = await fetchStats();
        setStats(s);
      } catch {
        // Stats may time out during heavy indexing -- keep previous values
      }
    };

    poll();
    const interval = setInterval(poll, POLL_STATS_MS);
    return () => clearInterval(interval);
  }, []);

  // Poll indexing status every 2s while tasks are active, slow down when idle
  useEffect(() => {
    if (!health) return;

    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const checkIndexing = async () => {
      try {
        const status = await fetchIndexingStatus();
        if (!cancelled) {
          setActiveTasks(status.tasks);
          // When no active tasks, switch to slow polling (10s) to reduce load
          const nextDelay = status.active > 0 ? POLL_INDEXING_ACTIVE_MS : POLL_INDEXING_IDLE_MS;
          if (intervalId !== null) clearInterval(intervalId);
          if (!cancelled) {
            intervalId = setInterval(checkIndexing, nextDelay);
          }
        }
      } catch {
        // Backend not ready or endpoint missing -- ignore
      }
    };

    checkIndexing();
    intervalId = setInterval(checkIndexing, POLL_INDEXING_ACTIVE_MS);

    return () => {
      cancelled = true;
      if (intervalId !== null) clearInterval(intervalId);
    };
  }, [health]);

  // Poll model status until cached (first-launch download UX)
  useEffect(() => {
    if (!health) return;

    let cancelled = false;
    const checkModel = async () => {
      try {
        const status = await fetchModelStatus();
        if (!cancelled) {
          setModelCached(status.cached);
          setModelName(status.model_name);
        }
      } catch {
        // Backend not ready yet -- will retry
      }
    };

    checkModel();

    // Poll every 3s while model is downloading, stop once cached
    if (modelCached !== true) {
      const interval = setInterval(checkModel, POLL_MODEL_MS);
      return () => {
        cancelled = true;
        clearInterval(interval);
      };
    }
    return () => { cancelled = true; };
  }, [health, modelCached]);

  return (
    <div>
      {/* Header with status dot */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${
              health
                ? "bg-accent-green"
                : startingUp
                  ? "bg-accent-amber"
                  : "bg-accent-red"
            }`}
          />
          <span className="text-sm text-text-secondary">
            {health
              ? `v${health.version}`
              : startingUp
                ? "Starting up..."
                : "Offline"}
          </span>
        </div>
      </div>

      {/* Error / startup banner */}
      {error && startingUp && (
        <div className="bg-bg-surface border border-accent-amber/30 rounded-lg p-4 mb-6 text-sm text-text-secondary">
          Server is starting up, please wait...
        </div>
      )}
      {error && !startingUp && (
        <div className="bg-bg-surface border border-accent-red/30 rounded-lg p-4 mb-6 text-sm text-accent-red">
          {error} &mdash; Start the backend with:{" "}
          <code className="text-text-primary">smart-search serve</code>
        </div>
      )}

      {/* Indexing in progress banner */}
      {activeTasks.some((t) => t.state === "running" || t.state === "pending") && (
        <div className="bg-bg-surface border border-accent-blue/30 rounded-lg p-4 mb-6">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 border-2 border-accent-blue border-t-transparent rounded-full animate-spin" />
            <div>
              <p className="text-sm font-medium text-text-primary">
                Indexing{" "}
                {activeTasks
                  .filter((t) => t.state === "running" || t.state === "pending")
                  .map((t) => t.folder.split(/[\\/]/).pop())
                  .join(", ")}
                ...
              </p>
              <p className="text-xs text-text-secondary mt-1">
                {(() => {
                  // Include all tasks (running + completed) for accurate totals
                  const done = activeTasks.reduce((sum, t) => sum + t.indexed + t.skipped + t.failed, 0);
                  const total = activeTasks.reduce((sum, t) => sum + t.total, 0);
                  const failed = activeTasks.reduce((sum, t) => sum + t.failed, 0);
                  const detail = failed > 0 ? `, ${failed} failed` : "";
                  return total > 0 ? `${done} of ${total} files processed${detail}` : `${done} files processed${detail}`;
                })()}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Completed/failed task results (shown briefly via state) */}
      {activeTasks.some((t) => t.state === "failed") && (
        <div className="bg-bg-surface border border-accent-red/30 rounded-lg p-4 mb-6 text-sm text-accent-red">
          Indexing failed for:{" "}
          {activeTasks
            .filter((t) => t.state === "failed")
            .map((t) => t.folder.split(/[\\/]/).pop())
            .join(", ")}
        </div>
      )}

      {/* Model download banner (first-launch UX) */}
      {health && modelCached === false && (
        <div className="bg-bg-surface border border-accent-amber/30 rounded-lg p-4 mb-6">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 border-2 border-accent-amber border-t-transparent rounded-full animate-spin" />
            <div>
              <p className="text-sm font-medium text-text-primary">
                Downloading {modelName ?? "embedding model"}...
              </p>
              <p className="text-xs text-text-secondary mt-1">
                First-time setup. Search will be available once complete.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          icon={FileText}
          label="Documents"
          value={stats?.document_count ?? "--"}
        />
        <StatsCard
          icon={Layers}
          label="Chunks"
          value={stats?.chunk_count ?? "--"}
        />
        <StatsCard
          icon={HardDrive}
          label="Index Size"
          value={stats ? `${stats.index_size_mb} MB` : "--"}
        />
        <StatsCard
          icon={Clock}
          label="Last Indexed"
          value={
            stats?.last_indexed_at
              ? new Date(stats.last_indexed_at).toLocaleDateString()
              : "Never"
          }
        />
      </div>

      {/* Format badges */}
      {stats && stats.formats_indexed.length > 0 && (
        <div className="mt-6 bg-bg-surface rounded-lg p-4">
          <h2 className="text-sm font-medium text-text-secondary mb-2">
            Indexed Formats
          </h2>
          <div className="flex gap-2">
            {stats.formats_indexed.map((fmt) => (
              <span
                key={fmt}
                className="px-2 py-1 bg-bg-elevated rounded text-xs text-text-primary"
              >
                {fmt}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Server info */}
      {health && (
        <div className="mt-4 bg-bg-surface rounded-lg p-4">
          <h2 className="text-sm font-medium text-text-secondary mb-2">
            Server
          </h2>
          <div className="flex gap-6 text-sm">
            <span className="text-text-secondary">
              Uptime:{" "}
              <span className="text-text-primary">
                {formatUptime(health.uptime_seconds)}
              </span>
            </span>
            <span className="text-text-secondary">
              Status: <span className="text-accent-green">Running</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
