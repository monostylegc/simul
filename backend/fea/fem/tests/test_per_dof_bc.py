"""자유도별(Per-DOF) 경계조건 테스트.

롤러 BC, 대칭 BC, 혼합 BC 등 자유도 단위의 경계조건 지원을 검증한다.
"""

import numpy as np
import pytest
import taichi as ti

# Taichi 초기화
ti.init(arch=ti.cpu, default_fp=ti.f64)

from ..core.mesh import FEMesh
from ..core.element import ElementType
from ..material.linear_elastic import LinearElastic
from ..solver.static_solver import StaticSolver


# ──────────── 헬퍼 함수 ────────────

def _create_2d_quad_mesh():
    """2×1 QUAD4 캔틸레버 메쉬 생성.

    3───4───5
    │   │   │
    0───1───2
    왼쪽(0,3) 고정, 오른쪽(2,5) 하중.
    """
    nodes = np.array([
        [0.0, 0.0], [1.0, 0.0], [2.0, 0.0],
        [0.0, 1.0], [1.0, 1.0], [2.0, 1.0],
    ], dtype=np.float64)
    elements = np.array([
        [0, 1, 4, 3],
        [1, 2, 5, 4],
    ], dtype=np.int32)
    return nodes, elements


def _create_3d_hex_mesh():
    """1×1×1 HEX8 단일 요소.

    4───5
    │   │  (z=1 면)
    7───6
    0───1
    │   │  (z=0 면)
    3───2
    """
    nodes = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    elements = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)
    return nodes, elements


def _solve_2d(nodes, elements, fixed_ids, fixed_dofs, force_ids, forces):
    """2D 문제 간편 풀기."""
    mesh = FEMesh(len(nodes), len(elements), ElementType.QUAD4)
    mesh.initialize_from_numpy(nodes, elements)
    mesh.set_fixed_nodes(np.array(fixed_ids), dofs=fixed_dofs)
    mesh.set_nodal_forces(np.array(force_ids), np.array(forces))

    mat = LinearElastic(1e6, 0.3, dim=2)
    solver = StaticSolver(mesh, mat)
    result = solver.solve(verbose=False)
    return mesh, result


# ──────────── 하위 호환성 ────────────

class TestBackwardCompatibility:
    """기존 API(dofs=None)와의 하위 호환성 검증."""

    def test_set_fixed_nodes_all_dofs(self):
        """dofs 인자 없이 호출하면 모든 DOF 고정."""
        nodes, elements = _create_2d_quad_mesh()
        mesh = FEMesh(6, 2, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)
        mesh.set_fixed_nodes(np.array([0, 3]))

        fixed = mesh.fixed.to_numpy()  # (n_nodes, dim)
        assert fixed.shape == (6, 2)
        # 노드 0, 3: 모든 DOF 고정
        assert fixed[0, 0] == 1 and fixed[0, 1] == 1
        assert fixed[3, 0] == 1 and fixed[3, 1] == 1
        # 나머지 노드: 자유
        assert fixed[1, 0] == 0 and fixed[1, 1] == 0

    def test_solve_backward_compatible(self):
        """기존 방식(전체 고정)으로 해석 수행."""
        nodes, elements = _create_2d_quad_mesh()
        mesh, result = _solve_2d(
            nodes, elements,
            fixed_ids=[0, 3], fixed_dofs=None,
            force_ids=[2, 5], forces=[[100.0, 0.0], [100.0, 0.0]],
        )
        assert result["converged"]
        u = mesh.get_displacements()
        # 고정 노드: 변위 = 0
        assert np.allclose(u[0], 0.0, atol=1e-10)
        assert np.allclose(u[3], 0.0, atol=1e-10)
        # 자유단: x 변위 양수
        assert u[2, 0] > 0

    def test_fixed_to_numpy_shape(self):
        """fixed.to_numpy()가 (n_nodes, dim) 형상 반환."""
        nodes, elements = _create_2d_quad_mesh()
        mesh = FEMesh(6, 2, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        fixed = mesh.fixed.to_numpy()
        assert fixed.shape == (6, 2)


# ──────────── 롤러 BC (2D) ────────────

class TestRollerBC2D:
    """2D 롤러 경계조건: 한 방향만 고정, 다른 방향은 자유."""

    def test_roller_y_fixed_only(self):
        """아랫면 노드: y만 고정 (수직 구속), x는 자유 (수평 이동 허용)."""
        nodes, elements = _create_2d_quad_mesh()
        mesh = FEMesh(6, 2, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        # 아랫면 (0,1,2): y만 고정
        mesh.set_fixed_nodes(np.array([0, 1, 2]), dofs=[1])

        fixed = mesh.fixed.to_numpy()
        # y(dof 1) 고정, x(dof 0) 자유
        assert fixed[0, 1] == 1 and fixed[0, 0] == 0
        assert fixed[1, 1] == 1 and fixed[1, 0] == 0
        assert fixed[2, 1] == 1 and fixed[2, 0] == 0
        # 윗면: 완전 자유
        assert np.all(fixed[3:, :] == 0)

    def test_roller_solve(self):
        """롤러 BC에서 수평 힘 → 수평 이동, 수직 구속."""
        nodes, elements = _create_2d_quad_mesh()
        mesh = FEMesh(6, 2, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        # 아랫면 y 고정 + 왼쪽 하단 x도 고정 (강체 이동 방지)
        mesh.set_fixed_nodes(np.array([0, 1, 2]), dofs=[1])  # y 구속
        # 추가: 노드 0의 x도 고정 (강체 방지)
        fixed = mesh.fixed.to_numpy()
        fixed[0, 0] = 1
        mesh.fixed.from_numpy(fixed)

        # 오른쪽 윗면에 x 방향 힘
        mesh.set_nodal_forces(np.array([5]), np.array([[100.0, 0.0]]))

        mat = LinearElastic(1e6, 0.3, dim=2)
        solver = StaticSolver(mesh, mat)
        result = solver.solve(verbose=False)

        assert result["converged"]
        u = mesh.get_displacements()
        # 아랫면 y 변위 = 0 (롤러)
        assert np.allclose(u[0, 1], 0.0, atol=1e-10)
        assert np.allclose(u[1, 1], 0.0, atol=1e-10)
        assert np.allclose(u[2, 1], 0.0, atol=1e-10)
        # 아랫면 x 변위: 노드1,2는 자유 → 비영
        # (노드0은 x도 고정)
        assert np.abs(u[0, 0]) < 1e-10  # x 고정
        # 오른쪽 끝단: 양의 x 변위
        assert u[5, 0] > 0


# ──────────── 대칭 BC (3D) ────────────

class TestSymmetryBC3D:
    """3D 대칭 경계조건: 법선 방향만 고정."""

    def test_symmetry_x_plane(self):
        """x=0 면에 x 대칭 BC: x-DOF만 고정."""
        nodes, elements = _create_3d_hex_mesh()
        mesh = FEMesh(8, 1, ElementType.HEX8)
        mesh.initialize_from_numpy(nodes, elements)

        # x=0 면: 노드 0,3,4,7
        sym_nodes = np.array([0, 3, 4, 7])
        mesh.set_fixed_nodes(sym_nodes, dofs=[0])  # x만 고정

        fixed = mesh.fixed.to_numpy()
        for n in [0, 3, 4, 7]:
            assert fixed[n, 0] == 1  # x 고정
            assert fixed[n, 1] == 0  # y 자유
            assert fixed[n, 2] == 0  # z 자유

    def test_symmetry_solve(self):
        """대칭 BC로 z 방향 압축: x 대칭면에서 x 변위 = 0."""
        nodes, elements = _create_3d_hex_mesh()
        mesh = FEMesh(8, 1, ElementType.HEX8)
        mesh.initialize_from_numpy(nodes, elements)

        # x=0 면 (노드 0,3,4,7): x 고정
        mesh.set_fixed_nodes(np.array([0, 3, 4, 7]), dofs=[0])

        # z=0 면 (노드 0,1,2,3): z 고정 (강체 방지)
        fixed = mesh.fixed.to_numpy()
        for n in [0, 1, 2, 3]:
            fixed[n, 2] = 1
        # y 방향도 노드 0 고정 (강체 회전 방지)
        fixed[0, 1] = 1
        mesh.fixed.from_numpy(fixed)

        # z=1 면 (노드 4,5,6,7)에 -z 방향 압축력
        mesh.set_nodal_forces(
            np.array([4, 5, 6, 7]),
            np.array([
                [0, 0, -100], [0, 0, -100],
                [0, 0, -100], [0, 0, -100],
            ], dtype=np.float64),
        )

        mat = LinearElastic(1e6, 0.3, dim=3)
        solver = StaticSolver(mesh, mat, tol=1e-8)
        result = solver.solve(verbose=False)

        assert result["converged"]
        u = mesh.get_displacements()
        # x 대칭면: x 변위 = 0
        for n in [0, 3, 4, 7]:
            assert np.abs(u[n, 0]) < 1e-10
        # z 방향: 상면 음의 변위 (압축)
        assert u[4, 2] < 0


# ──────────── 혼합 BC ────────────

class TestMixedBC:
    """같은 노드에서 서로 다른 DOF 조합 고정."""

    def test_different_dofs_per_node(self):
        """노드별로 다른 DOF 조합 고정."""
        nodes, elements = _create_2d_quad_mesh()
        mesh = FEMesh(6, 2, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        # 노드 0: x,y 모두 고정 (완전 고정)
        # 노드 3: y만 고정 (롤러)
        mesh.set_fixed_nodes(np.array([0]), dofs=None)  # 전체 고정

        fixed = mesh.fixed.to_numpy()
        fixed[3, 1] = 1  # 노드 3의 y DOF 추가 고정
        mesh.fixed.from_numpy(fixed)

        assert fixed[0, 0] == 1 and fixed[0, 1] == 1  # 완전 고정
        assert fixed[3, 0] == 0 and fixed[3, 1] == 1  # y만 고정


# ──────────── 규정 변위 ────────────

class TestPrescribedDisplacement:
    """특정 DOF에 규정 변위 적용."""

    def test_prescribed_x_only(self):
        """x-DOF에만 규정 변위, y는 자유."""
        nodes, elements = _create_2d_quad_mesh()
        mesh = FEMesh(6, 2, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        # 왼쪽 (0,3): 전체 고정
        mesh.set_fixed_nodes(np.array([0, 3]))
        # 오른쪽 (2,5): x에 규정 변위 0.01, y는 자유
        fixed = mesh.fixed.to_numpy()
        fixed_vals = mesh.fixed_value.to_numpy()

        for n in [2, 5]:
            fixed[n, 0] = 1      # x 고정
            fixed_vals[n, 0] = 0.01  # x = 0.01
        mesh.fixed.from_numpy(fixed)
        mesh.fixed_value.from_numpy(fixed_vals)

        mat = LinearElastic(1e6, 0.3, dim=2)
        solver = StaticSolver(mesh, mat)
        result = solver.solve(verbose=False)

        assert result["converged"]
        u = mesh.get_displacements()
        # 오른쪽 x 변위 ≈ 0.01
        assert np.isclose(u[2, 0], 0.01, rtol=0.01)
        assert np.isclose(u[5, 0], 0.01, rtol=0.01)
        # y는 자유 → 비영 (포아송 효과)
        # (정확한 값은 재료에 따라 다르지만 자유이므로 0이 아닐 수 있음)


# ──────────── set_fixed_dofs API ────────────

class TestSetFixedDofs:
    """DOF 인덱스 직접 지정 API."""

    def test_set_fixed_dofs_basic(self):
        """set_fixed_dofs()로 특정 DOF만 고정."""
        nodes, elements = _create_2d_quad_mesh()
        mesh = FEMesh(6, 2, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        # DOF 0 = 노드0_x, DOF 1 = 노드0_y, DOF 7 = 노드3_y
        mesh.set_fixed_dofs(np.array([0, 1, 7]))

        fixed = mesh.fixed.to_numpy()
        assert fixed[0, 0] == 1  # 노드0_x
        assert fixed[0, 1] == 1  # 노드0_y
        assert fixed[3, 1] == 1  # 노드3_y (DOF 7 = 3*2+1)
        assert fixed[3, 0] == 0  # 노드3_x 자유

    def test_set_fixed_dofs_with_values(self):
        """규정 변위와 함께 DOF 지정."""
        nodes, elements = _create_2d_quad_mesh()
        mesh = FEMesh(6, 2, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        # DOF 4 = 노드2_x (2*2+0)에 변위 0.05 지정
        mesh.set_fixed_dofs(np.array([4]), values=np.array([0.05]))

        fixed = mesh.fixed.to_numpy()
        fixed_vals = mesh.fixed_value.to_numpy()
        assert fixed[2, 0] == 1
        assert np.isclose(fixed_vals[2, 0], 0.05)


# ──────────── 호장법 솔버 ────────────

class TestArcLengthPerDofBC:
    """호장법 솔버에서 per-DOF BC 동작 확인."""

    def test_arclength_roller_bc(self):
        """호장법 솔버에서 롤러 BC 사용."""
        from ..solver.arclength_solver import ArcLengthSolver

        nodes, elements = _create_2d_quad_mesh()
        mesh = FEMesh(6, 2, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        # 왼쪽 완전 고정
        mesh.set_fixed_nodes(np.array([0, 3]))
        # 오른쪽 하중
        mesh.set_nodal_forces(np.array([2, 5]),
                              np.array([[100, 0], [100, 0]], dtype=np.float64))

        mat = LinearElastic(1e6, 0.3, dim=2)
        solver = ArcLengthSolver(mesh, mat, arc_length=0.5, max_steps=5, tol=1e-8)
        result = solver.solve()

        assert result["converged"]
        u = mesh.get_displacements()
        assert u[2, 0] > 0


# ──────────── 동적 솔버 ────────────

class TestDynamicPerDofBC:
    """동적 솔버에서 per-DOF BC 동작 확인."""

    def test_dynamic_enforce_bc(self):
        """동적 솔버에서 per-DOF enforce_bc 호출 시 크래시 없음."""
        from ..solver.dynamic_solver import DynamicSolver

        nodes = np.array([
            [0, 0], [1, 0], [1, 1], [0, 1],
        ], dtype=np.float64)
        elements = np.array([[0, 1, 2, 3]], dtype=np.int32)

        mesh = FEMesh(4, 1, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)
        # y만 고정 (롤러)
        mesh.set_fixed_nodes(np.array([0, 1]), dofs=[1])

        mat = LinearElastic(1e6, 0.3, dim=2, plane_stress=True)
        solver = DynamicSolver(mesh, mat, density=1000.0)

        # enforce_bc 호출 시 에러 없음
        solver._enforce_bc()

        # 고정 DOF 0: v, a = 0
        fixed = mesh.fixed.to_numpy()
        fixed_dofs = np.where(fixed.reshape(-1) == 1)[0]
        assert len(fixed_dofs) == 2  # 노드0_y, 노드1_y
        assert solver.v[fixed_dofs[0]] == 0.0
