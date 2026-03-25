# Copy locally-available model files into the HuggingFace cache structure.

"""Handles manual model import: copies model files from a user-selected
directory into the HF Hub cache so the embedder can find them. Also
probes ONNX output shape to auto-detect embedding dimensions."""

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from smart_search.model_download import get_hf_cache_path

_logger = logging.getLogger(__name__)


def copy_model_to_cache(
    source_path: str,
    model_name: str,
) -> Dict[str, Any]:
    """Copy model files from a local directory into the HF Hub cache.

    Creates the expected HuggingFace Hub cache directory structure
    so that huggingface_hub.try_to_load_from_cache() finds the model.

    Args:
        source_path: Path to directory containing model files.
        model_name: HuggingFace model identifier.

    Returns:
        Dict with success, files_copied, cache_path, native_dims, or error.
    """
    source = Path(source_path)
    if not source.is_dir():
        return {"success": False, "error": f"Source path not found: {source_path}"}

    # Verify ONNX model file exists
    onnx_files = list(source.rglob("*.onnx"))
    if not onnx_files:
        return {"success": False, "error": "No ONNX model file found in source directory"}

    # Build HF cache target path.
    # Use a deterministic SHA1 of "imported-{model_name}" so the snapshot dir
    # is a valid 40-char hex string that HF Hub expects, not the literal "imported".
    snapshot_sha = hashlib.sha1(f"imported-{model_name}".encode("utf-8")).hexdigest()
    cache_base = Path(get_hf_cache_path())
    safe_name = model_name.replace("/", "--")
    model_cache = cache_base / f"models--{safe_name}" / "snapshots" / snapshot_sha
    model_cache.mkdir(parents=True, exist_ok=True)

    # Copy all files preserving subdirectory structure
    files_copied = 0
    for src_file in source.rglob("*"):
        if src_file.is_file():
            rel_path = src_file.relative_to(source)
            dst_file = model_cache / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_file), str(dst_file))
            files_copied += 1

    # Create refs/main pointer so HF Hub resolves the snapshot.
    # Must contain the same SHA as the snapshot directory name.
    refs_dir = model_cache.parent.parent / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "main").write_text(snapshot_sha, encoding="utf-8")

    # Auto-detect embedding dimensions from the ONNX model
    native_dims = _detect_embedding_dims(model_cache)

    _logger.info(
        "Imported %d model files for %s to %s (detected dims: %s)",
        files_copied, model_name, model_cache, native_dims,
    )

    return {
        "success": True,
        "files_copied": files_copied,
        "cache_path": str(model_cache),
        "native_dims": native_dims,
    }


def _detect_embedding_dims(model_dir: Path) -> Optional[int]:
    """Probe the ONNX model to detect native embedding dimensions.

    Args:
        model_dir: Path to the model directory with onnx/ subfolder.

    Returns:
        Native embedding dimension (e.g. 768) or None if detection fails.
    """
    try:
        import onnxruntime as ort

        onnx_path = model_dir / "onnx" / "model_quantized.onnx"
        if not onnx_path.exists():
            onnx_path = model_dir / "onnx" / "model.onnx"
        if not onnx_path.exists():
            onnx_path = model_dir / "model.onnx"
        if not onnx_path.exists():
            return None

        sess_options = ort.SessionOptions()
        sess_options.log_severity_level = 3
        session = ort.InferenceSession(
            str(onnx_path), sess_options,
            providers=["CPUExecutionProvider"],
        )
        outputs = session.get_outputs()
        if outputs and len(outputs[0].shape) >= 2:
            native_dims = outputs[0].shape[-1]
            if isinstance(native_dims, int) and native_dims > 0:
                del session
                return native_dims
        del session
    except Exception:
        _logger.debug("Failed to detect embedding dims", exc_info=True)
    return None
