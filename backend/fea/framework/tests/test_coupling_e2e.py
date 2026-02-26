"""FEM-PD/SPG 커플링 E2E 통합 테스트.

실제 CoupledSolver를 사용하여:
1. 초기화 → 영역 분할 → 인터페이스 검증
2. 순수 FEM 참조 해석 (빈 PD 영역)
3. 수동 모드 커플링 해석 (절반 FEM + 절반 PD)
4. 자동 모드 커플링 해석

2D 캔틸레버 빔: 좌측 고정, 우측 하중.
"""

import numpy as np
import pytest
import taichi as ti

ti.init(arch=ti.cpu, default_fp=ti.f64)

# PD 솔버 테스트용 옵션 (반복 수 제한 → 속도 확보)
_PD_TEST_OPTIONS = {"max_iterations": 1000, "tol": 1e-3}


def _create_beam_mesh(nx=8, ny=2, Lx=8.0, Ly=2.0):
    """2D 캔틸레버 빔 QUAD4 메쉬 생성.

    Args:
        nx: x방향 요소 수
        ny: y방향 요소 수
        Lx: 빔 길이
        Ly: 빔 높이

    Returns:
        nodes, elements (int64), n_nodes, n_elements
    """
    dx = Lx / nx
    dy = Ly / ny
    n_nodes = (nx + 1) * (ny + 1)
    n_elements = nx * ny

    nodes = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            nodes.append([i * dx, j * dy])
    nodes = np.array(nodes, dtype=np.float64)

    elements = []
    for ey in range(ny):
        for ex in range(nx):
            n0 = ex + ey * (nx + 1)
            n1 = n0 + 1
            n2 = n0 + (nx + 1) + 1
            n3 = n0 + (nx + 1)
            elements.append([n0, n1, n2, n3])
    elements = np.array(elements, dtype=np.int64)

    return nodes, elements, n_nodes, n_elements


def _get_bc_indices(nodes, nx, ny, Lx):
    """경계조건 인덱스 계산.

    Returns:
        fixed_nodes: x=0 고정 노드
        force_nodes: x=Lx 하중 노드
    """
    fixed_nodes = np.where(np.abs(nodes[:, 0]) < 1e-6)[0].astype(np.int64)
    force_nodes = np.where(np.abs(nodes[:, 0] - Lx) < 1e-6)[0].astype(np.int64)
    return fixed_nodes, force_nodes


# ──────────────────────────────────────────────────────────
# 1. CoupledSolver 초기화 테스트
# ──────────────────────────────────────────────────────────

class TestCoupledSolverInit:
    """커플링 솔버 초기화 및 영역 분할 E2E 테스트."""

    def test_initialization_with_pd_zone(self):
        """CoupledSolver가 PD 영역이 있을 때 정상 초기화되는지 확인."""
        from ..coupling.coupled_solver import CoupledSolver
        from ..material import Material

        nx, ny = 4, 2
        nodes, elements, n_nodes, n_elements = _create_beam_mesh(nx, ny, 4.0, 2.0)
        material = Material(E=1e6, nu=0.3, dim=2)

        # 우측 절반 PD (x > 2.0인 요소)
        pd_mask = np.zeros(n_elements, dtype=bool)
        for ey in range(ny):
            for ex in range(nx):
                if ex >= nx // 2:
                    pd_mask[ex + ey * nx] = True

        fixed_nodes, force_nodes = _get_bc_indices(nodes, nx, ny, 4.0)

        solver = CoupledSolver(
            nodes=nodes,
            elements=elements,
            material=material,
            pd_element_mask=pd_mask,
            particle_method="pd",
            fixed_nodes=fixed_nodes,
            force_nodes=force_nodes,
            force_values=np.array([0.0, -100.0]),
        )

        # 영역 분할 검증
        split = solver.split
        assert len(split.fem_elements) > 0, "FEM 요소가 비어있음"
        assert len(split.pd_nodes) > 0, "PD 입자가 비어있음"
        assert len(split.interface_global) > 0, "인터페이스가 비어있음"

        # 인터페이스 좌표 일치 확인
        fem_intf_coords = split.fem_nodes[split.interface_fem]
        pd_intf_coords = split.pd_nodes[split.interface_pd]
        np.testing.assert_allclose(
            fem_intf_coords, pd_intf_coords, atol=1e-12,
            err_msg="인터페이스 FEM/PD 좌표 불일치",
        )

    def test_initialization_empty_pd(self):
        """PD 영역이 비어있을 때 (전체 FEM) 초기화 확인."""
        from ..coupling.coupled_solver import CoupledSolver
        from ..material import Material

        nx, ny = 4, 2
        nodes, elements, n_nodes, n_elements = _create_beam_mesh(nx, ny, 4.0, 2.0)
        material = Material(E=1e6, nu=0.3, dim=2)

        pd_mask = np.zeros(n_elements, dtype=bool)  # 전부 FEM
        fixed_nodes, force_nodes = _get_bc_indices(nodes, nx, ny, 4.0)

        solver = CoupledSolver(
            nodes=nodes,
            elements=elements,
            material=material,
            pd_element_mask=pd_mask,
            fixed_nodes=fixed_nodes,
            force_nodes=force_nodes,
            force_values=np.array([0.0, -100.0]),
        )

        split = solver.split
        assert len(split.fem_elements) == n_elements
        assert len(split.pd_nodes) == 0
        assert len(split.interface_global) == 0
        assert solver.pd_adapter is None

    def test_fem_submesh_bc_propagation(self):
        """경계조건이 FEM 서브메쉬에 올바르게 전달되는지 확인."""
        from ..coupling.coupled_solver import CoupledSolver
        from ..material import Material

        nx, ny = 4, 2
        nodes, elements, n_nodes, n_elements = _create_beam_mesh(nx, ny, 4.0, 2.0)
        material = Material(E=1e6, nu=0.3, dim=2)

        # 좌측 절반만 PD → 고정 노드(x=0)는 PD 영역에 포함
        pd_mask = np.zeros(n_elements, dtype=bool)
        for ey in range(ny):
            for ex in range(nx):
                if ex < nx // 2:
                    pd_mask[ex + ey * nx] = True

        fixed_nodes, force_nodes = _get_bc_indices(nodes, nx, ny, 4.0)

        solver = CoupledSolver(
            nodes=nodes,
            elements=elements,
            material=material,
            pd_element_mask=pd_mask,
            particle_method="pd",
            fixed_nodes=fixed_nodes,
            force_nodes=force_nodes,
            force_values=np.array([0.0, -100.0]),
        )

        # FEM 서브메쉬에 외력이 설정되었는지 확인
        f_ext = solver.fem_mesh.f_ext.to_numpy()
        assert np.any(f_ext != 0), "FEM 서브메쉬에 외력이 전달되지 않음"

    def test_pd_fixed_bc_merged(self):
        """사용자 고정 BC + 인터페이스 BC가 병합되는지 확인."""
        from ..coupling.coupled_solver import CoupledSolver
        from ..material import Material

        nx, ny = 4, 1
        nodes, elements, n_nodes, n_elements = _create_beam_mesh(nx, ny, 4.0, 1.0)
        material = Material(E=1e6, nu=0.3, dim=2)

        # 좌측 2요소 PD (고정 노드가 PD 영역에 포함)
        pd_mask = np.array([True, True, False, False])
        fixed_nodes = np.where(np.abs(nodes[:, 0]) < 1e-6)[0].astype(np.int64)

        solver = CoupledSolver(
            nodes=nodes,
            elements=elements,
            material=material,
            pd_element_mask=pd_mask,
            particle_method="pd",
            fixed_nodes=fixed_nodes,
        )

        # PD 도메인의 고정 인덱스에 사용자 BC + 인터페이스 모두 포함
        pd_fixed = solver.pd_domain._fixed_indices
        assert pd_fixed is not None
        assert len(pd_fixed) > 0

        # 인터페이스 노드 인덱스가 고정에 포함되어 있는지
        for intf_idx in solver.split.interface_pd:
            assert intf_idx in pd_fixed, \
                f"인터페이스 PD 인덱스 {intf_idx}가 고정 BC에 없음"


# ──────────────────────────────────────────────────────────
# 2. 순수 FEM 참조 해석
# ──────────────────────────────────────────────────────────

class TestPureFEMReference:
    """순수 FEM 해석 참조값 테스트 (커플링 없이)."""

    def test_pure_fem_cantilever(self):
        """순수 FEM 캔틸레버 빔 해석이 올바른 변위를 산출하는지 확인."""
        from ...fem.core.mesh import FEMesh
        from ...fem.core.element import ElementType
        from ...fem.solver.static_solver import StaticSolver
        from ...fem.material.linear_elastic import LinearElastic

        nx, ny = 8, 2
        Lx, Ly = 8.0, 2.0
        nodes, elements, n_nodes, n_elements = _create_beam_mesh(nx, ny, Lx, Ly)

        mesh = FEMesh(n_nodes, n_elements, ElementType.QUAD4)
        mesh.initialize_from_numpy(
            nodes, elements.astype(np.int32),
        )

        fixed_nodes, force_nodes = _get_bc_indices(nodes, nx, ny, Lx)
        mesh.set_fixed_nodes(fixed_nodes)
        forces = np.tile([0.0, -100.0], (len(force_nodes), 1))
        mesh.set_nodal_forces(force_nodes, forces)

        material = LinearElastic(
            youngs_modulus=1e6, poisson_ratio=0.3, dim=2,
        )
        solver = StaticSolver(mesh, material)
        result = solver.solve(verbose=False)

        assert result["converged"], "순수 FEM 해석 미수렴"

        u = mesh.get_displacements()
        # 캔틸레버: 끝단 변위 < 0 (아래 방향)
        right_tip_disp = u[force_nodes, 1]
        assert np.all(right_tip_disp < 0), \
            f"끝단 변위가 음수가 아님: {right_tip_disp}"

        max_disp = np.max(np.abs(u))
        assert max_disp > 1e-10, f"변위가 너무 작음: {max_disp}"

    def test_empty_pd_coupled_equals_pure_fem(self):
        """빈 PD 커플링 = 순수 FEM 결과 일치 확인."""
        from ..coupling.coupled_solver import CoupledSolver
        from ..material import Material
        from ...fem.core.mesh import FEMesh
        from ...fem.core.element import ElementType
        from ...fem.solver.static_solver import StaticSolver
        from ...fem.material.linear_elastic import LinearElastic

        nx, ny = 4, 1
        Lx, Ly = 4.0, 1.0
        nodes, elements, n_nodes, n_elements = _create_beam_mesh(nx, ny, Lx, Ly)
        fixed_nodes, force_nodes = _get_bc_indices(nodes, nx, ny, Lx)

        # 순수 FEM 참조 해석
        mesh = FEMesh(n_nodes, n_elements, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements.astype(np.int32))
        mesh.set_fixed_nodes(fixed_nodes)
        forces = np.tile([0.0, -10.0], (len(force_nodes), 1))
        mesh.set_nodal_forces(force_nodes, forces)

        fem_mat = LinearElastic(youngs_modulus=1e6, poisson_ratio=0.3, dim=2)
        fem_solver = StaticSolver(mesh, fem_mat)
        fem_solver.solve(verbose=False)
        u_fem = mesh.get_displacements()

        # 빈 PD 커플링 해석
        material = Material(E=1e6, nu=0.3, dim=2)
        pd_mask = np.zeros(n_elements, dtype=bool)
        coupled = CoupledSolver(
            nodes=nodes, elements=elements, material=material,
            pd_element_mask=pd_mask,
            fixed_nodes=fixed_nodes,
            force_nodes=force_nodes,
            force_values=np.array([0.0, -10.0]),
        )
        coupled.solve(verbose=False)
        u_coupled = coupled.get_displacements()

        # 결과 비교 — 빈 PD이므로 완전 일치해야 함
        np.testing.assert_allclose(
            u_coupled, u_fem, atol=1e-10,
            err_msg="빈 PD 커플링 결과가 순수 FEM과 불일치",
        )


# ──────────────────────────────────────────────────────────
# 3. 수동 모드 커플링 해석 E2E
# ──────────────────────────────────────────────────────────

class TestCoupledManualE2E:
    """수동 모드 커플링 E2E 테스트.

    4×1 QUAD4 빔의 우측 절반을 PD로 지정하고 커플링 해석한다.
    """

    def test_coupled_solve_runs_without_error(self):
        """CoupledSolver.solve()가 크래시 없이 실행되는지 확인."""
        from ..coupling.coupled_solver import CoupledSolver
        from ..material import Material

        nx, ny = 4, 1
        Lx, Ly = 4.0, 1.0
        nodes, elements, n_nodes, n_elements = _create_beam_mesh(nx, ny, Lx, Ly)
        material = Material(E=1e4, nu=0.3, dim=2, density=1000.0)

        pd_mask = np.zeros(n_elements, dtype=bool)
        for ex in range(nx):
            if ex >= nx // 2:
                pd_mask[ex] = True

        fixed_nodes, force_nodes = _get_bc_indices(nodes, nx, ny, Lx)

        solver = CoupledSolver(
            nodes=nodes, elements=elements, material=material,
            pd_element_mask=pd_mask,
            particle_method="pd",
            coupling_tol=1e-2,
            max_coupling_iters=3,
            fixed_nodes=fixed_nodes,
            force_nodes=force_nodes,
            force_values=np.array([0.0, -10.0]),
            pd_solver_options=_PD_TEST_OPTIONS,
        )

        result = solver.solve(verbose=True)

        assert "converged" in result
        assert "coupling_iterations" in result
        assert result["coupling_iterations"] > 0

        disp = solver.get_displacements()
        assert disp.shape == (n_nodes, 2)

    def test_coupled_displacements_nonzero(self):
        """커플링 해석 후 변위가 비영인지 확인."""
        from ..coupling.coupled_solver import CoupledSolver
        from ..material import Material

        nx, ny = 4, 1
        Lx, Ly = 4.0, 1.0
        nodes, elements, n_nodes, n_elements = _create_beam_mesh(nx, ny, Lx, Ly)
        material = Material(E=1e4, nu=0.3, dim=2, density=1000.0)

        pd_mask = np.zeros(n_elements, dtype=bool)
        for ex in range(nx):
            if ex >= nx // 2:
                pd_mask[ex] = True

        fixed_nodes, force_nodes = _get_bc_indices(nodes, nx, ny, Lx)

        solver = CoupledSolver(
            nodes=nodes, elements=elements, material=material,
            pd_element_mask=pd_mask,
            particle_method="pd",
            coupling_tol=1e-2,
            max_coupling_iters=3,
            fixed_nodes=fixed_nodes,
            force_nodes=force_nodes,
            force_values=np.array([0.0, -10.0]),
            pd_solver_options=_PD_TEST_OPTIONS,
        )

        solver.solve(verbose=False)
        disp = solver.get_displacements()

        # FEM 영역(좌측) 변위는 반드시 비영
        fem_node_mask = nodes[:, 0] < Lx / 2 + 0.1
        fem_disp = disp[fem_node_mask]
        max_fem_disp = np.max(np.abs(fem_disp))
        assert max_fem_disp > 1e-12, \
            f"FEM 영역 변위가 0: max={max_fem_disp}"

    def test_stress_and_damage_accessible(self):
        """커플링 해석 후 응력/손상도 접근 가능한지 확인."""
        from ..coupling.coupled_solver import CoupledSolver
        from ..material import Material

        nx, ny = 4, 1
        Lx, Ly = 4.0, 1.0
        nodes, elements, n_nodes, n_elements = _create_beam_mesh(nx, ny, Lx, Ly)
        material = Material(E=1e4, nu=0.3, dim=2, density=1000.0)

        pd_mask = np.zeros(n_elements, dtype=bool)
        pd_mask[nx // 2:] = True

        fixed_nodes, force_nodes = _get_bc_indices(nodes, nx, ny, Lx)

        solver = CoupledSolver(
            nodes=nodes, elements=elements, material=material,
            pd_element_mask=pd_mask,
            particle_method="pd",
            coupling_tol=1e-2,
            max_coupling_iters=2,
            fixed_nodes=fixed_nodes,
            force_nodes=force_nodes,
            force_values=np.array([0.0, -10.0]),
            pd_solver_options=_PD_TEST_OPTIONS,
        )

        solver.solve(verbose=False)

        stress = solver.get_stress()
        assert stress.shape == (n_nodes,), f"응력 shape 불일치: {stress.shape}"

        damage = solver.get_damage()
        assert damage.shape == (n_nodes,), f"손상도 shape 불일치: {damage.shape}"


# ──────────────────────────────────────────────────────────
# 4. 자동 모드 커플링 E2E
# ──────────────────────────────────────────────────────────

class TestCoupledAutomaticE2E:
    """자동 모드 커플링 E2E 테스트.

    FEM 1차 해석 → 응력 기준 → 자동 영역 분할 → 커플링 해석.
    """

    def test_automatic_no_switching(self):
        """응력 기준이 매우 높으면 전환 없이 FEM만 수행."""
        from ..coupling.coupled_solver import CoupledSolver
        from ..coupling.criteria import SwitchingCriteria
        from ..material import Material

        nx, ny = 4, 1
        Lx, Ly = 4.0, 1.0
        nodes, elements, n_nodes, n_elements = _create_beam_mesh(nx, ny, Lx, Ly)
        material = Material(E=1e6, nu=0.3, dim=2, density=1000.0)

        pd_mask = np.zeros(n_elements, dtype=bool)
        fixed_nodes, force_nodes = _get_bc_indices(nodes, nx, ny, Lx)

        solver = CoupledSolver(
            nodes=nodes, elements=elements, material=material,
            pd_element_mask=pd_mask,
            fixed_nodes=fixed_nodes,
            force_nodes=force_nodes,
            force_values=np.array([0.0, -10.0]),
        )

        criteria = SwitchingCriteria(
            von_mises_threshold=1e15,
            buffer_layers=0,
        )

        result = solver.solve_automatic(criteria, verbose=True)

        assert result.get("fem_only", False), \
            "높은 임계값인데 전환이 발생함"
        assert result["switched_elements"] == 0

    def test_automatic_with_switching(self):
        """응력 기준이 낮으면 일부 요소가 PD로 전환된다."""
        from ..coupling.coupled_solver import CoupledSolver
        from ..coupling.criteria import SwitchingCriteria
        from ..material import Material

        nx, ny = 4, 1
        Lx, Ly = 4.0, 1.0
        nodes, elements, n_nodes, n_elements = _create_beam_mesh(nx, ny, Lx, Ly)
        material = Material(E=1e4, nu=0.3, dim=2, density=1000.0)

        pd_mask = np.zeros(n_elements, dtype=bool)
        fixed_nodes, force_nodes = _get_bc_indices(nodes, nx, ny, Lx)

        solver = CoupledSolver(
            nodes=nodes, elements=elements, material=material,
            pd_element_mask=pd_mask,
            coupling_tol=1e-2,
            max_coupling_iters=2,
            fixed_nodes=fixed_nodes,
            force_nodes=force_nodes,
            force_values=np.array([0.0, -100.0]),
            pd_solver_options=_PD_TEST_OPTIONS,
        )

        criteria = SwitchingCriteria(
            von_mises_threshold=1.0,
            buffer_layers=1,
        )

        result = solver.solve_automatic(criteria, verbose=True)

        assert not result.get("fem_only", True), \
            "낮은 임계값인데 전환이 발생하지 않음"
        assert result["switched_elements"] > 0, \
            "전환된 요소가 0개"
        # 전체 전환되면 pd_only, 부분 전환이면 커플링
        assert result.get("pd_only", False) or result["coupling_iterations"] > 0
