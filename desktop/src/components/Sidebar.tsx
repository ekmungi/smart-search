// Icon sidebar for navigation between views with animated active indicator.

import { motion } from "motion/react";
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
          className="relative w-10 h-10 rounded-lg flex items-center justify-center transition-colors text-text-secondary hover:text-text-primary hover:bg-bg-elevated/50"
        >
          {/* Animated active background pill */}
          {activeView === id && (
            <motion.div
              layoutId="sidebar-active"
              className="absolute inset-0 bg-bg-elevated rounded-lg ring-1 ring-accent-blue/20"
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            />
          )}
          <Icon
            size={20}
            className={`relative z-10 ${
              activeView === id ? "text-accent-blue" : ""
            }`}
          />
        </button>
      ))}
    </nav>
  );
}
