# Cross-encoder reranker for search quality improvement.

"""Reranks search results using a cross-encoder model that jointly scores
(query, document) pairs. Uses the same lazy-load + idle-unload pattern
as embedder.py. Model: cross-encoder/ms-marco-TinyBERT-L-2-v2 (~15MB ONNX).

The cross-encoder sees query and document text together, enabling richer
relevance judgments than independent bi-encoder embeddings."""

import gc
import logging
import threading
import time
from pathlib import Path
from typing import List, Optional

import numpy as np

from smart_search.config import SmartSearchConfig
from smart_search.models import SearchResult

logger = logging.getLogger(__name__)

# Maximum tokens per (query, document) pair for the cross-encoder.
_MAX_TOKEN_LENGTH = 512


class Reranker:
    """Cross-encoder reranker with lazy ONNX loading and idle auto-unload.

    Mirrors the Embedder lifecycle: loads on first rerank() call,
    unloads after configurable idle timeout to minimize RAM usage.
    Thread-safe via double-checked locking.
    """

    def __init__(self, config: SmartSearchConfig) -> None:
        """Initialize the reranker -- does NOT load the model yet.

        Args:
            config: SmartSearchConfig with reranker settings.
        """
        self._config = config
        self._enabled = config.reranking_enabled
        self._model_name = config.reranker_model
        self._idle_timeout = config.reranker_idle_timeout
        self._top_n = config.rerank_top_n

        # Tokenizer state -- loaded once, stays resident (cheap: ~5MB)
        self._tokenizer = None
        self._tokenizer_loaded = False

        # ONNX session state -- lazy-loads and idle-unloads
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

    def rerank(
        self, query: str, results: List[SearchResult], limit: int = 0
    ) -> List[SearchResult]:
        """Rerank search results using cross-encoder scoring.

        When disabled or given empty results, passes through unchanged.
        Reranks the top rerank_top_n results, appends remaining results
        after the reranked set.

        Args:
            query: The search query string.
            results: Pre-ranked search results from fusion stage.
            limit: Max results to return (0 = return all).

        Returns:
            Re-ordered SearchResult list with updated ranks and scores.
        """
        if not self._enabled or not results:
            return results

        # Split into rerank candidates and tail (passed through)
        candidates = results[: self._top_n]
        tail = results[self._top_n :]

        self._ensure_loaded()

        # Score each (query, chunk_text) pair
        scores = self._score_pairs(
            query, [r.chunk.text for r in candidates]
        )

        # Normalize scores to 0-1 range
        normalized = self._normalize_scores(scores)

        # Sort candidates by cross-encoder score descending
        scored_pairs = list(zip(candidates, normalized))
        scored_pairs.sort(key=lambda pair: pair[1], reverse=True)

        # Rebuild SearchResults with updated ranks and scores
        reranked: List[SearchResult] = []
        for rank_idx, (result, norm_score) in enumerate(scored_pairs, start=1):
            reranked.append(
                SearchResult(
                    rank=rank_idx,
                    score=round(norm_score, 6),
                    chunk=result.chunk,
                )
            )

        # Append tail results with continued ranks
        next_rank = len(reranked) + 1
        for result in tail:
            reranked.append(
                SearchResult(
                    rank=next_rank,
                    score=result.score,
                    chunk=result.chunk,
                )
            )
            next_rank += 1

        if limit > 0:
            return reranked[:limit]
        return reranked

    def _score_pairs(self, query: str, texts: List[str]) -> List[float]:
        """Score (query, text) pairs using the cross-encoder.

        Args:
            query: Search query.
            texts: Document texts to score against the query.

        Returns:
            List of raw logit scores (higher = more relevant).
        """
        if not texts:
            return []

        # Tokenize as sentence pairs: (query, text) for each candidate
        pairs = [(query, text) for text in texts]
        encoded_batch = self._tokenizer.encode_batch(pairs)

        input_ids = np.array(
            [e.ids for e in encoded_batch], dtype=np.int64
        )
        attention_mask = np.array(
            [e.attention_mask for e in encoded_batch], dtype=np.int64
        )

        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}

        # Add token_type_ids if the model expects them (BERT-family)
        input_names = {inp.name for inp in self._session.get_inputs()}
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.array(
                [e.type_ids for e in encoded_batch], dtype=np.int64
            )

        outputs = self._session.run(None, feeds)

        # Cross-encoder output: (batch, 1) logit -- squeeze to flat list
        logits = outputs[0].squeeze(-1) if outputs[0].ndim > 1 else outputs[0]

        self._reset_idle_timer()
        return logits.tolist()

    @staticmethod
    def _normalize_scores(scores: List[float]) -> List[float]:
        """Normalize raw logit scores to 0-1 range via min-max scaling.

        Args:
            scores: Raw cross-encoder logit scores.

        Returns:
            Scores scaled to [0, 1] where max = 1.0.
        """
        if not scores:
            return []
        if len(scores) == 1:
            return [1.0]

        min_s = min(scores)
        max_s = max(scores)
        span = max_s - min_s

        if span == 0:
            return [1.0] * len(scores)

        return [(s - min_s) / span for s in scores]

    def _ensure_loaded(self) -> None:
        """Load tokenizer and ONNX session if not loaded. Thread-safe.

        Uses double-checked locking to avoid redundant loads.
        """
        if not self._tokenizer_loaded:
            with self._lock:
                if not self._tokenizer_loaded:
                    self._tokenizer = self._load_tokenizer()
                    self._tokenizer_loaded = True
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._session = self._load_session()
            self._loaded = True
            logger.info("Cross-encoder reranker loaded: %s", self._model_name)

    def unload(self) -> None:
        """Unload ONNX session to free RAM. Tokenizer stays resident.

        Thread-safe. gc.collect() forces C++ buffers back to OS.
        """
        with self._lock:
            self._session = None
            self._loaded = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        gc.collect()
        logger.info("Cross-encoder reranker unloaded")

    def _reset_idle_timer(self) -> None:
        """Reset the idle unload timer after each use."""
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

    def _get_model_path(self) -> Path:
        """Download the cross-encoder model if needed, return local path.

        Returns:
            Path to local model directory.
        """
        from huggingface_hub import snapshot_download

        model_dir = snapshot_download(
            self._model_name,
            ignore_patterns=["*.bin", "*.pt", "*.safetensors", "*.msgpack"],
        )
        return Path(model_dir)

    def _load_tokenizer(self):
        """Load the standalone tokenizer for the cross-encoder.

        Returns:
            tokenizers.Tokenizer configured for sentence pairs.
        """
        from tokenizers import Tokenizer

        model_path = self._get_model_path()
        tokenizer_path = model_path / "tokenizer.json"

        if not tokenizer_path.exists():
            raise FileNotFoundError(
                f"No tokenizer.json in {model_path}. "
                "Model download may be incomplete."
            )

        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        tokenizer.enable_truncation(max_length=_MAX_TOKEN_LENGTH)
        return tokenizer

    def _load_session(self):
        """Load the ONNX inference session with memory-optimized settings.

        Prefers quantized ONNX when available. Mirrors embedder.py settings.

        Returns:
            onnxruntime.InferenceSession for the cross-encoder.
        """
        import onnxruntime as ort

        model_path = self._get_model_path()

        # Prefer quantized, fall back to fp32
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
        sess_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        sess_options.enable_cpu_mem_arena = False
        sess_options.enable_mem_pattern = True
        sess_options.intra_op_num_threads = 2
        sess_options.inter_op_num_threads = 1
        sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        return ort.InferenceSession(
            str(onnx_path),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )
