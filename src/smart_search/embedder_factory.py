# Factory that selects the embedder backend (local ONNX vs cloud API) from config.

"""make_embedder reads config.embedding_backend and returns the matching
EmbedderProtocol implementation. Cloud dimension alignment is handled at
config construction time (SmartSearchConfig.align_cloud_dimensions) so the
LanceDB vector column is always sized correctly regardless of call order."""

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
        # Dimension alignment happens at config construction
        # (SmartSearchConfig.align_cloud_dimensions). Here we only warn when
        # the model is unknown, so the dimension could not be auto-aligned.
        if config.embedding_cloud_model not in CLOUD_MODEL_DIMS:
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


def embedder_is_ready(config: SmartSearchConfig) -> bool:
    """Whether a vector embedder can currently produce embeddings.

    Cloud: ready when api key and model are configured (no local model needed).
    Local/auto: ready when a model is configured AND cached on disk.
    None: never ready (keyword-only).

    Args:
        config: SmartSearchConfig to inspect.

    Returns:
        True if the configured backend can embed immediately, False otherwise.
    """
    backend = (config.embedding_backend or "local").lower()
    if backend == "cloud":
        return bool(config.embedding_api_key and config.embedding_cloud_model)
    if backend == "none":
        return False
    if not config.embedding_model:
        return False
    return Embedder.is_model_cached(config.embedding_model)


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
