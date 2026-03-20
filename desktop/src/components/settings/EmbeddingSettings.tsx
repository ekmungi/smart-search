// Embedding settings: model selector dropdown and Matryoshka dimension picker.

import { Loader2, AlertTriangle } from "lucide-react";
import { Section, SettingRow } from "./SettingsLayout";
import type { ModelInfo } from "../../lib/api";

/** Props for the embedding settings section. */
interface EmbeddingSettingsProps {
  models: ModelInfo[];
  currentModel: string;
  currentDims: string;
  reindexing: boolean;
  onModelChangeRequest: (modelId: string) => void;
  onDimsChange: (key: string, value: number) => void;
}

/** Model selector and dimension picker. */
export function EmbeddingSettings({
  models,
  currentModel,
  currentDims,
  reindexing,
  onModelChangeRequest,
  onDimsChange,
}: EmbeddingSettingsProps) {
  const selectedModel = models.find((m) => m.model_id === currentModel);
  const hasMrl = selectedModel && selectedModel.mrl_dims.length > 0;

  return (
    <Section title="Embedding">
      <SettingRow
        label="Model"
        description="Changing model requires full re-index"
      >
        {models.length > 0 ? (
          <select
            value={currentModel}
            onChange={(e) => onModelChangeRequest(e.target.value)}
            disabled={reindexing}
            className="bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary max-w-[220px]"
          >
            {models.map((m) => (
              <option key={m.model_id} value={m.model_id}>
                {m.display_name} ({m.size_mb} MB, {(m.mteb_retrieval * 100).toFixed(1)}%)
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
    </Section>
  );
}

/** Props for the model change confirmation dialog. */
interface ModelChangeDialogProps {
  reindexing: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Modal confirmation dialog for embedding model changes. */
export function ModelChangeDialog({
  reindexing,
  onConfirm,
  onCancel,
}: ModelChangeDialogProps) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-bg-surface border border-border rounded-lg p-6 max-w-md mx-4">
        <div className="flex items-center gap-2 mb-3 text-amber-400">
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
      </div>
    </div>
  );
}
