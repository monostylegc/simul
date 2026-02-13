"""세그멘테이션 스테이지 — 자동 척추 분할."""

import time
from pathlib import Path
from typing import Callable, Optional

from .base import StageBase, StageResult


class SegmentStage(StageBase):
    """CT/MRI 자동 세그멘테이션 스테이지.

    TotalSegmentator(CT) 또는 TotalSpineSeg(MRI)를 사용하여
    입력 영상에서 척추 구조를 자동 분할한다.
    """

    name = "segment"

    def __init__(
        self,
        engine: str = "totalseg",
        device: str = "gpu",
        fast: bool = False,
        roi_subset: Optional[list[str]] = None,
    ):
        self.engine_name = engine
        self.device = device
        self.fast = fast
        self.roi_subset = roi_subset

    def validate_input(self, input_path: str | Path) -> bool:
        """NIfTI 파일 유효성 검증."""
        input_path = Path(input_path)
        if not input_path.exists():
            return False
        suffixes = "".join(input_path.suffixes).lower()
        return suffixes in (".nii", ".nii.gz", ".nrrd", ".mha")

    def run(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> StageResult:
        """세그멘테이션 실행.

        Args:
            input_path: 입력 NIfTI 파일
            output_dir: 출력 디렉토리
            progress_callback: 진행률 콜백

        Returns:
            StageResult (output_path = 라벨맵 NIfTI 경로)
        """
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not self.validate_input(input_path):
            return StageResult(
                success=False,
                output_path=output_dir,
                elapsed_time=0.0,
                message=f"입력 파일이 유효하지 않습니다: {input_path}",
            )

        if progress_callback:
            progress_callback("segment", {"message": f"{self.engine_name} 엔진으로 세그멘테이션 시작..."})

        start = time.time()

        try:
            from src.segmentation.factory import create_engine
            from src.segmentation.labels import convert_to_standard

            engine = create_engine(self.engine_name)
            raw_output = output_dir / "raw_labels.nii.gz"

            # 세그멘테이션 실행
            result_path = engine.segment(
                input_path=input_path,
                output_path=raw_output,
                device=self.device,
                fast=self.fast,
                roi_subset=self.roi_subset,
            )

            # 표준 라벨로 변환
            import nibabel as nib
            import numpy as np

            img = nib.load(str(result_path))
            raw_labels = np.asarray(img.dataobj, dtype=np.int32)

            mapping = engine.get_standard_label_mapping()
            standard_labels = convert_to_standard(raw_labels, mapping)

            # 표준 라벨 저장
            standard_output = output_dir / "labels.nii.gz"
            out_img = nib.Nifti1Image(standard_labels, img.affine, img.header)
            nib.save(out_img, str(standard_output))

            elapsed = time.time() - start

            if progress_callback:
                n_labels = len(np.unique(standard_labels)) - 1  # 배경 제외
                progress_callback("segment", {"message": f"완료: {n_labels}개 구조 검출 ({elapsed:.1f}초)"})

            return StageResult(
                success=True,
                output_path=standard_output,
                elapsed_time=elapsed,
                message=f"{n_labels}개 척추 구조 검출",
            )

        except Exception as e:
            elapsed = time.time() - start
            return StageResult(
                success=False,
                output_path=output_dir,
                elapsed_time=elapsed,
                message=f"세그멘테이션 실패: {e}",
            )
