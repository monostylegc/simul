"""TotalSegmentator 래퍼 — CT 세그멘테이션.

TotalSegmentator v2를 사용하여 CT 영상에서 척추 구조를 분할한다.
설치: `pip install TotalSegmentator` 또는 `uv pip install TotalSegmentator`
"""

from pathlib import Path
from typing import Optional

from .base import SegmentationEngine
from .labels import TOTALSEG_TO_STANDARD


class TotalSegmentatorEngine(SegmentationEngine):
    """TotalSegmentator CT 세그멘테이션 엔진."""

    name = "totalseg"
    supported_modalities = ["CT"]

    def is_available(self) -> bool:
        """TotalSegmentator 설치 여부 확인."""
        try:
            import totalsegmentator  # noqa: F401
            return True
        except ImportError:
            return False

    def segment(
        self,
        input_path: str | Path,
        output_path: str | Path,
        device: str = "gpu",
        fast: bool = False,
        roi_subset: Optional[list[str]] = None,
        modality: Optional[str] = None,
    ) -> Path:
        """CT 세그멘테이션 실행.

        Args:
            input_path: 입력 CT NIfTI 경로
            output_path: 출력 라벨맵 NIfTI 경로
            device: "gpu" 또는 "cpu"
            fast: True면 3mm 저해상도 (빠르지만 정확도 ↓)
            roi_subset: 관심 영역 (None이면 전체)

        Returns:
            출력 파일 경로
        """
        if not self.is_available():
            raise RuntimeError(
                "TotalSegmentator가 설치되지 않았습니다.\n"
                "설치: pip install TotalSegmentator\n"
                "또는: uv pip install 'pysim[seg-ct]'"
            )

        from totalsegmentator.python_api import totalsegmentator

        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        totalsegmentator(
            input=input_path,
            output=output_path,
            ml=True,  # 멀티라벨 출력
            fast=fast,
            device=device,
            roi_subset=roi_subset,
            task="total",
        )

        return output_path

    def get_standard_label_mapping(self) -> dict[int, int]:
        """TotalSegmentator → SpineLabel 매핑."""
        return TOTALSEG_TO_STANDARD.copy()
