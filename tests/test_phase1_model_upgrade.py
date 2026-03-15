# Tests for Phase 1: snowflake model upgrade, Matryoshka truncation, dynamic schema.

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_search.config import SmartSearchConfig
from smart_search.config_manager import ConfigManager
from smart_search.embedder import Embedder, _l2_normalize


# --- Task 1.1: Config defaults ---


class TestSnowflakeConfigDefaults:
    """Verify config defaults point to snowflake model with 256 dims."""

    def test_default_model_is_snowflake(self):
        """Default embedding model should be snowflake-arctic-embed-m-v2.0."""
        config = SmartSearchConfig()
        assert config.embedding_model == "Snowflake/snowflake-arctic-embed-m-v2.0"

    def test_default_dimensions_256(self):
        """Default embedding dimensions should be 256 (MRL truncation)."""
        config = SmartSearchConfig()
        assert config.embedding_dimensions == 256

    def test_config_manager_default_model(self, tmp_path):
        """ConfigManager defaults to snowflake model."""
        mgr = ConfigManager(tmp_path)
        config = mgr.load()
        assert config["embedding_model"] == "Snowflake/snowflake-arctic-embed-m-v2.0"

    def test_config_manager_default_dims_is_int(self, tmp_path):
        """ConfigManager stores default dimensions as int, not string."""
        mgr = ConfigManager(tmp_path)
        config = mgr.load()
        assert config["embedding_dimensions"] == 256
        assert isinstance(config["embedding_dimensions"], int)

    def test_embedder_idle_timeout_default(self):
        """Default embedder idle timeout should be 60 seconds."""
        config = SmartSearchConfig()
        assert config.embedder_idle_timeout == 60.0


# --- Task 1.2: Matryoshka truncation ---


@pytest.fixture
def snowflake_config(tmp_path):
    """SmartSearchConfig for snowflake model with 256 dims."""
    return SmartSearchConfig(
        lancedb_path=str(tmp_path / "vectors"),
        sqlite_path=str(tmp_path / "meta.db"),
        embedding_model="Snowflake/snowflake-arctic-embed-m-v2.0",
        embedding_dimensions=256,
    )


@pytest.fixture
def nomic_config(tmp_path):
    """SmartSearchConfig for nomic model with 256 dims."""
    return SmartSearchConfig(
        lancedb_path=str(tmp_path / "vectors"),
        sqlite_path=str(tmp_path / "meta.db"),
        embedding_model="nomic-ai/nomic-embed-text-v1.5",
        embedding_dimensions=256,
    )


def _make_mock_embedder(config, hidden_dim=768):
    """Create an Embedder with mocked ONNX session and tokenizer.

    Args:
        config: SmartSearchConfig instance.
        hidden_dim: Hidden dimension of the mock model output.

    Returns:
        Embedder instance with mocked internals.
    """
    mock_tokenizer = MagicMock()
    mock_tokenizer._last_texts = []

    def tokenize(texts, **kwargs):
        mock_tokenizer._last_texts = texts
        return {
            "input_ids": np.ones((len(texts), 10), dtype=np.int64),
            "attention_mask": np.ones((len(texts), 10), dtype=np.int64),
        }

    mock_tokenizer.side_effect = tokenize

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
    embedder._session = mock_session
    embedder._loaded = True

    return embedder


class TestMatryoshkaTruncation:
    """Tests for MRL truncation in the embedder."""

    def test_truncate_reduces_dimensions(self, snowflake_config):
        """Embedding output should match configured dimensions (256)."""
        embedder = _make_mock_embedder(snowflake_config)
        result = embedder.embed_query("test query")
        assert len(result) == 256

    def test_truncate_documents_reduces_dimensions(self, snowflake_config):
        """Document embeddings should also be truncated to 256 dims."""
        embedder = _make_mock_embedder(snowflake_config)
        results = embedder.embed_documents(["doc one", "doc two"])
        assert all(len(vec) == 256 for vec in results)

    def test_truncate_renormalizes(self, snowflake_config):
        """Truncated vectors should have approximately unit L2 norm."""
        embedder = _make_mock_embedder(snowflake_config)
        result = embedder.embed_query("test")
        vec = np.array(result)
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 0.01

    def test_no_truncation_when_dims_match(self, tmp_path):
        """When configured dims == native dims, output is 768."""
        config = SmartSearchConfig(
            lancedb_path=str(tmp_path / "vectors"),
            sqlite_path=str(tmp_path / "meta.db"),
            embedding_dimensions=768,
        )
        embedder = _make_mock_embedder(config)
        result = embedder.embed_query("test")
        assert len(result) == 768


# --- Task 1.2b: Model-aware prefixes ---


class TestModelAwarePrefixes:
    """Tests for model-specific prefix behavior."""

    def test_snowflake_query_has_prefix(self, snowflake_config):
        """Snowflake queries get the retrieval prefix."""
        embedder = _make_mock_embedder(snowflake_config)
        embedder.embed_query("test query")
        last_texts = embedder._tokenizer._last_texts
        assert last_texts[0].startswith(
            "Represent this sentence for searching relevant passages: "
        )

    def test_snowflake_document_no_prefix(self, snowflake_config):
        """Snowflake documents get NO prefix (raw text only)."""
        embedder = _make_mock_embedder(snowflake_config)
        embedder.embed_documents(["hello world"])
        last_texts = embedder._tokenizer._last_texts
        assert last_texts[0] == "hello world"

    def test_nomic_query_has_prefix(self, nomic_config):
        """Nomic queries get 'search_query: ' prefix."""
        embedder = _make_mock_embedder(nomic_config)
        embedder.embed_query("test query")
        last_texts = embedder._tokenizer._last_texts
        assert last_texts[0].startswith("search_query: ")

    def test_nomic_document_has_prefix(self, nomic_config):
        """Nomic documents get 'search_document: ' prefix."""
        embedder = _make_mock_embedder(nomic_config)
        embedder.embed_documents(["hello world"])
        last_texts = embedder._tokenizer._last_texts
        assert last_texts[0].startswith("search_document: ")


# --- Task 1.4: Dynamic LanceDB schema ---


class TestDynamicSchema:
    """Tests for LanceDB schema using configured dimensions."""

    def test_store_schema_uses_config_dims(self, tmp_path):
        """LanceDB table schema should use embedding_dimensions from config."""
        from smart_search.store import ChunkStore

        config = SmartSearchConfig(
            lancedb_path=str(tmp_path / "vectors"),
            sqlite_path=str(tmp_path / "meta.db"),
            embedding_dimensions=256,
        )
        store = ChunkStore(config)
        store.initialize()

        # Check that the schema's embedding field has width 256
        schema = store._table.schema
        embedding_field = schema.field("embedding")
        assert embedding_field.type.value_type == "float"
        assert embedding_field.type.list_size == 256


# --- Task 1.5: Multimodal-ready protocol ---


class TestMultimodalProtocol:
    """Tests for embed_image on the Embedder protocol."""

    def test_embed_image_raises_not_implemented(self, snowflake_config):
        """Text-only embedder should raise NotImplementedError for embed_image."""
        embedder = _make_mock_embedder(snowflake_config)
        with pytest.raises(NotImplementedError, match="Text-only model"):
            embedder.embed_image("some/image.png")

    def test_embedder_protocol_has_embed_image(self):
        """EmbedderProtocol should define embed_image method."""
        from smart_search.protocols import EmbedderProtocol
        assert hasattr(EmbedderProtocol, "embed_image")


# --- Task 1.6: rebuild_table ---


class TestRebuildTable:
    """Tests for store.rebuild_table() migration support."""

    def test_rebuild_creates_empty_table(self, tmp_path):
        """rebuild_table should drop and recreate an empty table."""
        from smart_search.store import ChunkStore

        config = SmartSearchConfig(
            lancedb_path=str(tmp_path / "vectors"),
            sqlite_path=str(tmp_path / "meta.db"),
            embedding_dimensions=256,
        )
        store = ChunkStore(config)
        store.initialize()

        # Verify table exists and is empty
        assert store._table.count_rows() == 0

        # Change config dims and rebuild
        config2 = SmartSearchConfig(
            lancedb_path=str(tmp_path / "vectors"),
            sqlite_path=str(tmp_path / "meta.db"),
            embedding_dimensions=128,
        )
        store._config = config2
        store.rebuild_table()

        # Verify new table exists with 0 rows
        assert store._table.count_rows() == 0
        schema = store._table.schema
        embedding_field = schema.field("embedding")
        assert embedding_field.type.list_size == 128

    def test_rebuild_clears_sqlite_records(self, tmp_path):
        """rebuild_table should clear indexed_files from SQLite."""
        from smart_search.store import ChunkStore

        config = SmartSearchConfig(
            lancedb_path=str(tmp_path / "vectors"),
            sqlite_path=str(tmp_path / "meta.db"),
            embedding_dimensions=256,
        )
        store = ChunkStore(config)
        store.initialize()

        # Add a fake file record
        store.record_file_indexed("/fake/file.md", "abc123", 5)
        assert len(store.list_indexed_files()) == 1

        store.rebuild_table()

        # SQLite records should be cleared
        assert len(store.list_indexed_files()) == 0
