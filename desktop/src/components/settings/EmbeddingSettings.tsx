// Embedding settings: model selector dropdown and Matryoshka dimension picker.

import { Loader2, AlertTriangle, Cpu } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { Section, SettingRow } from "./SettingsLayout";
import type { ModelInfo, GpuInfo } from "../../lib/api";

/** Props for the embedding settings section. */
interface EmbeddingSettingsProps {
  models: ModelInfo[];
  currentModel: string;
  currentDims: string;
  currentBackend: string;
  gpuInfo: GpuInfo | null;
  reindexing: boolean;
  onModelChangeRequest: (modelId: string) => void;
  onDimsChange: (key: string, value: number) => void;
  onBackendChange: (backend: string) => void;
}

/** Inline chip showing the active compute device. */
function DeviceChip({ gpuInfo }: { gpuInfo: GpuInfo | null }) {
  if (!gpuInfo) return null;
  const isGpu = gpuInfo.type !== "cpu";
  const chipClass = isGpu
    ? "bg-accent-green/10 text-accent-green border-accent-green/25"
    : "bg-accent-blue/10 text-accent-blue border-accent-blue/25";
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[0.7rem] font-mono font-medium border ${chipClass}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${isGpu ? "bg-accent-green" : "bg-accent-blue"}`} />
      {gpuInfo.name}
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
  onModelChangeRequest,
  onDimsChange,
  onBackendChange,
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
            onChange={(e) => onModelChangeRequest(e.target.value)}
            disabled={reindexing}
            className="bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary max-w-[220px]"
          >
            {availableModels.map((m) => (
              <option key={m.model_id} value={m.model_id}>
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
          <DeviceChip gpuInfo={gpuInfo} />
        </div>
      </SettingRow>
    </Section>
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
