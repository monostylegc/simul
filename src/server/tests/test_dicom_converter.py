"""DICOM 변환 모듈 테스트."""

import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestConvertDicomToNifti:
    """DICOM → NIfTI 변환 테스트 (SimpleITK mock)."""

    def _make_mock_image(self):
        """가짜 SimpleITK 이미지 생성."""
        img = MagicMock()
        img.GetSpacing.return_value = (0.5, 0.5, 1.0)
        img.GetSize.return_value = (512, 512, 100)
        return img

    def _make_mock_reader(self, series_ids=None, file_counts=None):
        """가짜 ImageSeriesReader 생성."""
        reader = MagicMock()
        if series_ids is None:
            series_ids = ["1.2.3.4"]
        if file_counts is None:
            file_counts = {sid: 100 for sid in series_ids}

        reader.GetGDCMSeriesIDs.return_value = series_ids
        reader.GetGDCMSeriesFileNames.side_effect = (
            lambda path, sid: [f"file_{i}.dcm" for i in range(file_counts.get(sid, 10))]
        )
        reader.HasMetaDataKey.return_value = False
        reader.Execute.return_value = self._make_mock_image()
        return reader

    @patch("src.server.dicom_converter.sitk", create=True)
    def test_single_series(self, mock_sitk_module, tmp_path):
        """단일 시리즈 변환."""
        import SimpleITK as sitk

        dicom_dir = tmp_path / "dicom"
        dicom_dir.mkdir()
        (dicom_dir / "file1.dcm").write_bytes(b"\x00" * 100)

        mock_reader = self._make_mock_reader(["1.2.3"])
        mock_image = self._make_mock_image()
        mock_reader.Execute.return_value = mock_image

        output_path = str(tmp_path / "output.nii.gz")

        with patch("SimpleITK.ImageSeriesReader", return_value=mock_reader):
            with patch("SimpleITK.WriteImage") as mock_write:
                from src.server.dicom_converter import convert_dicom_to_nifti
                result = convert_dicom_to_nifti(str(dicom_dir), output_path)

        assert result["nifti_path"] == output_path
        assert result["n_slices"] == 100
        assert result["spacing"] == [0.5, 0.5, 1.0]
        assert result["size"] == [512, 512, 100]
        mock_write.assert_called_once()

    @patch("SimpleITK.WriteImage")
    @patch("SimpleITK.ImageSeriesReader")
    def test_multiple_series_selects_largest(self, MockReader, mock_write, tmp_path):
        """복수 시리즈 → 슬라이스 수 최대인 시리즈 선택."""
        dicom_dir = tmp_path / "dicom"
        dicom_dir.mkdir()
        (dicom_dir / "file1.dcm").write_bytes(b"\x00")

        reader = self._make_mock_reader(
            ["series_A", "series_B", "series_C"],
            {"series_A": 50, "series_B": 200, "series_C": 80},
        )
        MockReader.return_value = reader

        from src.server.dicom_converter import convert_dicom_to_nifti
        result = convert_dicom_to_nifti(str(dicom_dir), str(tmp_path / "out.nii.gz"))

        assert result["n_slices"] == 200
        # SetFileNames가 series_B의 200개 파일로 호출되었는지 확인
        set_files_call = reader.SetFileNames.call_args[0][0]
        assert len(set_files_call) == 200

    def test_missing_directory(self, tmp_path):
        """존재하지 않는 디렉토리 → FileNotFoundError."""
        from src.server.dicom_converter import convert_dicom_to_nifti
        with pytest.raises(FileNotFoundError):
            convert_dicom_to_nifti(str(tmp_path / "nonexistent"))

    @patch("SimpleITK.ImageSeriesReader")
    def test_no_series_found(self, MockReader, tmp_path):
        """DICOM 시리즈 없음 → ValueError."""
        dicom_dir = tmp_path / "empty_dicom"
        dicom_dir.mkdir()

        reader = MagicMock()
        reader.GetGDCMSeriesIDs.return_value = []
        MockReader.return_value = reader

        from src.server.dicom_converter import convert_dicom_to_nifti
        with pytest.raises(ValueError, match="유효한 DICOM 시리즈 없음"):
            convert_dicom_to_nifti(str(dicom_dir))

    @patch("SimpleITK.WriteImage")
    @patch("SimpleITK.ImageSeriesReader")
    def test_progress_callback(self, MockReader, mock_write, tmp_path):
        """진행률 콜백이 호출되는지 확인."""
        dicom_dir = tmp_path / "dicom"
        dicom_dir.mkdir()
        (dicom_dir / "file.dcm").write_bytes(b"\x00")

        reader = self._make_mock_reader()
        MockReader.return_value = reader

        callback = MagicMock()

        from src.server.dicom_converter import convert_dicom_to_nifti
        convert_dicom_to_nifti(str(dicom_dir), str(tmp_path / "o.nii.gz"),
                               progress_callback=callback)

        assert callback.call_count >= 3  # 스캔, 읽기, 저장, 완료

    @patch("SimpleITK.WriteImage")
    @patch("SimpleITK.ImageSeriesReader")
    def test_default_output_path(self, MockReader, mock_write, tmp_path):
        """output_path 미지정 시 자동 경로 생성."""
        dicom_dir = tmp_path / "my_dicom"
        dicom_dir.mkdir()
        (dicom_dir / "f.dcm").write_bytes(b"\x00")

        reader = self._make_mock_reader()
        MockReader.return_value = reader

        from src.server.dicom_converter import convert_dicom_to_nifti
        result = convert_dicom_to_nifti(str(dicom_dir))

        assert result["nifti_path"] == str(tmp_path / "my_dicom.nii.gz")

    @patch("SimpleITK.WriteImage")
    @patch("SimpleITK.ImageSeriesReader")
    def test_patient_info_extraction(self, MockReader, mock_write, tmp_path):
        """환자 메타데이터 추출."""
        dicom_dir = tmp_path / "dicom"
        dicom_dir.mkdir()
        (dicom_dir / "f.dcm").write_bytes(b"\x00")

        reader = self._make_mock_reader()
        # 메타데이터 설정
        reader.HasMetaDataKey.side_effect = lambda idx, tag: tag in ("0008|0060", "0010|0020")
        reader.GetMetaData.side_effect = lambda idx, tag: {
            "0008|0060": "CT",
            "0010|0020": "PAT001",
        }.get(tag, "")
        MockReader.return_value = reader

        from src.server.dicom_converter import convert_dicom_to_nifti
        result = convert_dicom_to_nifti(str(dicom_dir), str(tmp_path / "o.nii.gz"))

        assert result["patient_info"]["modality"] == "CT"
        assert result["patient_info"]["patient_id"] == "PAT001"


class TestDicomPipelineRequest:
    """DicomPipelineRequest 모델 테스트."""

    def test_defaults(self):
        from src.server.models import DicomPipelineRequest
        req = DicomPipelineRequest(dicom_dir="/tmp/test")
        assert req.engine == "auto"
        assert req.device == "gpu"
        assert req.fast is False
        assert req.smooth is True
        assert req.resolution == 64

    def test_custom(self):
        from src.server.models import DicomPipelineRequest
        req = DicomPipelineRequest(
            dicom_dir="/data/patient1",
            engine="spine_unified",
            device="cpu",
            fast=True,
            modality="MRI",
            smooth=False,
            resolution=128,
        )
        assert req.engine == "spine_unified"
        assert req.modality == "MRI"
        assert req.resolution == 128
