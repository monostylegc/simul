"""라벨맵 → 메쉬 추출 파이프라인 — 각 라벨별 Marching Cubes."""

import numpy as np
from pathlib import Path
from typing import Callable, Optional

from .models import MeshExtractRequest


def extract_meshes(
    request: MeshExtractRequest,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """라벨맵에서 각 라벨별 삼각형 메쉬 추출.

    Args:
        request: 메쉬 추출 요청
        progress_callback: 진행률 콜백 (step, detail)

    Returns:
        {meshes: [{label, name, vertices, faces, material_type, bounds, color}]}
    """
    labels_path = Path(request.labels_path)
    if not labels_path.exists():
        raise FileNotFoundError(f"라벨맵 파일 없음: {labels_path}")

    # 1. 라벨맵 로드
    if progress_callback:
        progress_callback("mesh_extract", {"message": "라벨맵 로드 중..."})

    labels, metadata = _load_labels(labels_path)

    # 2. 추출할 라벨 선택
    unique_labels = np.unique(labels)
    unique_labels = unique_labels[unique_labels > 0]  # 배경 제거

    if request.selected_labels:
        unique_labels = [l for l in unique_labels if l in request.selected_labels]

    total = len(unique_labels)
    if total == 0:
        return {"meshes": []}

    # 3. 라벨별 메쉬 추출
    from src.segmentation.labels import SpineLabel

    meshes = []
    for idx, lbl in enumerate(unique_labels):
        lbl_int = int(lbl)
        try:
            name = SpineLabel(lbl_int).name
        except ValueError:
            name = f"label_{lbl_int}"

        if progress_callback:
            progress_callback("mesh_extract", {
                "message": f"메쉬 추출 중: {name} ({idx + 1}/{total})",
                "current": idx + 1,
                "total": total,
            })

        # 이진 마스크 생성
        mask = (labels == lbl_int).astype(np.float32)

        # 스무딩 (가우시안 블러) — 선택적
        if request.smooth:
            try:
                from scipy.ndimage import gaussian_filter
                mask = gaussian_filter(mask, sigma=0.8)
            except ImportError:
                pass

        # Marching Cubes (scikit-image)
        vertices, faces = _marching_cubes_skimage(mask, metadata, isovalue=0.5)

        if len(vertices) == 0:
            continue

        # 재료 타입 및 색상
        mat_type = SpineLabel.to_material_type(lbl_int)
        mat_name = {0: "empty", 1: "bone", 2: "disc", 3: "soft_tissue"}.get(mat_type, "unknown")
        color = _material_color(mat_name)

        # 바운딩 박스
        vmin = vertices.min(axis=0).tolist()
        vmax = vertices.max(axis=0).tolist()

        meshes.append({
            "label": lbl_int,
            "name": name,
            "vertices": vertices.tolist(),
            "faces": faces.tolist(),
            "material_type": mat_name,
            "color": color,
            "bounds": {"min": vmin, "max": vmax},
            "n_vertices": len(vertices),
            "n_faces": len(faces),
        })

    if progress_callback:
        progress_callback("done", {"message": f"메쉬 추출 완료: {len(meshes)}개"})

    return {"meshes": meshes}


def _load_labels(path: Path):
    """라벨맵 파일 로드 (NIfTI 또는 NPZ)."""
    suffix = path.suffix.lower()
    suffixes = "".join(path.suffixes).lower()

    if suffixes.endswith(".nii.gz") or suffix == ".nii":
        from src.core.volume_io import VolumeLoader
        data, metadata = VolumeLoader.load(str(path))
        return data.astype(np.int32), metadata
    elif suffix == ".npz":
        npz = np.load(str(path))
        labels = npz["labels"]
        # 메타데이터 생략 시 기본값
        from src.core.volume_io import VolumeMetadata
        metadata = VolumeMetadata(
            origin=(0.0, 0.0, 0.0),
            spacing=(1.0, 1.0, 1.0),
            direction=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
            size=tuple(labels.shape),
        )
        return labels.astype(np.int32), metadata
    else:
        raise ValueError(f"지원하지 않는 라벨맵 형식: {suffix}")


def _marching_cubes_skimage(mask: np.ndarray, metadata, isovalue: float = 0.5):
    """scikit-image Marching Cubes를 사용한 메쉬 추출.

    Taichi MC는 Taichi 초기화가 필요하므로, 서버에서는 scikit-image 사용.
    """
    try:
        from skimage.measure import marching_cubes
    except ImportError:
        # 폴백: 빈 메쉬 반환
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32)

    if mask.max() < isovalue:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32)

    try:
        verts, faces, _, _ = marching_cubes(mask, level=isovalue, spacing=metadata.spacing)
    except (ValueError, RuntimeError):
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32)

    # 원점 오프셋 적용
    verts[:, 0] += metadata.origin[0]
    verts[:, 1] += metadata.origin[1]
    verts[:, 2] += metadata.origin[2]

    return verts.astype(np.float32), faces.astype(np.int32)


def _material_color(mat_name: str) -> str:
    """재료 타입 → 16진 색상."""
    colors = {
        "bone": "#e6d5c3",
        "disc": "#6ba3d6",
        "soft_tissue": "#f0a0b0",
        "empty": "#888888",
        "unknown": "#888888",
    }
    return colors.get(mat_name, "#888888")
