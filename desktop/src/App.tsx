// Main app layout with icon sidebar and routed content area.

import { useState } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";

type View = "dashboard" | "folders" | "settings";

function App() {
  const [activeView, setActiveView] = useState<View>("dashboard");

  return (
    <div className="flex h-screen bg-bg-primary text-text-primary">
      <Sidebar activeView={activeView} onNavigate={setActiveView} />
      <main className="flex-1 overflow-auto p-6">
        {activeView === "dashboard" && <Dashboard />}
        {activeView === "folders" && (
          <p className="text-text-secondary">Folders (coming in Phase 4)</p>
        )}
        {activeView === "settings" && (
          <p className="text-text-secondary">Settings (coming in Phase 4)</p>
        )}
      </main>
    </div>
  );
}

export default App;
