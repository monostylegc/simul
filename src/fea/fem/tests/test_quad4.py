"""QUAD4 요소 테스트.

4노드 사각형 요소의 형상함수, Gauss 적분, 메쉬 생성 및 해석 테스트.
"""

import pytest
import numpy as np
import taichi as ti


@pytest.fixture(scope="module", autouse=True)
def init_taichi():
    """모듈당 한 번 Taichi 초기화."""
    ti.init(arch=ti.cpu, default_fp=ti.f32)


class TestQUAD4ShapeFunctions:
    """QUAD4 형상함수 테스트."""

    def test_shape_function_sum(self):
        """형상함수 합 = 1 테스트 (파티션 오브 유니티)."""
        from spine_sim.analysis.fem.core.element import get_shape_functions_quad4

        # 여러 점에서 테스트
        test_points = [
            (0, 0),         # 중심
            (0.5, 0.5),
            (-0.5, -0.5),
            (1, 1),         # 모서리
            (-1, -1),       # 모서리
            (0.7, -0.3),
        ]

        for xi, eta in test_points:
            N = get_shape_functions_quad4(xi, eta)
            assert np.isclose(np.sum(N), 1.0, atol=1e-10), \
                f"Sum of shape functions at ({xi}, {eta}) = {np.sum(N)}"

    def test_shape_function_at_nodes(self):
        """노드에서 형상함수 값 테스트 (Kronecker delta)."""
        from spine_sim.analysis.fem.core.element import get_shape_functions_quad4, QUAD4_NODE_COORDS

        for i in range(4):
            xi, eta = QUAD4_NODE_COORDS[i]
            N = get_shape_functions_quad4(xi, eta)

            for j in range(4):
                expected = 1.0 if i == j else 0.0
                assert np.isclose(N[j], expected, atol=1e-10), \
                    f"N_{j}(node_{i}) = {N[j]}, expected {expected}"

    def test_shape_derivatives_sum(self):
        """형상함수 미분 합 = 0 테스트."""
        from spine_sim.analysis.fem.core.element import get_shape_derivatives_quad4

        test_points = [
            (0, 0),
            (0.5, 0.5),
            (-0.5, -0.5),
        ]

        for xi, eta in test_points:
            dN = get_shape_derivatives_quad4(xi, eta)
            # 각 방향의 미분 합 = 0
            for d in range(2):
                assert np.isclose(np.sum(dN[:, d]), 0.0, atol=1e-10), \
                    f"Sum of dN/d{['xi','eta'][d]} at ({xi}, {eta}) = {np.sum(dN[:, d])}"


class TestQUAD4GaussPoints:
    """QUAD4 Gauss 적분점 테스트."""

    def test_gauss_points_count(self):
        """Gauss점 개수 테스트."""
        from spine_sim.analysis.fem.core.element import get_gauss_points_quad4

        points, weights = get_gauss_points_quad4()

        assert points.shape == (4, 2)
        assert weights.shape == (4,)

    def test_gauss_weights_sum(self):
        """Gauss 가중치 합 테스트 (기준 사각형 면적 = 4)."""
        from spine_sim.analysis.fem.core.element import get_gauss_points_quad4

        points, weights = get_gauss_points_quad4()

        # 기준 사각형 [-1,1]^2의 면적 = 2^2 = 4
        assert np.isclose(np.sum(weights), 4.0, atol=1e-10), \
            f"Sum of weights = {np.sum(weights)}, expected 4.0"


class TestQUAD4Mesh:
    """QUAD4 메쉬 테스트."""

    def test_unit_square_area(self):
        """단위 정사각형 면적 테스트."""
        from spine_sim.analysis.fem.core.mesh import FEMesh
        from spine_sim.analysis.fem.core.element import ElementType

        # 단위 정사각형 노드 (0~1 범위)
        nodes = np.array([
            [0.0, 0.0],  # 0
            [1.0, 0.0],  # 1
            [1.0, 1.0],  # 2
            [0.0, 1.0],  # 3
        ], dtype=np.float32)

        elements = np.array([[0, 1, 2, 3]], dtype=np.int32)

        mesh = FEMesh(
            n_nodes=4,
            n_elements=1,
            element_type=ElementType.QUAD4
        )
        mesh.initialize_from_numpy(nodes, elements)

        # 면적 = 1.0
        area = mesh.elem_vol.to_numpy()[0]
        assert np.isclose(area, 1.0, rtol=0.01), f"Area = {area}, expected 1.0"

    def test_scaled_rectangle_area(self):
        """크기 조절된 직사각형 면적 테스트."""
        from spine_sim.analysis.fem.core.mesh import FEMesh
        from spine_sim.analysis.fem.core.element import ElementType

        # 2x3 직사각형
        L, W = 2.0, 3.0

        nodes = np.array([
            [0.0, 0.0],
            [L, 0.0],
            [L, W],
            [0.0, W],
        ], dtype=np.float32)

        elements = np.array([[0, 1, 2, 3]], dtype=np.int32)

        mesh = FEMesh(
            n_nodes=4,
            n_elements=1,
            element_type=ElementType.QUAD4
        )
        mesh.initialize_from_numpy(nodes, elements)

        # 면적 = L * W = 6
        expected_area = L * W
        area = mesh.elem_vol.to_numpy()[0]
        assert np.isclose(area, expected_area, rtol=0.01), \
            f"Area = {area}, expected {expected_area}"

    def test_deformation_gradient_identity(self):
        """변형 없을 때 F = I 테스트."""
        from spine_sim.analysis.fem.core.mesh import FEMesh
        from spine_sim.analysis.fem.core.element import ElementType

        nodes = np.array([
            [0.0, 0.0],
            [1.0, 0.0],
            [1.0, 1.0],
            [0.0, 1.0],
        ], dtype=np.float32)

        elements = np.array([[0, 1, 2, 3]], dtype=np.int32)

        mesh = FEMesh(n_nodes=4, n_elements=1, element_type=ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        # 변위 = 0이면 F = I
        mesh.compute_deformation_gradient()

        F = mesh.F.to_numpy()
        I = np.eye(2)

        # 4개 Gauss점 모두 확인
        for g in range(4):
            assert np.allclose(F[g], I, atol=1e-5), f"F[{g}] = {F[g]}"


class TestQUAD4Mesh2x2:
    """QUAD4 2x2 메쉬 테스트."""

    def test_2x2_mesh_creation(self):
        """2x2 메쉬 생성 및 총 면적 테스트."""
        from spine_sim.analysis.fem.core.mesh import FEMesh
        from spine_sim.analysis.fem.core.element import ElementType

        # 2x2 메쉬 (4개 사각형)
        # 노드 생성: 3x3 = 9개
        nx, ny = 2, 2
        n_nodes = (nx+1) * (ny+1)
        n_elements = nx * ny

        spacing = 1.0
        nodes = []
        for j in range(ny+1):
            for i in range(nx+1):
                nodes.append([i * spacing, j * spacing])
        nodes = np.array(nodes, dtype=np.float32)

        # 요소 연결성
        elements = []
        for ey in range(ny):
            for ex in range(nx):
                n0 = ex + ey * (nx+1)
                n1 = n0 + 1
                n2 = n0 + (nx+1) + 1
                n3 = n0 + (nx+1)
                elements.append([n0, n1, n2, n3])
        elements = np.array(elements, dtype=np.int32)

        mesh = FEMesh(n_nodes=n_nodes, n_elements=n_elements, element_type=ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        # 총 면적 = 2 x 2 = 4
        elem_vols = mesh.elem_vol.to_numpy()
        total_area = np.sum(elem_vols)
        assert np.isclose(total_area, 4.0, rtol=0.01), f"Total area = {total_area}, expected 4.0"

        # 각 요소 면적 = 1.0
        for e in range(n_elements):
            assert np.isclose(elem_vols[e], 1.0, rtol=0.01), f"Element {e} area = {elem_vols[e]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
