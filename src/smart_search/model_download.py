# Model download management: timeout wrapper, status tracking, and HF helpers.

"""Wraps huggingface_hub.snapshot_download with configurable timeout and
tracks download status for the frontend to poll. Extracted from embedder.py
to keep that module under the 400-line hard max."""

import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Dict, List

from huggingface_hub import snapshot_download

_logger = logging.getLogger(__name__)

# --- Download status and progress tracking (module-level, thread-safe) ---
_download_status = "idle"  # "idle" | "downloading" | "cached" | "timeout"
_download_progress: float = 0.0  # 0.0-1.0; reset at start, 1.0 on success
_status_lock = threading.Lock()


def get_download_status() -> str:
    """Return current model download status.

    Returns:
        One of: "idle", "downloading", "cached", "timeout".
    """
    return _download_status


def set_download_status(status: str) -> None:
    """Update the download status thread-safely.

    Args:
        status: One of "idle", "downloading", "cached", "timeout".
    """
    global _download_status
    with _status_lock:
        _download_status = status


def get_download_progress() -> float:
    """Return current download progress as a fraction from 0.0 to 1.0.

    Returns:
        0.0 when idle or at start of download; 1.0 when download completed
        successfully. Intermediate values indicate partial progress.
    """
    return _download_progress


def set_download_progress(progress: float) -> None:
    """Update download progress thread-safely.

    Args:
        progress: Value between 0.0 (start) and 1.0 (complete).
    """
    global _download_progress
    with _status_lock:
        _download_progress = progress


# --- HuggingFace helpers ---

def get_hf_model_url(model_name: str) -> str:
    """Return the HuggingFace web URL for a model.

    Args:
        model_name: HuggingFace model identifier (e.g. "org/model-name").

    Returns:
        Full HTTPS URL to the model page on huggingface.co.
    """
    return f"https://huggingface.co/{model_name}"


def get_hf_cache_path() -> str:
    """Return the HuggingFace Hub cache directory path.

    Checks HF_HOME env var first; falls back to ~/.cache/huggingface/hub.

    Returns:
        String path to the HF hub cache directory.
    """
    hf_home = os.environ.get("HF_HOME", "")
    if hf_home:
        return str(Path(hf_home) / "hub")
    return str(Path.home() / ".cache" / "huggingface" / "hub")


def list_cached_models() -> List[str]:
    """Scan HF cache for all models that have ONNX files.

    Returns:
        List of model IDs (e.g. ["Snowflake/snowflake-arctic-embed-m-v2.0"]),
        sorted alphabetically. Empty list if cache directory does not exist.
    """
    cache_base = Path(get_hf_cache_path())
    if not cache_base.exists():
        return []
    models = []
    for model_dir in cache_base.iterdir():
        if not model_dir.name.startswith("models--"):
            continue
        snapshots = model_dir / "snapshots"
        if not snapshots.exists():
            continue
        has_onnx = any(
            f.suffix == ".onnx"
            for snapshot in snapshots.iterdir() if snapshot.is_dir()
            for f in snapshot.rglob("*.onnx")
        )
        if has_onnx:
            model_id = model_dir.name.replace("models--", "").replace("--", "/", 1)
            models.append(model_id)
    return sorted(models)


# --- Exception ---

class ModelDownloadTimeoutError(Exception):
    """Raised when model download exceeds the configured timeout."""

    def __init__(self, model_name: str, timeout_seconds: int,
                 download_url: str, cache_path: str) -> None:
        """Create a ModelDownloadTimeoutError.

        Args:
            model_name: HuggingFace model identifier.
            timeout_seconds: The timeout that was exceeded.
            download_url: URL where the model can be downloaded manually.
            cache_path: Local path where the model should be placed.
        """
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.download_url = download_url
        self.cache_path = cache_path
        super().__init__(
            f"Model download timed out after {timeout_seconds}s for {model_name}. "
            f"Download manually from {download_url} and copy to {cache_path}"
        )


# --- Download with timeout ---

def download_with_timeout(model_name: str, timeout_seconds: int = 0) -> Path:
    """Download model with timeout protection.

    Uses a ThreadPoolExecutor (not as context manager) so shutdown(wait=False)
    actually cancels the background thread rather than blocking.

    Args:
        model_name: HuggingFace model identifier.
        timeout_seconds: Max seconds to wait. 0 = no timeout.

    Returns:
        Path to the local model directory.

    Raises:
        ModelDownloadTimeoutError: If download exceeds timeout.
    """
    set_download_status("downloading")
    set_download_progress(0.0)

    _ignore = ["*.bin", "*.pt", "*.safetensors", "*.msgpack"]

    def _do_download():
        """Run snapshot_download and set progress milestone on completion.

        Returns:
            Local path string returned by snapshot_download.

        Raises:
            OSError: Re-raised unless it is a Windows symlink privilege error,
                which triggers the local_dir fallback path.
        """
        try:
            result = snapshot_download(model_name, ignore_patterns=_ignore)
            # Milestone: snapshot downloaded (file copy/verify still pending)
            set_download_progress(0.5)
            return result
        except OSError as e:
            # Windows symlink privilege error (WinError 1314): enterprise
            # group policy blocks os.symlink(). Fall back to downloading
            # into a temp dir (no symlinks), then copy into the HF cache
            # using the existing model importer.
            if "1314" not in str(e) and "privilege" not in str(e).lower():
                raise
            import tempfile
            _logger.warning(
                "Symlink creation failed (enterprise Windows). "
                "Falling back to direct download for %s", model_name,
            )
            local_dir = tempfile.mkdtemp(prefix="hf-download-")
            snapshot_download(
                model_name, local_dir=local_dir, ignore_patterns=_ignore,
            )
            from smart_search.model_importer import copy_model_to_cache
            result = copy_model_to_cache(local_dir, model_name)
            if result.get("success"):
                return result["cache_path"]
            raise OSError(result.get("error", str(e)))

    try:
        if timeout_seconds > 0:
            # Do NOT use `with ThreadPoolExecutor(...)` -- its __exit__ calls
            # shutdown(wait=True) which blocks until the download finishes,
            # defeating the timeout entirely.
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(_do_download)
            try:
                model_dir = future.result(timeout=timeout_seconds)
            except FutureTimeoutError:
                pool.shutdown(wait=False, cancel_futures=True)
                set_download_status("timeout")
                raise ModelDownloadTimeoutError(
                    model_name=model_name,
                    timeout_seconds=timeout_seconds,
                    download_url=get_hf_model_url(model_name),
                    cache_path=get_hf_cache_path(),
                )
            else:
                pool.shutdown(wait=False)
        else:
            model_dir = _do_download()

        set_download_progress(1.0)
        set_download_status("cached")
        return Path(model_dir)
    except ModelDownloadTimeoutError:
        raise
    except Exception:
        set_download_status("idle")
        raise


# --- URL parsing ---

# Matches: https://huggingface.co/org/model-name or org/model-name
_HF_URL_PATTERN = re.compile(
    r"^(?:https?://huggingface\.co/)?([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)/?$"
)


def parse_model_id(model_id_or_url: str) -> str:
    """Extract a HuggingFace model ID from a model name or URL.

    Accepts either "org/model-name" or "https://huggingface.co/org/model-name".

    Args:
        model_id_or_url: Model identifier or full HuggingFace URL.

    Returns:
        Normalized model ID (e.g. "Snowflake/snowflake-arctic-embed-m-v2.0").

    Raises:
        ValueError: If the input doesn't match a valid HF model pattern.
    """
    cleaned = model_id_or_url.strip()
    match = _HF_URL_PATTERN.match(cleaned)
    if not match:
        raise ValueError(
            f"Invalid model identifier: '{model_id_or_url}'. "
            "Expected 'org/model-name' or 'https://huggingface.co/org/model-name'."
        )
    return match.group(1)


# --- Full download with dimension detection ---

def download_hf_model(model_id_or_url: str, timeout_seconds: int = 0) -> Dict[str, Any]:
    """Download a model from HuggingFace and detect its embedding dimensions.

    Parses the input (model ID or URL), downloads all relevant files via
    snapshot_download, then probes the ONNX output shape.

    Args:
        model_id_or_url: HuggingFace model ID or full URL.
        timeout_seconds: Max seconds to wait. 0 = no timeout.

    Returns:
        Dict with success, model_id, cache_path, native_dims, download_url, error.
    """
    try:
        model_id = parse_model_id(model_id_or_url)
    except ValueError as e:
        return {"success": False, "model_id": "", "error": str(e)}

    try:
        model_dir = download_with_timeout(model_id, timeout_seconds)
    except ModelDownloadTimeoutError as e:
        return {
            "success": False,
            "model_id": model_id,
            "error": str(e),
            "download_url": get_hf_model_url(model_id),
            "cache_path": get_hf_cache_path(),
        }
    except Exception as e:
        return {
            "success": False,
            "model_id": model_id,
            "error": f"Download failed: {e}",
        }

    # Auto-detect embedding dimensions from the ONNX model
    from smart_search.model_importer import _detect_embedding_dims
    native_dims = _detect_embedding_dims(model_dir)

    _logger.info(
        "Downloaded model %s to %s (detected dims: %s)",
        model_id, model_dir, native_dims,
    )
    return {
        "success": True,
        "model_id": model_id,
        "cache_path": str(model_dir),
        "native_dims": native_dims,
        "download_url": get_hf_model_url(model_id),
    }
