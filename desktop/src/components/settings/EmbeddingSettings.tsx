// Embedding settings: model selector, dimension picker, and HF model download.

import { useState } from "react";
import { Loader2, AlertTriangle, Cpu, FolderOpen, Download, CheckCircle2, XCircle } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { Section, SettingRow } from "./SettingsLayout";
import type { ModelInfo, GpuInfo } from "../../lib/api";
import { importModel, downloadModel } from "../../lib/api";

/** Props for the embedding settings section. */
interface EmbeddingSettingsProps {
  models: ModelInfo[];
  currentModel: string;
  currentDims: string;
  currentBackend: string;
  gpuInfo: GpuInfo | null;
  reindexing: boolean;
  cachedModels: string[];
  onModelChangeRequest: (modelId: string) => void;
  onDimsChange: (key: string, value: number) => void;
  onBackendChange: (backend: string) => void;
  onAutoDownload?: (modelId: string) => void;
}

/** Inline chip showing what compute device(s) the selected model can use. */
function DeviceChip({
  gpuInfo,
  selectedModel,
}: {
  gpuInfo: GpuInfo | null;
  selectedModel: ModelInfo | undefined;
}) {
  if (!gpuInfo) return null;
  const hasGpu = gpuInfo.type !== "cpu";
  const gpuRequired = selectedModel?.gpu_required ?? false;

  // Determine label based on model capability + hardware availability
  let label: string;
  if (gpuRequired) {
    // Model needs GPU -- show GPU name only
    label = gpuInfo.name;
  } else if (hasGpu) {
    // Model runs on both, GPU is available
    label = `${gpuInfo.name} / CPU`;
  } else {
    // Model runs on CPU (no GPU available)
    label = "CPU";
  }

  const chipClass = hasGpu
    ? "bg-accent-green/10 text-accent-green border-accent-green/25"
    : "bg-accent-blue/10 text-accent-blue border-accent-blue/25";
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[0.7rem] font-mono font-medium border ${chipClass}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${hasGpu ? "bg-accent-green" : "bg-accent-blue"}`} />
      {label}
    </span>
  );
}

/** Model selector, dimension picker, and backend selector. */
export function EmbeddingSettings({
  models,
  currentModel,
  currentDims,
  currentBackend,
  gpuInfo,
  reindexing,
  cachedModels,
  onModelChangeRequest,
  onDimsChange,
  onBackendChange,
  onAutoDownload,
}: EmbeddingSettingsProps) {
  const isGpuAvailable = gpuInfo != null && gpuInfo.type !== "cpu";
  // Filter models: hide GPU-required models when no GPU is available
  const availableModels = models.filter(
    (m) => !m.gpu_required || isGpuAvailable,
  );
  const selectedModel = availableModels.find((m) => m.model_id === currentModel);
  const hasMrl = selectedModel && selectedModel.mrl_dims.length > 0;

  return (
    <Section title="Embedding" icon={Cpu}>
      <SettingRow
        label="Model"
        description="Changing model requires full re-index"
      >
        {availableModels.length > 0 ? (
          <select
            value={currentModel}
            onChange={(e) => {
              const selected = e.target.value;
              onModelChangeRequest(selected);
              if (!cachedModels.includes(selected) && onAutoDownload) {
                onAutoDownload(selected);
              }
            }}
            disabled={reindexing}
            className="bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary max-w-[220px]"
          >
            {currentModel === "" && (
              <option value="" disabled>(select a model)</option>
            )}
            {availableModels.map((m) => (
              <option key={m.model_id} value={m.model_id}>
                {cachedModels.includes(m.model_id) ? "\u2713 " : ""}
                {m.display_name} ({m.size_mb} MB, {(m.mteb_retrieval * 100).toFixed(1)}%)
                {m.gpu_required ? " [GPU]" : ""}
              </option>
            ))}
          </select>
        ) : (
          <span className="text-sm text-text-primary">{currentModel}</span>
        )}
      </SettingRow>
      <SettingRow
        label="Dimensions"
        description={
          hasMrl
            ? "Matryoshka: lower = faster search, higher = better quality"
            : "Fixed dimensions for this model"
        }
      >
        {hasMrl ? (
          <select
            value={Number(currentDims)}
            onChange={(e) =>
              onDimsChange(
                "embedding_dimensions",
                parseInt(e.target.value, 10),
              )
            }
            className="bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary"
          >
            {selectedModel.mrl_dims.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        ) : (
          <span className="text-sm text-text-primary">{currentDims}</span>
        )}
      </SettingRow>
      <SettingRow
        label="Backend"
        description="Where embeddings are computed"
      >
        <div className="flex items-center gap-2">
          <select
            value={currentBackend === "cloud" ? "cloud" : "local"}
            onChange={(e) => onBackendChange(e.target.value === "cloud" ? "cloud" : "auto")}
            className="bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary"
          >
            <option value="local">Local</option>
            <option value="cloud" disabled>Cloud (coming soon)</option>
          </select>
          <DeviceChip gpuInfo={gpuInfo} selectedModel={selectedModel} />
        </div>
      </SettingRow>
      <SettingRow
        label="Local Model"
        description="Import model files downloaded manually"
      >
        <button
          onClick={async () => {
            try {
              const { open } = await import("@tauri-apps/plugin-dialog");
              const selected = await open({ directory: true, title: "Select model directory" });
              if (selected) {
                const result = await importModel(selected as string);
                if (result.success) {
                  if (result.native_dims) {
                    onDimsChange("embedding_dimensions", result.native_dims);
                  }
                } else {
                  console.error("Model import failed:", result.error);
                }
              }
            } catch (err) {
              console.error("Import error:", err);
            }
          }}
          className="flex items-center gap-1.5 px-2 py-1 text-sm rounded bg-bg-elevated border border-border text-text-secondary hover:bg-border"
        >
          <FolderOpen size={14} />
          Import Model
        </button>
      </SettingRow>
      <HfModelDownload />
    </Section>
  );
}

/** Inline download widget for any HuggingFace model. */
function HfModelDownload() {
  const [modelInput, setModelInput] = useState("");
  const [status, setStatus] = useState<"idle" | "downloading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleDownload = async () => {
    const trimmed = modelInput.trim();
    if (!trimmed) return;

    setStatus("downloading");
    setMessage("");
    try {
      const result = await downloadModel(trimmed);
      if (result.success) {
        const dims = result.native_dims ? ` (${result.native_dims}-dim)` : "";
        setStatus("success");
        setMessage(`Downloaded ${result.model_id}${dims}`);
      } else {
        setStatus("error");
        setMessage(result.error || "Download failed");
      }
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Download failed");
    }
  };

  return (
    <SettingRow
      label="HuggingFace Download"
      description="Download any ONNX embedding model by ID or URL"
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-1.5">
          <input
            type="text"
            value={modelInput}
            onChange={(e) => {
              setModelInput(e.target.value);
              if (status !== "idle" && status !== "downloading") setStatus("idle");
            }}
            onKeyDown={(e) => { if (e.key === "Enter") handleDownload(); }}
            placeholder="org/model-name"
            disabled={status === "downloading"}
            className="bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary w-[220px] placeholder:text-text-secondary/40 focus:outline-none focus:border-accent-blue"
          />
          <button
            onClick={handleDownload}
            disabled={status === "downloading" || !modelInput.trim()}
            className="flex items-center gap-1.5 px-2 py-1 text-sm rounded bg-bg-elevated border border-border text-text-secondary hover:bg-border disabled:opacity-40"
          >
            {status === "downloading" ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Download size={14} />
            )}
            {status === "downloading" ? "Downloading..." : "Download"}
          </button>
        </div>
        <AnimatePresence>
          {status === "success" && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="flex items-center gap-1.5 text-xs text-accent-green"
            >
              <CheckCircle2 size={12} />
              {message}
            </motion.div>
          )}
          {status === "error" && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="flex items-start gap-1.5 text-xs text-accent-red max-w-[320px]"
            >
              <XCircle size={12} className="mt-0.5 shrink-0" />
              <span className="break-words">{message}</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </SettingRow>
  );
}

/** Props for the model change confirmation dialog. */
interface ModelChangeDialogProps {
  reindexing: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Modal confirmation dialog for embedding model changes with enter/exit animation. */
export function ModelChangeDialog({
  reindexing,
  onConfirm,
  onCancel,
}: ModelChangeDialogProps) {
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
          className="bg-bg-surface border border-border rounded-lg p-6 max-w-md mx-4"
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.15 }}
        >
          <div className="flex items-center gap-2 mb-3 text-accent-amber">
            <AlertTriangle size={20} />
            <h3 className="font-semibold">Change Embedding Model?</h3>
          </div>
          <p className="text-sm text-text-secondary mb-4">
            Changing the embedding model requires rebuilding the entire index.
            All documents will be re-indexed. This may take several minutes.
          </p>
          <div className="flex justify-end gap-2">
            <button
              onClick={onCancel}
              className="px-3 py-1.5 text-sm rounded bg-bg-elevated text-text-secondary hover:bg-border"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              disabled={reindexing}
              className="px-3 py-1.5 text-sm rounded bg-accent-blue text-text-primary hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
            >
              {reindexing && <Loader2 size={14} className="animate-spin" />}
              {reindexing ? "Re-indexing..." : "Continue"}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
