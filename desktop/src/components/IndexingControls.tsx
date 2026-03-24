// Compact play/pause controls for indexing on the dashboard.

import { Play, Pause } from "lucide-react";

interface IndexingControlsProps {
  paused: boolean;
  hasActiveTasks: boolean;
  onPause: () => void;
  onResume: () => void;
}

/** Small round play/pause buttons for controlling indexing. */
export default function IndexingControls({
  paused,
  hasActiveTasks,
  onPause,
  onResume,
}: IndexingControlsProps) {
  if (!hasActiveTasks && !paused) return null;

  return (
    <div className="flex items-center gap-1.5">
      {paused ? (
        <button
          onClick={onResume}
          className="w-7 h-7 rounded-full flex items-center justify-center bg-accent-green/10 text-accent-green hover:bg-accent-green/20 transition-colors"
          title="Resume indexing"
        >
          <Play size={14} className="ml-0.5" />
        </button>
      ) : (
        <button
          onClick={onPause}
          className="w-7 h-7 rounded-full flex items-center justify-center bg-accent-amber/10 text-accent-amber hover:bg-accent-amber/20 transition-colors"
          title="Pause indexing"
        >
          <Pause size={14} />
        </button>
      )}
    </div>
  );
}
