"""인접성 탐색 테스트."""

import numpy as np
import pytest

from backend.preprocessing.adjacency import find_adjacent_pairs, AdjacencyPair


class TestFindAdjacentPairs:
    """find_adjacent_pairs 테스트."""

    def test_two_labels_stacked(self):
        """Z 방향으로 쌓인 두 라벨."""
        vol = np.zeros((3, 3, 6), dtype=np.int32)
        vol[:, :, :3] = 101  # 하부
        vol[:, :, 3:] = 201  # 상부

        pairs = find_adjacent_pairs(vol)
        assert len(pairs) == 1

        p = pairs[0]
        assert p.label_a == 101
        assert p.label_b == 201
        # 경계는 z=2 ↔ z=3 면
        assert len(p.boundary_voxels_a) > 0
        assert len(p.boundary_voxels_b) > 0

    def test_three_labels_sandwich(self):
        """세 라벨 샌드위치 (L4-disc-L5 모사)."""
        vol = np.zeros((3, 3, 9), dtype=np.int32)
        vol[:, :, :3] = 101  # L4
        vol[:, :, 3:6] = 201  # disc
        vol[:, :, 6:] = 102  # L5

        pairs = find_adjacent_pairs(vol)
        assert len(pairs) == 2

        labels = {(p.label_a, p.label_b) for p in pairs}
        assert (101, 201) in labels
        assert (102, 201) in labels

    def test_ignore_background(self):
        """배경(0) 라벨 무시."""
        vol = np.zeros((4, 4, 4), dtype=np.int32)
        vol[1:3, 1:3, :2] = 101
        vol[1:3, 1:3, 2:] = 201

        pairs = find_adjacent_pairs(vol, ignore_labels={0})
        assert len(pairs) == 1
        assert pairs[0].label_a == 101
        assert pairs[0].label_b == 201

    def test_no_adjacency(self):
        """인접하지 않은 라벨 → 빈 결과."""
        vol = np.zeros((5, 5, 5), dtype=np.int32)
        vol[0, 0, 0] = 101
        vol[4, 4, 4] = 201

        pairs = find_adjacent_pairs(vol)
        assert len(pairs) == 0

    def test_uniform_label(self):
        """단일 라벨 → 인접 쌍 없음."""
        vol = np.full((3, 3, 3), 101, dtype=np.int32)

        pairs = find_adjacent_pairs(vol)
        assert len(pairs) == 0

    def test_boundary_voxel_positions(self):
        """경계 복셀 좌표가 실제 경계에 위치."""
        vol = np.zeros((2, 2, 4), dtype=np.int32)
        vol[:, :, :2] = 10
        vol[:, :, 2:] = 20

        pairs = find_adjacent_pairs(vol)
        assert len(pairs) == 1
        p = pairs[0]

        # 라벨 10 쪽 경계는 z=1에 위치
        assert np.all(p.boundary_voxels_a[:, 2] == 1)
        # 라벨 20 쪽 경계는 z=2에 위치
        assert np.all(p.boundary_voxels_b[:, 2] == 2)
