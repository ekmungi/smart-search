# Factory that selects the embedder backend (local ONNX vs cloud API) from config.

"""make_embedder reads config.embedding_backend and returns the matching
EmbedderProtocol implementation. For the cloud backend it aligns
config.embedding_dimensions to the chosen model so the LanceDB vector column
is created at the correct width."""

from smart_search.config import SmartSearchConfig
from smart_search.constants import CLOUD_MODEL_DIMS
from smart_search.embedder import Embedder
from smart_search.cloud_embedder import CloudEmbedder


def make_embedder(config: SmartSearchConfig):
    """Return the configured embedder backend.

    Args:
        config: Reads embedding_backend ("local" | "cloud" | "none" | "auto").

    Returns:
        An EmbedderProtocol implementation (Embedder or CloudEmbedder).

    Raises:
        ValueError: If backend is "none" (no vector embedder available).
    """
    backend = (config.embedding_backend or "local").lower()
    if backend == "cloud":
        # Size the store's vector column to the cloud model before init.
        dim = CLOUD_MODEL_DIMS.get(config.embedding_cloud_model)
        if dim:
            try:
                config.embedding_dimensions = dim
            except Exception:
                # pydantic-settings may be frozen; bypass the validator.
                object.__setattr__(config, "embedding_dimensions", dim)
        return CloudEmbedder(config)
    if backend == "none":
        raise ValueError(
            "embedding_backend='none': no vector embedder configured; "
            "use FTS5 keyword search instead"
        )
    # "local" or legacy "auto"
    return Embedder(config)
