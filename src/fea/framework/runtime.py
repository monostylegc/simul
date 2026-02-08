"""Taichi 런타임 초기화 중앙 관리.

GPU 자동 감지(Vulkan → CPU 폴백), 정밀도 설정, 프로세스당 1회 초기화를 보장한다.
"""

import enum
import taichi as ti
from typing import Optional


class Backend(enum.Enum):
    """Taichi 백엔드 열거형."""
    CPU = "cpu"
    VULKAN = "vulkan"
    CUDA = "cuda"
    AUTO = "auto"


class Precision(enum.Enum):
    """부동소수점 정밀도 열거형."""
    F32 = "f32"
    F64 = "f64"


# 모듈 전역 상태
_initialized = False
_active_backend: Optional[Backend] = None
_active_precision: Optional[Precision] = None


def init(backend: Backend = Backend.AUTO, precision: Precision = Precision.F64) -> dict:
    """Taichi 런타임 초기화.

    프로세스당 1회만 실행된다. 중복 호출 시 기존 설정을 반환한다.

    Args:
        backend: 사용할 백엔드 (AUTO면 Vulkan → CPU 폴백)
        precision: 부동소수점 정밀도

    Returns:
        초기화 정보 딕셔너리
    """
    global _initialized, _active_backend, _active_precision

    if _initialized:
        return {
            "backend": _active_backend.value,
            "precision": _active_precision.value,
            "already_initialized": True,
        }

    ti_precision = ti.f64 if precision == Precision.F64 else ti.f32
    _active_precision = precision

    if backend == Backend.AUTO:
        # Vulkan 시도 → CPU 폴백
        for try_backend in [Backend.VULKAN, Backend.CPU]:
            try:
                arch = _backend_to_arch(try_backend)
                ti.init(arch=arch, default_fp=ti_precision)
                _active_backend = try_backend
                _initialized = True
                return {
                    "backend": _active_backend.value,
                    "precision": _active_precision.value,
                    "already_initialized": False,
                }
            except Exception:
                continue
        # 모든 시도 실패 시 CPU로 강제
        ti.init(arch=ti.cpu, default_fp=ti_precision)
        _active_backend = Backend.CPU
    else:
        arch = _backend_to_arch(backend)
        ti.init(arch=arch, default_fp=ti_precision)
        _active_backend = backend

    _initialized = True
    return {
        "backend": _active_backend.value,
        "precision": _active_precision.value,
        "already_initialized": False,
    }


def get_ti_dtype():
    """현재 설정된 Taichi 부동소수점 타입 반환."""
    if _active_precision == Precision.F32:
        return ti.f32
    return ti.f64


def get_backend() -> Optional[Backend]:
    """현재 활성 백엔드 반환."""
    return _active_backend


def get_precision() -> Optional[Precision]:
    """현재 활성 정밀도 반환."""
    return _active_precision


def is_initialized() -> bool:
    """초기화 여부 반환."""
    return _initialized


def reset():
    """테스트용: 전역 상태 리셋 (실제 ti.init은 되돌릴 수 없음)."""
    global _initialized, _active_backend, _active_precision
    _initialized = False
    _active_backend = None
    _active_precision = None


def _backend_to_arch(backend: Backend):
    """Backend enum → Taichi arch 변환."""
    mapping = {
        Backend.CPU: ti.cpu,
        Backend.VULKAN: ti.vulkan,
        Backend.CUDA: ti.cuda,
    }
    return mapping[backend]
