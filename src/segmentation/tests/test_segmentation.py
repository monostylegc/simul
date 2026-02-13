"""세그멘테이션 엔진 테스트."""

import pytest

from src.segmentation.base import SegmentationEngine
from src.segmentation.totalseg import TotalSegmentatorEngine
from src.segmentation.totalspineseg import TotalSpineSegEngine
from src.segmentation.nnunet_spine import SpineUnifiedEngine
from src.segmentation.factory import create_engine, list_engines


class TestTotalSegmentatorEngine:
    """TotalSegmentator 엔진 테스트."""

    def test_engine_properties(self):
        """엔진 속성 확인."""
        engine = TotalSegmentatorEngine()
        assert engine.name == "totalseg"
        assert "CT" in engine.supported_modalities

    def test_is_subclass(self):
        """SegmentationEngine ABC 상속 확인."""
        assert issubclass(TotalSegmentatorEngine, SegmentationEngine)

    def test_standard_label_mapping(self):
        """표준 라벨 매핑 반환."""
        engine = TotalSegmentatorEngine()
        mapping = engine.get_standard_label_mapping()
        assert isinstance(mapping, dict)
        assert len(mapping) > 0
        # C1 매핑 존재 확인
        assert 26 in mapping  # TotalSeg C1 ID


class TestTotalSpineSegEngine:
    """TotalSpineSeg 엔진 테스트."""

    def test_engine_properties(self):
        """엔진 속성 확인."""
        engine = TotalSpineSegEngine()
        assert engine.name == "totalspineseg"
        assert "MRI" in engine.supported_modalities

    def test_is_subclass(self):
        """SegmentationEngine ABC 상속 확인."""
        assert issubclass(TotalSpineSegEngine, SegmentationEngine)

    def test_standard_label_mapping(self):
        """표준 라벨 매핑 반환."""
        engine = TotalSpineSegEngine()
        mapping = engine.get_standard_label_mapping()
        assert isinstance(mapping, dict)
        assert len(mapping) > 0


class TestFactory:
    """팩토리 함수 테스트."""

    def test_list_engines(self):
        """엔진 목록 조회."""
        engines = list_engines()
        assert len(engines) == 3
        names = [e["name"] for e in engines]
        assert "totalseg" in names
        assert "totalspineseg" in names
        assert "spine_unified" in names

    def test_create_unknown_engine(self):
        """알 수 없는 엔진 이름."""
        with pytest.raises(ValueError, match="알 수 없는"):
            create_engine("unknown_engine")

    def test_create_engine_unavailable(self):
        """미설치 엔진 생성 시도 (설치 환경에 따라 skip 가능)."""
        # TotalSegmentator가 설치되지 않은 환경에서만 테스트
        engine = TotalSegmentatorEngine()
        if not engine.is_available():
            with pytest.raises(RuntimeError, match="설치되지"):
                create_engine("totalseg")
        else:
            # 설치되어 있으면 정상 생성
            eng = create_engine("totalseg")
            assert eng.name == "totalseg"
