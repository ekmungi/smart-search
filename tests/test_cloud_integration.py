# End-to-end cloud embedder write path integration test.

"""Proves that the cloud embedder produces correctly-sized vectors that the
real ChunkStore accepts without a PyArrow/LanceDB dimension error.

The test stubs out the HTTP call to the embeddings endpoint so no real
network connection is required. Everything else — config construction,
CloudEmbedder, ChunkStore (LanceDB + SQLite), upsert, and vector_search —
uses real implementations to guard the dimension contract."""

import json
import urllib.request

import numpy as np
import pytest

from smart_search.config import SmartSearchConfig
from smart_search.embedder_factory import make_embedder
from smart_search.models import Chunk, generate_chunk_id
from smart_search.store import ChunkStore


# ---------------------------------------------------------------------------
# Fake HTTP layer
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal context-manager wrapping a pre-baked JSON payload."""

    def __init__(self, payload: dict) -> None:
        """Store the payload dict to be returned as UTF-8 JSON bytes.

        Args:
            payload: Dict to serialize and return from read().
        """
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def read(self) -> bytes:
        """Return the payload as UTF-8-encoded JSON bytes."""
        return json.dumps(self._payload).encode("utf-8")


def _fake_urlopen_factory(dim: int):
    """Return a fake urlopen that echoes back dim-dimensional unit vectors.

    Args:
        dim: Embedding dimension to use in the fake response.

    Returns:
        A callable with the same signature as urllib.request.urlopen.
    """
    def fake_urlopen(req: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        body = json.loads(req.data.decode("utf-8"))
        inputs = body["input"]
        # Each vector is [0.01 * (i+1)] * dim so all vectors are non-zero and
        # distinguishable by their magnitude.
        data = [
            {"index": i, "embedding": [0.01 * (i + 1)] * dim}
            for i in range(len(inputs))
        ]
        return _FakeResponse({"data": data})

    return fake_urlopen


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cloud_chunk(
    source_path: str,
    idx: int,
    embedding: list,
    model_name: str,
) -> Chunk:
    """Build a minimal but fully-valid Chunk for cloud embedding tests.

    Args:
        source_path: Absolute path to the source document.
        idx: Zero-based chunk index within the document.
        embedding: Pre-computed embedding vector.
        model_name: Cloud model identifier stored in the chunk.

    Returns:
        A Chunk instance ready for upsert into ChunkStore.
    """
    return Chunk(
        id=generate_chunk_id(source_path, idx),
        source_path=source_path,
        source_type="markdown",
        content_type="text",
        text=f"Cloud test chunk {idx}: semantic search content.",
        page_number=None,
        section_path="",
        embedding=embedding,
        has_image=False,
        image_path=None,
        entity_tags=None,
        source_title="Cloud Test Doc",
        source_date=None,
        indexed_at="2026-05-29T00:00:00Z",
        model_name=model_name,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCloudWriteEndToEnd:
    """End-to-end: cloud embedder writes correctly-sized vectors into the real store."""

    def test_cloud_vectors_match_store_column_width(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Upsert cloud-embedded vectors and confirm a search returns results.

        Verifies:
        (a) Config auto-aligns embedding_dimensions to 1536 for the chosen model.
        (b) CloudEmbedder returns 1536-dim vectors (no shape mismatch).
        (c) ChunkStore.upsert_chunks() does NOT raise a PyArrow dimension error.
        (d) ChunkStore.vector_search() returns at least one result, confirming
            the stored vectors are queryable.
        """
        cfg = SmartSearchConfig(
            embedding_backend="cloud",
            embedding_api_key="test-api-key",
            embedding_cloud_model="openai/text-embedding-3-small",
            lancedb_path=str(tmp_path / "vectors"),
            sqlite_path=str(tmp_path / "meta.db"),
        )
        # (a) Dimension alignment must happen at config construction.
        assert cfg.embedding_dimensions == 1536

        monkeypatch.setattr(
            "urllib.request.urlopen",
            _fake_urlopen_factory(cfg.embedding_dimensions),
        )

        store = ChunkStore(cfg)
        store.initialize()
        embedder = make_embedder(cfg)

        texts = [
            "Semantic search allows finding conceptually similar documents.",
            "Cloud embeddings are produced without a local ONNX model.",
        ]

        # (b) Verify the embedder returns correctly-sized vectors.
        vectors = embedder.embed_documents(texts)
        assert len(vectors) == len(texts)
        for vec in vectors:
            assert len(vec) == 1536, (
                f"Expected 1536-dim vector, got {len(vec)}"
            )

        # Build chunks pairing each text with its embedding.
        source_path = "/docs/cloud_test.md"
        chunks = [
            _make_cloud_chunk(
                source_path=source_path,
                idx=i,
                embedding=vectors[i],
                model_name=cfg.embedding_cloud_model,
            )
            for i in range(len(texts))
        ]

        # (c) Upsert must not raise a PyArrow/LanceDB dimension error.
        store.upsert_chunks(chunks)

        # Confirm the chunks landed in the store.
        retrieved = store.get_chunks_for_file(source_path)
        assert len(retrieved) == 2

        # (d) Vector search must return at least one result.
        query_vector = embedder.embed_query("semantic similarity search")
        assert len(query_vector) == 1536
        results = store.vector_search(query_vector, limit=5)
        assert len(results) >= 1, "vector_search returned no results after cloud upsert"

    def test_cloud_empty_documents_returns_empty(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """embed_documents([]) must return [] without hitting the network."""
        cfg = SmartSearchConfig(
            embedding_backend="cloud",
            embedding_api_key="test-api-key",
            embedding_cloud_model="openai/text-embedding-3-small",
            lancedb_path=str(tmp_path / "vectors"),
            sqlite_path=str(tmp_path / "meta.db"),
        )
        # No monkeypatch needed -- CloudEmbedder short-circuits for empty input.
        embedder = make_embedder(cfg)
        result = embedder.embed_documents([])
        assert result == []
