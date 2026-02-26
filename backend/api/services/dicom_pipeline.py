"""DICOM 원클릭 파이프라인 서비스 — 변환 → 세그멘테이션 → 메쉬 추출.

ws_handler에서 asyncio 의존 없는 순수 동기 함수로 추출.
각 단계의 진행 상황은 progress_callback을 통해 전달한다.
"""

from typing import Callable, Optional

from ..models import DicomPipelineRequest, SegmentationRequest, MeshExtractRequest


def run_dicom_pipeline(
    request: DicomPipelineRequest,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """DICOM 원클릭 파이프라인 실행.

    3단계를 순차적으로 실행하며 각 단계 완료 시 progress_callback으로 보고한다.

    Args:
        request: DICOM 파이프라인 요청
        progress_callback: 진행률 콜백 (step_name, detail_dict)

    Returns:
        {meshes, nifti_path, labels_path, seg_info, patient_info}

    Raises:
        FileNotFoundError: DICOM 디렉토리 없음
        ValueError: 유효한 DICOM 시리즈 없음
        Exception: 세그멘테이션 또는 메쉬 추출 실패
    """
    def _cb(step: str, detail: dict):
        """progress_callback 안전 호출 래퍼."""
        if progress_callback:
            progress_callback(step, detail)

    # ── 1단계: DICOM → NIfTI 변환 ──
    _cb("dicom_convert", {"message": "DICOM 변환 시작...", "phase": 1})

    from .dicom_convert import convert_dicom_to_nifti
    convert_result = convert_dicom_to_nifti(
        request.dicom_dir,
        progress_callback=progress_callback,
    )
    nifti_path = convert_result["nifti_path"]

    _cb("dicom_convert_done", {
        "message": "DICOM 변환 완료",
        "nifti_path": nifti_path,
        "phase": 1,
        **convert_result,
    })

    # ── 2단계: 세그멘테이션 (modality 자동 감지) ──
    patient_info = convert_result.get("patient_info", {})
    dicom_modality = patient_info.get("modality", "").upper().strip()

    # DICOM modality → 엔진/modality 자동 선택
    # TotalSpineSeg: CT/MRI 모두 지원 (척추골+디스크+척수+척추관)
    engine = request.engine
    modality = request.modality
    if engine == "auto":
        engine = "totalspineseg"
        if dicom_modality == "MR":
            modality = modality or "mri"
        else:
            modality = modality or "ct"

    _cb("segmentation", {
        "message": f"세그멘테이션 시작 (엔진: {engine}, modality: {dicom_modality or 'unknown'})...",
        "phase": 2,
    })

    from .segmentation import run_segmentation
    seg_request = SegmentationRequest(
        input_path=nifti_path,
        engine=engine,
        device=request.device,
        fast=request.fast,
        modality=modality,
    )
    seg_result = run_segmentation(seg_request, progress_callback=progress_callback)

    _cb("segmentation_done", {
        "message": f"세그멘테이션 완료: {seg_result['n_labels']}개 라벨",
        "labels_path": seg_result["labels_path"],
        "phase": 2,
        **seg_result,
    })

    # ── 3단계: 메쉬 추출 ──
    _cb("mesh_extract", {"message": "3D 모델 생성 시작...", "phase": 3})

    from .mesh_extract import extract_meshes
    mesh_request = MeshExtractRequest(
        labels_path=seg_result["labels_path"],
        resolution=request.resolution,
        smooth=request.smooth,
    )
    mesh_result = extract_meshes(mesh_request, progress_callback=progress_callback)

    _cb("done", {"message": f"파이프라인 완료: {len(mesh_result['meshes'])}개 메쉬", "phase": 3})

    # ── 최종 결과 조립 ──
    return {
        "meshes": mesh_result["meshes"],
        "nifti_path": nifti_path,
        "labels_path": seg_result["labels_path"],
        "seg_info": seg_result.get("label_info", []),
        "patient_info": convert_result.get("patient_info", {}),
    }
