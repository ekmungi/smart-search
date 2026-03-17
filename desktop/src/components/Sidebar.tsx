// Icon sidebar for navigation between views.

import { LayoutDashboard, FolderOpen, ScrollText, Settings } from "lucide-react";

type View = "dashboard" | "folders" | "log" | "settings";

interface Props {
  activeView: View;
  onNavigate: (view: View) => void;
}

const items: { id: View; icon: typeof LayoutDashboard; label: string }[] = [
  { id: "dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { id: "folders", icon: FolderOpen, label: "Folders" },
  { id: "log", icon: ScrollText, label: "Indexing Log" },
  { id: "settings", icon: Settings, label: "Settings" },
];

export default function Sidebar({ activeView, onNavigate }: Props) {
  return (
    <nav className="w-14 bg-bg-surface border-r border-border flex flex-col items-center py-4 gap-2">
      {items.map(({ id, icon: Icon, label }) => (
        <button
          key={id}
          onClick={() => onNavigate(id)}
          title={label}
          className={`w-10 h-10 rounded-lg flex items-center justify-center transition-colors ${
            activeView === id
              ? "bg-bg-elevated text-accent-blue"
              : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
          }`}
        >
          <Icon size={20} />
        </button>
      ))}
    </nav>
  );
}
