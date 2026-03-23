# GPU detection and ONNX Runtime provider chain builder.

"""Detects available GPU acceleration (CUDA, DirectML) and builds
the provider chain for ONNX Runtime sessions. Auto-detection
prioritizes CUDA > DirectML > CPU. Used by both the embedder
and the reranker for consistent GPU handling."""

import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Provider priority order: best performance first
_PROVIDER_PRIORITY = [
    ("CUDAExecutionProvider", "cuda"),
    ("DmlExecutionProvider", "directml"),
]


def _get_available_providers() -> List[str]:
    """Return list of available ONNX Runtime execution providers.

    Returns:
        List of provider name strings from onnxruntime.
    """
    try:
        import onnxruntime as ort
        return ort.get_available_providers()
    except ImportError:
        return ["CPUExecutionProvider"]


def detect_gpu() -> Optional[str]:
    """Detect the best available GPU acceleration provider.

    Checks ONNX Runtime for CUDA and DirectML providers.
    CUDA is preferred over DirectML when both are available.

    Returns:
        'cuda', 'directml', or None if only CPU is available.
    """
    available = _get_available_providers()
    for provider_name, short_name in _PROVIDER_PRIORITY:
        if provider_name in available:
            logger.info("GPU detected: %s", short_name)
            return short_name
    return None


def build_provider_chain(
    backend: str = "auto",
    device_id: int = 0,
    gpu_mem_limit_mb: int = 2048,
) -> List[Union[str, tuple]]:
    """Build an ONNX Runtime provider chain based on backend config.

    For 'auto' and 'local' backends, detects GPU and builds a
    fallback chain (e.g., [CUDA, CPU]). For 'cloud', returns
    an empty list since no local ONNX session is needed.

    Args:
        backend: 'auto', 'local', or 'cloud'.
        device_id: GPU device index for CUDA/DirectML.
        gpu_mem_limit_mb: Max VRAM allocation in MB (CUDA only).

    Returns:
        Provider list for ort.InferenceSession. Empty for cloud.
    """
    if backend == "cloud":
        return []

    available = _get_available_providers()
    chain: List[Union[str, tuple]] = []

    for provider_name, _ in _PROVIDER_PRIORITY:
        if provider_name in available:
            if provider_name == "CUDAExecutionProvider":
                chain.append((provider_name, {
                    "device_id": device_id,
                    "gpu_mem_limit": gpu_mem_limit_mb * 1024 * 1024,
                    "arena_extend_strategy": "kSameAsRequested",
                }))
            else:
                chain.append((provider_name, {"device_id": device_id}))
            break  # Use best available GPU only

    # Always include CPU as fallback
    provider_names = [c if isinstance(c, str) else c[0] for c in chain]
    if "CPUExecutionProvider" not in provider_names:
        chain.append("CPUExecutionProvider")

    return chain


def get_device_info() -> Dict[str, Any]:
    """Get information about the active compute device.

    Returns:
        Dict with 'type' ('cpu', 'cuda', 'directml') and 'name'.
    """
    gpu = detect_gpu()
    if gpu is None:
        return {"type": "cpu", "name": "CPU"}

    if gpu == "cuda":
        # ort.get_device() returns "GPU" not the actual device name.
        # Use generic label; detailed GPU name would require torch or pynvml.
        name = "CUDA GPU"
    elif gpu == "directml":
        name = "DirectML GPU"
    else:
        name = gpu.upper()

    return {"type": gpu, "name": name}
