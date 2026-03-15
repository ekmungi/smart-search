# Embedding generation with lazy loading, idle unload, and Matryoshka truncation.
#
# Supports snowflake-arctic-embed-m-v2.0 (default) and nomic-embed-text-v1.5.
# Uses huggingface_hub for download, transformers for tokenization, onnxruntime
# for inference. No torch/sentence-transformers dependency.

import threading
import time
from pathlib import Path
from typing import List, Optional

import numpy as np

from smart_search.config import SmartSearchConfig


# Model prefix configurations: (document_prefix, query_prefix)
# None means no prefix for that role.
_MODEL_PREFIXES = {
    "Snowflake/snowflake-arctic-embed-m-v2.0": (
        None,
        "Represent this sentence for searching relevant passages: ",
    ),
    "nomic-ai/nomic-embed-text-v1.5": (
        "search_document: ",
        "search_query: ",
    ),
}

# Default prefix style for unknown models: query-only (safest assumption)
_DEFAULT_PREFIXES = (None, "Represent this sentence for searching relevant passages: ")


def _mean_pool(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    """Mean-pool token embeddings using the attention mask.

    Args:
        token_embeddings: Shape (batch, seq_len, hidden_dim).
        attention_mask: Shape (batch, seq_len), 1 for real tokens, 0 for padding.

    Returns:
        Pooled embeddings of shape (batch, hidden_dim).
    """
    mask_expanded = np.expand_dims(attention_mask, axis=-1).astype(np.float32)
    summed = np.sum(token_embeddings * mask_expanded, axis=1)
    counts = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
    return summed / counts


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize each row vector.

    Args:
        vectors: Shape (batch, dim).

    Returns:
        Unit-length vectors of same shape.
    """
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.clip(norms, a_min=1e-12, a_max=None)
    return vectors / norms


def _truncate(vectors: np.ndarray, dimensions: int) -> np.ndarray:
    """Matryoshka truncation: slice to target dims and re-normalize.

    Args:
        vectors: Shape (batch, native_dim) -- full-width embeddings.
        dimensions: Target dimensionality (e.g. 256).

    Returns:
        Truncated and re-normalized vectors of shape (batch, dimensions).
    """
    if dimensions >= vectors.shape[1]:
        return vectors
    truncated = vectors[:, :dimensions]
    return _l2_normalize(truncated)


class Embedder:
    """Generates text embeddings with lazy loading and idle auto-unload.

    The ONNX model is loaded on first use and unloaded after a configurable
    idle timeout to minimize RAM consumption when not actively indexing
    or searching. Thread-safe via a loading lock.
    """

    def __init__(self, config: SmartSearchConfig) -> None:
        """Initialize the embedder -- does NOT load the model yet.

        The model is loaded lazily on first embed call via _ensure_loaded().

        Args:
            config: SmartSearchConfig with model name, dims, and backend.
        """
        self._config = config
        self._dimensions = config.embedding_dimensions
        self._idle_timeout = config.embedder_idle_timeout
        self._doc_prefix, self._query_prefix = _MODEL_PREFIXES.get(
            config.embedding_model, _DEFAULT_PREFIXES
        )

        # Model state -- guarded by _lock
        self._tokenizer = None
        self._session = None
        self._loaded = False
        self._lock = threading.Lock()

        # Idle timer state
        self._last_used: float = 0.0
        self._timer: Optional[threading.Timer] = None

    @property
    def is_loaded(self) -> bool:
        """Whether the ONNX model is currently loaded in memory."""
        return self._loaded

    def _ensure_loaded(self) -> None:
        """Load the model if not already loaded. Thread-safe.

        Acquires the lock and checks again (double-checked locking pattern)
        to avoid redundant loads from concurrent callers.
        """
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._tokenizer, self._session = self._load_model(self._config)
            self._loaded = True

    def unload(self) -> None:
        """Unload the ONNX model from memory to free RAM.

        Thread-safe -- acquires the lock to prevent unloading during inference.
        """
        with self._lock:
            self._session = None
            self._tokenizer = None
            self._loaded = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _reset_idle_timer(self) -> None:
        """Reset the idle unload timer after each use.

        Cancels any existing timer and starts a new one. When the timer
        fires, _check_idle() will unload the model if still idle.
        """
        if self._idle_timeout <= 0:
            return
        if self._timer is not None:
            self._timer.cancel()
        self._last_used = time.monotonic()
        self._timer = threading.Timer(self._idle_timeout, self._check_idle)
        self._timer.daemon = True
        self._timer.start()

    def _check_idle(self) -> None:
        """Timer callback: unload model if idle timeout has elapsed."""
        elapsed = time.monotonic() - self._last_used
        if elapsed >= self._idle_timeout:
            self.unload()

    @staticmethod
    def _get_model_dir(model_name: str) -> Optional[Path]:
        """Return the local snapshot directory if the model is already cached.

        Args:
            model_name: HuggingFace model identifier.

        Returns:
            Path to cached model directory, or None if not cached.
        """
        try:
            from huggingface_hub import try_to_load_from_cache
            result = try_to_load_from_cache(model_name, "onnx/model.onnx")
            if result is not None and isinstance(result, str):
                return Path(result).parent.parent
            result = try_to_load_from_cache(model_name, "onnx/model_quantized.onnx")
            if result is not None and isinstance(result, str):
                return Path(result).parent.parent
        except Exception:
            pass
        return None

    @staticmethod
    def is_model_cached(model_name: str = "Snowflake/snowflake-arctic-embed-m-v2.0") -> bool:
        """Check whether the ONNX model files are available locally.

        Args:
            model_name: HuggingFace model identifier.

        Returns:
            True if the model is cached and ready for offline use.
        """
        return Embedder._get_model_dir(model_name) is not None

    def _load_model(self, config: SmartSearchConfig):
        """Download (if needed) and load the ONNX model and tokenizer.

        Prefers int8 quantized ONNX when available (smaller, faster on CPU).

        Args:
            config: Configuration with model name.

        Returns:
            Tuple of (AutoTokenizer, onnxruntime.InferenceSession).
        """
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer
        import onnxruntime as ort

        model_dir = snapshot_download(
            config.embedding_model,
            ignore_patterns=["*.bin", "*.pt", "*.safetensors", "*.msgpack"],
        )
        model_path = Path(model_dir)

        tokenizer = AutoTokenizer.from_pretrained(str(model_path))

        # Prefer quantized int8, fall back to fp32
        onnx_path = model_path / "onnx" / "model_quantized.onnx"
        if not onnx_path.exists():
            onnx_path = model_path / "onnx" / "model.onnx"
        if not onnx_path.exists():
            onnx_path = model_path / "model.onnx"
        if not onnx_path.exists():
            raise FileNotFoundError(
                f"No ONNX model found in {model_dir}. "
                "Expected onnx/model_quantized.onnx, onnx/model.onnx, or model.onnx."
            )

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = ort.InferenceSession(
            str(onnx_path),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )

        return tokenizer, session

    def _encode(self, texts: List[str]) -> np.ndarray:
        """Tokenize, run ONNX inference, and apply Matryoshka truncation.

        Calls _ensure_loaded() first, then resets the idle timer after use.

        Args:
            texts: Pre-prefixed text strings.

        Returns:
            L2-normalized embeddings of shape (batch, self._dimensions).
        """
        self._ensure_loaded()

        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=8192,
            return_tensors="np",
        )
        input_ids = encoded["input_ids"].astype(np.int64)
        attention_mask = encoded["attention_mask"].astype(np.int64)

        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
        input_names = [inp.name for inp in self._session.get_inputs()]
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)

        outputs = self._session.run(None, feeds)

        token_embeddings = outputs[0]
        pooled = _mean_pool(token_embeddings, encoded["attention_mask"].astype(np.float32))
        normalized = _l2_normalize(pooled)
        truncated = _truncate(normalized, self._dimensions)

        # Reset idle timer after successful inference
        self._reset_idle_timer()

        return truncated

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for document chunks.

        Applies model-specific document prefix if configured.

        Args:
            texts: List of document text strings to embed.

        Returns:
            List of embedding vectors (each self._dimensions-dim float list).
        """
        if self._doc_prefix:
            prefixed = [f"{self._doc_prefix}{t}" for t in texts]
        else:
            prefixed = list(texts)
        embeddings = self._encode(prefixed)
        return [vec.tolist() for vec in embeddings]

    def embed_query(self, query: str) -> List[float]:
        """Generate embedding for a search query.

        Applies model-specific query prefix.

        Args:
            query: Search query string.

        Returns:
            Embedding vector as float list (self._dimensions dims).
        """
        if self._query_prefix:
            prefixed = [f"{self._query_prefix}{query}"]
        else:
            prefixed = [query]
        embeddings = self._encode(prefixed)
        return embeddings[0].tolist()

    def embed_image(self, image_path: str) -> List[float]:
        """Generate embedding for an image file.

        Not supported by text-only models. Multimodal models (v0.8.0)
        will override this method.

        Args:
            image_path: Path to the image file.

        Raises:
            NotImplementedError: Always, for text-only models.
        """
        raise NotImplementedError("Text-only model does not support image embedding")

    def get_model_name(self) -> str:
        """Return the configured embedding model identifier.

        Returns:
            Model name string.
        """
        return self._config.embedding_model
