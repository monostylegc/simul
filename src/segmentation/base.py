"""세그멘테이션 엔진 추상 클래스."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class SegmentationEngine(ABC):
    """세그멘테이션 엔진 ABC.

    CT 또는 MRI 영상에서 척추 구조를 자동으로 분할한다.
    각 엔진은 고유한 라벨 체계를 가지며, get_standard_label_mapping()으로
    표준 SpineLabel 체계로의 매핑을 제공한다.
    """

    name: str = "base"
    supported_modalities: list[str] = []

    @abstractmethod
    def is_available(self) -> bool:
        """엔진 사용 가능 여부 확인 (라이브러리 설치 여부)."""
        ...

    @abstractmethod
    def segment(
        self,
        input_path: str | Path,
        output_path: str | Path,
        device: str = "gpu",
        fast: bool = False,
        roi_subset: Optional[list[str]] = None,
        modality: Optional[str] = None,
    ) -> Path:
        """세그멘테이션 실행.

        Args:
            input_path: 입력 NIfTI 파일 경로
            output_path: 출력 NIfTI 파일 경로
            device: 연산 장치 ("gpu" 또는 "cpu")
            fast: 빠른 모드 (저해상도)
            roi_subset: 관심 영역 부분집합
            modality: 입력 모달리티 ("CT" 또는 "MRI", None이면 자동 감지)

        Returns:
            출력 파일 경로
        """
        ...

    @abstractmethod
    def get_standard_label_mapping(self) -> dict[int, int]:
        """원본 라벨 → SpineLabel 표준 매핑 반환."""
        ...
