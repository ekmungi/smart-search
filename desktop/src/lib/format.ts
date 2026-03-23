// Number and text formatting utilities.

/** Format a number with locale-aware separators (e.g. 1,234). */
export function formatNumber(n: number | string): string {
  const num = typeof n === "string" ? parseInt(n, 10) : n;
  if (isNaN(num)) return String(n);
  return num.toLocaleString();
}

/** Truncate a file path to the last N segments. */
export function truncatePath(path: string, segments = 3): string {
  const parts = path.split(/[\\/]/);
  if (parts.length <= segments) return path;
  return "..." + parts.slice(-segments).join("/");
}
