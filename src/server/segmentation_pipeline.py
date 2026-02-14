"""세그멘테이션 서버 파이프라인 — NIfTI → 세그멘테이션 → 표준 라벨맵."""

from pathlib import Path
from typing import Callable, Optional

from .models import SegmentationRequest


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

    # 1. 세그멘테이션 엔진 생성
    if progress_callback:
        progress_callback("segment", {"message": f"엔진 로드 중: {request.engine}..."})

    from src.segmentation.factory import create_engine
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

    try:
        engine.segment(**seg_kwargs)
    except Exception as gpu_err:
        # GPU 실패 시 CPU 자동 폴백
        if seg_kwargs.get("device", "gpu") != "cpu":
            if progress_callback:
                progress_callback("segment", {
                    "message": f"GPU 실패 ({gpu_err}), CPU로 재시도...",
                })
            seg_kwargs["device"] = "cpu"
            engine.segment(**seg_kwargs)
        else:
            raise

    # 3. 표준 라벨로 변환
    if progress_callback:
        progress_callback("segment", {"message": "라벨 변환 중..."})

    import numpy as np
    from src.core.volume_io import VolumeLoader
    from src.segmentation.labels import (
        SpineLabel,
        convert_to_standard,
        TOTALSEG_TO_STANDARD,
        TOTALSPINESEG_TO_STANDARD,
        NNUNET_SPINE_TO_STANDARD,
    )

    raw_data, metadata = VolumeLoader.load(str(labels_path))

    # 엔진별 매핑 선택
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
