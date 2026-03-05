# Tests for Embedder: nomic-embed-text-v1.5 ONNX embedding generation.

from unittest.mock import MagicMock, patch

import pytest

from smart_search.config import SmartSearchConfig
from smart_search.embedder import Embedder


@pytest.fixture
def tmp_config(tmp_path):
    """SmartSearchConfig with paths pointing to tmp_path."""
    return SmartSearchConfig(
        lancedb_path=str(tmp_path / "vectors"),
        sqlite_path=str(tmp_path / "meta.db"),
    )


@pytest.fixture
def mock_embedder(tmp_config):
    """Embedder with a mocked SentenceTransformer model."""
    import numpy as np

    mock_model = MagicMock()
    # Return deterministic 768-dim vectors based on input length
    mock_model.encode.side_effect = lambda texts, **kwargs: np.array(
        [[float(i) / 768] * 768 for i in range(len(texts))]
    )
    mock_model.get_sentence_embedding_dimension.return_value = 768

    with patch("smart_search.embedder.SentenceTransformer", return_value=mock_model):
        embedder = Embedder(tmp_config)

    return embedder


class TestEmbedderFast:
    """Fast tests using mocked model."""

    def test_prefix_applied_to_documents(self, mock_embedder):
        """Verify 'search_document: ' prefix is prepended before encoding."""
        texts = ["hello world"]
        mock_embedder.embed_documents(texts)
        call_args = mock_embedder._model.encode.call_args
        actual_texts = call_args[0][0]
        assert actual_texts[0].startswith("search_document: ")

    def test_prefix_applied_to_query(self, mock_embedder):
        """Verify 'search_query: ' prefix is prepended for queries."""
        mock_embedder.embed_query("test query")
        call_args = mock_embedder._model.encode.call_args
        actual_texts = call_args[0][0]
        assert actual_texts[0].startswith("search_query: ")

    def test_embed_documents_returns_list_of_lists(self, mock_embedder):
        """embed_documents returns a list of float lists."""
        result = mock_embedder.embed_documents(["a", "b"])
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], list)

    def test_model_name_matches_config(self, mock_embedder):
        """get_model_name returns the configured model ID."""
        assert mock_embedder.get_model_name() == "nomic-ai/nomic-embed-text-v1.5"


@pytest.mark.slow
class TestEmbedderSlow:
    """Slow tests that load the real nomic-embed model."""

    @pytest.fixture(autouse=True)
    def real_embedder(self, tmp_config):
        """Load actual nomic-embed-text-v1.5 model."""
        self.embedder = Embedder(tmp_config)

    def test_embed_query_returns_768_dims(self):
        """Query embedding has 768 dimensions."""
        vec = self.embedder.embed_query("What is machine learning?")
        assert len(vec) == 768

    def test_embed_documents_batch(self):
        """Three texts produce three vectors."""
        texts = ["First doc.", "Second doc.", "Third doc."]
        vecs = self.embedder.embed_documents(texts)
        assert len(vecs) == 3
        assert all(len(v) == 768 for v in vecs)

    def test_embed_documents_consistent(self):
        """Same input produces same output (deterministic)."""
        text = "Reproducibility matters."
        vec_a = self.embedder.embed_documents([text])[0]
        vec_b = self.embedder.embed_documents([text])[0]
        assert vec_a == vec_b

    def test_query_document_similarity(self):
        """Related texts have higher cosine similarity than unrelated."""
        import numpy as np

        doc_vecs = self.embedder.embed_documents([
            "Machine learning is a subset of artificial intelligence.",
            "The weather in Paris is sunny today.",
        ])
        query_vec = self.embedder.embed_query("What is AI?")

        def cosine_sim(a, b):
            a, b = np.array(a), np.array(b)
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

        sim_related = cosine_sim(query_vec, doc_vecs[0])
        sim_unrelated = cosine_sim(query_vec, doc_vecs[1])
        assert sim_related > sim_unrelated
