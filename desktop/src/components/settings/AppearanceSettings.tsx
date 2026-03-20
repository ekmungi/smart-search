// Appearance settings: font size slider for proportional UI scaling.

import { Section, SettingRow } from "./SettingsLayout";

/** Props for the appearance settings section. */
interface AppearanceSettingsProps {
  fontSize: number;
  onFontSizeChange: (size: number) => void;
  fontMin: number;
  fontMax: number;
}

/** Font size slider section. */
export function AppearanceSettings({
  fontSize,
  onFontSizeChange,
  fontMin,
  fontMax,
}: AppearanceSettingsProps) {
  return (
    <Section title="Appearance">
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
          <span className="text-sm text-text-secondary w-10 text-right">
            {fontSize}px
          </span>
        </div>
      </SettingRow>
    </Section>
  );
}
