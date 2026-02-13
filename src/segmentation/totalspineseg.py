"""TotalSpineSeg 래퍼 — MRI 세그멘테이션.

TotalSpineSeg를 사용하여 MRI 영상에서 척추 구조를 분할한다.
설치: `pip install totalspineseg nnunetv2==2.6.2`
"""

import subprocess
from pathlib import Path
from typing import Optional

from .base import SegmentationEngine
from .labels import TOTALSPINESEG_TO_STANDARD


class TotalSpineSegEngine(SegmentationEngine):
    """TotalSpineSeg MRI 세그멘테이션 엔진."""

    name = "totalspineseg"
    supported_modalities = ["MRI"]

    def is_available(self) -> bool:
        """TotalSpineSeg CLI 사용 가능 여부 확인."""
        try:
            result = subprocess.run(
                ["totalspineseg", "--help"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
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
        """MRI 세그멘테이션 실행.

        Args:
            input_path: 입력 MRI NIfTI 경로
            output_path: 출력 디렉토리 또는 파일 경로
            device: "gpu" 또는 "cpu"
            fast: 사용하지 않음 (호환성 인자)
            roi_subset: 사용하지 않음

        Returns:
            최종 라벨맵 파일 경로
        """
        if not self.is_available():
            raise RuntimeError(
                "TotalSpineSeg가 설치되지 않았습니다.\n"
                "설치: pip install totalspineseg nnunetv2==2.6.2\n"
                "또는: uv pip install 'pysim[seg-mri]'"
            )

        input_path = Path(input_path)
        output_path = Path(output_path)

        # 출력이 파일이면 부모 디렉토리를 작업 디렉토리로 사용
        if output_path.suffix in (".nii", ".gz"):
            output_dir = output_path.parent
        else:
            output_dir = output_path

        output_dir.mkdir(parents=True, exist_ok=True)

        # TotalSpineSeg CLI 실행
        cmd = ["totalspineseg", str(input_path), str(output_dir)]
        if device == "cpu":
            cmd.extend(["--device", "cpu"])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"TotalSpineSeg 실행 실패:\n{result.stderr}"
            )

        # 최종 라벨맵 찾기 (step2_output/ 폴더)
        step2_dir = output_dir / "step2_output"
        if step2_dir.exists():
            nifti_files = list(step2_dir.glob("*.nii.gz"))
            if nifti_files:
                return nifti_files[0]

        # 폴백: 출력 디렉토리에서 찾기
        nifti_files = list(output_dir.glob("*.nii.gz"))
        if nifti_files:
            return nifti_files[0]

        raise FileNotFoundError(
            f"세그멘테이션 출력 파일을 찾을 수 없습니다: {output_dir}"
        )

    def get_standard_label_mapping(self) -> dict[int, int]:
        """TotalSpineSeg → SpineLabel 매핑."""
        return TOTALSPINESEG_TO_STANDARD.copy()
