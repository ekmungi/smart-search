"""Tests for pipeline protocol definitions."""

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
    """Current Embedder class structurally matches EmbedderProtocol."""
    from smart_search.embedder import Embedder

    assert hasattr(Embedder, "embed_documents")
    assert hasattr(Embedder, "embed_query")
