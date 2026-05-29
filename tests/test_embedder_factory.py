# Tests for make_embedder: backend selection and cloud dimension alignment.

import pytest

from smart_search.config import SmartSearchConfig
from smart_search.embedder import Embedder
from smart_search.cloud_embedder import CloudEmbedder
from smart_search.embedder_factory import make_embedder


class TestMakeEmbedder:
    def test_local_returns_onnx_embedder(self):
        cfg = SmartSearchConfig(embedding_backend="local")
        assert isinstance(make_embedder(cfg), Embedder)

    def test_auto_is_treated_as_local(self):
        cfg = SmartSearchConfig(embedding_backend="auto")
        assert isinstance(make_embedder(cfg), Embedder)

    def test_cloud_returns_cloud_embedder(self):
        cfg = SmartSearchConfig(
            embedding_backend="cloud",
            embedding_api_key="k",
            embedding_cloud_model="openai/text-embedding-3-small",
        )
        emb = make_embedder(cfg)
        assert isinstance(emb, CloudEmbedder)

    def test_cloud_aligns_dimensions_to_model(self):
        cfg = SmartSearchConfig(
            embedding_backend="cloud",
            embedding_api_key="k",
            embedding_cloud_model="openai/text-embedding-3-small",
            embedding_dimensions=256,  # wrong on purpose
        )
        make_embedder(cfg)
        assert cfg.embedding_dimensions == 1536  # aligned to the cloud model

    def test_none_backend_raises(self):
        cfg = SmartSearchConfig(embedding_backend="none")
        with pytest.raises(ValueError):
            make_embedder(cfg)
