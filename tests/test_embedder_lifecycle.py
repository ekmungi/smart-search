# Tests for embedder lifecycle: lazy loading, idle unload, thread safety.

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_search.config import SmartSearchConfig
from smart_search.embedder import Embedder


def _make_mock_components():
    """Create mock tokenizer and session for testing lifecycle."""
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
            batch_size, seq_len, 768
        ).astype(np.float32)
        return [token_embs]

    mock_session.run.side_effect = mock_run
    return mock_tokenizer, mock_session


@pytest.fixture
def config(tmp_path):
    """Config with short idle timeout for testing."""
    return SmartSearchConfig(
        lancedb_path=str(tmp_path / "vectors"),
        sqlite_path=str(tmp_path / "meta.db"),
        embedder_idle_timeout=0.2,
    )


@pytest.fixture
def no_timeout_config(tmp_path):
    """Config with idle timeout disabled."""
    return SmartSearchConfig(
        lancedb_path=str(tmp_path / "vectors"),
        sqlite_path=str(tmp_path / "meta.db"),
        embedder_idle_timeout=0,
    )


class TestLazyLoading:
    """Tests that __init__ does NOT load the model."""

    def test_init_does_not_load(self, config):
        """Embedder __init__ should NOT call _load_model."""
        with patch.object(Embedder, "_load_model") as mock_load:
            embedder = Embedder(config)
            mock_load.assert_not_called()
            assert embedder.is_loaded is False

    def test_first_embed_triggers_load(self, config):
        """First embed_query call should trigger _load_model."""
        mock_tok, mock_sess = _make_mock_components()
        with patch.object(Embedder, "_load_model", return_value=(mock_tok, mock_sess)) as mock_load:
            embedder = Embedder(config)
            assert embedder.is_loaded is False
            embedder.embed_query("hello")
            mock_load.assert_called_once()
            assert embedder.is_loaded is True

    def test_second_embed_does_not_reload(self, config):
        """Subsequent calls should not reload the model."""
        mock_tok, mock_sess = _make_mock_components()
        with patch.object(Embedder, "_load_model", return_value=(mock_tok, mock_sess)) as mock_load:
            embedder = Embedder(config)
            embedder.embed_query("a")
            embedder.embed_query("b")
            mock_load.assert_called_once()


class TestIdleUnload:
    """Tests for automatic model unload after idle timeout."""

    def test_unload_after_idle(self, config):
        """Model should unload after idle timeout elapses."""
        mock_tok, mock_sess = _make_mock_components()
        with patch.object(Embedder, "_load_model", return_value=(mock_tok, mock_sess)):
            embedder = Embedder(config)
            embedder.embed_query("test")
            assert embedder.is_loaded is True

            # Wait for idle timeout (0.2s) plus margin
            time.sleep(0.4)
            assert embedder.is_loaded is False

    def test_timer_resets_on_use(self, config):
        """Using the embedder should reset the idle timer."""
        mock_tok, mock_sess = _make_mock_components()
        with patch.object(Embedder, "_load_model", return_value=(mock_tok, mock_sess)):
            embedder = Embedder(config)
            embedder.embed_query("a")

            # Wait partway through timeout
            time.sleep(0.1)
            embedder.embed_query("b")  # resets timer

            # Wait another partial period
            time.sleep(0.1)
            assert embedder.is_loaded is True  # still loaded

    def test_no_timer_when_timeout_zero(self, no_timeout_config):
        """No idle timer should be set when timeout is 0."""
        mock_tok, mock_sess = _make_mock_components()
        with patch.object(Embedder, "_load_model", return_value=(mock_tok, mock_sess)):
            embedder = Embedder(no_timeout_config)
            embedder.embed_query("test")
            assert embedder._timer is None
            assert embedder.is_loaded is True

    def test_reload_after_unload(self, config):
        """Model should reload on next use after unload."""
        mock_tok, mock_sess = _make_mock_components()
        with patch.object(Embedder, "_load_model", return_value=(mock_tok, mock_sess)) as mock_load:
            embedder = Embedder(config)
            embedder.embed_query("first")
            assert mock_load.call_count == 1

            embedder.unload()
            assert embedder.is_loaded is False

            embedder.embed_query("second")
            assert mock_load.call_count == 2
            assert embedder.is_loaded is True


class TestManualUnload:
    """Tests for explicit unload() method."""

    def test_unload_frees_resources(self, config):
        """unload() should set session and tokenizer to None."""
        mock_tok, mock_sess = _make_mock_components()
        with patch.object(Embedder, "_load_model", return_value=(mock_tok, mock_sess)):
            embedder = Embedder(config)
            embedder.embed_query("test")
            embedder.unload()
            assert embedder._session is None
            assert embedder._tokenizer is None
            assert embedder.is_loaded is False

    def test_unload_when_not_loaded_is_safe(self, config):
        """Calling unload() before any load should not raise."""
        with patch.object(Embedder, "_load_model"):
            embedder = Embedder(config)
            embedder.unload()  # should not raise


class TestThreadSafety:
    """Tests for concurrent access to the embedder."""

    def test_concurrent_first_calls(self, config):
        """Multiple threads calling embed_query simultaneously should not crash."""
        mock_tok, mock_sess = _make_mock_components()
        with patch.object(Embedder, "_load_model", return_value=(mock_tok, mock_sess)):
            embedder = Embedder(config)

            def embed_task(text):
                return embedder.embed_query(text)

            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(embed_task, f"text {i}") for i in range(8)]
                results = [f.result() for f in futures]

            assert len(results) == 8
            assert all(len(r) == 256 for r in results)
