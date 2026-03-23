// Keyboard shortcut recorder component for capturing hotkey combinations.

import { useState, useCallback } from "react";

interface ShortcutRecorderProps {
  /** Current shortcut string, e.g. "Ctrl+Space". */
  value: string;
  /** Called with the new shortcut string when the user records one. */
  onChange: (shortcut: string) => void;
  /** Disable interaction when true. */
  disabled?: boolean;
}

/** Captures a keyboard shortcut combination via modifier+key press. */
export function ShortcutRecorder({ value, onChange, disabled }: ShortcutRecorderProps) {
  const [recording, setRecording] = useState(false);

  /** Handle keydown events during recording to capture the shortcut. */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!recording) return;
      e.preventDefault();
      e.stopPropagation();

      const parts: string[] = [];
      if (e.ctrlKey) parts.push("Ctrl");
      if (e.shiftKey) parts.push("Shift");
      if (e.altKey) parts.push("Alt");
      if (e.metaKey) parts.push("Super");

      // Ignore bare modifier presses -- wait for a real key
      const ignoredKeys = ["Control", "Shift", "Alt", "Meta"];
      if (ignoredKeys.includes(e.key)) return;

      // Require at least one modifier for a global shortcut
      if (parts.length === 0) return;

      // Map key names to the format parse_shortcut expects
      let key = e.key;
      if (key === " ") key = "Space";
      else if (key.length === 1) key = key.toUpperCase();

      parts.push(key);

      const shortcut = parts.join("+");
      onChange(shortcut);
      setRecording(false);
    },
    [recording, onChange],
  );

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        className={`px-3 py-1.5 rounded text-sm font-mono transition-colors ${
          recording
            ? "bg-accent-amber/20 border border-accent-amber text-accent-amber"
            : "bg-bg-elevated border border-border text-text-primary hover:bg-border"
        } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
        onClick={() => !disabled && setRecording(!recording)}
        onKeyDown={handleKeyDown}
        onBlur={() => setRecording(false)}
        disabled={disabled}
      >
        {recording ? "Press keys..." : value || "Click to record"}
      </button>
    </div>
  );
}
