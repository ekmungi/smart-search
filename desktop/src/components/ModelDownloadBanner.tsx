// Model download progress banner with auto-dismiss on completion.

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Check } from "lucide-react";
import type { ModelStatusResponse } from "../lib/api-types";

interface ModelDownloadBannerProps {
  modelStatus: ModelStatusResponse | null;
}

export default function ModelDownloadBanner({ modelStatus }: ModelDownloadBannerProps) {
  // Track "just completed" state for the green checkmark
  const [showComplete, setShowComplete] = useState(false);
  const prevStatus = useRef<string | null>(null);

  useEffect(() => {
    if (!modelStatus) return;
    const curr = modelStatus.download_status;
    // Detect download completion: either direct "cached" transition or
    // missed transition (polls jumped past "cached" with progress at 100%).
    const wasDownloading = prevStatus.current === "downloading";
    const completed = wasDownloading && (
      curr === "cached" || (curr !== "downloading" && modelStatus.progress >= 1.0)
    );
    if (completed) {
      setShowComplete(true);
      const timer = setTimeout(() => setShowComplete(false), 3000);
      prevStatus.current = curr;
      return () => clearTimeout(timer);
    }
    prevStatus.current = curr;
  }, [modelStatus?.download_status]);

  const isDownloading = modelStatus?.download_status === "downloading";
  const visible = isDownloading || showComplete;
  const progress = modelStatus?.progress ?? 0;
  const pct = Math.round(progress * 100);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className={`rounded-lg p-4 mb-6 border ${
            showComplete
              ? "bg-bg-surface border-accent-green/30"
              : "bg-bg-surface border-accent-amber/30"
          }`}
        >
          {showComplete ? (
            <div className="flex items-center gap-3">
              <Check className="w-4 h-4 text-accent-green" />
              <p className="text-sm font-medium text-accent-green">Model ready</p>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <div className="w-4 h-4 border-2 border-accent-amber border-t-transparent rounded-full animate-spin" />
              <div className="flex-1">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm font-medium text-text-primary">
                    Downloading {modelStatus?.model_name ?? "model"}...
                  </p>
                  <span className="text-xs text-text-secondary font-mono">{pct}%</span>
                </div>
                <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-accent-blue rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
              </div>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
