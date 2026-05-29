# Tests for CloudEmbedder: OpenAI-format request, response parsing, validation.

import json

import pytest

from smart_search.config import SmartSearchConfig
from smart_search.cloud_embedder import CloudEmbedder


def _cloud_config(**overrides):
    base = dict(
        embedding_backend="cloud",
        embedding_api_key="test-key",
        embedding_cloud_model="openai/text-embedding-3-small",
        embedding_dimensions=1536,
    )
    base.update(overrides)
    return SmartSearchConfig(**base)


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class TestCloudEmbedder:
    def test_requires_api_key(self):
        with pytest.raises(ValueError):
            CloudEmbedder(_cloud_config(embedding_api_key=""))

    def test_requires_model(self):
        with pytest.raises(ValueError):
            CloudEmbedder(_cloud_config(embedding_cloud_model=""))

    def test_embed_documents_posts_openai_format(self, monkeypatch):
        captured = {}

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["auth"] = req.headers.get("Authorization")
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeResp(
                {"data": [{"index": 0, "embedding": [0.1] * 1536}]}
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        emb = CloudEmbedder(_cloud_config())
        out = emb.embed_documents(["hello world"])

        assert len(out) == 1
        assert len(out[0]) == 1536
        assert captured["url"].endswith("/embeddings")
        assert captured["auth"] == "Bearer test-key"
        assert captured["body"]["model"] == "openai/text-embedding-3-small"
        assert captured["body"]["input"] == ["hello world"]

    def test_embed_query_returns_single_vector(self, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda req, timeout=0: _FakeResp(
                {"data": [{"index": 0, "embedding": [0.2] * 1536}]}
            ),
        )
        emb = CloudEmbedder(_cloud_config())
        vec = emb.embed_query("q")
        assert isinstance(vec, list) and len(vec) == 1536

    def test_results_sorted_by_index(self, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda req, timeout=0: _FakeResp(
                {
                    "data": [
                        {"index": 1, "embedding": [0.9]},
                        {"index": 0, "embedding": [0.1]},
                    ]
                }
            ),
        )
        emb = CloudEmbedder(_cloud_config(embedding_dimensions=1))
        out = emb.embed_documents(["a", "b"])
        assert out[0] == [0.1] and out[1] == [0.9]

    def test_empty_input_returns_empty(self):
        emb = CloudEmbedder(_cloud_config())
        assert emb.embed_documents([]) == []

    def test_embed_image_not_implemented(self):
        emb = CloudEmbedder(_cloud_config())
        with pytest.raises(NotImplementedError):
            emb.embed_image("/x.png")

    def test_satisfies_protocol(self):
        from smart_search.protocols import EmbedderProtocol

        assert isinstance(CloudEmbedder(_cloud_config()), EmbedderProtocol)
