# Curated model registry for embedding model selection UI.
#
# Each entry describes a supported embedding model with its properties,
# quality metrics, and prefix configuration. Used by the Settings UI
# to show model options and by the embedder for prefix behavior.

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ModelInfo:
    """Metadata for a curated embedding model.

    Attributes:
        model_id: HuggingFace model identifier.
        display_name: Human-readable name for the UI.
        size_mb: Approximate int8 ONNX model size in MB.
        mteb_retrieval: MTEB retrieval benchmark score (0-1).
        native_dims: Native embedding dimensions before truncation.
        mrl_dims: Supported Matryoshka dimensions (empty = no MRL support).
        default_dims: Recommended default dimension for this model.
        doc_prefix: Prefix for document texts (None = no prefix).
        query_prefix: Prefix for query texts (None = no prefix).
        modalities: Supported input types (e.g. ["text"], ["text", "image"]).
        description: Short description for the UI tooltip.
    """

    model_id: str
    display_name: str
    size_mb: int
    mteb_retrieval: float
    native_dims: int
    mrl_dims: List[int] = field(default_factory=list)
    default_dims: int = 256
    doc_prefix: Optional[str] = None
    query_prefix: Optional[str] = None
    modalities: List[str] = field(default_factory=lambda: ["text"])
    description: str = ""


# Curated list of supported models, ordered by quality (best first)
CURATED_MODELS: List[ModelInfo] = [
    ModelInfo(
        model_id="Snowflake/snowflake-arctic-embed-m-v2.0",
        display_name="Snowflake Arctic Embed M v2.0",
        size_mb=297,
        mteb_retrieval=0.554,
        native_dims=768,
        mrl_dims=[256, 512, 768],
        default_dims=256,
        doc_prefix=None,
        query_prefix="Represent this sentence for searching relevant passages: ",
        description="Best quality. 7% better retrieval than nomic. First-party int8 ONNX.",
    ),
    ModelInfo(
        model_id="nomic-ai/nomic-embed-text-v1.5",
        display_name="Nomic Embed Text v1.5",
        size_mb=131,
        mteb_retrieval=0.52,
        native_dims=768,
        mrl_dims=[256, 384, 512, 768],
        default_dims=256,
        doc_prefix="search_document: ",
        query_prefix="search_query: ",
        description="Smaller download. Good quality. Dual prefix model.",
    ),
]

# Lookup by model_id for fast access
_MODELS_BY_ID: Dict[str, ModelInfo] = {m.model_id: m for m in CURATED_MODELS}


def get_model_info(model_id: str) -> Optional[ModelInfo]:
    """Look up model metadata by HuggingFace model identifier.

    Args:
        model_id: HuggingFace model identifier (e.g. "Snowflake/snowflake-arctic-embed-m-v2.0").

    Returns:
        ModelInfo if found, None for unknown models.
    """
    return _MODELS_BY_ID.get(model_id)


def get_prefix_pair(model_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (doc_prefix, query_prefix) for a model.

    Falls back to query-only prefix for unknown models.

    Args:
        model_id: HuggingFace model identifier.

    Returns:
        Tuple of (document_prefix, query_prefix).
    """
    info = _MODELS_BY_ID.get(model_id)
    if info is not None:
        return (info.doc_prefix, info.query_prefix)
    return (None, "Represent this sentence for searching relevant passages: ")


def list_models() -> List[ModelInfo]:
    """Return all curated models.

    Returns:
        List of ModelInfo objects ordered by quality.
    """
    return list(CURATED_MODELS)
