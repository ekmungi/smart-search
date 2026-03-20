# Embedding utility functions for pooling, normalization, and truncation.

"""Pure numpy helper functions used by the Embedder class for post-processing
ONNX model outputs into final embedding vectors."""

import numpy as np


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
