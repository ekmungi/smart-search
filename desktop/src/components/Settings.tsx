// Settings panel: view/edit configuration, delegates rendering to sub-components.

import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { enable, disable, isEnabled } from "@tauri-apps/plugin-autostart";
import { Save } from "lucide-react";
import {
  fetchConfig,
  updateConfig,
  fetchModels,
  repairIndex,
  rebuildIndex,
} from "../lib/api";
import type { ModelInfo, RepairResponse, SmartSearchConfig } from "../lib/api";
import {
  FONT_MIN,
  FONT_MAX,
  FONT_DEFAULT,
  STORAGE_KEY_FONT_SIZE,
  STORAGE_KEY_MCP_REGISTERED,
  STORAGE_KEY_CLOSE_TO_TRAY,
} from "../lib/constants";
import { AppearanceSettings } from "./settings/AppearanceSettings";
import { SystemSettings } from "./settings/SystemSettings";
import { EmbeddingSettings, ModelChangeDialog } from "./settings/EmbeddingSettings";
import { SearchSettings } from "./settings/SearchSettings";

export default function Settings() {
  const [config, setConfig] = useState<SmartSearchConfig>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [fontSize, setFontSize] = useState(FONT_DEFAULT);
  const [autostart, setAutostart] = useState(false);
  const [mcpRegistered, setMcpRegistered] = useState(() => {
    return localStorage.getItem(STORAGE_KEY_MCP_REGISTERED) === "true";
  });
  const [mcpChecking, setMcpChecking] = useState(() => {
    return localStorage.getItem(STORAGE_KEY_MCP_REGISTERED) === null;
  });
  const [mcpRegistering, setMcpRegistering] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [confirmDialog, setConfirmDialog] = useState<{
    model: string;
    dims: number;
  } | null>(null);
  const [reindexing, setReindexing] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [repairResult, setRepairResult] = useState<RepairResponse | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuildResult, setRebuildResult] = useState<{
    folders_queued: number;
    hashes_cleared: number;
  } | null>(null);
  const [closeToTray, setCloseToTray] = useState(() => {
    return localStorage.getItem(STORAGE_KEY_CLOSE_TO_TRAY) !== "false";
  });

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
    const stored = localStorage.getItem(STORAGE_KEY_FONT_SIZE);
    if (stored) {
      const size = parseInt(stored, 10);
      setFontSize(size);
      document.documentElement.style.fontSize = `${size}px`;
    }
    isEnabled().then(setAutostart).catch(() => {});
    fetchModels()
      .then((res) => setModels(res.models))
      .catch(() => {});
    const cached = localStorage.getItem(STORAGE_KEY_MCP_REGISTERED);
    if (cached === null) {
      invoke<boolean>("check_mcp_registered")
        .then((registered) => {
          setMcpRegistered(registered);
          localStorage.setItem(STORAGE_KEY_MCP_REGISTERED, String(registered));
        })
        .catch(() => {})
        .finally(() => setMcpChecking(false));
    }
  }, [refresh]);

  /** Flash the "Saved" indicator for 2 seconds. */
  const flashSaved = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  /** Toggle font size and persist to localStorage. */
  const handleFontChange = (size: number) => {
    setFontSize(size);
    document.documentElement.style.fontSize = `${size}px`;
    localStorage.setItem(STORAGE_KEY_FONT_SIZE, String(size));
  };

  /** Save a backend config key. */
  const handleSave = async (key: string, value: unknown) => {
    try {
      const res = await updateConfig({ [key]: value });
      setConfig(res.config);
      flashSaved();
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

  /** Toggle close-to-tray behavior. */
  const handleCloseToTrayToggle = () => {
    const newValue = !closeToTray;
    setCloseToTray(newValue);
    localStorage.setItem(STORAGE_KEY_CLOSE_TO_TRAY, String(newValue));
  };

  /** Register smart-search as MCP server with Claude Code. */
  const handleRegisterMcp = async () => {
    setMcpRegistering(true);
    setError(null);
    try {
      await invoke<string>("register_mcp");
      setMcpRegistered(true);
      localStorage.setItem(STORAGE_KEY_MCP_REGISTERED, "true");
      flashSaved();
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
      flashSaved();
    } catch (err) {
      setError(`Failed to update shortcut: ${String(err)}`);
    }
  };

  /** Initiate a model change -- shows confirmation dialog. */
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
      flashSaved();
    } catch (err) {
      setError(`Model change failed: ${String(err)}`);
    } finally {
      setReindexing(false);
      setConfirmDialog(null);
    }
  };

  /** Clear all file hashes and re-index every watched folder. */
  const handleRebuildIndex = async () => {
    setRebuilding(true);
    setRebuildResult(null);
    setError(null);
    try {
      const result = await rebuildIndex();
      setRebuildResult(result);
    } catch {
      setError("Index rebuild failed");
    } finally {
      setRebuilding(false);
    }
  };

  /** Run all index maintenance operations. */
  const handleRepairIndex = async () => {
    setRepairing(true);
    setRepairResult(null);
    setError(null);
    try {
      const result = await repairIndex();
      setRepairResult(result);
    } catch {
      setError("Index repair failed");
    } finally {
      setRepairing(false);
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

      <AppearanceSettings
        fontSize={fontSize}
        onFontSizeChange={handleFontChange}
        fontMin={FONT_MIN}
        fontMax={FONT_MAX}
      />

      <SystemSettings
        autostart={autostart}
        onAutostartToggle={handleAutostartToggle}
        closeToTray={closeToTray}
        onCloseToTrayToggle={handleCloseToTrayToggle}
        mcpChecking={mcpChecking}
        mcpRegistered={mcpRegistered}
        mcpRegistering={mcpRegistering}
        onRegisterMcp={handleRegisterMcp}
        shortcutKey={String(config.shortcut_key || "Ctrl+Space")}
        onShortcutChange={handleShortcutChange}
        repairing={repairing}
        repairResult={repairResult}
        onRepairIndex={handleRepairIndex}
        rebuilding={rebuilding}
        rebuildResult={rebuildResult}
        onRebuildIndex={handleRebuildIndex}
      />

      <EmbeddingSettings
        models={models}
        currentModel={model}
        currentDims={dims}
        reindexing={reindexing}
        onModelChangeRequest={handleModelChangeRequest}
        onDimsChange={handleSave}
      />

      {confirmDialog && (
        <ModelChangeDialog
          reindexing={reindexing}
          onConfirm={handleModelChangeConfirm}
          onCancel={() => setConfirmDialog(null)}
        />
      )}

      <SearchSettings
        searchLimit={searchLimit}
        relevanceThreshold={relevanceThreshold}
        excludePatterns={excludes}
        onSave={handleSave}
      />
    </div>
  );
}
