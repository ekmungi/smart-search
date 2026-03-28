// Appearance settings: theme toggle and font size slider.

import { Palette, Sun, Moon } from "lucide-react";
import { Section, SettingRow } from "./SettingsLayout";

/** Props for the appearance settings section. */
interface AppearanceSettingsProps {
  fontSize: number;
  onFontSizeChange: (size: number) => void;
  fontMin: number;
  fontMax: number;
  theme: "dark" | "light";
  onThemeChange: (theme: "dark" | "light") => void;
}

/** Theme toggle and font size slider section. */
export function AppearanceSettings({
  fontSize,
  onFontSizeChange,
  fontMin,
  fontMax,
  theme,
  onThemeChange,
}: AppearanceSettingsProps) {
  return (
    <Section title="Appearance" icon={Palette}>
      <SettingRow label="Theme" description="Switch between dark and light mode">
        <div className="flex items-center gap-1 bg-bg-elevated rounded-lg p-1">
          <button
            onClick={() => onThemeChange("dark")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
              theme === "dark"
                ? "bg-bg-surface text-text-primary shadow-sm"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            <Moon size={14} />
            Dark
          </button>
          <button
            onClick={() => onThemeChange("light")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
              theme === "light"
                ? "bg-bg-surface text-text-primary shadow-sm"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            <Sun size={14} />
            Light
          </button>
        </div>
      </SettingRow>
      <SettingRow label="Font Size" description="Proportional UI scaling">
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={fontMin}
            max={fontMax}
            value={fontSize}
            onChange={(e) => onFontSizeChange(parseInt(e.target.value, 10))}
            className="w-32 accent-accent-blue"
          />
          <span className="text-sm text-text-secondary w-10 text-right font-mono">
            {fontSize}px
          </span>
        </div>
      </SettingRow>
    </Section>
  );
}
