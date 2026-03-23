# Tests for query preprocessing (stopword removal, FTS5/embedding paths).

"""Unit tests for query_preprocessor module -- stopword removal for FTS5,
quoted phrase preservation, and embedding-path preprocessing."""

import pytest

from smart_search.query_preprocessor import preprocess_for_embedding, preprocess_for_fts


class TestPreprocessForFts:
    """Tests for FTS5 query preprocessing."""

    def test_removes_common_stopwords(self):
        """Common English stopwords are removed from multi-term queries."""
        result = preprocess_for_fts("what is the best approach for testing")
        assert "what" not in result.lower()
        assert "is" not in result.lower()
        assert "the" not in result.lower()
        assert "for" not in result.lower()
        assert "best" in result.lower()
        assert "approach" in result.lower()
        assert "testing" in result.lower()

    def test_preserves_quoted_phrases(self):
        """User-supplied quoted phrases are passed through unchanged."""
        result = preprocess_for_fts('"machine learning"')
        assert "machine" in result.lower()
        assert "learning" in result.lower()

    def test_single_meaningful_word_not_removed(self):
        """A single non-stopword term is preserved."""
        result = preprocess_for_fts("Python")
        assert "python" in result.lower()

    def test_all_stopwords_falls_back_to_original(self):
        """If removing stopwords leaves nothing, return original terms."""
        result = preprocess_for_fts("is the a")
        # Should not return empty -- fall back to original query terms
        assert len(result.strip()) > 0

    def test_preserves_technical_terms(self):
        """Technical terms, acronyms, and domain words are not removed."""
        result = preprocess_for_fts("FHIR API endpoint authentication")
        assert "fhir" in result.lower()
        assert "api" in result.lower()
        assert "endpoint" in result.lower()
        assert "authentication" in result.lower()

    def test_empty_query_returns_empty(self):
        """Empty or whitespace query returns empty string."""
        assert preprocess_for_fts("") == ""
        assert preprocess_for_fts("   ") == ""

    def test_mixed_stopwords_and_content(self):
        """Stopwords removed, content words kept from mixed query."""
        result = preprocess_for_fts("how do I configure the search engine")
        assert "how" not in result.lower()
        assert "do" not in result.lower()
        assert "configure" in result.lower()
        assert "search" in result.lower()
        assert "engine" in result.lower()

    def test_case_insensitive_stopword_removal(self):
        """Stopwords are removed regardless of case."""
        result = preprocess_for_fts("The BEST Way To Do It")
        assert "the" not in result.lower().split()
        assert "to" not in result.lower().split()
        assert "do" not in result.lower().split()
        assert "it" not in result.lower().split()
        assert "best" in result.lower()
        assert "way" in result.lower()


class TestPreprocessForEmbedding:
    """Tests for embedding query preprocessing."""

    def test_strips_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        result = preprocess_for_embedding("  hello world  ")
        assert result == "hello world"

    def test_preserves_query_content(self):
        """Query content is preserved for the embedding model."""
        query = "what is the best approach for testing"
        result = preprocess_for_embedding(query)
        # Embedding preprocessing should NOT remove stopwords
        # (the embedding model handles context words)
        assert "what" in result
        assert "best" in result
        assert "testing" in result

    def test_empty_query_returns_empty(self):
        """Empty query returns empty string."""
        assert preprocess_for_embedding("") == ""
        assert preprocess_for_embedding("   ") == ""

    def test_normalizes_internal_whitespace(self):
        """Multiple internal spaces collapsed to single space."""
        result = preprocess_for_embedding("hello    world")
        assert result == "hello world"
