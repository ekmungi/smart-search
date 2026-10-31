# Tests for make_embedder: backend selection and cloud dimension alignment.

import inspect

import pytest

from smart_search.config import SmartSearchConfig
from smart_search.embedder import Embedder
from smart_search.cloud_embedder import CloudEmbedder
from smart_search.embedder_factory import (
    embedder_is_ready,
    estimate_cloud_cost,
    make_embedder,
)


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


class TestEmbedderIsReady:
    """Unit tests for embedder_is_ready backend-aware readiness helper."""

    def test_cloud_with_key_and_model_is_ready(self) -> None:
        """Cloud backend with both api key and model configured returns True."""
        cfg = SmartSearchConfig(
            embedding_backend="cloud",
            embedding_api_key="sk-test",
            embedding_cloud_model="openai/text-embedding-3-small",
        )
        assert embedder_is_ready(cfg) is True

    def test_cloud_without_key_is_not_ready(self) -> None:
        """Cloud backend with no api key returns False."""
        cfg = SmartSearchConfig(
            embedding_backend="cloud",
            embedding_api_key="",
            embedding_cloud_model="openai/text-embedding-3-small",
        )
        assert embedder_is_ready(cfg) is False

    def test_cloud_without_model_is_not_ready(self) -> None:
        """Cloud backend with no cloud model configured returns False."""
        cfg = SmartSearchConfig(
            embedding_backend="cloud",
            embedding_api_key="sk-test",
            embedding_cloud_model="",
        )
        assert embedder_is_ready(cfg) is False

    def test_none_backend_is_never_ready(self) -> None:
        """backend='none' always returns False (keyword-only mode)."""
        cfg = SmartSearchConfig(embedding_backend="none")
        assert embedder_is_ready(cfg) is False

    def test_local_without_model_is_not_ready(self) -> None:
        """Local backend with no embedding_model configured returns False."""
        cfg = SmartSearchConfig(embedding_backend="local", embedding_model="")
        assert embedder_is_ready(cfg) is False

    def test_local_with_cached_model_is_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Local backend with model configured and cached on disk returns True."""
        monkeypatch.setattr(Embedder, "is_model_cached", staticmethod(lambda _: True))
        cfg = SmartSearchConfig(
            embedding_backend="local",
            embedding_model="snowflake/snowflake-arctic-embed-m-v2.0",
        )
        assert embedder_is_ready(cfg) is True

    def test_auto_with_cached_model_is_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Auto backend (treated as local) with cached model returns True."""
        monkeypatch.setattr(Embedder, "is_model_cached", staticmethod(lambda _: True))
        cfg = SmartSearchConfig(
            embedding_backend="auto",
            embedding_model="snowflake/snowflake-arctic-embed-m-v2.0",
        )
        assert embedder_is_ready(cfg) is True


class TestCostEstimate:
    def test_known_model_cost(self):
        # 5,000,000 tokens at $0.02 / 1M = $0.10
        cost = estimate_cloud_cost(5_000_000, "openai/text-embedding-3-small")
        assert round(cost, 2) == 0.10

    def test_unknown_model_returns_none(self):
        assert estimate_cloud_cost(1000, "unknown/model") is None
