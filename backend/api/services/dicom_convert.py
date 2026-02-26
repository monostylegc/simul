"""DICOM → NIfTI 변환 서비스 — SimpleITK 기반."""

from pathlib import Path
from typing import Callable, Optional


def convert_dicom_to_nifti(
    dicom_dir: str,
    output_path: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """DICOM 시리즈를 NIfTI 파일로 변환.

    Args:
        dicom_dir: DICOM 파일들이 있는 디렉토리 경로
        output_path: 출력 NIfTI 경로 (None이면 dicom_dir 옆에 생성)
        progress_callback: 진행률 콜백 (step, detail)

    Returns:
        {nifti_path, n_slices, spacing, size, patient_info}

    Raises:
        FileNotFoundError: DICOM 디렉토리 없음
        ValueError: 유효한 DICOM 시리즈 없음
    """
    import SimpleITK as sitk

    dicom_path = Path(dicom_dir)
    if not dicom_path.is_dir():
        raise FileNotFoundError(f"DICOM 디렉토리 없음: {dicom_dir}")

    if progress_callback:
        progress_callback("dicom_convert", {"message": "DICOM 시리즈 스캔 중..."})

    # 1. 시리즈 탐색
    reader = sitk.ImageSeriesReader()
    series_ids = reader.GetGDCMSeriesIDs(str(dicom_path))

    if not series_ids:
        raise ValueError(f"유효한 DICOM 시리즈 없음: {dicom_dir}")

    # 2. 복수 시리즈 시 슬라이스 수가 가장 많은 시리즈 선택
    best_series_id = series_ids[0]
    best_count = 0
    for sid in series_ids:
        file_names = reader.GetGDCMSeriesFileNames(str(dicom_path), sid)
        if len(file_names) > best_count:
            best_count = len(file_names)
            best_series_id = sid

    if progress_callback:
        progress_callback("dicom_convert", {
            "message": f"시리즈 선택: {best_series_id[:16]}... ({best_count} slices)",
            "n_series": len(series_ids),
            "selected_slices": best_count,
        })

    # 3. DICOM 시리즈 읽기
    file_names = reader.GetGDCMSeriesFileNames(str(dicom_path), best_series_id)
    reader.SetFileNames(file_names)
    reader.MetaDataDictionaryArrayUpdateOn()
    reader.LoadPrivateTagsOn()

    if progress_callback:
        progress_callback("dicom_convert", {"message": "DICOM 볼륨 읽는 중..."})

    image = reader.Execute()

    # 4. 환자 메타데이터 추출
    patient_info = _extract_patient_info(reader)

    # 5. NIfTI 저장
    if output_path is None:
        output_path = str(dicom_path.parent / f"{dicom_path.name}.nii.gz")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback("dicom_convert", {"message": "NIfTI 파일 저장 중..."})

    sitk.WriteImage(image, str(output_file))

    spacing = list(image.GetSpacing())
    size = list(image.GetSize())

    if progress_callback:
        progress_callback("dicom_convert", {
            "message": f"변환 완료: {size[0]}x{size[1]}x{size[2]}, spacing={spacing}",
        })

    return {
        "nifti_path": str(output_file),
        "n_slices": best_count,
        "spacing": spacing,
        "size": size,
        "patient_info": patient_info,
    }


def _extract_patient_info(reader) -> dict:
    """DICOM 메타데이터에서 환자 정보 추출 (안전)."""
    info = {}
    # DICOM 태그 → 키 매핑
    tag_map = {
        "0008|0060": "modality",
        "0010|0020": "patient_id",
        "0010|0010": "patient_name",
        "0008|0020": "study_date",
        "0008|103e": "series_description",
        "0018|0050": "slice_thickness",
        "0028|0030": "pixel_spacing",
    }

    for tag, key in tag_map.items():
        try:
            if reader.HasMetaDataKey(0, tag):
                info[key] = reader.GetMetaData(0, tag).strip()
        except Exception:
            pass

    return info
