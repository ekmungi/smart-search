// Settings panel: view/edit configuration, font size slider, autostart, MCP status.

import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { enable, disable, isEnabled } from "@tauri-apps/plugin-autostart";
import { Save, Check, X, Loader2 } from "lucide-react";
import { fetchConfig, updateConfig } from "../lib/api";

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

  if (loading) {
    return <p className="text-text-secondary text-sm">Loading settings...</p>;
  }

  const model = String(config.embedding_model || "unknown");
  const dims = String(config.embedding_dimensions || "unknown");
  const excludes = Array.isArray(config.exclude_patterns)
    ? config.exclude_patterns
    : [];
  const searchLimit = Number(config.search_default_limit || 10);

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
      </Section>

      {/* Embedding Model */}
      <Section title="Embedding">
        <SettingRow label="Model" description="ONNX embedding model">
          <span className="text-sm text-text-primary">{model}</span>
        </SettingRow>
        <SettingRow label="Dimensions" description="Embedding vector size">
          <span className="text-sm text-text-primary">{dims}</span>
        </SettingRow>
      </Section>

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
