"""복셀 → HEX8 메쉬 변환 모듈.

복셀 중심 좌표를 8노드 육면체(HEX8) 요소로 변환한다.
인접 복셀 간 노드를 좌표 해싱으로 합병하여 연속 메쉬를 생성한다.
"""

import numpy as np
from typing import Tuple


def voxels_to_hex_mesh(
    voxel_centers: np.ndarray,
    spacing: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """복셀 중심 좌표를 HEX8 메쉬로 변환.

    각 복셀의 8개 꼭짓점을 생성하고,
    좌표 해싱으로 인접 복셀 간 공유 노드를 합병한다.

    Args:
        voxel_centers: 복셀 중심 좌표 (n_voxels, 3)
        spacing: 복셀 간격 (3,) — [dx, dy, dz]

    Returns:
        nodes: 합병된 노드 좌표 (n_nodes, 3)
        elements: HEX8 연결성 (n_elements, 8), 0-indexed
    """
    voxel_centers = np.asarray(voxel_centers, dtype=np.float64)
    spacing = np.asarray(spacing, dtype=np.float64)

    n_voxels = len(voxel_centers)
    if n_voxels == 0:
        return np.empty((0, 3)), np.empty((0, 8), dtype=np.int64)

    half = spacing / 2.0

    # HEX8 꼭짓점 오프셋 (표준 순서: 바닥 반시계 → 윗면 반시계)
    # 0: (-,-,-), 1: (+,-,-), 2: (+,+,-), 3: (-,+,-)
    # 4: (-,-,+), 5: (+,-,+), 6: (+,+,+), 7: (-,+,+)
    offsets = np.array([
        [-1, -1, -1],
        [+1, -1, -1],
        [+1, +1, -1],
        [-1, +1, -1],
        [-1, -1, +1],
        [+1, -1, +1],
        [+1, +1, +1],
        [-1, +1, +1],
    ], dtype=np.float64) * half[np.newaxis, :]

    # 모든 복셀의 8개 꼭짓점 좌표 생성 (n_voxels × 8, 3)
    all_vertices = voxel_centers[:, np.newaxis, :] + offsets[np.newaxis, :, :]
    all_vertices = all_vertices.reshape(-1, 3)

    # 좌표 해싱으로 노드 합병
    # 반올림 → 정수 키 (spacing의 1/1000 이내 정밀도)
    precision = np.min(spacing) * 1e-4
    rounded = np.round(all_vertices / precision).astype(np.int64)

    # 고유 좌표 찾기
    _, unique_indices, inverse_map = np.unique(
        rounded, axis=0, return_index=True, return_inverse=True,
    )

    nodes = all_vertices[unique_indices]
    elements = inverse_map.reshape(n_voxels, 8).astype(np.int64)

    return nodes, elements
