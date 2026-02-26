"""세그멘테이션 엔진 팩토리."""

from .base import SegmentationEngine
from .totalseg import TotalSegmentatorEngine
from .totalspineseg import TotalSpineSegEngine
from .nnunet_spine import SpineUnifiedEngine

# 등록된 엔진 목록
_ENGINES: dict[str, type[SegmentationEngine]] = {
    "totalseg": TotalSegmentatorEngine,
    "totalspineseg": TotalSpineSegEngine,
    "spine_unified": SpineUnifiedEngine,
}


def create_engine(name: str, **kwargs) -> SegmentationEngine:
    """세그멘테이션 엔진 생성.

    Args:
        name: 엔진 이름 ("totalseg" 또는 "totalspineseg")
        **kwargs: 엔진 생성자 인자

    Returns:
        SegmentationEngine 인스턴스

    Raises:
        ValueError: 알 수 없는 엔진 이름
        RuntimeError: 엔진 미설치
    """
    if name not in _ENGINES:
        available = ", ".join(_ENGINES.keys())
        raise ValueError(
            f"알 수 없는 세그멘테이션 엔진: '{name}'. "
            f"사용 가능: {available}"
        )

    engine = _ENGINES[name]()

    if not engine.is_available():
        hints = {
            "totalseg": "pip install TotalSegmentator 또는 uv pip install 'pysim[seg-ct]'",
            "totalspineseg": "pip install totalspineseg nnunetv2==2.6.2 또는 uv pip install 'pysim[seg-mri]'",
            "spine_unified": "uv pip install 'pysim[seg-unified]' + spine-sim download-model spine_unified",
        }
        raise RuntimeError(
            f"'{name}' 엔진이 설치되지 않았습니다.\n"
            f"설치 방법: {hints.get(name, '문서를 참조하세요')}"
        )

    return engine


def list_engines() -> list[dict[str, str | bool]]:
    """사용 가능한 엔진 목록 반환."""
    result = []
    for name, cls in _ENGINES.items():
        engine = cls()
        result.append({
            "name": name,
            "modalities": engine.supported_modalities,
            "available": engine.is_available(),
        })
    return result
