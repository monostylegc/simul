"""복셀 → HEX8 변환 테스트."""

import numpy as np
import pytest

from backend.preprocessing.voxel_to_hex import voxels_to_hex_mesh


class TestVoxelsToHexMesh:
    """voxels_to_hex_mesh 테스트."""

    def test_single_voxel(self):
        """단일 복셀 → 8노드, 1요소."""
        centers = np.array([[0.5, 0.5, 0.5]])
        spacing = np.array([1.0, 1.0, 1.0])

        nodes, elements = voxels_to_hex_mesh(centers, spacing)

        assert nodes.shape == (8, 3)
        assert elements.shape == (1, 8)
        # 모든 노드 인덱스가 유효
        assert np.all(elements >= 0)
        assert np.all(elements < 8)
        # 8개 노드가 모두 다른 인덱스
        assert len(np.unique(elements[0])) == 8

    def test_two_adjacent_voxels_share_nodes(self):
        """인접 복셀은 4개 노드를 공유."""
        centers = np.array([
            [0.5, 0.5, 0.5],
            [1.5, 0.5, 0.5],  # x방향 인접
        ])
        spacing = np.array([1.0, 1.0, 1.0])

        nodes, elements = voxels_to_hex_mesh(centers, spacing)

        # 2개 복셀 × 8 = 16 꼭짓점 중 4개 공유 → 12 고유 노드
        assert nodes.shape == (12, 3)
        assert elements.shape == (2, 8)

        # 모든 노드 인덱스 유효
        assert np.all(elements >= 0)
        assert np.all(elements < 12)

    def test_2x2x2_cube(self):
        """2×2×2 복셀 큐브 → 27 노드, 8 요소."""
        centers = []
        for i in range(2):
            for j in range(2):
                for k in range(2):
                    centers.append([0.5 + i, 0.5 + j, 0.5 + k])
        centers = np.array(centers)
        spacing = np.array([1.0, 1.0, 1.0])

        nodes, elements = voxels_to_hex_mesh(centers, spacing)

        assert elements.shape == (8, 8)
        # 2×2×2 격자의 노드 수: (2+1)³ = 27
        assert nodes.shape == (27, 3)

    def test_non_uniform_spacing(self):
        """비균등 간격."""
        centers = np.array([[1.0, 2.0, 3.0]])
        spacing = np.array([2.0, 4.0, 6.0])

        nodes, elements = voxels_to_hex_mesh(centers, spacing)

        assert nodes.shape == (8, 3)
        # 최소/최대 좌표 확인
        np.testing.assert_allclose(nodes.min(axis=0), [0.0, 0.0, 0.0])
        np.testing.assert_allclose(nodes.max(axis=0), [2.0, 4.0, 6.0])

    def test_empty_input(self):
        """빈 입력 → 빈 출력."""
        centers = np.empty((0, 3))
        spacing = np.array([1.0, 1.0, 1.0])

        nodes, elements = voxels_to_hex_mesh(centers, spacing)

        assert nodes.shape == (0, 3)
        assert elements.shape == (0, 8)

    def test_node_coordinates_correct(self):
        """노드 좌표가 복셀 꼭짓점에 정확히 위치."""
        centers = np.array([[5.0, 5.0, 5.0]])
        spacing = np.array([2.0, 2.0, 2.0])

        nodes, elements = voxels_to_hex_mesh(centers, spacing)

        # 8개 노드가 (4,4,4) ~ (6,6,6) 범위
        np.testing.assert_allclose(nodes.min(axis=0), [4.0, 4.0, 4.0])
        np.testing.assert_allclose(nodes.max(axis=0), [6.0, 6.0, 6.0])
