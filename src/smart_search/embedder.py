# Embedding generation using nomic-embed-text-v1.5 with ONNX backend.

from typing import List

from sentence_transformers import SentenceTransformer

from smart_search.config import SmartSearchConfig


class Embedder:
    """Generates text embeddings using nomic-embed-text-v1.5.

    Handles task prefix injection (search_document: / search_query:)
    required by the nomic model. Uses ONNX backend for CPU performance,
    falling back to PyTorch if ONNX is unavailable.
    """

    def __init__(self, config: SmartSearchConfig) -> None:
        """Initialize the embedder with the configured model.

        Args:
            config: SmartSearchConfig with model name and backend settings.
        """
        self._config = config
        self._model = self._load_model(config)

    def _load_model(self, config: SmartSearchConfig) -> SentenceTransformer:
        """Load SentenceTransformer with ONNX backend, PyTorch fallback.

        Args:
            config: Configuration with model name and backend preference.

        Returns:
            Loaded SentenceTransformer model.
        """
        try:
            return SentenceTransformer(
                config.embedding_model,
                backend=config.embedding_backend,
                trust_remote_code=True,
            )
        except Exception:
            # ONNX unavailable -- fall back to PyTorch
            return SentenceTransformer(
                config.embedding_model,
                trust_remote_code=True,
            )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for document chunks.

        Prepends 'search_document: ' prefix required by nomic-embed.

        Args:
            texts: List of document text strings to embed.

        Returns:
            List of embedding vectors (each 768-dim float list).
        """
        prefixed = [f"{self._config.nomic_document_prefix}{t}" for t in texts]
        embeddings = self._model.encode(prefixed, show_progress_bar=False)
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
        embeddings = self._model.encode(prefixed, show_progress_bar=False)
        return embeddings[0].tolist()

    def get_model_name(self) -> str:
        """Return the configured embedding model identifier.

        Returns:
            Model name string (e.g., 'nomic-ai/nomic-embed-text-v1.5').
        """
        return self._config.embedding_model
