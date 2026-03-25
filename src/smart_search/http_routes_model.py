# Embedding model HTTP route handlers.

"""APIRouter factory for embedding model status and listing endpoints."""

from typing import Callable

from fastapi import APIRouter

from smart_search.config import SmartSearchConfig
from smart_search.gpu_provider import get_device_info
from smart_search.http_models import (
    GpuInfoResponse,
    ModelDownloadRequest,
    ModelDownloadResponse,
    ModelImportRequest,
    ModelImportResponse,
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
                gpu_required=m.gpu_required,
            )
            for m in _list()
        ]
        return ModelsResponse(models=models)

    @router.get("/model/status", response_model=ModelStatusResponse)
    def model_status():
        """Check embedding model cache status with download details.

        Reads from ConfigManager for live config (B4 fix), falling
        back to startup config if no persisted value exists.
        """
        from smart_search.embedder import Embedder
        from smart_search.model_download import (
            get_download_status,
            get_hf_model_url,
            get_hf_cache_path,
        )

        live_config = get_config_mgr().load()
        model_name = live_config.get("embedding_model", config.embedding_model)
        device_info = get_device_info()
        return ModelStatusResponse(
            cached=Embedder.is_model_cached(model_name),
            model_name=model_name,
            gpu_info=GpuInfoResponse(**device_info),
            download_status=get_download_status(),
            download_url=get_hf_model_url(model_name),
            cache_path=get_hf_cache_path(),
        )

    @router.get("/model/loaded", response_model=ModelLoadedResponse)
    def model_loaded():
        """Check whether the embedding model is currently loaded in memory."""
        engine = get_engine()
        is_loaded = getattr(engine._embedder, "is_loaded", True)
        return ModelLoadedResponse(loaded=is_loaded)

    @router.post("/model/import")
    def import_model(req: ModelImportRequest):
        """Import model files from a local directory to HF cache."""
        from smart_search.model_importer import copy_model_to_cache

        live_config = get_config_mgr().load()
        model_name = live_config.get("embedding_model", config.embedding_model)
        result = copy_model_to_cache(req.source_path, model_name)
        return ModelImportResponse(**result)

    @router.post("/model/download", response_model=ModelDownloadResponse)
    def download_model(req: ModelDownloadRequest):
        """Download a model from HuggingFace by ID or URL.

        Accepts either 'org/model-name' or a full HuggingFace URL.
        Downloads all relevant files (ONNX, tokenizer, config) and
        auto-detects embedding dimensions from the ONNX output shape.
        """
        from smart_search.model_download import download_hf_model

        live_config = get_config_mgr().load()
        timeout = int(live_config.get(
            "model_download_timeout",
            config.model_download_timeout,
        ))
        result = download_hf_model(req.model_id, timeout_seconds=timeout)
        return ModelDownloadResponse(**result)

    return router
