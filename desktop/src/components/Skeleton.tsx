// Skeleton loading primitive -- pulsing placeholder matching warm dark theme.

interface SkeletonProps {
  /** Tailwind width class, e.g. "w-24" or "w-full". */
  width?: string;
  /** Tailwind height class, e.g. "h-4" or "h-8". */
  height?: string;
  /** Additional CSS classes. */
  className?: string;
}

/** Warm-pulsing placeholder rectangle for loading states. */
export default function Skeleton({
  width = "w-full",
  height = "h-4",
  className = "",
}: SkeletonProps) {
  return (
    <div
      className={`bg-bg-elevated rounded-lg animate-skeleton ${width} ${height} ${className}`}
    />
  );
}
