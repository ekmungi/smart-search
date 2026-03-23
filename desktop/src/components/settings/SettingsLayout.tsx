// Shared layout primitives for settings sections and rows.

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

/** Props for the Section wrapper component. */
interface SectionProps {
  title: string;
  icon?: LucideIcon;
  children: ReactNode;
}

/** Section wrapper with optional icon, title, and grouped card styling. */
export function Section({ title, icon: Icon, children }: SectionProps) {
  return (
    <div className="mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-3 flex items-center gap-2">
        {Icon && <Icon size={14} />}
        {title}
      </h2>
      <div className="bg-bg-surface rounded-lg divide-y divide-border">
        {children}
      </div>
    </div>
  );
}

/** Props for a single setting row inside a Section. */
interface SettingRowProps {
  label: string;
  description: string;
  children: ReactNode;
}

/** Row inside a settings section: label+description on the left, control on the right. */
export function SettingRow({ label, description, children }: SettingRowProps) {
  return (
    <div className="flex items-center justify-between p-4 hover:bg-bg-elevated/30 transition-colors">
      <div>
        <p className="text-sm">{label}</p>
        <p className="text-xs text-text-muted">{description}</p>
      </div>
      {children}
    </div>
  );
}
