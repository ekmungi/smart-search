// Modal dialog shown when model download times out, offering recovery options.

import { motion, AnimatePresence } from "motion/react";
import { AlertTriangle, Download, Search, Copy } from "lucide-react";

interface ModelTimeoutDialogProps {
  downloadUrl: string;
  cachePath: string;
  onContinueKeywordOnly: () => void;
  onDismiss: () => void;
}

/** Recovery dialog when embedding model download exceeds timeout. */
export default function ModelTimeoutDialog({
  downloadUrl,
  cachePath,
  onContinueKeywordOnly,
  onDismiss,
}: ModelTimeoutDialogProps) {
  const openInBrowser = async () => {
    try {
      const { open } = await import("@tauri-apps/plugin-shell");
      await open(downloadUrl);
    } catch {
      window.open(downloadUrl, "_blank");
    }
  };

  const copyPath = () => {
    navigator.clipboard.writeText(cachePath);
  };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
      >
        <motion.div
          className="bg-bg-surface border border-border rounded-lg p-6 max-w-lg mx-4"
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.15 }}
        >
          <div className="flex items-center gap-2 mb-3 text-accent-amber">
            <AlertTriangle size={20} />
            <h3 className="font-semibold">Model Download Timed Out</h3>
          </div>

          <p className="text-sm text-text-secondary mb-4">
            The embedding model could not be downloaded. This is usually caused by a
            corporate proxy or firewall blocking access to HuggingFace.
          </p>

          <div className="bg-bg-elevated rounded p-3 mb-4">
            <p className="text-xs text-text-secondary mb-1">
              After downloading, copy model files to:
            </p>
            <div className="flex items-center gap-2">
              <code className="text-xs text-text-primary font-mono flex-1 break-all">
                {cachePath}
              </code>
              <button
                onClick={copyPath}
                className="p-1 rounded hover:bg-border text-text-secondary"
                title="Copy path"
              >
                <Copy size={14} />
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <button
              onClick={openInBrowser}
              className="flex items-center justify-center gap-2 px-3 py-2 text-sm rounded bg-accent-blue text-text-primary hover:opacity-90"
            >
              <Download size={14} />
              Download Manually
            </button>
            <button
              onClick={() => { onContinueKeywordOnly(); onDismiss(); }}
              className="flex items-center justify-center gap-2 px-3 py-2 text-sm rounded bg-bg-elevated text-text-secondary hover:bg-border"
            >
              <Search size={14} />
              Continue with Keyword Search Only
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
