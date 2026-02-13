"""라벨맵 후처리 스테이지 — 형태학적 정리."""

import time
from pathlib import Path
from typing import Callable, Optional

from .base import StageBase, StageResult


class PostprocessStage(StageBase):
    """라벨맵 후처리 스테이지.

    형태학적 연산으로 라벨맵을 정리한다:
    - 작은 구성요소 제거 (min_volume_mm3 미만)
    - 구멍 채우기 (fill_holes)
    - 가우시안 스무딩 (smooth_sigma)
    """

    name = "postprocess"

    def __init__(
        self,
        min_volume_mm3: float = 100.0,
        fill_holes: bool = True,
        smooth_sigma: float = 0.5,
    ):
        self.min_volume_mm3 = min_volume_mm3
        self.fill_holes = fill_holes
        self.smooth_sigma = smooth_sigma

    def validate_input(self, input_path: str | Path) -> bool:
        """NIfTI 라벨맵 유효성 검증."""
        input_path = Path(input_path)
        if not input_path.exists():
            return False
        suffixes = "".join(input_path.suffixes).lower()
        return suffixes in (".nii", ".nii.gz")

    def run(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> StageResult:
        """후처리 실행."""
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
            progress_callback("postprocess", {"message": "라벨맵 후처리 시작..."})

        start = time.time()

        try:
            import SimpleITK as sitk
            import numpy as np

            # 라벨맵 로드
            image = sitk.ReadImage(str(input_path))
            spacing = image.GetSpacing()
            voxel_volume_mm3 = spacing[0] * spacing[1] * spacing[2]

            labels_arr = sitk.GetArrayFromImage(image)
            unique_labels = np.unique(labels_arr)
            unique_labels = unique_labels[unique_labels != 0]  # 배경 제외

            processed = np.zeros_like(labels_arr)

            for label_val in unique_labels:
                mask = (labels_arr == label_val).astype(np.uint8)
                mask_sitk = sitk.GetImageFromArray(mask)
                mask_sitk.CopyInformation(image)

                # 작은 구성요소 제거
                cc = sitk.ConnectedComponent(mask_sitk)
                stats = sitk.LabelShapeStatisticsImageFilter()
                stats.Execute(cc)

                cc_arr = sitk.GetArrayFromImage(cc)
                filtered_mask = np.zeros_like(mask)

                for cc_label in stats.GetLabels():
                    n_pixels = stats.GetNumberOfPixels(cc_label)
                    volume_mm3 = n_pixels * voxel_volume_mm3
                    if volume_mm3 >= self.min_volume_mm3:
                        filtered_mask[cc_arr == cc_label] = 1

                # 구멍 채우기
                if self.fill_holes and np.any(filtered_mask):
                    filled_sitk = sitk.GetImageFromArray(filtered_mask.astype(np.uint8))
                    filled_sitk.CopyInformation(image)
                    filled_sitk = sitk.BinaryFillhole(filled_sitk)
                    filtered_mask = sitk.GetArrayFromImage(filled_sitk)

                # 가우시안 스무딩 후 이진화
                if self.smooth_sigma > 0 and np.any(filtered_mask):
                    smooth_sitk = sitk.GetImageFromArray(filtered_mask.astype(np.float32))
                    smooth_sitk.CopyInformation(image)
                    smooth_sitk = sitk.SmoothingRecursiveGaussian(smooth_sitk, self.smooth_sigma)
                    smooth_arr = sitk.GetArrayFromImage(smooth_sitk)
                    filtered_mask = (smooth_arr > 0.5).astype(np.uint8)

                processed[filtered_mask > 0] = label_val

            # 저장
            output_path = output_dir / "labels_processed.nii.gz"
            out_image = sitk.GetImageFromArray(processed.astype(np.int32))
            out_image.CopyInformation(image)
            sitk.WriteImage(out_image, str(output_path))

            elapsed = time.time() - start
            n_labels = len(unique_labels)
            n_out = len(np.unique(processed)) - 1

            if progress_callback:
                progress_callback("postprocess", {
                    "message": f"완료: {n_labels} → {n_out}개 라벨 ({elapsed:.1f}초)"
                })

            return StageResult(
                success=True,
                output_path=output_path,
                elapsed_time=elapsed,
                message=f"{n_labels} → {n_out}개 라벨 후처리 완료",
            )

        except Exception as e:
            elapsed = time.time() - start
            return StageResult(
                success=False,
                output_path=output_dir,
                elapsed_time=elapsed,
                message=f"후처리 실패: {e}",
            )
