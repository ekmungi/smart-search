# Model download management: timeout wrapper, status tracking, and HF helpers.

"""Wraps huggingface_hub.snapshot_download with configurable timeout and
tracks download status for the frontend to poll. Extracted from embedder.py
to keep that module under the 400-line hard max."""

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path

from huggingface_hub import snapshot_download

_logger = logging.getLogger(__name__)

# --- Download status tracking (module-level, thread-safe) ---
_download_status = "idle"  # "idle" | "downloading" | "cached" | "timeout"
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

    def _do_download():
        return snapshot_download(
            model_name,
            ignore_patterns=["*.bin", "*.pt", "*.safetensors", "*.msgpack"],
        )

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

        set_download_status("cached")
        return Path(model_dir)
    except ModelDownloadTimeoutError:
        raise
    except Exception:
        set_download_status("idle")
        raise
