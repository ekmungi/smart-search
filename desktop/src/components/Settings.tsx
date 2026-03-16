// Settings panel: view/edit configuration, font size slider, autostart, MCP status.

import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { enable, disable, isEnabled } from "@tauri-apps/plugin-autostart";
import { Save, Check, X, Loader2, AlertTriangle } from "lucide-react";
import {
  fetchConfig,
  updateConfig,
  fetchModels,
} from "../lib/api";
import type { ModelInfo } from "../lib/api";
import { ShortcutRecorder } from "./ShortcutRecorder";

/** Font size range for the proportional scaling slider. */
const FONT_MIN = 14;
const FONT_MAX = 22;
const FONT_DEFAULT = 18;

export default function Settings() {
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [fontSize, setFontSize] = useState(FONT_DEFAULT);
  const [autostart, setAutostart] = useState(false);
  const [mcpRegistered, setMcpRegistered] = useState(() => {
    // Use cached value to avoid re-checking on every mount
    return localStorage.getItem("smart-search-mcp-registered") === "true";
  });
  const [mcpChecking, setMcpChecking] = useState(() => {
    // Skip spinner if we already have a cached result
    return localStorage.getItem("smart-search-mcp-registered") === null;
  });
  const [mcpRegistering, setMcpRegistering] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [confirmDialog, setConfirmDialog] = useState<{
    model: string;
    dims: number;
  } | null>(null);
  const [reindexing, setReindexing] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await fetchConfig();
      setConfig(res.config);
      setError(null);
    } catch {
      setError("Could not load configuration");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    // Load saved font size from localStorage
    const stored = localStorage.getItem("smart-search-font-size");
    if (stored) {
      const size = parseInt(stored, 10);
      setFontSize(size);
      document.documentElement.style.fontSize = `${size}px`;
    }
    // Check autostart status
    isEnabled().then(setAutostart).catch(() => {});
    // Fetch available models
    fetchModels()
      .then((res) => setModels(res.models))
      .catch(() => {});
    // Check MCP registration status only if not cached (avoid spinner on re-mount)
    const cached = localStorage.getItem("smart-search-mcp-registered");
    if (cached === null) {
      invoke<boolean>("check_mcp_registered")
        .then((registered) => {
          setMcpRegistered(registered);
          localStorage.setItem("smart-search-mcp-registered", String(registered));
        })
        .catch(() => {})
        .finally(() => setMcpChecking(false));
    }
  }, [refresh]);

  /** Toggle font size and persist to localStorage. */
  const handleFontChange = (size: number) => {
    setFontSize(size);
    document.documentElement.style.fontSize = `${size}px`;
    localStorage.setItem("smart-search-font-size", String(size));
  };

  /** Save a backend config key. */
  const handleSave = async (key: string, value: unknown) => {
    try {
      const res = await updateConfig({ [key]: value });
      setConfig(res.config);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      setError("Failed to save configuration");
    }
  };

  /** Toggle start-on-login via the autostart plugin. */
  const handleAutostartToggle = async () => {
    try {
      if (autostart) {
        await disable();
      } else {
        await enable();
      }
      const enabled = await isEnabled();
      setAutostart(enabled);
    } catch {
      setError("Failed to update autostart setting");
    }
  };

  /** Register smart-search as MCP server with Claude Code. */
  const handleRegisterMcp = async () => {
    setMcpRegistering(true);
    setError(null);
    try {
      await invoke<string>("register_mcp");
      setMcpRegistered(true);
      localStorage.setItem("smart-search-mcp-registered", "true");
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(String(err));
    } finally {
      setMcpRegistering(false);
    }
  };

  /** Update the global shortcut: save to backend config and apply live via Tauri. */
  const handleShortcutChange = async (newShortcut: string) => {
    try {
      const res = await updateConfig({ shortcut_key: newShortcut });
      setConfig(res.config);
      await invoke<string>("update_shortcut", { shortcut: newShortcut });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(`Failed to update shortcut: ${String(err)}`);
    }
  };

  /** Initiate a model change — shows confirmation dialog. */
  const handleModelChangeRequest = (modelId: string) => {
    const info = models.find((m) => m.model_id === modelId);
    if (!info) return;
    if (modelId === config.embedding_model) return;
    setConfirmDialog({ model: modelId, dims: info.default_dims });
  };

  /** Execute the confirmed model change: update config, rebuild, re-index. */
  const handleModelChangeConfirm = async () => {
    if (!confirmDialog) return;
    setReindexing(true);
    setError(null);
    try {
      const res = await updateConfig({
        embedding_model: confirmDialog.model,
        embedding_dimensions: confirmDialog.dims,
      });
      setConfig(res.config);
      // Backend already submits all folders for re-indexing when model changes
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(`Model change failed: ${String(err)}`);
    } finally {
      setReindexing(false);
      setConfirmDialog(null);
    }
  };

  if (loading) {
    return <p className="text-text-secondary text-sm">Loading settings...</p>;
  }

  const model = String(config.embedding_model || "unknown");
  const dims = String(config.embedding_dimensions || "unknown");
  const excludes = Array.isArray(config.exclude_patterns)
    ? config.exclude_patterns
    : [];
  const searchLimit = Number(config.search_default_limit || 10);
  const relevanceThreshold = Number(config.relevance_threshold ?? 0.50);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Settings</h1>
        {saved && (
          <span className="text-sm text-accent-green flex items-center gap-1">
            <Save size={14} /> Saved
          </span>
        )}
      </div>

      {error && (
        <div className="bg-bg-surface border border-accent-red/30 rounded-lg p-3 mb-4 text-sm text-accent-red">
          {error}
        </div>
      )}

      {/* Appearance */}
      <Section title="Appearance">
        <SettingRow label="Font Size" description="Proportional UI scaling">
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={FONT_MIN}
              max={FONT_MAX}
              value={fontSize}
              onChange={(e) => handleFontChange(parseInt(e.target.value, 10))}
              className="w-32 accent-accent-blue"
            />
            <span className="text-sm text-text-secondary w-10 text-right">
              {fontSize}px
            </span>
          </div>
        </SettingRow>
      </Section>

      {/* System */}
      <Section title="System">
        <SettingRow
          label="Start on Login"
          description="Launch Smart Search when you sign in"
        >
          <button
            onClick={handleAutostartToggle}
            className={`relative w-10 h-5 rounded-full transition-colors ${
              autostart ? "bg-accent-blue" : "bg-bg-elevated"
            }`}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-text-primary transition-transform ${
                autostart ? "translate-x-5" : ""
              }`}
            />
          </button>
        </SettingRow>
        <SettingRow
          label="MCP Server"
          description="Register with Claude Code for AI search"
        >
          {mcpChecking ? (
            <Loader2 size={16} className="text-text-muted animate-spin" />
          ) : mcpRegistered ? (
            <span className="text-sm text-accent-green flex items-center gap-1">
              <Check size={14} /> Registered
            </span>
          ) : (
            <button
              onClick={handleRegisterMcp}
              disabled={mcpRegistering}
              className="px-3 py-1 text-sm bg-accent-blue text-text-primary rounded hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
            >
              {mcpRegistering ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <X size={14} />
              )}
              {mcpRegistering ? "Registering..." : "Register"}
            </button>
          )}
        </SettingRow>
        <SettingRow
          label="Quick Search Shortcut"
          description="Global hotkey to toggle the search overlay"
        >
          <ShortcutRecorder
            value={String(config.shortcut_key || "Ctrl+Space")}
            onChange={handleShortcutChange}
          />
        </SettingRow>
      </Section>

      {/* Embedding Model */}
      <Section title="Embedding">
        <SettingRow
          label="Model"
          description="Changing model requires full re-index"
        >
          {models.length > 0 ? (
            <select
              value={model}
              onChange={(e) => handleModelChangeRequest(e.target.value)}
              disabled={reindexing}
              className="bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary max-w-[220px]"
            >
              {models.map((m) => (
                <option key={m.model_id} value={m.model_id}>
                  {m.display_name} ({m.size_mb} MB, {(m.mteb_retrieval * 100).toFixed(1)}%)
                </option>
              ))}
            </select>
          ) : (
            <span className="text-sm text-text-primary">{model}</span>
          )}
        </SettingRow>
        {(() => {
          const selectedModel = models.find((m) => m.model_id === model);
          const hasMrl = selectedModel && selectedModel.mrl_dims.length > 0;
          return (
            <SettingRow
              label="Dimensions"
              description={
                hasMrl
                  ? "Matryoshka: lower = faster search, higher = better quality"
                  : "Fixed dimensions for this model"
              }
            >
              {hasMrl ? (
                <select
                  value={Number(dims)}
                  onChange={(e) =>
                    handleSave(
                      "embedding_dimensions",
                      parseInt(e.target.value, 10),
                    )
                  }
                  className="bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary"
                >
                  {selectedModel.mrl_dims.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="text-sm text-text-primary">{dims}</span>
              )}
            </SettingRow>
          );
        })()}
      </Section>

      {/* Model change confirmation dialog */}
      {confirmDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-bg-surface border border-border rounded-lg p-6 max-w-md mx-4">
            <div className="flex items-center gap-2 mb-3 text-amber-400">
              <AlertTriangle size={20} />
              <h3 className="font-semibold">Change Embedding Model?</h3>
            </div>
            <p className="text-sm text-text-secondary mb-4">
              Changing the embedding model requires rebuilding the entire index.
              All documents will be re-indexed. This may take several minutes.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmDialog(null)}
                className="px-3 py-1.5 text-sm rounded bg-bg-elevated text-text-secondary hover:bg-border"
              >
                Cancel
              </button>
              <button
                onClick={handleModelChangeConfirm}
                disabled={reindexing}
                className="px-3 py-1.5 text-sm rounded bg-accent-blue text-text-primary hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
              >
                {reindexing && <Loader2 size={14} className="animate-spin" />}
                {reindexing ? "Re-indexing..." : "Continue"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Search */}
      <Section title="Search">
        <SettingRow label="Default Limit" description="Max results per query">
          <select
            value={searchLimit}
            onChange={(e) =>
              handleSave("search_default_limit", parseInt(e.target.value, 10))
            }
            className="bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary"
          >
            {[5, 10, 20, 50].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </SettingRow>
        <SettingRow
          label="Relevance Threshold"
          description="Minimum similarity score for search results. Lower values return more results but may include less relevant matches."
        >
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={0}
              max={100}
              value={Math.round(relevanceThreshold * 100)}
              onChange={(e) =>
                handleSave(
                  "relevance_threshold",
                  parseInt(e.target.value, 10) / 100
                )
              }
              className="w-32 accent-accent-blue"
            />
            <span className="text-sm text-text-secondary w-10 text-right">
              {Math.round(relevanceThreshold * 100)}%
            </span>
          </div>
        </SettingRow>
      </Section>

      {/* Exclusions */}
      <Section title="Exclusions">
        <SettingRow
          label="Excluded Patterns"
          description="Directories skipped during indexing"
        >
          <div className="flex flex-wrap gap-1">
            {excludes.map((p) => (
              <span
                key={String(p)}
                className="px-2 py-0.5 bg-bg-elevated rounded text-xs text-text-secondary"
              >
                {String(p)}
              </span>
            ))}
          </div>
        </SettingRow>
      </Section>
    </div>
  );
}

/** Section wrapper with a title. */
function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-6">
      <h2 className="text-sm font-medium text-text-secondary mb-3">{title}</h2>
      <div className="bg-bg-surface rounded-lg divide-y divide-border">
        {children}
      </div>
    </div>
  );
}

/** Row inside a settings section. */
function SettingRow({
  label,
  description,
  children,
}: {
  label: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between p-4">
      <div>
        <p className="text-sm">{label}</p>
        <p className="text-xs text-text-muted">{description}</p>
      </div>
      {children}
    </div>
  );
}
