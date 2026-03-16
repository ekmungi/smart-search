// Quick search overlay: global hotkey (Ctrl+Space) opens this floating search bar.
//
// Debounced search-as-you-type with keyboard navigation (arrow keys,
// Enter to open, ESC to dismiss). Uses Tauri IPC for reliable window hiding.

import { useState, useEffect, useRef, useCallback } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { invoke } from "@tauri-apps/api/core";
import { Search, FileText, X } from "lucide-react";
import { searchDocuments, fetchModelLoaded, type SearchHit } from "../lib/api";

/** Debounce delay in milliseconds for search-as-you-type. */
const DEBOUNCE_MS = 250;

/** Maximum results to display in the overlay. */
const MAX_RESULTS = 10;

export default function QuickSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchHit[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [warmingUp, setWarmingUp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const warmupCheckedRef = useRef(false);

  /** Hide the overlay via Tauri command (more reliable than JS window API). */
  const hideWindow = useCallback(async () => {
    try {
      await invoke("hide_search_window");
    } catch {
      // Fallback to direct window API
      try {
        await getCurrentWindow().hide();
      } catch {
        // Window may already be hidden
      }
    }
  }, []);

  // Global ESC listener (fires even if React loses focus within the window)
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        hideWindow();
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [hideWindow]);

  // Auto-focus input and handle window focus/blur events.
  useEffect(() => {
    inputRef.current?.focus();

    const currentWindow = getCurrentWindow();
    const unlisten = currentWindow.onFocusChanged(({ payload: focused }) => {
      if (focused) {
        // Clean slate on every open (Spotlight behavior)
        setQuery("");
        setResults([]);
        setSelectedIndex(0);
        setError(null);
        setWarmingUp(false);
        warmupCheckedRef.current = false;
        inputRef.current?.focus();
      } else {
        // Auto-hide on blur (Spotlight behavior)
        hideWindow();
      }
    });

    return () => {
      unlisten.then((fn) => fn());
    };
  }, [hideWindow]);

  /** Check if the embedding model is loaded; show "Warming up..." if not. */
  const checkModelWarmup = useCallback(async () => {
    if (warmupCheckedRef.current) return;
    warmupCheckedRef.current = true;
    try {
      const { loaded } = await fetchModelLoaded();
      if (!loaded) setWarmingUp(true);
    } catch {
      // Backend unreachable -- doSearch will surface the error
    }
  }, []);

  /** Execute search against the backend API. */
  const doSearch = useCallback(async (q: string) => {
    if (q.trim().length < 3) {
      setResults([]);
      setSelectedIndex(0);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      // Fetch more results than needed so dedup still yields enough unique files
      const res = await searchDocuments(q, MAX_RESULTS * 3);
      // Deduplicate by file: keep highest-scoring chunk per source_path
      const seen = new Set<string>();
      const deduped = res.results.filter((hit) => {
        if (seen.has(hit.source_path)) return false;
        seen.add(hit.source_path);
        return true;
      }).slice(0, MAX_RESULTS);
      setResults(deduped);
      setSelectedIndex(0);
      // Model is now loaded after a successful search
      setWarmingUp(false);
    } catch {
      setError("Search failed -- is the backend running?");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  /** Update query and schedule debounced search. */
  const handleInputChange = (value: string) => {
    setQuery(value);
    // Check model warmup status on first keystroke
    if (value.trim().length === 1) checkModelWarmup();
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), DEBOUNCE_MS);
  };

  /** Open a search result in the default application. */
  const openResult = async (hit: SearchHit) => {
    try {
      await invoke("open_file", { path: hit.source_path });
      await hideWindow();
    } catch (err) {
      setError(String(err));
    }
  };

  /** Handle keyboard navigation: arrows, Enter, Escape. */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    switch (e.key) {
      case "Escape":
        e.preventDefault();
        hideWindow();
        break;
      case "ArrowDown":
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
        break;
      case "Enter":
        e.preventDefault();
        if (results[selectedIndex]) {
          openResult(results[selectedIndex]);
        }
        break;
    }
  };

  /** Format file extension for display badge. */
  const formatType = (sourceType: string) => {
    return sourceType.replace(".", "").toUpperCase();
  };

  /** Truncate long paths, showing only the last 3 segments. */
  const formatPath = (path: string) => {
    const parts = path.replace(/\\/g, "/").split("/");
    if (parts.length <= 3) return parts.join("/");
    return `.../${parts.slice(-3).join("/")}`;
  };

  /** Truncate snippet text to a maximum length. */
  const formatSnippet = (text: string, maxLen = 120) => {
    if (text.length <= maxLen) return text;
    return text.slice(0, maxLen).trimEnd() + "...";
  };

  return (
    <div
      className="flex flex-col h-screen bg-bg-primary border border-border rounded-lg overflow-hidden"
      onKeyDown={handleKeyDown}
    >
      {/* Search input */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
        <Search size={18} className="text-text-muted shrink-0" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => handleInputChange(e.target.value)}
          placeholder="Search documents..."
          className="flex-1 bg-transparent text-text-primary text-base outline-none placeholder:text-text-muted"
          autoFocus
        />
        {/* Close button -- always visible */}
        <button
          onClick={hideWindow}
          className="text-text-muted hover:text-text-secondary"
          title="Close (Esc)"
        >
          <X size={16} />
        </button>
      </div>

      {/* Results list */}
      <div className="flex-1 overflow-auto">
        {error && (
          <div className="px-4 py-3 text-sm text-accent-red">{error}</div>
        )}

        {warmingUp && loading && results.length === 0 && (
          <div className="px-4 py-3 text-sm text-text-muted">
            Warming up... first search may take a moment
          </div>
        )}

        {!warmingUp && loading && results.length === 0 && (
          <div className="px-4 py-3 text-sm text-text-muted">Searching...</div>
        )}

        {!loading && query.trim().length >= 3 && results.length === 0 && !error && (
          <div className="px-4 py-3 text-sm text-text-muted">
            No results found
          </div>
        )}

        {results.map((hit, index) => (
          <button
            key={`${hit.source_path}-${hit.rank}`}
            onClick={() => openResult(hit)}
            onMouseEnter={() => setSelectedIndex(index)}
            className={`w-full text-left px-4 py-2.5 flex items-start gap-3 transition-colors ${
              index === selectedIndex
                ? "bg-bg-elevated"
                : "hover:bg-bg-surface"
            }`}
          >
            <FileText size={16} className="text-text-muted mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm text-text-primary truncate">
                  {formatPath(hit.source_path)}
                </span>
                <span className="text-xs text-text-muted shrink-0">
                  {formatType(hit.source_type)}
                </span>
                <span className="text-xs text-accent-blue shrink-0">
                  {(hit.score * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-xs text-text-secondary mt-0.5 line-clamp-2">
                {formatSnippet(hit.text)}
              </p>
            </div>
          </button>
        ))}
      </div>

      {/* Footer with keyboard hints */}
      <div className="px-4 py-2 border-t border-border flex items-center gap-4 text-xs text-text-muted">
        <span>
          <kbd className="px-1 py-0.5 bg-bg-elevated rounded text-text-secondary">
            ↑↓
          </kbd>{" "}
          navigate
        </span>
        <span>
          <kbd className="px-1 py-0.5 bg-bg-elevated rounded text-text-secondary">
            ↵
          </kbd>{" "}
          open
        </span>
        <span>
          <kbd className="px-1 py-0.5 bg-bg-elevated rounded text-text-secondary">
            esc
          </kbd>{" "}
          close
        </span>
      </div>
    </div>
  );
}
