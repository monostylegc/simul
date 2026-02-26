"""TotalSpineSeg 래퍼 — CT/MRI 척추 세그멘테이션.

TotalSpineSeg를 사용하여 CT/MRI 영상에서 척추골+디스크+척수+척추관을 분할한다.
GPU(CUDA) 자동 활용, 모델 자동 다운로드.
설치: `pip install totalspineseg`
"""

import logging
import sys
import subprocess
from pathlib import Path
from typing import Optional

from .base import SegmentationEngine
from .labels import TOTALSPINESEG_TO_STANDARD

logger = logging.getLogger(__name__)


class TotalSpineSegEngine(SegmentationEngine):
    """TotalSpineSeg CT/MRI 통합 세그멘테이션 엔진.

    척추골(C1~S), 디스크(C2C3~L5S1), 척수, 척추관을 세그멘테이션한다.
    """

    name = "totalspineseg"
    supported_modalities = ["CT", "MRI"]

    def is_available(self) -> bool:
        """TotalSpineSeg 모듈 사용 가능 여부 확인."""
        try:
            import totalspineseg  # noqa: F401
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
        """CT/MRI 세그멘테이션 실행.

        Args:
            input_path: 입력 NIfTI 경로 (CT 또는 MRI)
            output_path: 출력 디렉토리 또는 파일 경로
            device: "gpu"/"cuda" 또는 "cpu"
            fast: True면 step1만 (빠르지만 정밀도↓)
            roi_subset: 사용하지 않음
            modality: 사용하지 않음 (자동 감지)

        Returns:
            최종 라벨맵 파일 경로
        """
        if not self.is_available():
            raise RuntimeError(
                "TotalSpineSeg가 설치되지 않았습니다.\n"
                "설치: pip install totalspineseg"
            )

        input_path = Path(input_path)
        output_path = Path(output_path)

        # 출력이 파일이면 부모 디렉토리를 작업 디렉토리로 사용
        if output_path.suffix in (".nii", ".gz"):
            output_dir = output_path.parent
        else:
            output_dir = output_path

        output_dir.mkdir(parents=True, exist_ok=True)

        # 장치 변환: gpu → cuda
        cuda_device = "cuda" if device in ("gpu", "cuda") else "cpu"

        # venv 내 totalspineseg 스크립트 경로 탐색
        venv_dir = Path(sys.executable).parent
        tss_script = venv_dir / "totalspineseg"
        if not tss_script.exists():
            tss_script = venv_dir / "totalspineseg.exe"

        if tss_script.exists():
            cmd = [str(tss_script)]
        else:
            # 폴백: PATH에서 찾기
            cmd = ["totalspineseg"]

        cmd.extend([
            str(input_path), str(output_dir),
            "--device", cuda_device,
        ])
        if fast:
            cmd.append("--step1")

        logger.info("TotalSpineSeg 실행: %s (device=%s)", input_path.name, cuda_device)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1시간 제한
        )

        if result.returncode != 0:
            stderr = result.stderr[-1000:] if result.stderr else ""
            raise RuntimeError(
                f"TotalSpineSeg 실행 실패 (code {result.returncode}):\n{stderr}"
            )

        # 최종 라벨맵 찾기 (step2_output/ 폴더 → step1_output/ 폴백)
        for subdir in ["step2_output", "step1_output"]:
            step_dir = output_dir / subdir
            if step_dir.exists():
                nifti_files = list(step_dir.glob("*.nii.gz"))
                if nifti_files:
                    logger.info("세그멘테이션 완료: %s", nifti_files[0])
                    return nifti_files[0]

        # 폴백: 출력 디렉토리 직접 탐색
        nifti_files = list(output_dir.glob("*.nii.gz"))
        if nifti_files:
            return nifti_files[0]

        raise FileNotFoundError(
            f"세그멘테이션 출력 파일을 찾을 수 없습니다: {output_dir}"
        )

    def get_standard_label_mapping(self) -> dict[int, int]:
        """TotalSpineSeg → SpineLabel 매핑."""
        return TOTALSPINESEG_TO_STANDARD.copy()
