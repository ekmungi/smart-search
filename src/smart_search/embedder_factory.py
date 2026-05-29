# Factory that selects the embedder backend (local ONNX vs cloud API) from config.

"""make_embedder reads config.embedding_backend and returns the matching
EmbedderProtocol implementation. For the cloud backend it aligns
config.embedding_dimensions to the chosen model so the LanceDB vector column
is created at the correct width."""

import logging
from typing import Optional

from smart_search.config import SmartSearchConfig
from smart_search.constants import CLOUD_MODEL_DIMS, CLOUD_MODEL_PRICE_PER_1M
from smart_search.embedder import Embedder
from smart_search.cloud_embedder import CloudEmbedder
from smart_search.protocols import EmbedderProtocol

logger = logging.getLogger(__name__)


def make_embedder(config: SmartSearchConfig) -> EmbedderProtocol:
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
        else:
            # Unknown cloud model: cannot size the vector column from the
            # registry. Warn loudly so a wrong-dimension index is observable
            # rather than silent; the configured embedding_dimensions is used.
            logger.warning(
                "Cloud embedding model %r not in CLOUD_MODEL_DIMS; using "
                "configured embedding_dimensions=%d. Verify it matches the "
                "model's true output dimension to avoid index corruption.",
                config.embedding_cloud_model,
                config.embedding_dimensions,
            )
        return CloudEmbedder(config)
    if backend == "none":
        raise ValueError(
            "embedding_backend='none': no vector embedder configured; "
            "use FTS5 keyword search instead"
        )
    # "local" or legacy "auto"
    return Embedder(config)


def estimate_cloud_cost(num_tokens: int, model: str) -> Optional[float]:
    """Estimate USD cost to embed num_tokens with a cloud model.

    Args:
        num_tokens: Total input tokens to embed.
        model: Cloud model id (must be in CLOUD_MODEL_PRICE_PER_1M).

    Returns:
        Estimated USD cost, or None if the model price is unknown.
    """
    price = CLOUD_MODEL_PRICE_PER_1M.get(model)
    if price is None:
        return None
    return (num_tokens / 1_000_000) * price
