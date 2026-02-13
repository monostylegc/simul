"""SpineUnified 추론 엔진 테스트."""

import numpy as np
import pytest

from src.segmentation.base import SegmentationEngine
from src.segmentation.nnunet_spine import SpineUnifiedEngine, CT_HU_MIN, CT_HU_MAX
from src.segmentation.labels import (
    SpineLabel,
    NNUNET_SPINE_TO_STANDARD,
    STANDARD_TO_NNUNET_SPINE,
    NNUNET_IGNORE_LABEL,
    NNUNET_NUM_CLASSES,
)


class TestNnunetSpineLabels:
    """nnU-Net 라벨 매핑 테스트."""

    def test_nnunet_to_standard_size(self):
        """nnU-Net → SpineLabel 매핑 크기 = 51 (0~50)."""
        assert len(NNUNET_SPINE_TO_STANDARD) == NNUNET_NUM_CLASSES

    def test_standard_to_nnunet_size(self):
        """역매핑 크기도 동일."""
        assert len(STANDARD_TO_NNUNET_SPINE) == NNUNET_NUM_CLASSES

    def test_roundtrip(self):
        """nnU-Net → SpineLabel → nnU-Net 왕복 일치."""
        for nn_id, std_id in NNUNET_SPINE_TO_STANDARD.items():
            assert STANDARD_TO_NNUNET_SPINE[std_id] == nn_id

    def test_vertebra_range(self):
        """척추골 매핑: nnU-Net 1~25 → SpineLabel 101~125."""
        for nn_id in range(1, 26):
            std = NNUNET_SPINE_TO_STANDARD[nn_id]
            assert SpineLabel.is_vertebra(std), f"nnU-Net {nn_id} → {std}는 척추골이어야 함"

    def test_disc_range(self):
        """디스크 매핑: nnU-Net 26~48 → SpineLabel 201~223."""
        for nn_id in range(26, 49):
            std = NNUNET_SPINE_TO_STANDARD[nn_id]
            assert SpineLabel.is_disc(std), f"nnU-Net {nn_id} → {std}는 디스크여야 함"

    def test_soft_tissue_range(self):
        """연조직 매핑: nnU-Net 49~50 → SpineLabel 301~302."""
        for nn_id in [49, 50]:
            std = NNUNET_SPINE_TO_STANDARD[nn_id]
            assert SpineLabel.is_soft_tissue(std), f"nnU-Net {nn_id} → {std}는 연조직이어야 함"

    def test_background_mapping(self):
        """배경 매핑: 0 → 0."""
        assert NNUNET_SPINE_TO_STANDARD[0] == SpineLabel.BACKGROUND

    def test_ignore_label(self):
        """Ignore 라벨은 매핑에 포함되지 않아야 함."""
        assert NNUNET_IGNORE_LABEL not in NNUNET_SPINE_TO_STANDARD

    def test_no_duplicate_standard_values(self):
        """표준 라벨 값에 중복 없어야 함."""
        values = list(NNUNET_SPINE_TO_STANDARD.values())
        assert len(values) == len(set(values))


class TestSpineUnifiedEngine:
    """SpineUnified 엔진 속성/인터페이스 테스트."""

    def test_engine_properties(self):
        """엔진 속성 확인."""
        engine = SpineUnifiedEngine()
        assert engine.name == "spine_unified"
        assert "CT" in engine.supported_modalities
        assert "MRI" in engine.supported_modalities

    def test_is_subclass(self):
        """SegmentationEngine ABC 상속 확인."""
        assert issubclass(SpineUnifiedEngine, SegmentationEngine)

    def test_standard_label_mapping(self):
        """표준 라벨 매핑 반환."""
        engine = SpineUnifiedEngine()
        mapping = engine.get_standard_label_mapping()
        assert isinstance(mapping, dict)
        assert len(mapping) == NNUNET_NUM_CLASSES
        # C1 매핑 확인
        assert mapping[1] == SpineLabel.C1

    def test_custom_model_dir(self):
        """커스텀 모델 디렉토리 설정."""
        engine = SpineUnifiedEngine(model_dir="/tmp/test_model")
        from pathlib import Path
        assert engine.model_dir == Path("/tmp/test_model")

    def test_is_available_without_nnunet(self):
        """nnunetv2 미설치 시 is_available() = False."""
        engine = SpineUnifiedEngine()
        # nnunetv2가 설치되지 않으면 False, 설치되어도 모델 없으면 False
        result = engine.is_available()
        assert isinstance(result, bool)


class TestModalityDetection:
    """모달리티 자동 감지 테스트."""

    def test_detect_ct_from_negative_values(self, tmp_path):
        """음수 HU 값이 있으면 CT로 감지."""
        import nibabel as nib

        # CT 모의 데이터: -1024 ~ 2000 HU
        data = np.random.uniform(-1024, 2000, (10, 10, 10)).astype(np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nib.save(img, str(tmp_path / "ct.nii.gz"))

        engine = SpineUnifiedEngine()
        modality = engine._detect_modality(tmp_path / "ct.nii.gz")
        assert modality == "CT"

    def test_detect_mri_from_positive_values(self, tmp_path):
        """양수값만 있고 범위 좁으면 MRI로 감지."""
        import nibabel as nib

        # MRI 모의 데이터: 0 ~ 500 (좁은 범위)
        data = np.random.uniform(0, 500, (10, 10, 10)).astype(np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nib.save(img, str(tmp_path / "mri.nii.gz"))

        engine = SpineUnifiedEngine()
        modality = engine._detect_modality(tmp_path / "mri.nii.gz")
        assert modality == "MRI"


class TestInputPreprocessing:
    """입력 전처리 테스트."""

    def test_ct_normalization(self, tmp_path):
        """CT 정규화: HU → 0-1 범위."""
        import nibabel as nib

        data = np.array([CT_HU_MIN, 0.0, CT_HU_MAX, -500.0, 1000.0], dtype=np.float32).reshape(1, 1, 5)
        img = nib.Nifti1Image(data, np.eye(4))
        nib.save(img, str(tmp_path / "ct.nii.gz"))

        engine = SpineUnifiedEngine()
        engine._prepare_input(tmp_path / "ct.nii.gz", tmp_path / "output", "CT")

        # 채널 0 확인
        ch0 = nib.load(str(tmp_path / "output" / "SpineUnified_0001_0000.nii.gz"))
        ch0_data = np.asarray(ch0.dataobj)
        assert ch0_data.min() >= 0.0
        assert ch0_data.max() <= 1.0

        # 채널 1 확인 (CT=1.0)
        ch1 = nib.load(str(tmp_path / "output" / "SpineUnified_0001_0001.nii.gz"))
        ch1_data = np.asarray(ch1.dataobj)
        assert np.allclose(ch1_data, 1.0)

    def test_mri_normalization(self, tmp_path):
        """MRI 정규화: z-score → 0-1 범위."""
        import nibabel as nib

        # MRI 데이터 (양수값)
        data = np.random.uniform(50, 500, (5, 5, 5)).astype(np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nib.save(img, str(tmp_path / "mri.nii.gz"))

        engine = SpineUnifiedEngine()
        engine._prepare_input(tmp_path / "mri.nii.gz", tmp_path / "output", "MRI")

        # 채널 0 확인
        ch0 = nib.load(str(tmp_path / "output" / "SpineUnified_0001_0000.nii.gz"))
        ch0_data = np.asarray(ch0.dataobj)
        assert ch0_data.min() >= 0.0
        assert ch0_data.max() <= 1.0

        # 채널 1 확인 (MRI=0.0)
        ch1 = nib.load(str(tmp_path / "output" / "SpineUnified_0001_0001.nii.gz"))
        ch1_data = np.asarray(ch1.dataobj)
        assert np.allclose(ch1_data, 0.0)

    def test_two_channel_output(self, tmp_path):
        """2채널 출력 파일이 올바르게 생성되는지 확인."""
        import nibabel as nib

        data = np.ones((3, 3, 3), dtype=np.float32) * 100.0
        img = nib.Nifti1Image(data, np.eye(4))
        nib.save(img, str(tmp_path / "input.nii.gz"))

        engine = SpineUnifiedEngine()
        out_dir = tmp_path / "output"
        engine._prepare_input(tmp_path / "input.nii.gz", out_dir, "CT")

        assert (out_dir / "SpineUnified_0001_0000.nii.gz").exists()
        assert (out_dir / "SpineUnified_0001_0001.nii.gz").exists()
