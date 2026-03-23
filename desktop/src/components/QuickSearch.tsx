// Quick search overlay: global hotkey (Ctrl+Space) opens this floating search bar.
//
// Debounced search-as-you-type with keyboard navigation (arrow keys,
// Enter to open, ESC to dismiss). Uses Tauri IPC for reliable window hiding.

import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { invoke } from "@tauri-apps/api/core";
import { Search, FileText, X } from "lucide-react";
import { searchDocuments, fetchModelLoaded, type SearchHit } from "../lib/api";
import { truncatePath } from "../lib/format";
import Skeleton from "./Skeleton";

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
        setQuery("");
        setResults([]);
        setSelectedIndex(0);
        setError(null);
        setWarmingUp(false);
        warmupCheckedRef.current = false;
        inputRef.current?.focus();
      } else {
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
      const res = await searchDocuments(q, MAX_RESULTS * 4);
      const seen = new Set<string>();
      const deduped = res.results.filter((hit) => {
        if (seen.has(hit.source_path)) return false;
        seen.add(hit.source_path);
        return true;
      }).slice(0, MAX_RESULTS);
      setResults(deduped);
      setSelectedIndex(0);
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
        <Search
          size={18}
          className={`shrink-0 transition-colors ${
            loading ? "text-accent-blue" : "text-text-muted"
          }`}
        />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => handleInputChange(e.target.value)}
          placeholder="Search documents..."
          className="flex-1 bg-transparent text-text-primary text-base outline-none placeholder:text-text-muted"
          autoFocus
        />
        <button
          onClick={hideWindow}
          className="text-text-muted hover:text-text-secondary transition-colors"
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
          <div className="px-4 py-3 text-sm text-text-muted animate-pulse">
            Warming up... first search may take a moment
          </div>
        )}

        {/* Skeleton loading rows */}
        {!warmingUp && loading && results.length === 0 && (
          <div className="px-4 py-2">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="flex items-start gap-3 py-2.5">
                <Skeleton width="w-4" height="h-4" className="rounded mt-0.5 shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton width={i % 2 === 0 ? "w-3/4" : "w-1/2"} height="h-4" />
                  <Skeleton width="w-full" height="h-3" />
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && query.trim().length >= 3 && results.length === 0 && !error && (
          <div className="px-4 py-8 text-center">
            <Search size={24} className="text-text-muted opacity-40 mx-auto mb-2" />
            <p className="text-sm text-text-muted">No results found</p>
          </div>
        )}

        <AnimatePresence mode="wait">
          {results.length > 0 && (
            <motion.div
              key={query}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.12 }}
            >
              {results.map((hit, index) => (
                <motion.button
                  key={`${hit.source_path}-${hit.rank}`}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.12, delay: index * 0.03 }}
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
                        {truncatePath(hit.source_path)}
                      </span>
                      <span className="text-xs text-text-muted shrink-0">
                        {formatType(hit.source_type)}
                      </span>
                      <span className="text-xs text-accent-blue font-mono shrink-0">
                        {(hit.score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p className="text-xs text-text-secondary mt-0.5 line-clamp-2">
                      {formatSnippet(hit.text)}
                    </p>
                  </div>
                </motion.button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
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
