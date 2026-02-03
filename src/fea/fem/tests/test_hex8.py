"""HEX8 요소 테스트.

8노드 육면체 요소의 형상함수, Gauss 적분, 메쉬 생성 및 해석 테스트.
"""

import pytest
import numpy as np
import taichi as ti


@pytest.fixture(scope="module", autouse=True)
def init_taichi():
    """모듈당 한 번 Taichi 초기화."""
    ti.init(arch=ti.cpu, default_fp=ti.f32)


class TestHEX8ShapeFunctions:
    """HEX8 형상함수 테스트."""

    def test_shape_function_sum(self):
        """형상함수 합 = 1 테스트 (파티션 오브 유니티)."""
        from spine_sim.analysis.fem.core.element import get_shape_functions_hex8

        # 여러 점에서 테스트
        test_points = [
            (0, 0, 0),      # 중심
            (0.5, 0.5, 0.5),
            (-0.5, -0.5, -0.5),
            (1, 1, 1),      # 모서리
            (-1, -1, -1),   # 모서리
        ]

        for xi, eta, zeta in test_points:
            N = get_shape_functions_hex8(xi, eta, zeta)
            assert np.isclose(np.sum(N), 1.0, atol=1e-10), \
                f"Sum of shape functions at ({xi}, {eta}, {zeta}) = {np.sum(N)}"

    def test_shape_function_at_nodes(self):
        """노드에서 형상함수 값 테스트 (Kronecker delta)."""
        from spine_sim.analysis.fem.core.element import get_shape_functions_hex8, HEX8_NODE_COORDS

        for i in range(8):
            xi, eta, zeta = HEX8_NODE_COORDS[i]
            N = get_shape_functions_hex8(xi, eta, zeta)

            for j in range(8):
                expected = 1.0 if i == j else 0.0
                assert np.isclose(N[j], expected, atol=1e-10), \
                    f"N_{j}(node_{i}) = {N[j]}, expected {expected}"

    def test_shape_derivatives_sum(self):
        """형상함수 미분 합 = 0 테스트."""
        from spine_sim.analysis.fem.core.element import get_shape_derivatives_hex8

        test_points = [
            (0, 0, 0),
            (0.5, 0.5, 0.5),
            (-0.5, -0.5, -0.5),
        ]

        for xi, eta, zeta in test_points:
            dN = get_shape_derivatives_hex8(xi, eta, zeta)
            # 각 방향의 미분 합 = 0
            for d in range(3):
                assert np.isclose(np.sum(dN[:, d]), 0.0, atol=1e-10), \
                    f"Sum of dN/d{['xi','eta','zeta'][d]} at ({xi}, {eta}, {zeta}) = {np.sum(dN[:, d])}"


class TestHEX8GaussPoints:
    """HEX8 Gauss 적분점 테스트."""

    def test_gauss_points_count(self):
        """Gauss점 개수 테스트."""
        from spine_sim.analysis.fem.core.element import get_gauss_points_hex8

        points, weights = get_gauss_points_hex8()

        assert points.shape == (8, 3)
        assert weights.shape == (8,)

    def test_gauss_weights_sum(self):
        """Gauss 가중치 합 테스트 (기준 육면체 부피 = 8)."""
        from spine_sim.analysis.fem.core.element import get_gauss_points_hex8

        points, weights = get_gauss_points_hex8()

        # 기준 육면체 [-1,1]^3의 부피 = 2^3 = 8
        assert np.isclose(np.sum(weights), 8.0, atol=1e-10), \
            f"Sum of weights = {np.sum(weights)}, expected 8.0"


class TestHEX8Mesh:
    """HEX8 메쉬 테스트."""

    def test_unit_cube_volume(self):
        """단위 정육면체 부피 테스트."""
        from spine_sim.analysis.fem.core.mesh import FEMesh
        from spine_sim.analysis.fem.core.element import ElementType

        # 단위 정육면체 노드 (0~1 범위)
        nodes = np.array([
            [0.0, 0.0, 0.0],  # 0
            [1.0, 0.0, 0.0],  # 1
            [1.0, 1.0, 0.0],  # 2
            [0.0, 1.0, 0.0],  # 3
            [0.0, 0.0, 1.0],  # 4
            [1.0, 0.0, 1.0],  # 5
            [1.0, 1.0, 1.0],  # 6
            [0.0, 1.0, 1.0],  # 7
        ], dtype=np.float32)

        elements = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)

        mesh = FEMesh(
            n_nodes=8,
            n_elements=1,
            element_type=ElementType.HEX8
        )
        mesh.initialize_from_numpy(nodes, elements)

        # 부피 = 1.0
        vol = mesh.elem_vol.to_numpy()[0]
        assert np.isclose(vol, 1.0, rtol=0.01), f"Volume = {vol}, expected 1.0"

    def test_scaled_cube_volume(self):
        """크기 조절된 정육면체 부피 테스트."""
        from spine_sim.analysis.fem.core.mesh import FEMesh
        from spine_sim.analysis.fem.core.element import ElementType

        # 2x3x4 직육면체
        L, W, H = 2.0, 3.0, 4.0

        nodes = np.array([
            [0.0, 0.0, 0.0],
            [L, 0.0, 0.0],
            [L, W, 0.0],
            [0.0, W, 0.0],
            [0.0, 0.0, H],
            [L, 0.0, H],
            [L, W, H],
            [0.0, W, H],
        ], dtype=np.float32)

        elements = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)

        mesh = FEMesh(
            n_nodes=8,
            n_elements=1,
            element_type=ElementType.HEX8
        )
        mesh.initialize_from_numpy(nodes, elements)

        # 부피 = L * W * H = 24
        expected_vol = L * W * H
        vol = mesh.elem_vol.to_numpy()[0]
        assert np.isclose(vol, expected_vol, rtol=0.01), \
            f"Volume = {vol}, expected {expected_vol}"

    def test_deformation_gradient_identity(self):
        """변형 없을 때 F = I 테스트."""
        from spine_sim.analysis.fem.core.mesh import FEMesh
        from spine_sim.analysis.fem.core.element import ElementType

        nodes = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
            [0.0, 1.0, 1.0],
        ], dtype=np.float32)

        elements = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)

        mesh = FEMesh(n_nodes=8, n_elements=1, element_type=ElementType.HEX8)
        mesh.initialize_from_numpy(nodes, elements)

        # 변위 = 0이면 F = I
        mesh.compute_deformation_gradient()

        F = mesh.F.to_numpy()
        I = np.eye(3)

        # 8개 Gauss점 모두 확인
        for g in range(8):
            assert np.allclose(F[g], I, atol=1e-5), f"F[{g}] = {F[g]}"


class TestHEX8Solver:
    """HEX8 요소 해석 테스트."""

    def test_compression_direction(self):
        """압축 시 변위 방향 테스트."""
        from spine_sim.analysis.fem.core.mesh import FEMesh
        from spine_sim.analysis.fem.core.element import ElementType
        from spine_sim.analysis.fem.material.linear_elastic import LinearElastic
        from spine_sim.analysis.fem.solver.static_solver import StaticSolver

        # 2x2x2 메쉬 (8개 육면체)
        # 노드 생성: 3x3x3 = 27개
        nx, ny, nz = 2, 2, 2
        n_nodes = (nx+1) * (ny+1) * (nz+1)
        n_elements = nx * ny * nz

        spacing = 1.0
        nodes = []
        for k in range(nz+1):
            for j in range(ny+1):
                for i in range(nx+1):
                    nodes.append([i * spacing, j * spacing, k * spacing])
        nodes = np.array(nodes, dtype=np.float32)

        # 요소 연결성
        elements = []
        for ez in range(nz):
            for ey in range(ny):
                for ex in range(nx):
                    # 노드 인덱스
                    n0 = ex + ey * (nx+1) + ez * (nx+1) * (ny+1)
                    n1 = n0 + 1
                    n2 = n0 + (nx+1) + 1
                    n3 = n0 + (nx+1)
                    n4 = n0 + (nx+1) * (ny+1)
                    n5 = n4 + 1
                    n6 = n4 + (nx+1) + 1
                    n7 = n4 + (nx+1)
                    elements.append([n0, n1, n2, n3, n4, n5, n6, n7])
        elements = np.array(elements, dtype=np.int32)

        mesh = FEMesh(n_nodes=n_nodes, n_elements=n_elements, element_type=ElementType.HEX8)
        mesh.initialize_from_numpy(nodes, elements)

        # 바닥면 고정 (z=0)
        bottom_nodes = np.where(nodes[:, 2] < 0.1)[0]
        mesh.set_fixed_nodes(bottom_nodes)

        # 상단면에 압축력
        top_nodes = np.where(nodes[:, 2] > nz*spacing - 0.1)[0]
        forces = np.zeros((len(top_nodes), 3), dtype=np.float32)
        forces[:, 2] = -100.0  # -z 방향
        mesh.set_nodal_forces(top_nodes, forces)

        # 재료 및 솔버
        material = LinearElastic(youngs_modulus=1e6, poisson_ratio=0.3, dim=3)
        solver = StaticSolver(mesh, material)

        result = solver.solve(verbose=False)

        assert result["converged"], "Solver did not converge"

        # 상단 노드가 -z 방향으로 이동
        u = mesh.get_displacements()
        for node in top_nodes:
            assert u[node, 2] < 0, f"Node {node} should move in -z direction"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
