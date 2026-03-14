// Settings panel: view/edit configuration, font size slider.

import { useState, useEffect, useCallback } from "react";
import { Save } from "lucide-react";
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
  }, [refresh]);

  const handleFontChange = (size: number) => {
    setFontSize(size);
    document.documentElement.style.fontSize = `${size}px`;
    localStorage.setItem("smart-search-font-size", String(size));
  };

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

      {/* Font Size */}
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
