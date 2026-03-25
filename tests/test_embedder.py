# Tests for Embedder: Matryoshka truncation, model-aware prefixes, ONNX inference.

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_search.config import SmartSearchConfig
from smart_search.embedder import Embedder, _mean_pool, _l2_normalize, _truncate


@pytest.fixture
def tmp_config(tmp_path):
    """SmartSearchConfig with paths pointing to tmp_path (snowflake default)."""
    return SmartSearchConfig(
        lancedb_path=str(tmp_path / "vectors"),
        sqlite_path=str(tmp_path / "meta.db"),
    )


@pytest.fixture
def nomic_config(tmp_path):
    """SmartSearchConfig configured for nomic model."""
    return SmartSearchConfig(
        lancedb_path=str(tmp_path / "vectors"),
        sqlite_path=str(tmp_path / "meta.db"),
        embedding_model="nomic-ai/nomic-embed-text-v1.5",
        embedding_dimensions=256,
    )


class _MockEncoding:
    """Mimics tokenizers.Encoding with .ids and .attention_mask attributes."""

    def __init__(self, ids, attention_mask):
        self.ids = ids
        self.attention_mask = attention_mask


def _make_mock_embedder(config, hidden_dim=768):
    """Create an Embedder with mocked ONNX session and standalone tokenizer.

    Since __init__ does not load tokenizer or session (lazy loading), we
    manually inject the mock components and set _loaded = True.
    The mock tokenizer mimics the standalone tokenizers.Tokenizer API
    (encode_batch returns list of Encoding objects).
    """
    mock_tokenizer = MagicMock()
    mock_tokenizer._last_texts = []

    def encode_batch(texts):
        mock_tokenizer._last_texts = texts
        return [
            _MockEncoding(
                ids=[1] * 10,
                attention_mask=[1] * 10,
            )
            for _ in texts
        ]

    mock_tokenizer.encode_batch = encode_batch

    mock_session = MagicMock()
    mock_input_ids = MagicMock()
    mock_input_ids.name = "input_ids"
    mock_attn = MagicMock()
    mock_attn.name = "attention_mask"
    mock_session.get_inputs.return_value = [mock_input_ids, mock_attn]

    def mock_run(output_names, feeds):
        batch_size = feeds["input_ids"].shape[0]
        seq_len = feeds["input_ids"].shape[1]
        token_embs = np.random.RandomState(42).randn(
            batch_size, seq_len, hidden_dim
        ).astype(np.float32)
        return [token_embs]

    mock_session.run.side_effect = mock_run

    # Create embedder (lazy — no model loaded) then inject mocks
    embedder = Embedder(config)
    embedder._tokenizer = mock_tokenizer
    embedder._tokenizer_loaded = True
    embedder._session = mock_session
    embedder._loaded = True

    return embedder


@pytest.fixture
def mock_embedder(tmp_config):
    """Embedder with mocked ONNX session (snowflake default config)."""
    return _make_mock_embedder(tmp_config)


@pytest.fixture
def mock_nomic_embedder(nomic_config):
    """Embedder with mocked ONNX session (nomic config)."""
    return _make_mock_embedder(nomic_config)


class TestMeanPool:
    """Tests for the _mean_pool helper function."""

    def test_uniform_mask(self):
        """All-ones mask should produce a simple mean."""
        tokens = np.array([[[1.0, 2.0], [3.0, 4.0]]])
        mask = np.array([[1.0, 1.0]])
        result = _mean_pool(tokens, mask)
        expected = np.array([[2.0, 3.0]])
        np.testing.assert_allclose(result, expected)

    def test_partial_mask(self):
        """Masked tokens should be excluded from the mean."""
        tokens = np.array([[[1.0, 2.0], [3.0, 4.0]]])
        mask = np.array([[1.0, 0.0]])
        result = _mean_pool(tokens, mask)
        expected = np.array([[1.0, 2.0]])
        np.testing.assert_allclose(result, expected)

    def test_batch_dimension(self):
        """Should handle batches correctly."""
        tokens = np.array([
            [[1.0, 0.0], [0.0, 1.0]],
            [[2.0, 0.0], [0.0, 2.0]],
        ])
        mask = np.array([[1.0, 1.0], [1.0, 1.0]])
        result = _mean_pool(tokens, mask)
        assert result.shape == (2, 2)


class TestL2Normalize:
    """Tests for the _l2_normalize helper function."""

    def test_unit_length(self):
        """Output vectors should have unit L2 norm."""
        vectors = np.array([[3.0, 4.0], [1.0, 0.0]])
        result = _l2_normalize(vectors)
        norms = np.linalg.norm(result, axis=1)
        np.testing.assert_allclose(norms, [1.0, 1.0], atol=1e-6)

    def test_zero_vector_safe(self):
        """Near-zero vectors should not produce NaN."""
        vectors = np.array([[0.0, 0.0]])
        result = _l2_normalize(vectors)
        assert not np.any(np.isnan(result))


class TestTruncate:
    """Tests for the _truncate Matryoshka helper function."""

    def test_truncates_to_target(self):
        """Should slice vectors to target dimensions."""
        vectors = np.random.randn(2, 768).astype(np.float32)
        vectors = _l2_normalize(vectors)
        result = _truncate(vectors, 256)
        assert result.shape == (2, 256)

    def test_renormalizes_after_truncation(self):
        """Truncated vectors should have unit L2 norm."""
        vectors = np.random.randn(3, 768).astype(np.float32)
        vectors = _l2_normalize(vectors)
        result = _truncate(vectors, 256)
        norms = np.linalg.norm(result, axis=1)
        np.testing.assert_allclose(norms, [1.0, 1.0, 1.0], atol=1e-6)

    def test_no_op_when_dims_match(self):
        """Should return input unchanged when dims >= native."""
        vectors = np.random.randn(2, 256).astype(np.float32)
        vectors = _l2_normalize(vectors)
        result = _truncate(vectors, 256)
        np.testing.assert_array_equal(result, vectors)


class TestEmbedderSnowflake:
    """Tests for snowflake model (default) — query-only prefix, 256 dims."""

    def test_query_has_snowflake_prefix(self, mock_embedder):
        """Snowflake queries get the retrieval instruction prefix."""
        mock_embedder.embed_query("test query")
        last_texts = mock_embedder._tokenizer._last_texts
        assert last_texts[0].startswith(
            "Represent this sentence for searching relevant passages: "
        )

    def test_document_has_no_prefix(self, mock_embedder):
        """Snowflake documents should have NO prefix (raw text)."""
        mock_embedder.embed_documents(["hello world"])
        last_texts = mock_embedder._tokenizer._last_texts
        assert last_texts[0] == "hello world"

    def test_embed_query_returns_256_dims(self, mock_embedder):
        """Query embedding should be 256-dimensional (MRL truncation)."""
        result = mock_embedder.embed_query("test")
        assert len(result) == 256

    def test_embed_documents_returns_256_dims(self, mock_embedder):
        """Document embeddings should be 256-dimensional."""
        result = mock_embedder.embed_documents(["a", "b"])
        assert len(result) == 2
        assert all(len(vec) == 256 for vec in result)

    def test_embed_documents_returns_list_of_lists(self, mock_embedder):
        """embed_documents returns a list of float lists."""
        result = mock_embedder.embed_documents(["a", "b"])
        assert isinstance(result, list)
        assert isinstance(result[0], list)

    def test_embed_query_returns_list(self, mock_embedder):
        """embed_query returns a flat list of floats."""
        result = mock_embedder.embed_query("test")
        assert isinstance(result, list)

    def test_embeddings_are_normalized(self, mock_embedder):
        """Output embeddings should have approximately unit L2 norm."""
        result = mock_embedder.embed_documents(["normalize me"])
        vec = np.array(result[0])
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 0.01

    def test_model_name_matches_config(self, mock_embedder):
        """get_model_name returns the configured model ID."""
        assert mock_embedder.get_model_name() == "Snowflake/snowflake-arctic-embed-m-v2.0"


class TestEmbedderNomic:
    """Tests for nomic model — dual prefix, backward compat."""

    def test_query_has_nomic_prefix(self, mock_nomic_embedder):
        """Nomic queries get 'search_query: ' prefix."""
        mock_nomic_embedder.embed_query("test query")
        last_texts = mock_nomic_embedder._tokenizer._last_texts
        assert last_texts[0].startswith("search_query: ")

    def test_document_has_nomic_prefix(self, mock_nomic_embedder):
        """Nomic documents get 'search_document: ' prefix."""
        mock_nomic_embedder.embed_documents(["hello world"])
        last_texts = mock_nomic_embedder._tokenizer._last_texts
        assert last_texts[0].startswith("search_document: ")


class TestEmbedImage:
    """Tests for the multimodal-ready embed_image stub."""

    def test_embed_image_raises_not_implemented(self, mock_embedder):
        """Text-only embedder should raise NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Text-only model"):
            mock_embedder.embed_image("some/image.png")


class TestUnloadLifecycle:
    """Tests for separate tokenizer/session lifecycle and gc on unload."""

    def test_unload_keeps_tokenizer(self, mock_embedder):
        """After unload, tokenizer should stay resident (cheap: ~20MB)."""
        mock_embedder.unload()
        assert mock_embedder._tokenizer is not None
        assert mock_embedder._tokenizer_loaded is True
        assert mock_embedder._session is None
        assert mock_embedder._loaded is False

    def test_unload_clears_session(self, mock_embedder):
        """Unload should set _session to None."""
        assert mock_embedder._session is not None
        mock_embedder.unload()
        assert mock_embedder._session is None

    def test_unload_calls_gc(self, mock_embedder):
        """Unload should call gc.collect() to free ONNX C++ buffers."""
        with patch("smart_search.embedder.gc.collect") as mock_gc:
            mock_embedder.unload()
            mock_gc.assert_called_once()

    def test_reload_after_unload_only_loads_session(self, mock_embedder):
        """After unload + re-ensure_loaded, only session should reload."""
        mock_embedder.unload()
        # Simulate re-load by patching _load_session
        fake_session = MagicMock()
        with patch.object(Embedder, "_load_session", return_value=fake_session) as mock_load:
            mock_embedder._ensure_loaded()
            mock_load.assert_called_once()
        # Tokenizer should not have been reloaded
        assert mock_embedder._tokenizer_loaded is True

    def test_is_loaded_reflects_session_state(self, mock_embedder):
        """is_loaded should track ONNX session, not tokenizer."""
        assert mock_embedder.is_loaded is True
        mock_embedder.unload()
        assert mock_embedder.is_loaded is False


class TestOnnxSessionOptions:
    """Tests for memory-optimized ONNX session configuration."""

    def test_session_options_disable_arena(self):
        """_load_session should set enable_cpu_mem_arena = False."""
        with patch("smart_search.embedder.Embedder._get_model_path") as mock_path, \
             patch("onnxruntime.SessionOptions") as mock_opts_cls, \
             patch("onnxruntime.InferenceSession"):
            import onnxruntime as ort
            mock_model_path = MagicMock()
            mock_model_path.__truediv__ = MagicMock(side_effect=lambda x: mock_model_path)
            mock_model_path.exists.return_value = True
            mock_path.return_value = mock_model_path
            mock_opts = MagicMock()
            mock_opts_cls.return_value = mock_opts

            config = SmartSearchConfig(
                lancedb_path="test", sqlite_path="test"
            )
            Embedder._load_session(config)

            assert mock_opts.enable_cpu_mem_arena is False
            assert mock_opts.enable_mem_pattern is True
            assert mock_opts.intra_op_num_threads == 2
            assert mock_opts.inter_op_num_threads == 1
            assert mock_opts.execution_mode == ort.ExecutionMode.ORT_SEQUENTIAL


class TestStandaloneTokenizer:
    """Tests for standalone tokenizers (Rust) integration."""

    def test_encode_batch_produces_ids_and_mask(self, mock_embedder):
        """encode_batch output should have .ids and .attention_mask."""
        result = mock_embedder._tokenizer.encode_batch(["test"])
        assert hasattr(result[0], "ids")
        assert hasattr(result[0], "attention_mask")

    def test_tokenizer_file_not_found_raises(self, tmp_path):
        """_load_tokenizer should raise if tokenizer.json is missing."""
        with patch.object(Embedder, "_get_model_path", return_value=tmp_path):
            config = SmartSearchConfig(
                lancedb_path="test", sqlite_path="test"
            )
            with pytest.raises(FileNotFoundError, match="tokenizer.json"):
                Embedder._load_tokenizer(config)


class TestIsModelCached:
    """Tests for the static is_model_cached method."""

    def test_returns_false_when_not_cached(self):
        """Should return False when model is not in HF cache."""
        with patch("huggingface_hub.try_to_load_from_cache", return_value=None):
            assert Embedder.is_model_cached("fake/model") is False

    def test_returns_true_when_cached(self, tmp_path):
        """Should return True when model files exist in cache."""
        fake_onnx = tmp_path / "onnx" / "model.onnx"
        fake_onnx.parent.mkdir(parents=True)
        fake_onnx.write_bytes(b"fake")
        with patch("huggingface_hub.try_to_load_from_cache", return_value=str(fake_onnx)):
            assert Embedder.is_model_cached("fake/model") is True

    def test_handles_exception_gracefully(self):
        """Should return False on any exception, not crash."""
        with patch("huggingface_hub.try_to_load_from_cache", side_effect=Exception("boom")):
            assert Embedder.is_model_cached("fake/model") is False


class TestGetModelDir:
    """Tests for the static _get_model_dir method."""

    def test_get_model_dir_finds_imported_model(self, tmp_path, monkeypatch):
        """_get_model_dir should find models via direct snapshot scan."""
        cache = tmp_path / "hub"
        snapshot = cache / "models--test--model" / "snapshots" / "abc123" / "onnx"
        snapshot.mkdir(parents=True)
        (snapshot / "model_quantized.onnx").write_bytes(b"fake")

        monkeypatch.setenv("HF_HOME", str(tmp_path))

        with patch("huggingface_hub.try_to_load_from_cache", return_value=None), \
             patch("smart_search.model_download.get_hf_cache_path", return_value=str(cache)):
            result = Embedder._get_model_dir("test/model")
        assert result is not None
        assert "abc123" in str(result)


class TestEmbedderGpuProviders:
    """Tests for GPU provider integration in Embedder."""

    @patch("smart_search.embedder.detect_gpu")
    def test_gpu_active_when_gpu_detected(self, mock_detect, tmp_config):
        """Embedder sets _gpu_active=True when GPU is detected."""
        mock_detect.return_value = "cuda"
        embedder = Embedder(tmp_config)
        assert embedder._gpu_active is True

    @patch("smart_search.embedder.detect_gpu")
    def test_gpu_inactive_when_no_gpu(self, mock_detect, tmp_config):
        """Embedder sets _gpu_active=False when no GPU available."""
        mock_detect.return_value = None
        embedder = Embedder(tmp_config)
        assert embedder._gpu_active is False

    @patch("smart_search.embedder.detect_gpu")
    def test_disables_idle_unload_on_gpu(self, mock_detect, tmp_config):
        """When GPU is detected, idle timeout is set to 0 (no auto-unload)."""
        mock_detect.return_value = "directml"
        embedder = Embedder(tmp_config)
        assert embedder._idle_timeout == 0

    @patch("smart_search.embedder.detect_gpu")
    def test_preserves_idle_unload_on_cpu(self, mock_detect, tmp_config):
        """When no GPU, idle timeout remains as configured."""
        mock_detect.return_value = None
        embedder = Embedder(tmp_config)
        assert embedder._idle_timeout == tmp_config.embedder_idle_timeout

    @patch("smart_search.embedder.detect_gpu")
    def test_gpu_inactive_when_backend_cloud(self, mock_detect, tmp_config):
        """GPU is not used when backend is set to 'cloud'."""
        mock_detect.return_value = "cuda"
        config = tmp_config.model_copy(update={"embedding_backend": "cloud"})
        embedder = Embedder(config)
        assert embedder._gpu_active is False


@pytest.mark.slow
class TestEmbedderSlow:
    """Slow tests that load the real embedding model."""

    @pytest.fixture(autouse=True)
    def real_embedder(self, tmp_config):
        """Load actual embedding model."""
        self.embedder = Embedder(tmp_config)

    def test_embed_query_returns_configured_dims(self):
        """Query embedding has configured dimensions (256)."""
        vec = self.embedder.embed_query("What is machine learning?")
        assert len(vec) == 256

    def test_embed_documents_batch(self):
        """Three texts produce three vectors."""
        texts = ["First doc.", "Second doc.", "Third doc."]
        vecs = self.embedder.embed_documents(texts)
        assert len(vecs) == 3
        assert all(len(v) == 256 for v in vecs)

    def test_embed_documents_consistent(self):
        """Same input produces same output (deterministic)."""
        text = "Reproducibility matters."
        vec_a = self.embedder.embed_documents([text])[0]
        vec_b = self.embedder.embed_documents([text])[0]
        assert vec_a == vec_b

    def test_query_document_similarity(self):
        """Related texts have higher cosine similarity than unrelated."""
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

    def test_is_model_cached_after_load(self):
        """After loading the model, is_model_cached should return True."""
        assert Embedder.is_model_cached() is True
