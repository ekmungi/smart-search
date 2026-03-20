// Shared constants for the smart-search desktop app.

/** Backend HTTP server port. */
export const BACKEND_PORT = 9742;

/** Default timeout for GET requests (ms). */
export const API_TIMEOUT_MS = 30_000;

// Polling intervals (ms)
export const POLL_STATS_MS = 5_000;
export const POLL_INDEXING_ACTIVE_MS = 2_000;
export const POLL_INDEXING_IDLE_MS = 10_000;
export const POLL_MODEL_MS = 3_000;

// Font size range
export const FONT_MIN = 14;
export const FONT_MAX = 22;
export const FONT_DEFAULT = 18;

// localStorage keys
export const STORAGE_KEY_FONT_SIZE = "smart-search-font-size";
export const STORAGE_KEY_MCP_REGISTERED = "smart-search-mcp-registered";
export const STORAGE_KEY_CLOSE_TO_TRAY = "smart-search-close-to-tray";
