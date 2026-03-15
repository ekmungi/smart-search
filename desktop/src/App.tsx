// Main app layout with icon sidebar and routed content area.

import { useState, useEffect } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import FolderManager from "./components/FolderManager";
import Settings from "./components/Settings";

type View = "dashboard" | "folders" | "settings";

function App() {
  const [activeView, setActiveView] = useState<View>("dashboard");

  // Reset to Dashboard when main window is reopened from tray
  useEffect(() => {
    const currentWindow = getCurrentWindow();
    const unlisten = currentWindow.onFocusChanged(({ payload: focused }) => {
      if (focused) {
        setActiveView("dashboard");
      }
    });
    return () => { unlisten.then((fn) => fn()); };
  }, []);

  return (
    <div className="flex h-screen bg-bg-primary text-text-primary">
      <Sidebar activeView={activeView} onNavigate={setActiveView} />
      <main className="flex-1 overflow-auto p-6">
        {activeView === "dashboard" && <Dashboard />}
        {activeView === "folders" && <FolderManager />}
        {activeView === "settings" && <Settings />}
      </main>
    </div>
  );
}

export default App;
