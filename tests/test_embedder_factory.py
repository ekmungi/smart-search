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

    def test_cloud_unknown_model_preserves_dims_and_warns(self, caplog):
        """An unknown cloud model leaves dims unchanged and logs a warning."""
        import logging as _logging

        cfg = SmartSearchConfig(
            embedding_backend="cloud",
            embedding_api_key="k",
            embedding_cloud_model="acme/mystery-embed",
            embedding_dimensions=512,
        )
        with caplog.at_level(_logging.WARNING):
            emb = make_embedder(cfg)
        assert isinstance(emb, CloudEmbedder)
        assert cfg.embedding_dimensions == 512  # not aligned (model unknown)
        assert "not in CLOUD_MODEL_DIMS" in caplog.text


import inspect


class TestCallSitesUseFactory:
    """Embedder-constructing entry points route through make_embedder."""

    def test_cli_index_uses_factory(self):
        import smart_search.cli_index as m
        src = inspect.getsource(m)
        assert "make_embedder" in src
        assert "Embedder(cfg)" not in src and "Embedder(config)" not in src

    def test_cli_search_uses_factory(self):
        import smart_search.cli_search as m
        src = inspect.getsource(m)
        assert "make_embedder" in src
        assert "Embedder(cfg)" not in src and "Embedder(config)" not in src

    def test_ephemeral_store_uses_factory(self):
        import smart_search.ephemeral_store as m
        src = inspect.getsource(m)
        assert "make_embedder" in src
        assert "Embedder(config)" not in src

    def test_http_uses_factory(self):
        import smart_search.http as m
        src = inspect.getsource(m)
        assert "make_embedder" in src
        assert "Embedder(config)" not in src
