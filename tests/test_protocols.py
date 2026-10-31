"""Tests for pipeline protocol definitions."""

from typing import List

from smart_search.protocols import (
    ChunkEnricher,
    ChunkerProtocol,
    EmbedderProtocol,
    RetrieverProtocol,
)


def test_embedder_protocol_has_required_methods():
    """EmbedderProtocol defines embed_documents and embed_query."""
    assert hasattr(EmbedderProtocol, "embed_documents")
    assert hasattr(EmbedderProtocol, "embed_query")


def test_chunker_protocol_has_required_methods():
    """ChunkerProtocol defines chunk_file."""
    assert hasattr(ChunkerProtocol, "chunk_file")


def test_enricher_protocol_has_required_methods():
    """ChunkEnricher defines enrich."""
    assert hasattr(ChunkEnricher, "enrich")


def test_retriever_protocol_has_required_methods():
    """RetrieverProtocol defines retrieve."""
    assert hasattr(RetrieverProtocol, "retrieve")


def test_existing_embedder_satisfies_protocol():
    """Current Embedder instance structurally matches EmbedderProtocol."""
    from smart_search.config import SmartSearchConfig
    from smart_search.embedder import Embedder

    embedder = Embedder(SmartSearchConfig())
    assert isinstance(embedder, EmbedderProtocol)


class TestEmbedderProtocolShape:
    """EmbedderProtocol exposes dimensions and backend_type."""

    def test_protocol_requires_dimensions_and_backend_type(self):
        """A complete implementation with dimensions and backend_type satisfies the protocol."""

        class Dummy:
            @property
            def dimensions(self) -> int:
                return 256

            @property
            def backend_type(self) -> str:
                return "local"

            def embed_documents(self, texts: List[str]) -> List[List[float]]:
                return [[0.0] * 256 for _ in texts]

            def embed_query(self, query: str) -> List[float]:
                return [0.0] * 256

            def embed_image(self, image_path: str) -> List[float]:
                raise NotImplementedError

        assert isinstance(Dummy(), EmbedderProtocol)

    def test_missing_new_members_fails_isinstance(self):
        """Missing dimensions/backend_type means the class does not satisfy the protocol."""

        class Incomplete:
            def embed_documents(self, texts: List[str]) -> List[List[float]]:
                return []

            def embed_query(self, query: str) -> List[float]:
                return []

            def embed_image(self, image_path: str) -> List[float]:
                raise NotImplementedError

        # No dimensions/backend_type -> not a structural match.
        assert not isinstance(Incomplete(), EmbedderProtocol)
