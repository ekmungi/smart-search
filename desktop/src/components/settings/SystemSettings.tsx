// System settings: autostart, close-to-tray, MCP registration, shortcut, repair index.

import { Check, X, Loader2 } from "lucide-react";
import { Section, SettingRow } from "./SettingsLayout";
import { ShortcutRecorder } from "../ShortcutRecorder";
import type { RepairResponse } from "../../lib/api";

/** Toggle switch component for boolean settings. */
function ToggleSwitch({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className={`relative w-10 h-5 rounded-full transition-colors ${
        enabled ? "bg-accent-blue" : "bg-bg-elevated"
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-text-primary transition-transform ${
          enabled ? "translate-x-5" : ""
        }`}
      />
    </button>
  );
}

/** Result from the rebuild endpoint. */
interface RebuildResult {
  folders_queued: number;
  hashes_cleared: number;
}

/** Props for the system settings section. */
interface SystemSettingsProps {
  autostart: boolean;
  onAutostartToggle: () => void;
  closeToTray: boolean;
  onCloseToTrayToggle: () => void;
  mcpChecking: boolean;
  mcpRegistered: boolean;
  mcpRegistering: boolean;
  onRegisterMcp: () => void;
  shortcutKey: string;
  onShortcutChange: (shortcut: string) => void;
  repairing: boolean;
  repairResult: RepairResponse | null;
  onRepairIndex: () => void;
  rebuilding: boolean;
  rebuildResult: RebuildResult | null;
  onRebuildIndex: () => void;
}

/** System settings: autostart, tray, MCP, shortcut, repair. */
export function SystemSettings({
  autostart,
  onAutostartToggle,
  closeToTray,
  onCloseToTrayToggle,
  mcpChecking,
  mcpRegistered,
  mcpRegistering,
  onRegisterMcp,
  shortcutKey,
  onShortcutChange,
  repairing,
  repairResult,
  onRepairIndex,
  rebuilding,
  rebuildResult,
  onRebuildIndex,
}: SystemSettingsProps) {
  return (
    <Section title="System">
      <SettingRow
        label="Start on Login"
        description="Launch Smart Search when you sign in"
      >
        <ToggleSwitch enabled={autostart} onToggle={onAutostartToggle} />
      </SettingRow>
      <SettingRow
        label="Close to Tray"
        description="Minimize to system tray instead of quitting"
      >
        <ToggleSwitch enabled={closeToTray} onToggle={onCloseToTrayToggle} />
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
            onClick={onRegisterMcp}
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
        <ShortcutRecorder value={shortcutKey} onChange={onShortcutChange} />
      </SettingRow>
      <SettingRow
        label="Repair Index"
        description="Remove orphans, rebuild keyword index, compact storage"
      >
        <div className="flex items-center gap-3">
          {repairResult && (
            <span className="text-xs text-text-muted">
              Removed {repairResult.orphans_removed} orphans, rebuilt{" "}
              {repairResult.fts_rows} FTS rows, compacted:{" "}
              {repairResult.compacted ? "yes" : "no"}
            </span>
          )}
          <button
            onClick={onRepairIndex}
            disabled={repairing}
            className="px-3 py-1 text-sm bg-bg-elevated text-text-primary rounded hover:bg-border disabled:opacity-50 flex items-center gap-1"
          >
            {repairing && <Loader2 size={14} className="animate-spin" />}
            {repairing ? "Repairing..." : "Repair"}
          </button>
        </div>
      </SettingRow>
      <SettingRow
        label="Rebuild Index"
        description="Re-index all folders (required after upgrade)"
      >
        <div className="flex items-center gap-3">
          {rebuildResult && (
            <span className="text-xs text-text-muted">
              Queued {rebuildResult.folders_queued} folders, cleared{" "}
              {rebuildResult.hashes_cleared} hashes
            </span>
          )}
          <button
            onClick={onRebuildIndex}
            disabled={rebuilding}
            className="px-3 py-1 text-sm bg-bg-elevated text-text-primary rounded hover:bg-border disabled:opacity-50 flex items-center gap-1"
          >
            {rebuilding && <Loader2 size={14} className="animate-spin" />}
            {rebuilding ? "Rebuilding..." : "Rebuild"}
          </button>
        </div>
      </SettingRow>
    </Section>
  );
}
