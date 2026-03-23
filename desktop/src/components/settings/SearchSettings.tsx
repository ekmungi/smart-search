// Search settings: relevance threshold, default limit, reranking, MMR, exclusions.

import { Search, Filter } from "lucide-react";
import { motion } from "motion/react";
import { Section, SettingRow } from "./SettingsLayout";

/** Animated toggle switch -- matches SystemSettings pattern. */
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
      <motion.span
        className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-text-primary"
        animate={{ x: enabled ? 20 : 0 }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
      />
    </button>
  );
}

/** Props for the search settings section. */
interface SearchSettingsProps {
  searchLimit: number;
  relevanceThreshold: number;
  rerankingEnabled: boolean;
  mmrEnabled: boolean;
  excludePatterns: readonly unknown[];
  onSave: (key: string, value: unknown) => void;
}

/** Search configuration: limit, threshold, reranking, diversity, exclusions. */
export function SearchSettings({
  searchLimit,
  relevanceThreshold,
  rerankingEnabled,
  mmrEnabled,
  excludePatterns,
  onSave,
}: SearchSettingsProps) {
  return (
    <>
      <Section title="Search" icon={Search}>
        <SettingRow label="Default Limit" description="Max results per query">
          <select
            value={searchLimit}
            onChange={(e) =>
              onSave("search_default_limit", parseInt(e.target.value, 10))
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
          description="Minimum similarity score for search results"
        >
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={0}
              max={100}
              value={Math.round(relevanceThreshold * 100)}
              onChange={(e) =>
                onSave(
                  "relevance_threshold",
                  parseInt(e.target.value, 10) / 100,
                )
              }
              className="w-32 accent-accent-blue"
            />
            <span className="text-sm text-text-secondary w-10 text-right font-mono">
              {Math.round(relevanceThreshold * 100)}%
            </span>
          </div>
        </SettingRow>
        <SettingRow
          label="Reranking"
          description="Cross-encoder reranking for better result ordering"
        >
          <ToggleSwitch
            enabled={rerankingEnabled}
            onToggle={() => onSave("reranking_enabled", !rerankingEnabled)}
          />
        </SettingRow>
        <SettingRow
          label="Diversity"
          description="MMR filtering to reduce redundant results"
        >
          <ToggleSwitch
            enabled={mmrEnabled}
            onToggle={() => onSave("mmr_enabled", !mmrEnabled)}
          />
        </SettingRow>
      </Section>

      <Section title="Exclusions" icon={Filter}>
        <SettingRow
          label="Excluded Patterns"
          description="Directories skipped during indexing"
        >
          <div className="flex flex-wrap gap-1">
            {excludePatterns.map((p) => (
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
    </>
  );
}
