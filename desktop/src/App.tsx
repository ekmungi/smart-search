// Main app layout with custom title bar, icon sidebar, and routed content area.

import { useState, useCallback } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { invoke } from "@tauri-apps/api/core";
import { Minus, X } from "lucide-react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import FolderManager from "./components/FolderManager";
import IndexingLog from "./components/IndexingLog";
import Settings from "./components/Settings";
import { STORAGE_KEY_CLOSE_TO_TRAY } from "./lib/constants";

type View = "dashboard" | "folders" | "log" | "settings";

function App() {
  const [activeView, setActiveView] = useState<View>("dashboard");

  const appWindow = getCurrentWindow();

  /** Close button: hide to tray if enabled, otherwise quit the app. */
  const handleClose = useCallback(async () => {
    const closeToTray = localStorage.getItem(STORAGE_KEY_CLOSE_TO_TRAY) !== "false";
    if (closeToTray) {
      await appWindow.hide();
    } else {
      await invoke("quit_app");
    }
  }, [appWindow]);

  return (
    <div className="flex flex-col h-screen bg-bg-primary text-text-primary">
      {/* Custom title bar */}
      <div
        data-tauri-drag-region
        className="flex items-center justify-between h-9 bg-bg-surface border-b border-border select-none shrink-0"
      >
        <span
          data-tauri-drag-region
          className="text-xs text-text-muted pl-3 font-medium"
        >
          Smart Search
        </span>
        <div className="flex items-center h-full">
          <button
            onClick={() => appWindow.minimize()}
            className="h-full px-3 hover:bg-bg-elevated text-text-muted hover:text-text-primary transition-colors"
          >
            <Minus size={14} />
          </button>
          <button
            onClick={handleClose}
            className="h-full px-3 hover:bg-accent-red text-text-muted hover:text-text-primary transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar activeView={activeView} onNavigate={setActiveView} />
        <main className="flex-1 overflow-auto p-6">
          {activeView === "dashboard" && <Dashboard />}
          {activeView === "folders" && <FolderManager />}
          {activeView === "log" && <IndexingLog />}
          {activeView === "settings" && <Settings />}
        </main>
      </div>
    </div>
  );
}

export default App;
