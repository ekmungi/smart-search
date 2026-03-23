# Query preprocessing for FTS5 keyword search and embedding pipelines.

"""Splits query preprocessing into two paths: one for FTS5 (stopword
removal, term sanitization) and one for embeddings (light cleanup only).
No external dependencies -- stopword list is hardcoded."""

import re
from typing import FrozenSet

# Common English stopwords -- kept small to avoid removing meaningful terms.
# Based on a subset of NLTK's English stopwords, excluding words that may
# carry meaning in technical/knowledge search contexts.
_STOPWORDS: FrozenSet[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "is", "am", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "shall", "can",
    "not", "no", "nor", "so", "as", "it", "its", "this", "that", "these",
    "those", "i", "me", "my", "we", "our", "you", "your", "he", "she",
    "him", "her", "his", "they", "them", "their", "what", "which", "who",
    "whom", "how", "when", "where", "why", "just", "about", "into", "than",
    "then", "there", "here", "very", "too", "also",
})

_MULTI_SPACE_RE = re.compile(r"\s+")


def preprocess_for_fts(query: str) -> str:
    """Preprocess a query for FTS5 keyword search.

    Removes common stopwords to sharpen BM25 scoring. Preserves
    user-supplied quoted phrases unchanged. Falls back to the original
    query if stopword removal would leave nothing.

    Args:
        query: Raw user search query.

    Returns:
        Cleaned query string with stopwords removed, or empty string
        if the input is blank.
    """
    stripped = query.strip()
    if not stripped:
        return ""

    # User-supplied quoted phrase: pass through unchanged
    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) > 2:
        return stripped

    terms = stripped.split()
    filtered = [t for t in terms if t.lower() not in _STOPWORDS]

    # Fall back to original terms if all were stopwords
    if not filtered:
        return " ".join(terms)

    return " ".join(filtered)


def preprocess_for_embedding(query: str) -> str:
    """Preprocess a query for the embedding model.

    Light cleanup only -- the embedding model's tokenizer handles
    stopwords and context. Does NOT remove stopwords, as they carry
    semantic meaning for dense retrieval.

    Args:
        query: Raw user search query.

    Returns:
        Whitespace-normalized query string, or empty string if blank.
    """
    stripped = query.strip()
    if not stripped:
        return ""

    return _MULTI_SPACE_RE.sub(" ", stripped)
