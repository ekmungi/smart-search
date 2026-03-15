// Index dashboard with stats cards, server status, and format badges.

import { useState, useEffect } from "react";
import { FileText, Layers, HardDrive, Clock } from "lucide-react";
import {
  fetchHealth,
  fetchStats,
  fetchModelStatus,
  type HealthResponse,
  type StatsResponse,
} from "../lib/api";
import StatsCard from "./StatsCard";

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modelCached, setModelCached] = useState<boolean | null>(null);

  useEffect(() => {
    const poll = async () => {
      try {
        const [h, s] = await Promise.all([fetchHealth(), fetchStats()]);
        setHealth(h);
        setStats(s);
        setError(null);
      } catch {
        setError("Backend not reachable");
      }
    };

    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, []);

  // Poll model status until cached (first-launch download UX)
  useEffect(() => {
    if (!health) return;

    let cancelled = false;
    const checkModel = async () => {
      try {
        const status = await fetchModelStatus();
        if (!cancelled) setModelCached(status.cached);
      } catch {
        // Backend not ready yet -- will retry
      }
    };

    checkModel();

    // Poll every 3s while model is downloading, stop once cached
    if (modelCached !== true) {
      const interval = setInterval(checkModel, 3000);
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
              health ? "bg-accent-green" : "bg-accent-red"
            }`}
          />
          <span className="text-sm text-text-secondary">
            {health ? `v${health.version}` : "Offline"}
          </span>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-bg-surface border border-accent-red/30 rounded-lg p-4 mb-6 text-sm text-accent-red">
          {error} &mdash; Start the backend with:{" "}
          <code className="text-text-primary">smart-search serve</code>
        </div>
      )}

      {/* Model download banner (first-launch UX) */}
      {health && modelCached === false && (
        <div className="bg-bg-surface border border-accent-amber/30 rounded-lg p-4 mb-6">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 border-2 border-accent-amber border-t-transparent rounded-full animate-spin" />
            <div>
              <p className="text-sm font-medium text-text-primary">
                Downloading embedding model...
              </p>
              <p className="text-xs text-text-secondary mt-1">
                First-time setup (~250 MB). Search will be available once
                complete.
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
                .{fmt}
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
                {Math.round(health.uptime_seconds)}s
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
