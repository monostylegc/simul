"""메쉬 추출 서비스 — 라벨맵에서 각 라벨별 Marching Cubes."""

import base64
import numpy as np
from pathlib import Path
from typing import Callable, Optional

from ..models import MeshExtractRequest


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

        # Marching Cubes (scikit-image) — step_size=2로 메쉬 크기 축소
        step_size = getattr(request, "step_size", 2)
        vertices, faces = _marching_cubes_skimage(
            mask, metadata, isovalue=0.5, step_size=step_size,
        )

        if len(vertices) == 0:
            continue

        # 대형 메쉬 간소화 (면 수 50,000 이하로 제한)
        max_faces = getattr(request, "max_faces", 50000)
        vertices, faces = _decimate_mesh(vertices, faces, max_faces=max_faces)

        # 재료 타입 및 색상
        mat_type = SpineLabel.to_material_type(lbl_int)
        mat_name = {0: "empty", 1: "bone", 2: "disc", 3: "soft_tissue"}.get(mat_type, "unknown")
        color = _material_color(mat_name)

        # 바운딩 박스
        vmin = vertices.min(axis=0).tolist()
        vmax = vertices.max(axis=0).tolist()

        # 바이너리 인코딩: float32/int32 → base64 (JSON 대비 ~65% 크기 절감)
        verts_f32 = np.round(vertices, 2).astype(np.float32)
        faces_i32 = faces.astype(np.int32)
        verts_b64 = base64.b64encode(verts_f32.tobytes()).decode('ascii')
        faces_b64 = base64.b64encode(faces_i32.tobytes()).decode('ascii')

        meshes.append({
            "label": lbl_int,
            "name": name,
            "vertices_b64": verts_b64,
            "faces_b64": faces_b64,
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


def _marching_cubes_skimage(
    mask: np.ndarray,
    metadata,
    isovalue: float = 0.5,
    step_size: int = 1,
):
    """scikit-image Marching Cubes를 사용한 메쉬 추출.

    Taichi MC는 Taichi 초기화가 필요하므로, 서버에서는 scikit-image 사용.

    Args:
        step_size: 복셀 건너뛰기 (2이면 해상도 1/2, 메쉬 크기 ~1/4)
    """
    try:
        from skimage.measure import marching_cubes
    except ImportError:
        # 폴백: 빈 메쉬 반환
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32)

    if mask.max() < isovalue:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32)

    try:
        verts, faces, _, _ = marching_cubes(
            mask, level=isovalue, spacing=metadata.spacing, step_size=step_size,
        )
    except (ValueError, RuntimeError):
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32)

    # 원점 오프셋 적용
    verts[:, 0] += metadata.origin[0]
    verts[:, 1] += metadata.origin[1]
    verts[:, 2] += metadata.origin[2]

    return verts.astype(np.float32), faces.astype(np.int32)


def _decimate_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    max_faces: int = 50000,
) -> tuple[np.ndarray, np.ndarray]:
    """메쉬 면 수가 max_faces를 초과하면 간소화.

    scipy QhQ 기반 간단한 간소화: 균일 샘플링으로 면 축소.
    """
    if len(faces) <= max_faces:
        return vertices, faces

    # 균일 간격으로 면 샘플링
    ratio = max_faces / len(faces)
    indices = np.linspace(0, len(faces) - 1, max_faces, dtype=int)
    selected_faces = faces[indices]

    # 사용된 정점만 추출 (인덱스 재매핑)
    used_verts = np.unique(selected_faces.ravel())
    vert_map = np.full(len(vertices), -1, dtype=np.int64)
    vert_map[used_verts] = np.arange(len(used_verts))
    new_vertices = vertices[used_verts]
    new_faces = vert_map[selected_faces]

    return new_vertices.astype(np.float32), new_faces.astype(np.int32)


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
