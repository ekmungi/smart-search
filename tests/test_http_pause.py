# Tests for pause/resume and enhanced model status HTTP endpoints.
from smart_search.http_models import (
    PauseResponse,
    ModelStatusResponse,
    IndexingStatusResponse,
)


def test_pause_response_model():
    """PauseResponse should have paused field."""
    r = PauseResponse(paused=True)
    assert r.paused is True


def test_pause_response_model_false():
    """PauseResponse paused=False should work for resume."""
    r = PauseResponse(paused=False)
    assert r.paused is False


def test_model_status_response_has_download_fields():
    """ModelStatusResponse should include download_status, download_url, cache_path."""
    r = ModelStatusResponse(
        cached=True,
        model_name="test/model",
        gpu_info={"type": "cpu", "name": "CPU"},
        download_status="cached",
        download_url="https://huggingface.co/test/model",
        cache_path="/cache/path",
    )
    assert r.download_status == "cached"
    assert r.download_url == "https://huggingface.co/test/model"
    assert r.cache_path == "/cache/path"


def test_indexing_status_response_has_paused_and_model_ready():
    """IndexingStatusResponse should include paused and model_ready."""
    r = IndexingStatusResponse(
        active=0,
        paused=True,
        model_ready=False,
        tasks=[],
    )
    assert r.paused is True
    assert r.model_ready is False


def test_model_status_response_defaults():
    """ModelStatusResponse should have sensible defaults for new fields."""
    r = ModelStatusResponse(
        cached=False,
        model_name="test/model",
        gpu_info={"type": "cpu", "name": "CPU"},
    )
    assert r.download_status == "idle"
    assert r.download_url == ""
    assert r.cache_path == ""


def test_indexing_status_response_defaults():
    """IndexingStatusResponse paused and model_ready should default to False/True."""
    r = IndexingStatusResponse(active=0, tasks=[])
    assert r.paused is False
    assert r.model_ready is True
