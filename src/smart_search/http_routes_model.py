# Embedding model HTTP route handlers.

"""APIRouter factory for embedding model status and listing endpoints."""

from typing import Callable

from fastapi import APIRouter

from smart_search.config import SmartSearchConfig
from smart_search.http_models import (
    ModelInfoResponse,
    ModelLoadedResponse,
    ModelStatusResponse,
    ModelsResponse,
)


def create_model_router(
    get_engine: Callable,
    get_config_mgr: Callable,
    config: SmartSearchConfig,
) -> APIRouter:
    """Create an APIRouter for embedding model endpoints.

    Args:
        get_engine: Zero-arg callable returning SearchEngine instance.
        get_config_mgr: Zero-arg callable returning ConfigManager instance.
        config: SmartSearchConfig for fallback model name.

    Returns:
        Configured APIRouter with model endpoints.
    """
    router = APIRouter()

    @router.get("/models", response_model=ModelsResponse)
    def list_models():
        """List all curated embedding models with metadata."""
        from smart_search.model_registry import list_models as _list

        models = [
            ModelInfoResponse(
                model_id=m.model_id,
                display_name=m.display_name,
                size_mb=m.size_mb,
                mteb_retrieval=m.mteb_retrieval,
                native_dims=m.native_dims,
                mrl_dims=m.mrl_dims,
                default_dims=m.default_dims,
                modalities=m.modalities,
                description=m.description,
            )
            for m in _list()
        ]
        return ModelsResponse(models=models)

    @router.get("/model/status", response_model=ModelStatusResponse)
    def model_status():
        """Check whether the embedding model is cached locally.

        Reads from ConfigManager for live config (B4 fix), falling
        back to startup config if no persisted value exists.
        """
        from smart_search.embedder import Embedder

        live_config = get_config_mgr().load()
        model_name = live_config.get("embedding_model", config.embedding_model)
        return ModelStatusResponse(
            cached=Embedder.is_model_cached(model_name),
            model_name=model_name,
        )

    @router.get("/model/loaded", response_model=ModelLoadedResponse)
    def model_loaded():
        """Check whether the embedding model is currently loaded in memory."""
        engine = get_engine()
        is_loaded = getattr(engine._embedder, "is_loaded", True)
        return ModelLoadedResponse(loaded=is_loaded)

    return router
