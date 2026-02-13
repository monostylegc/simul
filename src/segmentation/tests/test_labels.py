"""라벨 체계 테스트."""

import numpy as np
import pytest

from src.segmentation.labels import (
    TOTALSEG_TO_STANDARD,
    TOTALSPINESEG_TO_STANDARD,
    SpineLabel,
    convert_to_standard,
)


class TestSpineLabel:
    """SpineLabel 열거형 테스트."""

    def test_vertebra_range(self):
        """척추골 라벨 범위 확인."""
        assert SpineLabel.C1 == 101
        assert SpineLabel.L5 == 124
        assert SpineLabel.SACRUM == 125

    def test_disc_range(self):
        """디스크 라벨 범위 확인."""
        assert SpineLabel.C2C3 == 201
        assert SpineLabel.L5S1 == 223

    def test_soft_tissue_range(self):
        """연조직 라벨 범위 확인."""
        assert SpineLabel.SPINAL_CORD == 301
        assert SpineLabel.SPINAL_CANAL == 302

    def test_is_vertebra(self):
        """척추골 판별."""
        assert SpineLabel.is_vertebra(101) is True
        assert SpineLabel.is_vertebra(125) is True
        assert SpineLabel.is_vertebra(100) is False
        assert SpineLabel.is_vertebra(201) is False
        assert SpineLabel.is_vertebra(0) is False

    def test_is_disc(self):
        """디스크 판별."""
        assert SpineLabel.is_disc(201) is True
        assert SpineLabel.is_disc(223) is True
        assert SpineLabel.is_disc(200) is False
        assert SpineLabel.is_disc(101) is False

    def test_is_soft_tissue(self):
        """연조직 판별."""
        assert SpineLabel.is_soft_tissue(301) is True
        assert SpineLabel.is_soft_tissue(302) is True
        assert SpineLabel.is_soft_tissue(101) is False

    def test_to_material_type(self):
        """라벨 → 재료 타입 변환."""
        assert SpineLabel.to_material_type(0) == 0      # 배경 → empty
        assert SpineLabel.to_material_type(101) == 1     # C1 → bone
        assert SpineLabel.to_material_type(125) == 1     # SACRUM → bone
        assert SpineLabel.to_material_type(201) == 2     # C2C3 → disc
        assert SpineLabel.to_material_type(301) == 3     # SPINAL_CORD → soft
        assert SpineLabel.to_material_type(999) == 0     # 미등록 → empty

    def test_vertebra_names(self):
        """척추골 이름 목록."""
        names = SpineLabel.vertebra_names()
        assert "C1" in names
        assert "L5" in names
        assert "SACRUM" in names
        assert len(names) == 25  # C1~C7 + T1~T12 + L1~L5 + SACRUM

    def test_disc_names(self):
        """디스크 이름 목록."""
        names = SpineLabel.disc_names()
        assert "C2C3" in names
        assert "L5S1" in names
        assert len(names) == 23  # C2C3 ~ L5S1

    def test_all_labels_unique(self):
        """모든 라벨 값이 고유한지 확인."""
        values = [m.value for m in SpineLabel]
        assert len(values) == len(set(values))


class TestLabelMappings:
    """라벨 매핑 테스트."""

    def test_totalseg_mapping_values(self):
        """TotalSegmentator 매핑 값이 유효한 SpineLabel인지 확인."""
        for src, std in TOTALSEG_TO_STANDARD.items():
            assert isinstance(src, int)
            assert isinstance(std, int)
            assert SpineLabel.is_vertebra(std), f"매핑값 {std}가 척추골 아님 (원본: {src})"

    def test_totalspineseg_mapping_values(self):
        """TotalSpineSeg 매핑 값이 유효한 SpineLabel인지 확인."""
        for src, std in TOTALSPINESEG_TO_STANDARD.items():
            assert isinstance(src, int)
            assert isinstance(std, int)
            # 척추골, 디스크, 연조직 중 하나여야 함
            valid = (
                SpineLabel.is_vertebra(std)
                or SpineLabel.is_disc(std)
                or SpineLabel.is_soft_tissue(std)
            )
            assert valid, f"매핑값 {std}가 유효하지 않음 (원본: {src})"

    def test_totalseg_has_all_vertebrae(self):
        """TotalSegmentator가 모든 척추골을 매핑하는지 확인."""
        mapped_vertebrae = set(TOTALSEG_TO_STANDARD.values())
        for v in range(101, 126):
            assert v in mapped_vertebrae, f"척추 {v}가 TotalSegmentator 매핑에 없음"


class TestConvertToStandard:
    """라벨 변환 함수 테스트."""

    def test_basic_conversion(self):
        """기본 변환 테스트."""
        arr = np.array([0, 26, 27, 45, 0], dtype=np.int32)
        result = convert_to_standard(arr, TOTALSEG_TO_STANDARD)
        assert result[0] == 0  # 배경
        assert result[1] == SpineLabel.C1
        assert result[2] == SpineLabel.C2
        assert result[3] == SpineLabel.L1
        assert result[4] == 0

    def test_unmapped_labels_become_zero(self):
        """매핑에 없는 라벨은 0으로."""
        arr = np.array([999, 1000], dtype=np.int32)
        result = convert_to_standard(arr, TOTALSEG_TO_STANDARD)
        assert np.all(result == 0)

    def test_3d_array(self):
        """3D 배열 변환."""
        arr = np.zeros((3, 3, 3), dtype=np.int32)
        arr[1, 1, 1] = 26  # TotalSeg C1
        result = convert_to_standard(arr, TOTALSEG_TO_STANDARD)
        assert result[1, 1, 1] == SpineLabel.C1
        assert result[0, 0, 0] == 0
