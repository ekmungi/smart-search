// Single stat card with icon, label, and value.

import type { LucideIcon } from "lucide-react";

interface Props {
  icon: LucideIcon;
  label: string;
  value: string | number;
}

export default function StatsCard({ icon: Icon, label, value }: Props) {
  return (
    <div className="bg-bg-surface rounded-lg p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} className="text-text-secondary" />
        <span className="text-xs text-text-secondary">{label}</span>
      </div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}
