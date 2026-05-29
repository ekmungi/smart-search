# Cloud embedding backend: OpenAI-compatible /v1/embeddings over stdlib urllib.

"""CloudEmbedder sends text to an OpenAI-compatible embeddings endpoint
(OpenRouter gateway by default). No model files are downloaded and no local
computation occurs. Uses only the Python standard library to avoid adding an
HTTP dependency to the build."""

import json
import urllib.request
from typing import List

from smart_search.config import SmartSearchConfig

# Request timeout for a single embeddings call (seconds).
_REQUEST_TIMEOUT = 60


class CloudEmbedder:
    """Embeds text via an OpenAI-compatible /v1/embeddings HTTP endpoint."""

    def __init__(self, config: SmartSearchConfig) -> None:
        """Initialize from config.

        Args:
            config: Must provide embedding_api_key and embedding_cloud_model.

        Raises:
            ValueError: If api key or model is missing.
        """
        self._base_url = config.embedding_api_base_url.rstrip("/")
        self._api_key = config.embedding_api_key
        self._model = config.embedding_cloud_model
        self._dimensions = config.embedding_dimensions
        if not self._api_key:
            raise ValueError("Cloud embedder requires embedding_api_key")
        if not self._model:
            raise ValueError("Cloud embedder requires embedding_cloud_model")

    @property
    def dimensions(self) -> int:
        """Output embedding dimension (matches the configured cloud model)."""
        return self._dimensions

    @property
    def backend_type(self) -> str:
        """Cloud backend identifier."""
        return "cloud"

    def _post(self, inputs: List[str]) -> List[List[float]]:
        """POST inputs to the embeddings endpoint and return ordered vectors."""
        payload = json.dumps({"model": self._model, "input": inputs}).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/embeddings",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        # OpenAI format: {"data": [{"index": i, "embedding": [...]}, ...]}
        ordered = sorted(body["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in ordered]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of document texts. Returns [] for empty input."""
        if not texts:
            return []
        return self._post(texts)

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query string."""
        return self._post([query])[0]

    def embed_image(self, image_path: str) -> List[float]:
        """Image embedding is not supported by the cloud text backend in F0a."""
        raise NotImplementedError("CloudEmbedder is text-only in F0a")

    def get_model_name(self) -> str:
        """Return the configured cloud model id."""
        return self._model
