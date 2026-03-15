# Tests for the curated model registry.

from smart_search.model_registry import (
    CURATED_MODELS,
    ModelInfo,
    get_model_info,
    get_prefix_pair,
    list_models,
)


class TestModelRegistry:
    """Tests for model lookup and listing."""

    def test_curated_models_not_empty(self):
        """Registry should contain at least one model."""
        assert len(CURATED_MODELS) >= 2

    def test_snowflake_is_default(self):
        """First model (highest quality) should be snowflake."""
        assert CURATED_MODELS[0].model_id == "Snowflake/snowflake-arctic-embed-m-v2.0"

    def test_get_model_info_found(self):
        """Should return ModelInfo for a known model."""
        info = get_model_info("Snowflake/snowflake-arctic-embed-m-v2.0")
        assert info is not None
        assert info.display_name == "Snowflake Arctic Embed M v2.0"
        assert info.size_mb == 297

    def test_get_model_info_not_found(self):
        """Should return None for an unknown model."""
        assert get_model_info("unknown/model") is None

    def test_list_models_returns_all(self):
        """list_models should return all curated models."""
        models = list_models()
        assert len(models) == len(CURATED_MODELS)


class TestPrefixPairs:
    """Tests for model-specific prefix lookup."""

    def test_snowflake_query_only_prefix(self):
        """Snowflake has no doc prefix, has query prefix."""
        doc, query = get_prefix_pair("Snowflake/snowflake-arctic-embed-m-v2.0")
        assert doc is None
        assert query is not None
        assert "searching relevant passages" in query

    def test_nomic_dual_prefix(self):
        """Nomic has both doc and query prefixes."""
        doc, query = get_prefix_pair("nomic-ai/nomic-embed-text-v1.5")
        assert doc == "search_document: "
        assert query == "search_query: "

    def test_unknown_model_falls_back(self):
        """Unknown models should get query-only fallback."""
        doc, query = get_prefix_pair("unknown/model")
        assert doc is None
        assert query is not None


class TestModelInfoFields:
    """Tests for ModelInfo dataclass properties."""

    def test_snowflake_mrl_dims(self):
        """Snowflake should support MRL dimensions."""
        info = get_model_info("Snowflake/snowflake-arctic-embed-m-v2.0")
        assert 256 in info.mrl_dims
        assert 768 in info.mrl_dims

    def test_nomic_mrl_dims(self):
        """Nomic should support more MRL dimensions."""
        info = get_model_info("nomic-ai/nomic-embed-text-v1.5")
        assert 256 in info.mrl_dims
        assert 384 in info.mrl_dims

    def test_modalities_default_text(self):
        """All current models should be text-only."""
        for model in CURATED_MODELS:
            assert "text" in model.modalities

    def test_model_info_is_frozen(self):
        """ModelInfo should be immutable."""
        info = get_model_info("Snowflake/snowflake-arctic-embed-m-v2.0")
        try:
            info.size_mb = 999
            assert False, "Should not allow mutation"
        except AttributeError:
            pass
