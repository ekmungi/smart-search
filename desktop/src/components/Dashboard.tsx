// Index dashboard with animated stats cards, server status, and format badges.

import { useState, useEffect, useRef } from "react";
import { motion } from "motion/react";
import { FileText, Layers, HardDrive, Clock, FolderSearch, AlertTriangle } from "lucide-react";
import {
  fetchHealth,
  fetchStats,
  fetchModelStatus,
  fetchIndexingStatus,
  pauseIndexing,
  resumeIndexing,
  type HealthResponse,
  type StatsResponse,
  type IndexingTask,
} from "../lib/api";
import type { ModelStatusResponse } from "../lib/api-types";
import ModelDownloadBanner from "./ModelDownloadBanner";
import {
  POLL_STATS_MS,
  POLL_INDEXING_ACTIVE_MS,
  POLL_INDEXING_IDLE_MS,
  POLL_MODEL_MS,
} from "../lib/constants";
import { staggerContainer } from "../lib/animations";
import StatsCard, { StatsCardSkeleton } from "./StatsCard";
import IndexingBanner from "./IndexingBanner";
import IndexingControls from "./IndexingControls";
import ModelTimeoutDialog from "./ModelTimeoutDialog";
import EmptyState from "./EmptyState";

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

interface DashboardProps {
  /** Whether the backend has ever responded successfully this session. */
  everConnected: boolean;
  /** Callback to notify App that the backend responded successfully. */
  onConnected: () => void;
}

export default function Dashboard({ everConnected, onConnected }: DashboardProps) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modelCached, setModelCached] = useState<boolean | null>(null);
  const [activeTasks, setActiveTasks] = useState<IndexingTask[]>([]);
  const [startingUp, setStartingUp] = useState<boolean>(!everConnected);
  const failingSince = useRef<number | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatusResponse | null>(null);
  const [indexingPaused, setIndexingPaused] = useState(false);
  const [showTimeoutDialog, setShowTimeoutDialog] = useState(false);
  const [timeoutDismissed, setTimeoutDismissed] = useState(false);

  // Poll health + stats
  useEffect(() => {
    const poll = async () => {
      try {
        const h = await fetchHealth();
        setHealth(h);
        setError(null);
        setStartingUp(false);
        onConnected();
        failingSince.current = null;
      } catch {
        setHealth(null);
        setError("Backend not reachable");
        if (failingSince.current === null) {
          failingSince.current = Date.now();
        }
        if (Date.now() - failingSince.current >= 30_000) {
          setStartingUp(false);
        }
      }
      try {
        const s = await fetchStats();
        setStats(s);
      } catch {
        // Stats may time out during heavy indexing
      }
    };
    poll();
    const interval = setInterval(poll, POLL_STATS_MS);
    return () => clearInterval(interval);
  }, []);

  // Poll indexing status
  useEffect(() => {
    if (!health) return;
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const checkIndexing = async () => {
      try {
        const status = await fetchIndexingStatus();
        if (!cancelled) {
          setActiveTasks(status.tasks);
          setIndexingPaused(status.paused ?? false);
          const nextDelay = status.active > 0 ? POLL_INDEXING_ACTIVE_MS : POLL_INDEXING_IDLE_MS;
          if (intervalId !== null) clearInterval(intervalId);
          if (!cancelled) intervalId = setInterval(checkIndexing, nextDelay);
        }
      } catch { /* ignore */ }
    };
    checkIndexing();
    intervalId = setInterval(checkIndexing, POLL_INDEXING_ACTIVE_MS);
    return () => { cancelled = true; if (intervalId !== null) clearInterval(intervalId); };
  }, [health]);

  // Poll model status
  useEffect(() => {
    if (!health) return;
    let cancelled = false;
    const checkModel = async () => {
      try {
        const status = await fetchModelStatus();
        if (!cancelled) {
          setModelStatus(status);
          setModelCached(status.cached);
          if (status.download_status === "timeout" && !timeoutDismissed) {
            setShowTimeoutDialog(true);
          }
          if (status.cached) {
            setShowTimeoutDialog(false);
          }
        }
      } catch { /* retry */ }
    };
    checkModel();
    if (modelCached !== true) {
      const interval = setInterval(checkModel, POLL_MODEL_MS);
      return () => { cancelled = true; clearInterval(interval); };
    }
    return () => { cancelled = true; };
  }, [health, modelCached, timeoutDismissed]);

  const showSkeleton = !health && !error;
  const hasNoFolders = health && stats && stats.document_count === 0 && activeTasks.length === 0;

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
                  ? "bg-accent-amber animate-pulse"
                  : everConnected
                    ? "bg-accent-amber animate-pulse"
                    : "bg-accent-red"
            }`}
          />
          <span className="text-sm text-text-secondary">
            {health
              ? `v${health.version}`
              : startingUp
                ? "Starting up..."
                : everConnected
                  ? "Reconnecting..."
                  : "Offline"}
          </span>
        </div>
      </div>

      {/* Error / startup banners */}
      {error && startingUp && (
        <div className="bg-bg-surface border border-accent-amber/30 rounded-lg p-4 mb-6 text-sm text-text-secondary">
          Server is starting up, please wait...
        </div>
      )}
      {error && !startingUp && (
        <div className={`bg-bg-surface border ${everConnected ? "border-accent-amber/30" : "border-accent-red/30"} rounded-lg p-4 mb-6 text-sm`}>
          {everConnected ? (
            <span className="text-accent-amber">Backend disconnected &mdash; reconnecting...</span>
          ) : (
            <span className="text-accent-red">
              {error} &mdash; Start the backend with:{" "}
              <code className="text-text-primary">smart-search serve</code>
            </span>
          )}
        </div>
      )}

      <ModelDownloadBanner modelStatus={modelStatus} />

      {showTimeoutDialog && modelStatus && (
        <ModelTimeoutDialog
          downloadUrl={modelStatus.download_url}
          cachePath={modelStatus.cache_path}
          onContinueKeywordOnly={() => setTimeoutDismissed(true)}
          onDismiss={() => setShowTimeoutDialog(false)}
        />
      )}

      {/* Empty state: no folders configured */}
      {hasNoFolders && (
        <EmptyState
          icon={FolderSearch}
          heading="No folders configured"
          description="Add a folder to start indexing your documents for semantic search."
        />
      )}

      {/* Stats grid -- skeleton while loading, animated cards when ready */}
      {!hasNoFolders && (
        <>
          {showSkeleton ? (
            <div className="grid grid-cols-[repeat(auto-fit,minmax(164px,1fr))] gap-4 mb-6">
              {[0, 1, 2, 3, 4].map((i) => (
                <StatsCardSkeleton key={i} />
              ))}
            </div>
          ) : (
            <motion.div
              className="grid grid-cols-[repeat(auto-fit,minmax(164px,1fr))] gap-4 mb-6"
              variants={staggerContainer}
              initial="hidden"
              animate="visible"
            >
              <StatsCard
                icon={FileText}
                label="Documents"
                value={stats?.document_count ?? 0}
                iconColor="text-accent-blue"
              />
              <StatsCard
                icon={AlertTriangle}
                label="Failed"
                value={stats?.failed_count ?? 0}
                iconColor="text-accent-red"
              />
              <StatsCard
                icon={Layers}
                label="Chunks"
                value={stats?.chunk_count ?? 0}
                iconColor="text-accent-green"
              />
              <StatsCard
                icon={HardDrive}
                label="Index Size"
                value={stats ? `${stats.index_size_mb} MB` : "0 MB"}
                iconColor="text-accent-amber"
              />
              <StatsCard
                icon={Clock}
                label="Last Indexed"
                value={
                  stats?.last_indexed_at
                    ? (() => {
                        const d = new Date(stats.last_indexed_at);
                        const y = d.getFullYear();
                        const m = String(d.getMonth() + 1).padStart(2, "0");
                        const day = String(d.getDate()).padStart(2, "0");
                        return `${y}/${m}/${day}`;
                      })()
                    : "Never"
                }
                iconColor="text-text-secondary"
              />
            </motion.div>
          )}

          {/* Indexing controls + banner */}
          {(activeTasks.some(t => t.state === "running") || indexingPaused) && (
            <div className="flex items-center gap-2 mb-2">
              <IndexingControls
                paused={indexingPaused}
                hasActiveTasks={activeTasks.some(t => t.state === "running")}
                onPause={async () => { await pauseIndexing(); setIndexingPaused(true); }}
                onResume={async () => { await resumeIndexing(); setIndexingPaused(false); }}
              />
            </div>
          )}
          <IndexingBanner tasks={activeTasks} />

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
                  <span className="text-text-primary font-mono">
                    {formatUptime(health.uptime_seconds)}
                  </span>
                </span>
                <span className="text-text-secondary">
                  Status: <span className="text-accent-green">Running</span>
                </span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
