# Embedding generation using nomic-embed-text-v1.5 with direct ONNX inference.
#
# Uses huggingface_hub for model download, transformers for tokenization,
# and onnxruntime for inference. No torch/sentence-transformers dependency.

from pathlib import Path
from typing import List, Optional

import numpy as np

from smart_search.config import SmartSearchConfig


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


class Embedder:
    """Generates text embeddings using nomic-embed-text-v1.5.

    Handles task prefix injection (search_document: / search_query:)
    required by the nomic model. Uses direct ONNX inference -- no
    torch or sentence-transformers dependency.
    """

    def __init__(self, config: SmartSearchConfig) -> None:
        """Initialize the embedder with the configured model.

        Downloads the ONNX model on first use via huggingface_hub.
        Subsequent runs use the cached version in HF_HOME / data_dir.

        Args:
            config: SmartSearchConfig with model name and backend settings.
        """
        self._config = config
        self._tokenizer, self._session = self._load_model(config)

    @staticmethod
    def _get_model_dir(model_name: str) -> Optional[Path]:
        """Return the local snapshot directory if the model is already cached.

        Checks the huggingface_hub cache for a completed snapshot.

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
        except Exception:
            pass
        return None

    @staticmethod
    def is_model_cached(model_name: str = "nomic-ai/nomic-embed-text-v1.5") -> bool:
        """Check whether the ONNX model files are available locally.

        Args:
            model_name: HuggingFace model identifier.

        Returns:
            True if the model is cached and ready for offline use.
        """
        return Embedder._get_model_dir(model_name) is not None

    def _load_model(self, config: SmartSearchConfig):
        """Download (if needed) and load the ONNX model and tokenizer.

        Args:
            config: Configuration with model name.

        Returns:
            Tuple of (AutoTokenizer, onnxruntime.InferenceSession).
        """
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer
        import onnxruntime as ort

        # Download the full model snapshot (tokenizer + ONNX weights)
        model_dir = snapshot_download(
            config.embedding_model,
            ignore_patterns=["*.bin", "*.pt", "*.safetensors", "*.msgpack"],
        )
        model_path = Path(model_dir)

        # Load tokenizer from the snapshot
        tokenizer = AutoTokenizer.from_pretrained(str(model_path))

        # Find the ONNX model file
        onnx_path = model_path / "onnx" / "model.onnx"
        if not onnx_path.exists():
            # Some models put it at the root
            onnx_path = model_path / "model.onnx"
        if not onnx_path.exists():
            raise FileNotFoundError(
                f"No ONNX model found in {model_dir}. "
                "Expected onnx/model.onnx or model.onnx."
            )

        # Create ONNX inference session (CPU only)
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = ort.InferenceSession(
            str(onnx_path),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )

        return tokenizer, session

    def _encode(self, texts: List[str]) -> np.ndarray:
        """Tokenize and run ONNX inference on a batch of texts.

        Args:
            texts: Pre-prefixed text strings.

        Returns:
            L2-normalized embeddings of shape (batch, 768).
        """
        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=8192,
            return_tensors="np",
        )
        input_ids = encoded["input_ids"].astype(np.int64)
        attention_mask = encoded["attention_mask"].astype(np.int64)

        # Run ONNX inference
        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
        # Add token_type_ids if the model expects it
        input_names = [inp.name for inp in self._session.get_inputs()]
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)

        outputs = self._session.run(None, feeds)

        # outputs[0] is last_hidden_state: (batch, seq_len, hidden_dim)
        token_embeddings = outputs[0]
        pooled = _mean_pool(token_embeddings, encoded["attention_mask"].astype(np.float32))
        normalized = _l2_normalize(pooled)

        return normalized

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for document chunks.

        Prepends 'search_document: ' prefix required by nomic-embed.

        Args:
            texts: List of document text strings to embed.

        Returns:
            List of embedding vectors (each 768-dim float list).
        """
        prefixed = [f"{self._config.nomic_document_prefix}{t}" for t in texts]
        embeddings = self._encode(prefixed)
        return [vec.tolist() for vec in embeddings]

    def embed_query(self, query: str) -> List[float]:
        """Generate embedding for a search query.

        Prepends 'search_query: ' prefix required by nomic-embed.

        Args:
            query: Search query string.

        Returns:
            768-dim embedding vector as float list.
        """
        prefixed = [f"{self._config.nomic_query_prefix}{query}"]
        embeddings = self._encode(prefixed)
        return embeddings[0].tolist()

    def get_model_name(self) -> str:
        """Return the configured embedding model identifier.

        Returns:
            Model name string (e.g., 'nomic-ai/nomic-embed-text-v1.5').
        """
        return self._config.embedding_model
