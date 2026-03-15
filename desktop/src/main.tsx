// Entry point: routes rendering based on the Tauri window label.
//
// The main window renders the full dashboard app; the search
// window renders only the quick search overlay.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { getCurrentWindow } from "@tauri-apps/api/window";
import "./index.css";
import App from "./App.tsx";
import QuickSearch from "./components/QuickSearch.tsx";

const windowLabel = getCurrentWindow().label;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {windowLabel === "search" ? <QuickSearch /> : <App />}
  </StrictMode>,
);
