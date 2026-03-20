# MCP response formatting functions for human-readable tool output.

"""Converts HTTP API response dicts into formatted text strings for MCP tool
responses. Used by server.py to present search, stats, and ingest results."""

from smart_search.constants import BYTES_PER_MB


def format_search_response(data: dict) -> str:
    """Format HTTP search response as MCP-friendly text.

    Args:
        data: Search response dict from HTTP API.

    Returns:
        Formatted search results string.
    """
    results = data.get("results", [])
    query = data.get("query", "")
    mode = data.get("mode", "semantic")

    if not results:
        return (
            f"KNOWLEDGE SEARCH\n"
            f"================\n"
            f"Query: {query}\n"
            f"Mode: {mode}\n"
            f"No results found."
        )

    lines = [
        "KNOWLEDGE SEARCH",
        "=" * 16,
        f"Query: {query}",
        f"Mode: {mode}",
        f"Results: {len(results)}",
        "",
    ]

    for r in results:
        lines.append(f"--- Result {r['rank']} (score: {r['score']:.4f}) ---")
        lines.append(f"Source: {r['source_path']}")
        if r.get("section_path"):
            lines.append(f"Section: {r['section_path']}")
        if r.get("page_number"):
            lines.append(f"Page: {r['page_number']}")
        lines.append(f"Text: {r['text']}")
        lines.append("")

    return "\n".join(lines)


def format_stats_response(data: dict) -> str:
    """Format HTTP stats response as MCP-friendly text.

    Args:
        data: Stats response dict from HTTP API.

    Returns:
        Formatted stats string.
    """
    size_mb = data.get("index_size_bytes", 0) / BYTES_PER_MB
    formats = ", ".join(data.get("formats_indexed", [])) or "none"
    last = data.get("last_indexed_at") or "never"

    separator = "=" * 26
    return (
        f"KNOWLEDGE BASE STATISTICS\n"
        f"{separator}\n"
        f"Documents indexed: {data.get('document_count', 0)}\n"
        f"Chunks stored: {data.get('chunk_count', 0)}\n"
        f"Index size: {size_mb:.1f} MB\n"
        f"Last indexed: {last}\n"
        f"Formats indexed: {formats}"
    )


def format_ingest_response(data: dict) -> str:
    """Format HTTP ingest response as MCP-friendly text.

    Args:
        data: Ingest response dict from HTTP API.

    Returns:
        Formatted ingest result string.
    """
    status = data.get("status", "unknown")
    path = data.get("path", "unknown")

    if status == "failed":
        return (
            f"INGEST RESULT\n"
            f"=============\n"
            f"Path: {path}\n"
            f"Status: FAILED\n"
            f"Error: {data.get('error', 'unknown')}"
        )

    if status == "accepted":
        return (
            f"INGEST RESULT\n"
            f"=============\n"
            f"Path: {path}\n"
            f"Status: Indexing started in background\n"
            f"Task ID: {data.get('task_id', 'unknown')}\n"
            f"Poll knowledge_stats() to check progress."
        )

    return (
        f"INGEST RESULT\n"
        f"=============\n"
        f"Path: {path}\n"
        f"Status: {status}\n"
        f"Indexed: {data.get('indexed', 0)} files\n"
        f"Skipped: {data.get('skipped', 0)} files\n"
        f"Failed: {data.get('failed', 0)} files\n"
        f"Chunks: {data.get('chunk_count', 0)}"
    )
