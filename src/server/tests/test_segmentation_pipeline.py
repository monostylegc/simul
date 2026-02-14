"""세그멘테이션 파이프라인 테스트.

실제 세그멘테이션 엔진(TotalSegmentator 등)은 설치 필요하므로,
파이프라인 로직/에러 처리만 테스트.
"""

import pytest
from pathlib import Path
from src.server.models import SegmentationRequest


class TestSegmentationPipeline:
    def test_nonexistent_file(self):
        """존재하지 않는 입력 파일."""
        from src.server.segmentation_pipeline import run_segmentation

        request = SegmentationRequest(input_path="/tmp/nonexistent.nii.gz")
        with pytest.raises(FileNotFoundError):
            run_segmentation(request)

    def test_request_defaults(self):
        """요청 기본값 확인."""
        request = SegmentationRequest(input_path="/tmp/test.nii.gz")
        assert request.engine == "totalspineseg"
        assert request.device == "gpu"
        assert request.fast is False

    def test_request_mri_engine(self):
        """MRI 엔진 요청."""
        request = SegmentationRequest(
            input_path="/tmp/test.nii.gz",
            engine="totalspineseg",
        )
        assert request.engine == "totalspineseg"
