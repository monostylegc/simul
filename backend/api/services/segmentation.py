"""세그멘테이션 서비스 — NIfTI → 세그멘테이션 → 표준 라벨맵."""

import logging
from pathlib import Path
from typing import Callable, Optional

from ..models import SegmentationRequest
from .gpu_detect import resolve_device

logger = logging.getLogger(__name__)


def run_segmentation(
    request: SegmentationRequest,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """NIfTI 입력을 세그멘테이션하여 표준 라벨맵 생성.

    Args:
        request: 세그멘테이션 요청
        progress_callback: 진행률 콜백 (step, detail)

    Returns:
        {labels_path, n_labels, label_names, label_info}
    """
    input_path = Path(request.input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {input_path}")

    output_dir = input_path.parent / "segmentation"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 0. GPU 사전 감지 — "gpu" 요청 시 CUDA 사용 가능 여부 확인
    actual_device = resolve_device(request.device)
    if actual_device != request.device:
        logger.info("디바이스 자동 전환: %s → %s", request.device, actual_device)
        if progress_callback:
            progress_callback("segment", {
                "message": f"GPU 사용 불가 → CPU 모드로 전환",
            })
        request = request.model_copy(update={"device": actual_device})
    else:
        if actual_device == "gpu" and progress_callback:
            from .gpu_detect import detect_gpu
            gpu_info = detect_gpu()
            progress_callback("segment", {
                "message": f"GPU 감지: {gpu_info.name} ({gpu_info.memory_mb}MB)",
            })

    # 1. 세그멘테이션 엔진 생성
    if progress_callback:
        progress_callback("segment", {"message": f"엔진 로드 중: {request.engine}..."})

    from backend.segmentation.factory import create_engine
    engine = create_engine(request.engine)

    # 2. 세그멘테이션 실행
    if progress_callback:
        progress_callback("segment", {"message": "세그멘테이션 실행 중..."})

    labels_path = output_dir / "labels.nii.gz"
    # 엔진별 segment 호출 (spine_unified는 modality 전달)
    seg_kwargs = dict(
        input_path=str(input_path),
        output_path=str(labels_path),
        device=request.device,
        fast=request.fast,
    )
    if request.engine == "spine_unified" and request.modality:
        seg_kwargs["modality"] = request.modality

    actual_labels_path = None
    try:
        actual_labels_path = engine.segment(**seg_kwargs)
    except Exception as gpu_err:
        # GPU 실패 시 CPU 자동 폴백
        if seg_kwargs.get("device", "gpu") != "cpu":
            if progress_callback:
                progress_callback("segment", {
                    "message": f"GPU 실패 ({gpu_err}), CPU로 재시도...",
                })
            seg_kwargs["device"] = "cpu"
            actual_labels_path = engine.segment(**seg_kwargs)
        else:
            raise

    # 엔진이 반환한 실제 경로 사용 (TotalSpineSeg는 step2_output/ 하위에 저장)
    if actual_labels_path and Path(actual_labels_path).exists():
        labels_path = Path(actual_labels_path)
    elif not labels_path.exists():
        # 폴백: output_dir에서 .nii.gz 파일 탐색
        nii_files = list(output_dir.rglob("*.nii.gz"))
        if nii_files:
            labels_path = nii_files[0]
        else:
            raise FileNotFoundError(
                f"세그멘테이션 출력 파일을 찾을 수 없습니다: {output_dir}"
            )

    if progress_callback:
        progress_callback("segment", {
            "message": f"라벨맵 로드: {labels_path.name}",
        })

    # 3. 표준 라벨로 변환
    if progress_callback:
        progress_callback("segment", {"message": "라벨 변환 중..."})

    import numpy as np
    from backend.utils.volume_io import VolumeLoader
    from backend.segmentation.labels import (
        SpineLabel,
        convert_to_standard,
        build_dynamic_totalspineseg_mapping,
        TOTALSEG_TO_STANDARD,
        TOTALSPINESEG_TO_STANDARD,
        NNUNET_SPINE_TO_STANDARD,
    )

    raw_data, metadata = VolumeLoader.load(str(labels_path))

    # 엔진별 매핑 선택
    mapping = None

    # TotalSpineSeg: step1_levels가 있으면 동적 매핑 사용 (레벨 식별 보정)
    if request.engine == "totalspineseg":
        step1_levels_dir = labels_path.parent.parent / "step1_levels"
        step1_levels_files = list(step1_levels_dir.glob("*.nii.gz")) if step1_levels_dir.exists() else []
        if step1_levels_files:
            if progress_callback:
                progress_callback("segment", {
                    "message": "step1_levels 기반 레벨 보정 중...",
                })
            levels_data, _ = VolumeLoader.load(str(step1_levels_files[0]))
            dynamic_mapping = build_dynamic_totalspineseg_mapping(
                levels_data.astype(np.int32),
                raw_data.astype(np.int32),
            )
            if dynamic_mapping:
                mapping = dynamic_mapping

    if mapping is None:
        _ENGINE_MAPPINGS = {
            "totalseg": TOTALSEG_TO_STANDARD,
            "totalspineseg": TOTALSPINESEG_TO_STANDARD,
            "spine_unified": NNUNET_SPINE_TO_STANDARD,
        }
        mapping = _ENGINE_MAPPINGS.get(request.engine, TOTALSEG_TO_STANDARD)

    std_labels = convert_to_standard(raw_data.astype(np.int32), mapping)

    # 표준 라벨맵 저장
    std_path = output_dir / "labels_standard.nii.gz"
    try:
        import SimpleITK as sitk
        img = sitk.GetImageFromArray(std_labels.transpose(2, 1, 0).astype(np.int16))
        img.SetOrigin(metadata.origin)
        img.SetSpacing(metadata.spacing)
        sitk.WriteImage(img, str(std_path))
    except ImportError:
        # SimpleITK 없으면 numpy 저장
        std_path = output_dir / "labels_standard.npz"
        np.savez_compressed(str(std_path), labels=std_labels)

    # 4. 라벨 정보 수집
    unique_labels = np.unique(std_labels)
    unique_labels = unique_labels[unique_labels > 0]  # 배경 제거

    label_names = {}
    label_info = []
    for lbl in unique_labels:
        lbl_int = int(lbl)
        try:
            name = SpineLabel(lbl_int).name
        except ValueError:
            name = f"label_{lbl_int}"
        label_names[lbl_int] = name
        mat_type = SpineLabel.to_material_type(lbl_int)
        mat_name = {0: "empty", 1: "bone", 2: "disc", 3: "soft_tissue"}.get(mat_type, "unknown")
        label_info.append({
            "label": lbl_int,
            "name": name,
            "material_type": mat_name,
            "voxel_count": int(np.sum(std_labels == lbl_int)),
        })

    if progress_callback:
        progress_callback("done", {"message": f"세그멘테이션 완료: {len(unique_labels)}개 라벨"})

    return {
        "labels_path": str(std_path),
        "n_labels": len(unique_labels),
        "label_names": label_names,
        "label_info": label_info,
        "metadata": {
            "origin": list(metadata.origin),
            "spacing": list(metadata.spacing),
            "size": list(metadata.size),
        },
    }
