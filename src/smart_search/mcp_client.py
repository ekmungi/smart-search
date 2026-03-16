# HTTP client for MCP server to proxy requests to the HTTP backend.
# Avoids loading heavy dependencies (ONNX, embedder) in the MCP process.

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:9742"


def _request(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, str]] = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Make an HTTP request to the backend server.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE).
        path: API path (e.g., "/api/stats").
        body: Optional JSON body for POST/PUT.
        params: Optional query parameters.
        base_url: Backend base URL.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response as dict.

    Raises:
        ConnectionError: If backend is not reachable.
        RuntimeError: If response indicates an error.
    """
    url = f"{base_url}{path}"
    if params:
        filtered = {k: v for k, v in params.items() if v is not None}
        if filtered:
            url = f"{url}?{urlencode(filtered)}"

    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        raise ConnectionError(
            f"Backend not reachable at {base_url}. "
            f"Start it with: smart-search serve\n"
            f"Error: {e}"
        ) from e


def is_backend_running(base_url: str = DEFAULT_BASE_URL) -> bool:
    """Check if the HTTP backend is running.

    Args:
        base_url: Backend base URL.

    Returns:
        True if backend responds to health check.
    """
    try:
        _request("GET", "/api/health", base_url=base_url, timeout=2.0)
        return True
    except (ConnectionError, Exception):
        return False


def get_stats(base_url: str = DEFAULT_BASE_URL) -> Dict[str, Any]:
    """Fetch index statistics from the backend.

    Args:
        base_url: Backend base URL.

    Returns:
        Stats dict with document_count, chunk_count, etc.
    """
    return _request("GET", "/api/stats", base_url=base_url)


def search(
    query: str,
    limit: int = 10,
    folder: Optional[str] = None,
    doc_types: Optional[List[str]] = None,
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    """Search the knowledge base via the backend.

    Args:
        query: Search query string.
        limit: Maximum results.
        folder: Optional folder filter.
        doc_types: Optional document type filter.
        base_url: Backend base URL.

    Returns:
        Search response dict with query, mode, total, results.
    """
    params = {"q": query, "limit": str(limit)}
    if folder:
        params["folder"] = folder
    if doc_types:
        params["doc_types"] = ",".join(doc_types)
    return _request("GET", "/api/search", params=params, base_url=base_url)


def ingest(
    path: str,
    force: bool = False,
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    """Ingest a file or folder via the backend.

    Args:
        path: Path to file or folder.
        force: Force re-index even if unchanged.
        base_url: Backend base URL.

    Returns:
        Ingest response dict.
    """
    return _request(
        "POST", "/api/ingest",
        body={"path": path, "force": force},
        base_url=base_url,
    )


def add_folder(
    folder_path: str,
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    """Add a folder to the watch list via the backend.

    Args:
        folder_path: Folder path to add.
        base_url: Backend base URL.

    Returns:
        Add folder response dict.
    """
    return _request(
        "POST", "/api/folders",
        body={"path": folder_path},
        base_url=base_url,
    )


def remove_folder(
    folder_path: str,
    remove_data: bool = False,
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    """Remove a folder from the watch list via the backend.

    Args:
        folder_path: Folder path to remove.
        remove_data: Whether to delete indexed data.
        base_url: Backend base URL.

    Returns:
        Remove folder response dict.
    """
    params = {"path": folder_path, "remove_data": str(remove_data).lower()}
    return _request("DELETE", "/api/folders", params=params, base_url=base_url)


def list_folders(base_url: str = DEFAULT_BASE_URL) -> Dict[str, Any]:
    """List watched folders via the backend.

    Args:
        base_url: Backend base URL.

    Returns:
        Folders response dict.
    """
    return _request("GET", "/api/folders", base_url=base_url)


def list_files(
    folder: Optional[str] = None,
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    """List indexed files via the backend.

    Args:
        folder: Optional folder filter.
        base_url: Backend base URL.

    Returns:
        Files response dict.
    """
    params = {"folder": folder} if folder else None
    return _request("GET", "/api/files", params=params, base_url=base_url)


def find_related(
    note_path: str,
    limit: int = 10,
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    """Find related notes via the backend.

    Args:
        note_path: Path to the source note.
        limit: Maximum number of related notes.
        base_url: Backend base URL.

    Returns:
        Related notes response dict.
    """
    params = {"note_path": note_path, "limit": str(limit)}
    return _request("GET", "/api/find-related", params=params, base_url=base_url)


def ephemeral_index(
    folder_path: str,
    force: bool = False,
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    """Create an ephemeral index via the backend.

    Args:
        folder_path: Folder path to index.
        force: Force re-index even if unchanged.
        base_url: Backend base URL.

    Returns:
        Ephemeral index response dict.
    """
    return _request(
        "POST", "/api/ephemeral/index",
        body={"folder_path": folder_path, "force": force},
        base_url=base_url,
        timeout=120.0,
    )


def ephemeral_list(
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    """List all ephemeral indexes via the backend.

    Args:
        base_url: Backend base URL.

    Returns:
        Ephemeral list response dict.
    """
    return _request("GET", "/api/ephemeral", base_url=base_url)


def ephemeral_cleanup(
    folder_path: str,
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    """Clean up an ephemeral index via the backend.

    Args:
        folder_path: Folder path to clean up.
        base_url: Backend base URL.

    Returns:
        Ephemeral cleanup response dict.
    """
    params = {"folder_path": folder_path}
    return _request(
        "DELETE", "/api/ephemeral", params=params, base_url=base_url,
    )
