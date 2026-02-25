"""GPU 자동 감지 유틸리티.

CUDA/GPU 사용 가능 여부를 사전 탐지하여
세그멘테이션/해석에서 적절한 디바이스를 자동 선택한다.
"""

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# 캐싱: 최초 1회만 탐지
_cached_info: Optional["GpuInfo"] = None


@dataclass(frozen=True)
class GpuInfo:
    """GPU 정보."""
    available: bool
    name: str
    memory_mb: int
    cuda_version: str
    driver_version: str


def detect_gpu() -> GpuInfo:
    """GPU/CUDA 사용 가능 여부를 탐지한다.

    탐지 우선순위:
      1. PyTorch torch.cuda (가장 정확)
      2. nvidia-smi CLI (PyTorch 없어도 동작)

    Returns:
        GpuInfo 객체 (available=False 면 GPU 미사용)
    """
    global _cached_info
    if _cached_info is not None:
        return _cached_info

    # 방법 1: PyTorch로 탐지
    info = _detect_via_torch()
    if info is not None:
        _cached_info = info
        return info

    # 방법 2: nvidia-smi로 탐지
    info = _detect_via_nvidia_smi()
    if info is not None:
        _cached_info = info
        return info

    # GPU 없음
    _cached_info = GpuInfo(
        available=False, name="N/A", memory_mb=0,
        cuda_version="N/A", driver_version="N/A",
    )
    logger.info("GPU 감지 결과: 사용 불가 (CPU 모드)")
    return _cached_info


def _detect_via_torch() -> Optional[GpuInfo]:
    """PyTorch의 torch.cuda로 GPU 탐지."""
    try:
        import torch
        if not torch.cuda.is_available():
            return GpuInfo(
                available=False, name="N/A", memory_mb=0,
                cuda_version="N/A", driver_version="N/A",
            )

        name = torch.cuda.get_device_name(0)
        mem_bytes = torch.cuda.get_device_properties(0).total_mem
        mem_mb = mem_bytes // (1024 * 1024)
        cuda_ver = torch.version.cuda or "unknown"

        info = GpuInfo(
            available=True,
            name=name,
            memory_mb=mem_mb,
            cuda_version=cuda_ver,
            driver_version="",  # torch에서는 직접 확인 어려움
        )
        logger.info("GPU 감지 (PyTorch): %s (%d MB, CUDA %s)", name, mem_mb, cuda_ver)
        return info
    except Exception as e:
        logger.debug("PyTorch GPU 감지 실패: %s", e)
        return None


def _detect_via_nvidia_smi() -> Optional[GpuInfo]:
    """nvidia-smi CLI로 GPU 탐지 (PyTorch 미설치 환경 대응)."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None

        line = result.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            return None

        name = parts[0]
        mem_mb = int(float(parts[1]))
        driver_ver = parts[2]

        info = GpuInfo(
            available=True,
            name=name,
            memory_mb=mem_mb,
            cuda_version="",
            driver_version=driver_ver,
        )
        logger.info("GPU 감지 (nvidia-smi): %s (%d MB, 드라이버 %s)", name, mem_mb, driver_ver)
        return info
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug("nvidia-smi GPU 감지 실패: %s", e)
        return None


def resolve_device(requested: str = "gpu") -> str:
    """요청된 디바이스 → 실제 사용할 디바이스로 해석.

    "gpu" 요청 시 GPU가 없으면 자동으로 "cpu"로 폴백.
    "cpu" 요청 시 그대로 "cpu" 반환.

    Args:
        requested: 요청 디바이스 ("gpu" | "cpu")

    Returns:
        실제 사용할 디바이스 문자열 ("gpu" | "cpu")
    """
    if requested == "cpu":
        return "cpu"

    gpu_info = detect_gpu()
    if gpu_info.available:
        return "gpu"

    logger.warning("GPU 요청이지만 CUDA 사용 불가 → CPU 폴백")
    return "cpu"
