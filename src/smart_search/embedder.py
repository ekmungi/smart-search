# Embedding generation with lazy loading, idle unload, and Matryoshka truncation.
#
# Supports snowflake-arctic-embed-m-v2.0 (default) and nomic-embed-text-v1.5.
# Uses huggingface_hub for download, standalone tokenizers (Rust) for tokenization,
# onnxruntime for inference. No torch/sentence-transformers dependency.
#
# Memory optimizations (v0.8.2):
# - ONNX arena disabled (saves 300-500MB), sequential execution, limited threads
# - Standalone tokenizers replaces transformers (saves 100-150MB baseline RSS)
# - Tokenizer lifecycle separated from ONNX session (faster reload after idle)
# - gc.collect() on unload ensures C++ buffers return to OS

import gc
import threading
import time
from pathlib import Path
from typing import List, Optional

import numpy as np

from smart_search.config import SmartSearchConfig
from smart_search.gpu_provider import build_provider_chain, detect_gpu
from smart_search.embedder_utils import _l2_normalize, _mean_pool, _truncate


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

# Maximum texts per ONNX inference call. Larger batches cause O(n) VRAM/RAM
# growth; 8 keeps peak memory well under 500 MB even with long sequences.
_EMBED_BATCH_SIZE = 8

# Maximum tokens per text. 512 covers our ~500-char chunks comfortably.
# Higher values (e.g. 8192) cause massive memory usage when the tokenizer
# pads all batch entries to the longest sequence length.
_MAX_TOKEN_LENGTH = 512


class Embedder:
    """Generates text embeddings with lazy loading and idle auto-unload.

    The ONNX model is loaded on first use and unloaded after a configurable
    idle timeout to minimize RAM consumption when not actively indexing
    or searching. Thread-safe via a loading lock.
    """

    def __init__(self, config: SmartSearchConfig) -> None:
        """Initialize the embedder -- does NOT load the model yet.

        The model is loaded lazily on first embed call via _ensure_loaded().
        Tokenizer and ONNX session have separate lifecycles: the tokenizer
        (~20MB) stays resident once loaded; the ONNX session (~400MB) lazy-loads
        and idle-unloads independently.

        Args:
            config: SmartSearchConfig with model name, dims, and backend.
        """
        self._config = config
        self._dimensions = config.embedding_dimensions
        self._idle_timeout = config.embedder_idle_timeout
        self._doc_prefix, self._query_prefix = _MODEL_PREFIXES.get(
            config.embedding_model, _DEFAULT_PREFIXES
        )

        # Tokenizer state -- loaded once, stays resident (cheap: ~20MB)
        self._tokenizer = None
        self._tokenizer_loaded = False

        # ONNX session state -- lazy-loads and idle-unloads (expensive: ~400MB)
        self._session = None
        self._loaded = False
        self._lock = threading.Lock()

        # GPU state -- disable idle-unload on GPU (VRAM leak bug in ONNX Runtime)
        self._gpu_active = (
            detect_gpu() is not None and config.embedding_backend != "cloud"
        )
        if self._gpu_active:
            self._idle_timeout = 0

        # Idle timer state
        self._last_used: float = 0.0
        self._timer: Optional[threading.Timer] = None

    @property
    def is_loaded(self) -> bool:
        """Whether the ONNX model is currently loaded in memory."""
        return self._loaded

    def _ensure_loaded(self) -> None:
        """Load tokenizer and ONNX session if not already loaded. Thread-safe.

        Tokenizer is loaded once and stays resident. ONNX session lazy-loads
        and idle-unloads independently. Uses double-checked locking to avoid
        redundant loads from concurrent callers.
        """
        if not self._tokenizer_loaded:
            with self._lock:
                if not self._tokenizer_loaded:
                    self._tokenizer = self._load_tokenizer(self._config)
                    self._tokenizer_loaded = True
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._session = self._load_session(self._config)
            self._loaded = True

    def unload(self) -> None:
        """Unload the ONNX session from memory to free RAM.

        Only unloads the ONNX session (~400MB). The tokenizer (~20MB) stays
        resident for fast reload. Thread-safe via lock.
        gc.collect() forces ONNX Runtime's C++ allocations back to the OS.
        """
        with self._lock:
            self._session = None
            self._loaded = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        # Force free ONNX C++ buffers outside the lock
        gc.collect()

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
        except (ImportError, OSError):
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

    @staticmethod
    def _get_model_path(model_name: str) -> Path:
        """Download model if needed and return the local snapshot path.

        Args:
            model_name: HuggingFace model identifier.

        Returns:
            Path to the local model directory.
        """
        from huggingface_hub import snapshot_download

        model_dir = snapshot_download(
            model_name,
            ignore_patterns=["*.bin", "*.pt", "*.safetensors", "*.msgpack"],
        )
        return Path(model_dir)

    @staticmethod
    def _load_tokenizer(config: SmartSearchConfig):
        """Load the standalone Rust tokenizer from tokenizer.json.

        Uses the lightweight `tokenizers` library (~5MB) instead of the full
        `transformers` package (~150MB RSS). The tokenizer.json file is
        self-contained and created by huggingface_hub during model download.

        Args:
            config: Configuration with model name.

        Returns:
            tokenizers.Tokenizer instance with padding and truncation configured.
        """
        from tokenizers import Tokenizer

        model_path = Embedder._get_model_path(config.embedding_model)
        tokenizer_path = model_path / "tokenizer.json"

        if not tokenizer_path.exists():
            raise FileNotFoundError(
                f"No tokenizer.json found in {model_path}. "
                "Run model download first or use transformers to generate it."
            )

        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        # Configure padding: pad_id=0 is standard for BERT-family models.
        # pad_token must match the model's vocabulary.
        tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        tokenizer.enable_truncation(max_length=_MAX_TOKEN_LENGTH)
        return tokenizer

    @staticmethod
    def _load_session(config: SmartSearchConfig):
        """Load the ONNX inference session with memory-optimized settings.

        Prefers int8 quantized ONNX when available (smaller, faster on CPU).
        Disables the CPU memory arena to avoid speculative pre-allocation
        (saves 300-500MB) at the cost of ~10% slower inference.

        Args:
            config: Configuration with model name.

        Returns:
            onnxruntime.InferenceSession.
        """
        import onnxruntime as ort

        model_path = Embedder._get_model_path(config.embedding_model)

        # Prefer quantized int8, fall back to fp32
        onnx_path = model_path / "onnx" / "model_quantized.onnx"
        if not onnx_path.exists():
            onnx_path = model_path / "onnx" / "model.onnx"
        if not onnx_path.exists():
            onnx_path = model_path / "model.onnx"
        if not onnx_path.exists():
            raise FileNotFoundError(
                f"No ONNX model found in {model_path}. "
                "Expected onnx/model_quantized.onnx, onnx/model.onnx, or model.onnx."
            )

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # Memory optimizations: disable speculative arena pre-allocation,
        # limit thread buffers, use sequential execution.
        sess_options.enable_cpu_mem_arena = False
        sess_options.enable_mem_pattern = True
        sess_options.intra_op_num_threads = 2
        sess_options.inter_op_num_threads = 1
        sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        # Build provider chain: CUDA -> DirectML -> CPU (auto-detected)
        providers = build_provider_chain(
            backend=config.embedding_backend,
            device_id=config.gpu_device_id,
            gpu_mem_limit_mb=config.gpu_mem_limit_mb,
        )
        if not providers:
            providers = ["CPUExecutionProvider"]

        return ort.InferenceSession(
            str(onnx_path),
            sess_options=sess_options,
            providers=providers,
        )

    def _encode(self, texts: List[str]) -> np.ndarray:
        """Tokenize, run ONNX inference, and apply Matryoshka truncation.

        Calls _ensure_loaded() first, then resets the idle timer after use.

        Args:
            texts: Pre-prefixed text strings.

        Returns:
            L2-normalized embeddings of shape (batch, self._dimensions).
        """
        self._ensure_loaded()

        # Standalone tokenizers API: encode_batch returns Encoding objects
        encoded_batch = self._tokenizer.encode_batch(texts)
        input_ids = np.array(
            [e.ids for e in encoded_batch], dtype=np.int64
        )
        attention_mask = np.array(
            [e.attention_mask for e in encoded_batch], dtype=np.int64
        )

        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
        input_names = [inp.name for inp in self._session.get_inputs()]
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)

        outputs = self._session.run(None, feeds)

        token_embeddings = outputs[0]
        pooled = _mean_pool(token_embeddings, attention_mask.astype(np.float32))
        normalized = _l2_normalize(pooled)
        truncated = _truncate(normalized, self._dimensions)

        # Reset idle timer after successful inference
        self._reset_idle_timer()

        return truncated

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for document chunks in bounded memory batches.

        Applies model-specific document prefix if configured, then processes
        texts in batches of _EMBED_BATCH_SIZE to cap peak RAM usage. Without
        batching, large files with hundreds of chunks allocate a single large
        tokenization matrix and ONNX output tensor (bug B24: 17 GB peak).

        Args:
            texts: List of document text strings to embed.

        Returns:
            List of embedding vectors (each self._dimensions-dim float list).
        """
        if self._doc_prefix:
            prefixed = [f"{self._doc_prefix}{t}" for t in texts]
        else:
            prefixed = list(texts)

        all_embeddings: List[List[float]] = []
        for i in range(0, len(prefixed), _EMBED_BATCH_SIZE):
            batch = prefixed[i : i + _EMBED_BATCH_SIZE]
            batch_embeddings = self._encode(batch)
            all_embeddings.extend(vec.tolist() for vec in batch_embeddings)
            del batch_embeddings
            # Free ONNX output tensors and tokenizer matrices between batches
            if len(prefixed) > _EMBED_BATCH_SIZE:
                gc.collect()
        return all_embeddings

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
