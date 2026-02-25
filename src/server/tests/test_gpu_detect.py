"""GPU 자동 감지 유틸리티 테스트."""

import pytest
from unittest.mock import patch, MagicMock

from src.server.services.gpu_detect import (
    detect_gpu,
    resolve_device,
    GpuInfo,
    _detect_via_nvidia_smi,
    _detect_via_torch,
)


class TestGpuDetect:
    """GPU 감지 기본 동작 테스트."""

    def setup_method(self):
        """매 테스트마다 캐시 초기화."""
        import src.server.services.gpu_detect as mod
        mod._cached_info = None

    def test_detect_gpu_returns_gpuinfo(self):
        """detect_gpu()는 GpuInfo 인스턴스를 반환."""
        info = detect_gpu()
        assert isinstance(info, GpuInfo)
        assert isinstance(info.available, bool)
        assert isinstance(info.name, str)
        assert isinstance(info.memory_mb, int)

    def test_detect_gpu_caching(self):
        """두 번째 호출은 캐싱된 결과 반환."""
        info1 = detect_gpu()
        info2 = detect_gpu()
        assert info1 is info2

    def test_resolve_device_cpu(self):
        """CPU 요청은 항상 CPU 반환."""
        result = resolve_device("cpu")
        assert result == "cpu"

    def test_resolve_device_gpu_no_cuda(self):
        """GPU 요청이지만 CUDA 없으면 CPU 반환."""
        fake_info = GpuInfo(
            available=False, name="N/A", memory_mb=0,
            cuda_version="N/A", driver_version="N/A",
        )
        with patch("src.server.services.gpu_detect.detect_gpu", return_value=fake_info):
            result = resolve_device("gpu")
            assert result == "cpu"

    def test_resolve_device_gpu_with_cuda(self):
        """GPU 요청 + CUDA 사용 가능 → GPU 반환."""
        fake_info = GpuInfo(
            available=True, name="RTX 4090", memory_mb=24576,
            cuda_version="12.1", driver_version="535.0",
        )
        with patch("src.server.services.gpu_detect.detect_gpu", return_value=fake_info):
            result = resolve_device("gpu")
            assert result == "gpu"


class TestDetectViaTorch:
    """PyTorch 기반 감지 테스트 (mock)."""

    def setup_method(self):
        import src.server.services.gpu_detect as mod
        mod._cached_info = None

    def test_torch_cuda_available(self):
        """torch.cuda.is_available() = True일 때 GPU 감지."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.get_device_name.return_value = "NVIDIA RTX 4090"
        mock_props = MagicMock()
        mock_props.total_mem = 24 * 1024 * 1024 * 1024  # 24GB
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.version.cuda = "12.1"

        with patch.dict("sys.modules", {"torch": mock_torch}):
            info = _detect_via_torch()
            assert info is not None
            assert info.available is True
            assert "RTX 4090" in info.name

    def test_torch_cuda_not_available(self):
        """torch.cuda.is_available() = False일 때."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        with patch.dict("sys.modules", {"torch": mock_torch}):
            info = _detect_via_torch()
            assert info is not None
            assert info.available is False

    def test_torch_import_error(self):
        """PyTorch 미설치 시 None 반환."""
        with patch("builtins.__import__", side_effect=ImportError("No module named 'torch'")):
            info = _detect_via_torch()
            # ImportError → None 또는 available=False
            # _detect_via_torch는 except Exception에서 None 반환
            assert info is None


class TestDetectViaNvidiaSmi:
    """nvidia-smi CLI 기반 감지 테스트 (mock)."""

    def setup_method(self):
        import src.server.services.gpu_detect as mod
        mod._cached_info = None

    def test_nvidia_smi_success(self):
        """nvidia-smi 성공 시 GPU 정보 파싱."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "NVIDIA GeForce RTX 4090, 24564, 535.129.03\n"

        with patch("subprocess.run", return_value=mock_result):
            info = _detect_via_nvidia_smi()
            assert info is not None
            assert info.available is True
            assert "RTX 4090" in info.name
            assert info.memory_mb == 24564

    def test_nvidia_smi_not_found(self):
        """nvidia-smi 미설치 시 None 반환."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            info = _detect_via_nvidia_smi()
            assert info is None

    def test_nvidia_smi_failure(self):
        """nvidia-smi 실행 실패 시 None 반환."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            info = _detect_via_nvidia_smi()
            assert info is None


class TestGpuInfoApi:
    """REST API /api/gpu-info 테스트."""

    def test_gpu_info_endpoint(self):
        """FastAPI gpu-info 엔드포인트 테스트."""
        from fastapi.testclient import TestClient
        from src.server.app import app

        client = TestClient(app)
        resp = client.get("/api/gpu-info")
        assert resp.status_code == 200
        data = resp.json()
        assert "available" in data
        assert "name" in data
        assert "memory_mb" in data
        assert isinstance(data["available"], bool)
