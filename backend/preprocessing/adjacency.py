"""라벨 볼륨 인접성 탐색 모듈.

6-connected 이웃 스캔으로 서로 다른 라벨 사이의 경계 복셀을 찾는다.
부위 무관한 범용 알고리즘.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict, Set


@dataclass
class AdjacencyPair:
    """인접한 두 라벨의 경계 정보.

    Attributes:
        label_a: 첫 번째 라벨 값
        label_b: 두 번째 라벨 값 (label_a < label_b 보장)
        boundary_voxels_a: label_a 측 경계 복셀 인덱스 (N, 3)
        boundary_voxels_b: label_b 측 경계 복셀 인덱스 (N, 3)
    """
    label_a: int
    label_b: int
    boundary_voxels_a: np.ndarray  # (n, 3) IJK 인덱스
    boundary_voxels_b: np.ndarray  # (n, 3) IJK 인덱스


def find_adjacent_pairs(
    label_volume: np.ndarray,
    ignore_labels: Set[int] = frozenset({0}),
) -> List[AdjacencyPair]:
    """인접한 서로 다른 라벨 쌍과 경계 복셀을 찾는다.

    6-connected (면 공유) 이웃을 스캔하여
    서로 다른 라벨이 맞닿는 경계 복셀 좌표를 수집한다.

    Args:
        label_volume: 3D 라벨 볼륨 (I, J, K), 정수 배열
        ignore_labels: 무시할 라벨 (기본: 배경=0)

    Returns:
        인접 쌍 리스트 (label_a < label_b 순서 보장)
    """
    label_volume = np.asarray(label_volume, dtype=np.int32)
    shape = label_volume.shape
    assert len(shape) == 3, f"3D 볼륨 필요, 받은 차원: {len(shape)}"

    # 6-connected 방향 벡터 (양의 방향만 — 중복 방지)
    directions = np.array([
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
    ], dtype=np.int32)

    # 인접 쌍별 경계 복셀 수집
    pair_boundaries: Dict[Tuple[int, int], Tuple[list, list]] = {}

    for d in directions:
        # 슬라이싱으로 이웃 비교 (벡터화)
        di, dj, dk = d
        # 원본 슬라이스
        sl_from = (
            slice(0, shape[0] - di) if di else slice(None),
            slice(0, shape[1] - dj) if dj else slice(None),
            slice(0, shape[2] - dk) if dk else slice(None),
        )
        # 이웃 슬라이스
        sl_to = (
            slice(di, shape[0]) if di else slice(None),
            slice(dj, shape[1]) if dj else slice(None),
            slice(dk, shape[2]) if dk else slice(None),
        )

        vol_from = label_volume[sl_from]
        vol_to = label_volume[sl_to]

        # 서로 다른 라벨인 위치
        diff_mask = vol_from != vol_to

        if not np.any(diff_mask):
            continue

        # 차이가 있는 위치의 인덱스
        indices = np.argwhere(diff_mask)

        for idx in indices:
            i, j, k = idx
            la = int(vol_from[i, j, k])
            lb = int(vol_to[i, j, k])

            # 무시할 라벨 건너뜀
            if la in ignore_labels or lb in ignore_labels:
                continue

            # 정렬 보장 (la < lb)
            voxel_a = np.array([i, j, k]) if la < lb else np.array([i + di, j + dj, k + dk])
            voxel_b = np.array([i + di, j + dj, k + dk]) if la < lb else np.array([i, j, k])
            la, lb = min(la, lb), max(la, lb)

            key = (la, lb)
            if key not in pair_boundaries:
                pair_boundaries[key] = ([], [])

            pair_boundaries[key][0].append(voxel_a)
            pair_boundaries[key][1].append(voxel_b)

    # AdjacencyPair 리스트 구성
    results = []
    for (la, lb), (voxels_a, voxels_b) in sorted(pair_boundaries.items()):
        arr_a = np.array(voxels_a, dtype=np.int32)
        arr_b = np.array(voxels_b, dtype=np.int32)

        # 중복 제거 (같은 경계 복셀이 여러 방향에서 탐지될 수 있음)
        combined_a = np.unique(arr_a, axis=0)
        combined_b = np.unique(arr_b, axis=0)

        results.append(AdjacencyPair(
            label_a=la,
            label_b=lb,
            boundary_voxels_a=combined_a,
            boundary_voxels_b=combined_b,
        ))

    return results
