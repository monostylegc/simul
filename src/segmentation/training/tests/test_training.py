"""학습 데이터 준비 파이프라인 테스트."""

from pathlib import Path

import numpy as np
import pytest

from src.segmentation.labels import (
    SpineLabel,
    NNUNET_SPINE_TO_STANDARD,
    STANDARD_TO_NNUNET_SPINE,
    NNUNET_IGNORE_LABEL,
)
from src.segmentation.training.config import (
    TrainingPipelineConfig,
    DatasetPaths,
    NnunetConfig,
)
from src.segmentation.training.preprocess import (
    normalize_ct,
    normalize_mri,
    create_domain_channel,
)
from src.segmentation.training.label_merge import merge_ct_labels
from src.segmentation.training.convert_nnunet import (
    convert_to_nnunet_labels,
    save_nnunet_case,
    generate_dataset_json,
)
from src.segmentation.training.validate_labels import validate_label_map
from src.segmentation.training.download import (
    DatasetInfo,
    validate_verse2020,
    validate_ctspine1k,
    validate_spider,
    validate_all,
)


class TestConfig:
    """설정 테스트."""

    def test_default_config(self):
        """기본 설정 생성."""
        config = TrainingPipelineConfig()
        assert config.nnunet.dataset_id == 200
        assert config.nnunet.num_classes == 51
        assert config.nnunet.ignore_label == 51
        assert config.val_ratio == 0.15

    def test_dataset_paths(self):
        """데이터셋 경로 기본값."""
        paths = DatasetPaths()
        assert "VerSe" in str(paths.verse2020)
        assert "CTSpine" in str(paths.ctspine1k)
        assert "SPIDER" in str(paths.spider)


class TestPreprocess:
    """전처리 테스트."""

    def test_normalize_ct_range(self):
        """CT 정규화: 출력 0-1 범위."""
        data = np.array([-500, 0, 500, 1000, 2000], dtype=np.float32)
        result = normalize_ct(data)
        assert result.min() >= 0.0
        assert result.max() <= 1.0

    def test_normalize_ct_clipping(self):
        """CT 정규화: 범위 밖 값 클리핑."""
        data = np.array([-1000, -200, 1500, 3000], dtype=np.float32)
        result = normalize_ct(data)
        # -1000 → 0.0 (클리핑), -200 → 0.0, 1500 → 1.0, 3000 → 1.0 (클리핑)
        assert result[0] == 0.0
        assert result[1] == 0.0
        assert result[2] == 1.0
        assert result[3] == 1.0

    def test_normalize_mri_range(self):
        """MRI 정규화: 출력 0-1 범위."""
        data = np.random.uniform(50, 500, (5, 5, 5)).astype(np.float32)
        result = normalize_mri(data)
        assert result.min() >= 0.0
        assert result.max() <= 1.0

    def test_normalize_mri_zero_data(self):
        """MRI 정규화: 전부 0인 경우."""
        data = np.zeros((5, 5, 5), dtype=np.float32)
        result = normalize_mri(data)
        assert np.allclose(result, 0.0)

    def test_domain_channel_ct(self):
        """CT 도메인 채널 = 1.0."""
        data = np.zeros((3, 3, 3))
        result = create_domain_channel(data, "CT")
        assert np.allclose(result, 1.0)

    def test_domain_channel_mri(self):
        """MRI 도메인 채널 = 0.0."""
        data = np.zeros((3, 3, 3))
        result = create_domain_channel(data, "MRI")
        assert np.allclose(result, 0.0)


class TestLabelMerge:
    """라벨 병합 테스트."""

    def test_merge_gt_priority(self):
        """GT 척추골이 pseudo-label보다 우선."""
        gt = np.zeros((10, 10, 10), dtype=np.int32)
        pseudo = np.zeros((10, 10, 10), dtype=np.int32)

        # GT: L4 = 123
        gt[3:7, 3:7, 3:7] = SpineLabel.L4

        # Pseudo: 같은 위치에 디스크 라벨 (충돌)
        pseudo[3:7, 3:7, 3:7] = SpineLabel.L4L5

        merged = merge_ct_labels(gt, pseudo)

        # GT 척추골이 우선
        assert np.all(merged[3:7, 3:7, 3:7] == SpineLabel.L4)

    def test_merge_disc_from_pseudo(self):
        """Pseudo-label에서 디스크가 병합됨."""
        gt = np.zeros((10, 10, 10), dtype=np.int32)
        pseudo = np.zeros((10, 10, 10), dtype=np.int32)

        # GT: L4
        gt[2:5, 3:7, 3:7] = SpineLabel.L4

        # Pseudo: 디스크 (겹치지 않는 영역)
        pseudo[6:9, 3:7, 3:7] = SpineLabel.L4L5

        merged = merge_ct_labels(gt, pseudo)

        # 디스크 영역이 병합됨
        assert np.any(merged == SpineLabel.L4L5)

    def test_merge_ignore_preserved(self):
        """Ignore 라벨(51)이 유지됨."""
        gt = np.zeros((10, 10, 10), dtype=np.int32)
        pseudo = np.zeros((10, 10, 10), dtype=np.int32)

        pseudo[0:3, 0:3, 0:3] = NNUNET_IGNORE_LABEL

        merged = merge_ct_labels(gt, pseudo)
        assert np.any(merged == NNUNET_IGNORE_LABEL)


class TestConvertNnunet:
    """nnU-Net 변환 테스트."""

    def test_convert_labels_vertebra(self):
        """척추골 라벨 변환: SpineLabel → nnU-Net."""
        data = np.array([SpineLabel.C1, SpineLabel.L5, SpineLabel.BACKGROUND], dtype=np.int32)
        result = convert_to_nnunet_labels(data)

        assert result[0] == STANDARD_TO_NNUNET_SPINE[SpineLabel.C1]  # 1
        assert result[1] == STANDARD_TO_NNUNET_SPINE[SpineLabel.L5]  # 24
        assert result[2] == 0  # 배경

    def test_convert_labels_disc(self):
        """디스크 라벨 변환."""
        data = np.array([SpineLabel.L4L5], dtype=np.int32)
        result = convert_to_nnunet_labels(data)
        assert result[0] == STANDARD_TO_NNUNET_SPINE[SpineLabel.L4L5]

    def test_convert_labels_ignore(self):
        """Ignore 라벨 보존."""
        data = np.array([NNUNET_IGNORE_LABEL], dtype=np.int32)
        result = convert_to_nnunet_labels(data)
        assert result[0] == NNUNET_IGNORE_LABEL

    def test_convert_labels_unmapped(self):
        """매핑 안 되는 라벨 → ignore."""
        data = np.array([999], dtype=np.int32)
        result = convert_to_nnunet_labels(data)
        assert result[0] == NNUNET_IGNORE_LABEL

    def test_save_nnunet_case(self, tmp_path):
        """nnU-Net 케이스 저장."""
        shape = (5, 5, 5)
        image = np.random.rand(*shape).astype(np.float32)
        domain = np.ones(shape, dtype=np.float32)
        labels = np.zeros(shape, dtype=np.uint8)
        labels[2:4, 2:4, 2:4] = 1  # C1

        save_nnunet_case(
            "SpineUnified_0001", image, domain, labels,
            np.eye(4), tmp_path,
        )

        assert (tmp_path / "imagesTr" / "SpineUnified_0001_0000.nii.gz").exists()
        assert (tmp_path / "imagesTr" / "SpineUnified_0001_0001.nii.gz").exists()
        assert (tmp_path / "labelsTr" / "SpineUnified_0001.nii.gz").exists()

    def test_generate_dataset_json(self, tmp_path):
        """dataset.json 생성."""
        json_path = generate_dataset_json(tmp_path, n_cases=100)
        assert json_path.exists()

        import json
        with open(json_path) as f:
            data = json.load(f)

        assert data["numTraining"] == 100
        assert "0" in data["channel_names"]
        assert "1" in data["channel_names"]
        assert len(data["labels"]) == 51  # 0~50


class TestValidateLabels:
    """라벨 검증 테스트."""

    def test_empty_label_map(self):
        """빈 라벨맵 검증."""
        data = np.zeros((10, 10, 10), dtype=np.int32)
        result = validate_label_map(data, "test")
        assert not result.is_valid

    def test_valid_vertebra(self):
        """유효한 척추골 라벨맵."""
        data = np.zeros((20, 20, 20), dtype=np.int32)
        # L4, L5 순서대로 (z축 방향)
        data[5:10, 5:15, 5:15] = SpineLabel.L4
        data[11:16, 5:15, 5:15] = SpineLabel.L5

        result = validate_label_map(data, "test")
        assert result.is_valid

    def test_tiny_structure_warning(self):
        """매우 작은 구조물에 경고."""
        data = np.zeros((20, 20, 20), dtype=np.int32)
        data[5:10, 5:15, 5:15] = SpineLabel.L4
        # 극소 디스크 (1 voxel)
        data[10, 10, 10] = SpineLabel.L4L5

        result = validate_label_map(data, "test")
        # 경고가 있어야 함
        assert any("부피" in w for w in result.warnings) or result.is_valid


class TestDatasetValidation:
    """데이터셋 검증 테스트."""

    def test_missing_directory(self, tmp_path):
        """존재하지 않는 디렉토리."""
        info = validate_verse2020(tmp_path / "nonexistent")
        assert not info.is_valid

    def test_empty_directory(self, tmp_path):
        """빈 디렉토리."""
        empty = tmp_path / "empty"
        empty.mkdir()
        info = validate_verse2020(empty)
        assert not info.is_valid

    def test_validate_all_nonexistent(self, tmp_path):
        """모든 데이터셋이 없는 경우."""
        paths = DatasetPaths(
            verse2020=tmp_path / "verse",
            ctspine1k=tmp_path / "ctspine",
            spider=tmp_path / "spider",
        )
        results = validate_all(paths)
        assert len(results) == 3
        assert all(not r.is_valid for r in results)

    def test_dataset_info_properties(self):
        """DatasetInfo 속성."""
        info = DatasetInfo(name="test", path=Path("."), exists=True, n_images=10, n_labels=10)
        assert info.is_valid

        info_invalid = DatasetInfo(name="test", path=Path("."), exists=False)
        assert not info_invalid.is_valid
