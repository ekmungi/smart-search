// Search settings: relevance threshold, default limit, and exclusion patterns.

import { Search, Filter } from "lucide-react";
import { Section, SettingRow } from "./SettingsLayout";

/** Props for the search settings section. */
interface SearchSettingsProps {
  searchLimit: number;
  relevanceThreshold: number;
  excludePatterns: readonly unknown[];
  onSave: (key: string, value: unknown) => void;
}

/** Search configuration: limit, threshold, exclusions. */
export function SearchSettings({
  searchLimit,
  relevanceThreshold,
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
          description="Minimum similarity score for search results. Lower values return more results but may include less relevant matches."
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
