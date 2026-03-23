# Tests for GPU provider detection and provider chain builder.

"""Unit tests for gpu_provider module -- ONNX Runtime provider detection,
provider chain construction, and device info retrieval."""

from unittest.mock import patch

import pytest

from smart_search.gpu_provider import build_provider_chain, detect_gpu, get_device_info


class TestDetectGpu:
    """Tests for GPU availability detection."""

    @patch("smart_search.gpu_provider._get_available_providers")
    def test_detects_cuda(self, mock_providers):
        """Returns 'cuda' when CUDAExecutionProvider is available."""
        mock_providers.return_value = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        result = detect_gpu()
        assert result == "cuda"

    @patch("smart_search.gpu_provider._get_available_providers")
    def test_detects_directml(self, mock_providers):
        """Returns 'directml' when DmlExecutionProvider is available."""
        mock_providers.return_value = ["DmlExecutionProvider", "CPUExecutionProvider"]
        result = detect_gpu()
        assert result == "directml"

    @patch("smart_search.gpu_provider._get_available_providers")
    def test_prefers_cuda_over_directml(self, mock_providers):
        """CUDA takes priority over DirectML when both are available."""
        mock_providers.return_value = [
            "CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"
        ]
        result = detect_gpu()
        assert result == "cuda"

    @patch("smart_search.gpu_provider._get_available_providers")
    def test_returns_none_when_cpu_only(self, mock_providers):
        """Returns None when only CPU is available."""
        mock_providers.return_value = ["CPUExecutionProvider"]
        result = detect_gpu()
        assert result is None


class TestBuildProviderChain:
    """Tests for ONNX provider chain construction."""

    @patch("smart_search.gpu_provider._get_available_providers")
    def test_auto_with_cuda(self, mock_providers):
        """Auto backend with CUDA builds chain starting with CUDA provider."""
        mock_providers.return_value = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        chain = build_provider_chain(backend="auto")
        first = chain[0]
        assert isinstance(first, tuple)
        assert first[0] == "CUDAExecutionProvider"
        assert first[1]["device_id"] == 0
        assert chain[-1] == "CPUExecutionProvider"

    @patch("smart_search.gpu_provider._get_available_providers")
    def test_auto_with_directml(self, mock_providers):
        """Auto backend with DirectML builds chain starting with DML provider."""
        mock_providers.return_value = ["DmlExecutionProvider", "CPUExecutionProvider"]
        chain = build_provider_chain(backend="auto")
        first = chain[0]
        assert isinstance(first, tuple)
        assert first[0] == "DmlExecutionProvider"
        assert chain[-1] == "CPUExecutionProvider"

    @patch("smart_search.gpu_provider._get_available_providers")
    def test_auto_cpu_only(self, mock_providers):
        """Auto backend with no GPU returns CPU only."""
        mock_providers.return_value = ["CPUExecutionProvider"]
        chain = build_provider_chain(backend="auto")
        assert chain == ["CPUExecutionProvider"]

    @patch("smart_search.gpu_provider._get_available_providers")
    def test_local_uses_gpu_if_available(self, mock_providers):
        """Local backend uses GPU if available."""
        mock_providers.return_value = ["DmlExecutionProvider", "CPUExecutionProvider"]
        chain = build_provider_chain(backend="local")
        provider_names = [c if isinstance(c, str) else c[0] for c in chain]
        assert "DmlExecutionProvider" in provider_names

    def test_cloud_returns_empty(self):
        """Cloud backend returns empty chain (no ONNX session needed)."""
        chain = build_provider_chain(backend="cloud")
        assert chain == []

    @patch("smart_search.gpu_provider._get_available_providers")
    def test_unknown_backend_falls_through_to_auto(self, mock_providers):
        """Unknown backend values (e.g. stale 'onnx') behave like auto."""
        mock_providers.return_value = ["CPUExecutionProvider"]
        chain = build_provider_chain(backend="onnx")
        assert chain == ["CPUExecutionProvider"]

    @patch("smart_search.gpu_provider._get_available_providers")
    def test_custom_device_id(self, mock_providers):
        """Device ID is passed through to provider options."""
        mock_providers.return_value = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        chain = build_provider_chain(backend="auto", device_id=1)
        first = chain[0]
        assert first[1]["device_id"] == 1

    @patch("smart_search.gpu_provider._get_available_providers")
    def test_cuda_mem_limit(self, mock_providers):
        """CUDA provider gets gpu_mem_limit in bytes."""
        mock_providers.return_value = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        chain = build_provider_chain(backend="auto", gpu_mem_limit_mb=4096)
        first = chain[0]
        assert first[1]["gpu_mem_limit"] == 4096 * 1024 * 1024


class TestGetDeviceInfo:
    """Tests for GPU device info retrieval."""

    @patch("smart_search.gpu_provider.detect_gpu")
    def test_returns_cpu_when_no_gpu(self, mock_detect):
        """Returns CPU info when no GPU detected."""
        mock_detect.return_value = None
        info = get_device_info()
        assert info["type"] == "cpu"
        assert info["name"] == "CPU"

    @patch("smart_search.gpu_provider.detect_gpu")
    def test_returns_gpu_type(self, mock_detect):
        """Returns GPU type when detected."""
        mock_detect.return_value = "directml"
        info = get_device_info()
        assert info["type"] == "directml"
        assert info["name"] == "DirectML GPU"
