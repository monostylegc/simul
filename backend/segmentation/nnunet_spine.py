"""SpineUnified nnU-Net 추론 엔진 — CT/MRI 통합 척추 세그멘테이션.

nnU-Net v2 기반 커스텀 모델로 CT와 MRI 모두에서
척추골(25) + 디스크(23) + 연조직(2) = 50 클래스를 세그멘테이션한다.

2채널 입력:
  - 채널 0: 정규화 영상 (CT: HU 클리핑 → 0-1, MRI: z-score → 0-1)
  - 채널 1: 도메인 채널 (CT=1.0, MRI=0.0)
"""

import shutil
from pathlib import Path
from typing import Optional

import numpy as np

from .base import SegmentationEngine
from .labels import NNUNET_SPINE_TO_STANDARD

# 모델 저장 경로
DEFAULT_MODEL_DIR = Path.home() / ".spine_sim" / "models" / "spine_unified"

# nnU-Net 데이터셋 ID
DATASET_ID = 200
DATASET_NAME = "Dataset200_SpineUnified"

# CT 정규화 파라미터
CT_HU_MIN = -200.0
CT_HU_MAX = 1500.0


class SpineUnifiedEngine(SegmentationEngine):
    """CT+MRI 통합 척추 세그멘테이션 엔진 (nnU-Net v2 기반)."""

    name = "spine_unified"
    supported_modalities = ["CT", "MRI"]

    def __init__(self, model_dir: Optional[str | Path] = None):
        self.model_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR

    def is_available(self) -> bool:
        """nnU-Net v2 설치 + 모델 가중치 존재 확인."""
        if not self._check_nnunet_installed():
            return False
        return self._check_model_exists()

    def _check_nnunet_installed(self) -> bool:
        """nnunetv2 패키지 설치 여부."""
        try:
            import nnunetv2  # noqa: F401
            return True
        except ImportError:
            return False

    def _check_model_exists(self) -> bool:
        """학습된 모델 가중치 존재 여부."""
        # nnU-Net 결과 디렉토리 구조: model_dir/nnUNetTrainer__nnUNetPlans__3d_fullres/
        plans_dir = self.model_dir / "nnUNetTrainer__nnUNetPlans__3d_fullres"
        if not plans_dir.exists():
            return False
        # 최소한 하나의 fold 체크포인트가 있어야 함
        fold_dirs = list(plans_dir.glob("fold_*"))
        return any((d / "checkpoint_final.pth").exists() for d in fold_dirs)

    def segment(
        self,
        input_path: str | Path,
        output_path: str | Path,
        device: str = "gpu",
        fast: bool = False,
        roi_subset: Optional[list[str]] = None,
        modality: Optional[str] = None,
    ) -> Path:
        """CT 또는 MRI 세그멘테이션 실행.

        Args:
            input_path: 입력 NIfTI 파일 경로
            output_path: 출력 라벨맵 NIfTI 경로
            device: "gpu" 또는 "cpu"
            fast: True면 3d_lowres 사용 (빠르지만 정확도 ↓)
            roi_subset: 사용하지 않음
            modality: "CT" 또는 "MRI" (None이면 자동 감지)

        Returns:
            출력 파일 경로
        """
        if not self.is_available():
            raise RuntimeError(
                "SpineUnified 엔진을 사용할 수 없습니다.\n"
                "1) nnunetv2 설치: uv pip install 'pysim[seg-unified]'\n"
                "2) 모델 다운로드: spine-sim download-model spine_unified"
            )

        import nibabel as nib

        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 모달리티 자동 감지
        if modality is None:
            modality = self._detect_modality(input_path)

        # 입력 전처리 → 2채널 NIfTI 생성
        tmp_dir = output_path.parent / "_spine_unified_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._prepare_input(input_path, tmp_dir, modality)

            # nnU-Net 추론 실행
            configuration = "3d_lowres" if fast else "3d_fullres"
            self._run_inference(tmp_dir, output_path.parent, device, configuration)

            # 추론 결과 이동
            # nnU-Net은 출력을 지정된 디렉토리에 저장
            pred_file = self._find_prediction(output_path.parent)
            if pred_file and pred_file != output_path:
                shutil.move(str(pred_file), str(output_path))

        finally:
            # 임시 디렉토리 정리
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

        return output_path

    def _detect_modality(self, input_path: Path) -> str:
        """HU 범위로 CT/MRI 자동 판별.

        CT: 일반적으로 -1024 ~ 3000+ HU (뼈 영역에서 >200 HU)
        MRI: 일반적으로 0 ~ 수천 (표준화 없음, 음수값 없음)
        """
        import nibabel as nib

        img = nib.load(str(input_path))
        data = np.asarray(img.dataobj, dtype=np.float32)

        # 표본 추출 (전체 복셀의 1% 또는 최대 100,000개)
        n_voxels = data.size
        n_sample = min(n_voxels, 100_000)
        rng = np.random.default_rng(42)
        sample = rng.choice(data.ravel(), size=n_sample, replace=False)

        # CT 판별 기준: 음수값 존재 (배경 공기 -1024), 또는 최소값 < -100
        min_val = float(np.min(sample))
        max_val = float(np.max(sample))

        if min_val < -100:
            return "CT"

        # 넓은 범위(>2000)면 CT일 가능성 높음
        if max_val - min_val > 2000:
            return "CT"

        return "MRI"

    def _prepare_input(self, input_path: Path, tmp_dir: Path, modality: str):
        """입력 영상을 2채널 nnU-Net 입력으로 변환.

        채널 0: 정규화 영상 (_0000.nii.gz)
        채널 1: 도메인 채널 (_0001.nii.gz)
        """
        import nibabel as nib

        tmp_dir.mkdir(parents=True, exist_ok=True)

        img = nib.load(str(input_path))
        data = np.asarray(img.dataobj, dtype=np.float32)

        # 채널 0: 영상 정규화
        if modality == "CT":
            # CT: HU 클리핑 → 0-1 선형 정규화
            normalized = np.clip(data, CT_HU_MIN, CT_HU_MAX)
            normalized = (normalized - CT_HU_MIN) / (CT_HU_MAX - CT_HU_MIN)
        else:
            # MRI: z-score 정규화 → sigmoid-like 클리핑
            mask = data > 0  # 배경 제외
            if mask.any():
                mean_val = float(np.mean(data[mask]))
                std_val = float(np.std(data[mask]))
                if std_val > 0:
                    normalized = (data - mean_val) / std_val
                else:
                    normalized = np.zeros_like(data)
            else:
                normalized = np.zeros_like(data)
            # z-score → 0-1 범위로 클리핑 (±3σ)
            normalized = np.clip(normalized, -3.0, 3.0)
            normalized = (normalized + 3.0) / 6.0

        # 채널 0 저장
        case_id = "SpineUnified_0001"
        ch0_img = nib.Nifti1Image(normalized, img.affine, img.header)
        nib.save(ch0_img, str(tmp_dir / f"{case_id}_0000.nii.gz"))

        # 채널 1: 도메인 채널 (CT=1.0, MRI=0.0)
        domain_val = 1.0 if modality == "CT" else 0.0
        domain_data = np.full_like(data, domain_val, dtype=np.float32)
        ch1_img = nib.Nifti1Image(domain_data, img.affine, img.header)
        nib.save(ch1_img, str(tmp_dir / f"{case_id}_0001.nii.gz"))

    def _run_inference(
        self,
        input_dir: Path,
        output_dir: Path,
        device: str,
        configuration: str,
    ):
        """nnU-Net v2 추론 실행."""
        from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

        predictor = nnUNetPredictor(
            tile_step_size=0.5,
            use_gaussian=True,
            use_mirroring=True,
            device=self._get_torch_device(device),
            verbose=False,
        )

        # 모델 로드
        predictor.initialize_from_trained_model_folder(
            str(self.model_dir / "nnUNetTrainer__nnUNetPlans__3d_fullres"),
            use_folds="all",
            checkpoint_name="checkpoint_final.pth",
        )

        # 추론
        predictor.predict_from_files(
            list_of_lists_or_source_folder=str(input_dir),
            output_folder_or_list_of_truncated_output_files=str(output_dir),
            save_probabilities=False,
            overwrite=True,
            num_processes_preprocessing=1,
            num_processes_segmentation_export=1,
        )

    @staticmethod
    def _get_torch_device(device: str):
        """문자열 → torch.device 변환."""
        import torch

        if device == "gpu" and torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")

    def _find_prediction(self, output_dir: Path) -> Optional[Path]:
        """nnU-Net 출력 예측 파일 찾기."""
        candidates = list(output_dir.glob("SpineUnified_*.nii.gz"))
        # _0000, _0001 채널 파일 제외
        candidates = [
            f for f in candidates
            if not any(f.name.endswith(f"_{i:04d}.nii.gz") for i in range(10))
        ]
        return candidates[0] if candidates else None

    def get_standard_label_mapping(self) -> dict[int, int]:
        """nnU-Net SpineUnified → SpineLabel 매핑."""
        return NNUNET_SPINE_TO_STANDARD.copy()

    @staticmethod
    def download_model(target_dir: Optional[str | Path] = None) -> Path:
        """GitHub Release에서 모델 가중치 다운로드.

        Args:
            target_dir: 저장 경로 (기본: ~/.spine_sim/models/spine_unified/)

        Returns:
            모델 디렉토리 경로
        """
        import urllib.request
        import zipfile

        target = Path(target_dir) if target_dir else DEFAULT_MODEL_DIR
        target.mkdir(parents=True, exist_ok=True)

        # TODO: 실제 GitHub Release URL로 교체
        model_url = (
            "https://github.com/user/spine-unified/releases/download/"
            "v1.0/spine_unified_model.zip"
        )

        zip_path = target / "model.zip"
        print(f"모델 다운로드 중: {model_url}")
        print(f"저장 위치: {target}")

        try:
            urllib.request.urlretrieve(model_url, str(zip_path))
        except Exception as e:
            raise RuntimeError(
                f"모델 다운로드 실패: {e}\n"
                "수동 다운로드 후 아래 경로에 압축 해제하세요:\n"
                f"  {target}"
            ) from e

        # 압축 해제
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            zf.extractall(str(target))

        zip_path.unlink()
        print("모델 다운로드 완료.")
        return target
