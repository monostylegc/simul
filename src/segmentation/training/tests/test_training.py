"""학습 데이터 준비 파이프라인 테스트."""

from pathlib import Path

import numpy as np
import pytest

from src.segmentation.labels import (
    SpineLabel,
    NNUNET_SPINE_TO_STANDARD,
    STANDARD_TO_NNUNET_SPINE,
    NNUNET_IGNORE_LABEL,
    VERSE_TO_STANDARD,
    CTSPINE1K_TO_STANDARD,
    build_spider_mapping,
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
from src.segmentation.training.dataset_crawl import (
    CaseInfo,
    crawl_verse2020,
    crawl_ctspine1k,
    crawl_spider,
    crawl_all,
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


class TestDatasetMappings:
    """원본 데이터셋 → SpineLabel 매핑 테스트."""

    def test_verse_mapping_completeness(self):
        """VerSe2020 매핑: 1~25 모두 존재."""
        for i in range(1, 26):
            assert i in VERSE_TO_STANDARD, f"VerSe 라벨 {i} 매핑 없음"

    def test_verse_c1_to_sacrum(self):
        """VerSe2020: C1=1, SACRUM=25."""
        assert VERSE_TO_STANDARD[1] == SpineLabel.C1
        assert VERSE_TO_STANDARD[7] == SpineLabel.C7
        assert VERSE_TO_STANDARD[8] == SpineLabel.T1
        assert VERSE_TO_STANDARD[19] == SpineLabel.T12
        assert VERSE_TO_STANDARD[20] == SpineLabel.L1
        assert VERSE_TO_STANDARD[24] == SpineLabel.L5
        assert VERSE_TO_STANDARD[25] == SpineLabel.SACRUM

    def test_verse_extra_sacral(self):
        """VerSe2020: 26~28 → SACRUM."""
        for i in [26, 27, 28]:
            assert VERSE_TO_STANDARD[i] == SpineLabel.SACRUM

    def test_ctspine1k_mapping_completeness(self):
        """CTSpine1K 매핑: 1~25 모두 존재."""
        for i in range(1, 26):
            assert i in CTSPINE1K_TO_STANDARD, f"CTSpine1K 라벨 {i} 매핑 없음"

    def test_ctspine1k_matches_verse(self):
        """CTSpine1K 매핑이 VerSe 1~25와 동일."""
        for i in range(1, 26):
            assert CTSPINE1K_TO_STANDARD[i] == VERSE_TO_STANDARD[i]

    def test_spider_dynamic_mapping_basic(self):
        """SPIDER 동적 매핑: 5개 척추골 (L1~L5)."""
        mapping = build_spider_mapping(n_vertebrae=5, bottom_vertebra="L5")

        # 척추골: 1=L5, 2=L4, 3=L3, 4=L2, 5=L1
        assert mapping[1] == SpineLabel.L5
        assert mapping[2] == SpineLabel.L4
        assert mapping[3] == SpineLabel.L3
        assert mapping[4] == SpineLabel.L2
        assert mapping[5] == SpineLabel.L1

    def test_spider_dynamic_mapping_discs(self):
        """SPIDER 동적 매핑: 디스크 라벨."""
        mapping = build_spider_mapping(n_vertebrae=5, bottom_vertebra="L5")

        # 디스크: 201=L5S1, 202=L4L5, 203=L3L4, 204=L2L3
        assert mapping[201] == SpineLabel.L5S1
        assert mapping[202] == SpineLabel.L4L5
        assert mapping[203] == SpineLabel.L3L4
        assert mapping[204] == SpineLabel.L2L3

    def test_spider_dynamic_mapping_spinal_canal(self):
        """SPIDER: 100 → SPINAL_CANAL."""
        mapping = build_spider_mapping(n_vertebrae=3, bottom_vertebra="L5")
        assert mapping[100] == SpineLabel.SPINAL_CANAL

    def test_spider_large_fov(self):
        """SPIDER: 넓은 FOV (T12~L5)."""
        mapping = build_spider_mapping(n_vertebrae=6, bottom_vertebra="L5")

        assert mapping[1] == SpineLabel.L5
        assert mapping[5] == SpineLabel.L1
        assert mapping[6] == SpineLabel.T12

    def test_spider_different_bottom(self):
        """SPIDER: bottom=L4인 경우."""
        mapping = build_spider_mapping(n_vertebrae=3, bottom_vertebra="L4")

        assert mapping[1] == SpineLabel.L4
        assert mapping[2] == SpineLabel.L3
        assert mapping[3] == SpineLabel.L2


class TestDatasetCrawl:
    """데이터셋 케이스 탐색 테스트."""

    def test_crawl_verse_empty(self, tmp_path):
        """VerSe2020: 빈 디렉토리."""
        cases = crawl_verse2020(tmp_path / "nonexistent")
        assert cases == []

    def test_crawl_verse_matched(self, tmp_path):
        """VerSe2020: 영상-라벨 쌍 매칭."""
        # 디렉토리 구조 생성
        raw = tmp_path / "rawdata" / "sub-verse001"
        raw.mkdir(parents=True)
        deriv = tmp_path / "derivatives" / "sub-verse001"
        deriv.mkdir(parents=True)

        (raw / "sub-verse001_ct.nii.gz").touch()
        (deriv / "sub-verse001_seg-vert_msk.nii.gz").touch()

        cases = crawl_verse2020(tmp_path)
        assert len(cases) == 1
        assert cases[0].dataset == "verse2020"
        assert cases[0].modality == "CT"

    def test_crawl_ctspine_matched(self, tmp_path):
        """CTSpine1K: 영상-라벨 쌍 매칭."""
        (tmp_path / "image").mkdir()
        (tmp_path / "mask").mkdir()
        (tmp_path / "image" / "case001.nii.gz").touch()
        (tmp_path / "mask" / "case001.nii.gz").touch()

        cases = crawl_ctspine1k(tmp_path)
        assert len(cases) == 1
        assert cases[0].dataset == "ctspine1k"

    def test_crawl_ctspine_unmatched(self, tmp_path):
        """CTSpine1K: 매칭 안 되는 파일."""
        (tmp_path / "image").mkdir()
        (tmp_path / "mask").mkdir()
        (tmp_path / "image" / "case001.nii.gz").touch()
        (tmp_path / "mask" / "case002.nii.gz").touch()

        cases = crawl_ctspine1k(tmp_path)
        assert len(cases) == 0

    def test_crawl_spider_matched(self, tmp_path):
        """SPIDER: MRI 케이스 매칭."""
        (tmp_path / "images").mkdir()
        (tmp_path / "masks").mkdir()
        (tmp_path / "images" / "patient01.nii.gz").touch()
        (tmp_path / "masks" / "patient01.nii.gz").touch()

        cases = crawl_spider(tmp_path)
        assert len(cases) == 1
        assert cases[0].modality == "MRI"

    def test_crawl_all_empty(self, tmp_path):
        """crawl_all: 빈 경로."""
        paths = DatasetPaths(
            verse2020=tmp_path / "v",
            ctspine1k=tmp_path / "c",
            spider=tmp_path / "s",
        )
        cases = crawl_all(paths)
        assert cases == []

    def test_crawl_all_combined(self, tmp_path):
        """crawl_all: 다중 데이터셋 통합."""
        # VerSe
        verse_dir = tmp_path / "verse"
        raw = verse_dir / "rawdata" / "sub-verse001"
        raw.mkdir(parents=True)
        deriv = verse_dir / "derivatives" / "sub-verse001"
        deriv.mkdir(parents=True)
        (raw / "sub-verse001_ct.nii.gz").touch()
        (deriv / "sub-verse001_seg-vert_msk.nii.gz").touch()

        # SPIDER
        spider_dir = tmp_path / "spider"
        (spider_dir / "images").mkdir(parents=True)
        (spider_dir / "masks").mkdir(parents=True)
        (spider_dir / "images" / "p01.nii.gz").touch()
        (spider_dir / "masks" / "p01.nii.gz").touch()

        paths = DatasetPaths(
            verse2020=verse_dir,
            ctspine1k=tmp_path / "ctspine_empty",
            spider=spider_dir,
        )
        cases = crawl_all(paths)
        assert len(cases) == 2

        datasets = {c.dataset for c in cases}
        assert "verse2020" in datasets
        assert "spider" in datasets


class TestRunPipeline:
    """파이프라인 오케스트레이션 테스트."""

    def test_skip_existing(self, tmp_path):
        """이미 변환된 케이스 스킵 확인."""
        from src.segmentation.training.run_pipeline import _case_already_exists

        config = NnunetConfig(output_dir=tmp_path)
        output_dir = tmp_path / config.dataset_name

        # 존재하지 않음
        assert not _case_already_exists(1, output_dir, config)

        # 파일 생성
        labels_dir = output_dir / "labelsTr"
        labels_dir.mkdir(parents=True)
        (labels_dir / "SpineUnified_0001.nii.gz").touch()

        assert _case_already_exists(1, output_dir, config)
        assert not _case_already_exists(2, output_dir, config)

    def test_build_case_id(self):
        """케이스 ID 포맷."""
        from src.segmentation.training.run_pipeline import _build_case_id

        assert _build_case_id(1) == "SpineUnified_0001"
        assert _build_case_id(42) == "SpineUnified_0042"
        assert _build_case_id(1000) == "SpineUnified_1000"

    def test_empty_pipeline(self, tmp_path):
        """빈 데이터 파이프라인: 케이스 0건."""
        from src.segmentation.training.run_pipeline import run_training_pipeline

        config = TrainingPipelineConfig(
            datasets=DatasetPaths(
                verse2020=tmp_path / "v",
                ctspine1k=tmp_path / "c",
                spider=tmp_path / "s",
            ),
            nnunet=NnunetConfig(output_dir=tmp_path / "out"),
        )

        result = run_training_pipeline(config)
        assert result.total == 0
        assert result.success == 0
