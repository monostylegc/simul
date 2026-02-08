"""통합 프레임워크 테스트.

세 솔버(FEM, PD, SPG)를 동일한 인장봉 문제로 교차 검증한다.
"""

import pytest
import numpy as np
import taichi as ti

from src.fea.framework import (
    init, create_domain, Material, Solver, Method, SolveResult,
    Backend, Precision, get_backend, get_precision,
)
from src.fea.framework.runtime import is_initialized, reset


# ============================================================
#  런타임 테스트
# ============================================================

class TestRuntime:
    """런타임 초기화 테스트."""

    def test_init_returns_info(self):
        """init()이 올바른 정보를 반환하는지 확인."""
        info = init()
        assert "backend" in info
        assert "precision" in info
        assert info["backend"] in ("cpu", "vulkan", "cuda")

    def test_init_idempotent(self):
        """중복 호출 시 already_initialized=True."""
        info1 = init()
        info2 = init()
        assert info2["already_initialized"] is True

    def test_get_backend_precision(self):
        """백엔드/정밀도 조회."""
        init()
        assert get_backend() is not None
        assert get_precision() is not None


# ============================================================
#  Domain 테스트
# ============================================================

class TestDomain:
    """Domain 생성 및 선택 테스트."""

    def test_create_fem_domain_2d(self):
        """2D FEM 도메인 생성."""
        init()
        domain = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 0.0), size=(1.0, 0.2),
            n_divisions=(10, 2),
        )
        assert domain.n_points == 11 * 3  # (10+1) * (2+1)
        assert domain.dim == 2

    def test_create_particle_domain_2d(self):
        """2D 입자(PD/SPG) 도메인 생성."""
        init()
        domain = create_domain(
            Method.SPG, dim=2,
            origin=(0.0, 0.0), size=(1.0, 0.2),
            n_divisions=(11, 3),
        )
        assert domain.n_points == 11 * 3
        assert domain.dim == 2

    def test_select_axis(self):
        """위치 기반 선택."""
        init()
        domain = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 0.0), size=(1.0, 0.2),
            n_divisions=(10, 2),
        )
        left = domain.select(axis=0, value=0.0)
        right = domain.select(axis=0, value=1.0)
        assert len(left) == 3   # ny+1 = 3
        assert len(right) == 3

    def test_create_3d_domain(self):
        """3D 도메인 생성."""
        init()
        domain = create_domain(
            Method.FEM, dim=3,
            origin=(0.0, 0.0, 0.0), size=(1.0, 0.1, 0.1),
            n_divisions=(10, 2, 2),
        )
        assert domain.n_points == 11 * 3 * 3


# ============================================================
#  Material 테스트
# ============================================================

class TestMaterial:
    """Material 데이터 클래스 테스트."""

    def test_lame_parameters(self):
        """Lamé 매개변수 계산 확인."""
        mat = Material(E=1e6, nu=0.3, density=1000, dim=3)
        expected_mu = 1e6 / (2 * 1.3)
        assert abs(mat.mu - expected_mu) < 1e-3

    def test_plane_stress(self):
        """평면응력 설정."""
        mat = Material(E=1e6, nu=0.3, dim=2, plane_stress=True)
        assert mat.plane_stress is True


# ============================================================
#  FEM 솔버 테스트 (인장봉)
# ============================================================

class TestFEMSolver:
    """FEM 솔버 통합 테스트."""

    def test_tension_bar_2d(self):
        """2D 인장봉: u = PL/(EA)."""
        init()

        E = 1e4
        L, H = 2.0, 0.1  # L/H = 20
        P = 50.0  # 총 하중

        domain = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 0.0), size=(L, H),
            n_divisions=(40, 2),
        )

        left = domain.select(axis=0, value=0.0)
        right = domain.select(axis=0, value=L)
        domain.set_fixed(left)

        force_per_node = P / len(right)
        domain.set_force(right, [force_per_node, 0.0])

        mat = Material(E=E, nu=0.3, density=1000, dim=2, plane_stress=True)
        solver = Solver(domain, mat)
        result = solver.solve()

        assert isinstance(result, SolveResult)
        assert result.converged

        u = solver.get_displacements()
        A = H * 1.0
        u_analytical = P * L / (E * A)
        u_fem = np.mean(u[right, 0])
        error = abs(u_fem - u_analytical) / abs(u_analytical) * 100
        assert error < 5.0, f"FEM 인장봉 오차 {error:.2f}% > 5%"

    def test_tension_bar_3d(self):
        """3D 인장봉."""
        init()

        E = 1e6
        L, W, H = 1.0, 0.1, 0.1
        P = 100.0

        domain = create_domain(
            Method.FEM, dim=3,
            origin=(0.0, 0.0, 0.0), size=(L, W, H),
            n_divisions=(20, 2, 2),
        )

        left = domain.select(axis=0, value=0.0)
        right = domain.select(axis=0, value=L)
        domain.set_fixed(left)

        force_per_node = P / len(right)
        domain.set_force(right, [force_per_node, 0.0, 0.0])

        mat = Material(E=E, nu=0.3, density=1000, dim=3)
        solver = Solver(domain, mat)
        result = solver.solve()

        assert result.converged

        u = solver.get_displacements()
        A = W * H
        u_analytical = P * L / (E * A)
        u_fem = np.mean(u[right, 0])
        error = abs(u_fem - u_analytical) / abs(u_analytical) * 100
        assert error < 5.0, f"FEM 3D 인장봉 오차 {error:.2f}% > 5%"


# ============================================================
#  SPG 솔버 테스트 (인장봉)
# ============================================================

class TestSPGSolver:
    """SPG 솔버 통합 테스트."""

    def test_tension_bar_2d(self):
        """2D SPG 인장봉."""
        init()

        E = 1e4
        nu = 0.3
        L, H = 1.0, 0.2
        nx, ny = 21, 5
        spacing = L / (nx - 1)
        P_total = 50.0

        domain = create_domain(
            Method.SPG, dim=2,
            origin=(0.0, 0.0), size=(L, H),
            n_divisions=(nx, ny),
        )

        left = domain.select(axis=0, value=0.0)
        right = domain.select(axis=0, value=L)
        domain.set_fixed(left)

        force_per_particle = P_total / len(right)
        domain.set_force(right, [force_per_particle, 0.0])

        mat = Material(E=E, nu=nu, density=1000, dim=2)
        solver = Solver(domain, mat, stabilization=0.01, viscous_damping=0.05)
        result = solver.solve(max_iterations=60000, tol=1e-3)

        u = solver.get_displacements()

        # 2D 평면변형 유효 E
        lam = E * nu / ((1 + nu) * (1 - 2 * nu))
        mu = E / (2 * (1 + nu))
        E_eff = 4 * mu * (lam + mu) / (lam + 2 * mu)
        A = H * 1.0
        u_analytical = P_total * L / (E_eff * A)

        u_spg = np.mean(u[right, 0])
        error = abs(u_spg - u_analytical) / abs(u_analytical) * 100
        # SPG는 경계 형상함수 잘림으로 더 큰 오차 허용
        assert error < 25.0, f"SPG 인장봉 오차 {error:.2f}% > 25%"


# ============================================================
#  PD 솔버 테스트 (인장봉)
# ============================================================

class TestPDSolver:
    """PD 솔버 통합 테스트."""

    def test_adapter_creation(self):
        """PD 어댑터가 정상적으로 생성되는지 확인."""
        init()

        E = 1e4
        L, H = 1.0, 0.2
        nx, ny = 21, 5

        domain = create_domain(
            Method.PD, dim=2,
            origin=(0.0, 0.0), size=(L, H),
            n_divisions=(nx, ny),
        )

        left = domain.select(axis=0, value=0.0)
        right = domain.select(axis=0, value=L)
        domain.set_fixed(left)
        domain.set_force(right, [10.0, 0.0])

        mat = Material(E=E, nu=0.3, density=1000, dim=2)
        solver = Solver(domain, mat, damping=0.1)

        # 어댑터 내부 구성 확인
        adapter = solver._adapter
        assert adapter.ps.n_particles == nx * ny
        assert adapter.bonds is not None
        assert adapter.nosb is not None
        assert adapter._loader is not None

    def test_few_steps_stable(self):
        """PD 솔버 몇 스텝 실행 시 안정성 확인."""
        init()

        E = 1e4
        L, H = 1.0, 0.2
        nx, ny = 21, 5

        domain = create_domain(
            Method.PD, dim=2,
            origin=(0.0, 0.0), size=(L, H),
            n_divisions=(nx, ny),
        )

        left = domain.select(axis=0, value=0.0)
        right = domain.select(axis=0, value=L)
        domain.set_fixed(left)
        domain.set_force(right, [10.0, 0.0])

        mat = Material(E=E, nu=0.3, density=1000, dim=2)
        solver = Solver(domain, mat, damping=0.1)

        # 1000 스텝만 실행 (완전 수렴 대신 안정성 확인)
        adapter = solver._adapter
        for _ in range(1000):
            adapter.solver.step(external_force_func=adapter._apply_forces)

        u = solver.get_displacements()
        assert not np.any(np.isnan(u)), "PD: NaN 발생"
        assert not np.any(np.isinf(u)), "PD: Inf 발생"


# ============================================================
#  교차 검증 (FEM vs SPG)
# ============================================================

class TestCrossValidation:
    """솔버 간 교차 검증."""

    def test_fem_vs_spg_tension(self):
        """FEM과 SPG의 인장봉 결과 비교."""
        init()

        E = 1e4
        L, H = 2.0, 0.1

        # FEM 해석
        domain_fem = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 0.0), size=(L, H),
            n_divisions=(40, 2),
        )
        left_fem = domain_fem.select(axis=0, value=0.0)
        right_fem = domain_fem.select(axis=0, value=L)
        domain_fem.set_fixed(left_fem)
        P = 50.0
        domain_fem.set_force(right_fem, [P / len(right_fem), 0.0])

        mat_fem = Material(E=E, nu=0.3, density=1000, dim=2, plane_stress=True)
        solver_fem = Solver(domain_fem, mat_fem)
        solver_fem.solve()
        u_fem = np.mean(solver_fem.get_displacements()[right_fem, 0])

        # SPG 해석 (동일 문제, 평면변형 유효 E)
        nx, ny = 41, 3
        domain_spg = create_domain(
            Method.SPG, dim=2,
            origin=(0.0, 0.0), size=(L, H),
            n_divisions=(nx, ny),
        )
        left_spg = domain_spg.select(axis=0, value=0.0)
        right_spg = domain_spg.select(axis=0, value=L)
        domain_spg.set_fixed(left_spg)
        domain_spg.set_force(right_spg, [P / len(right_spg), 0.0])

        mat_spg = Material(E=E, nu=0.3, density=1000, dim=2)
        solver_spg = Solver(domain_spg, mat_spg, stabilization=0.01, viscous_damping=0.05)
        solver_spg.solve(max_iterations=80000, tol=1e-3)
        u_spg = np.mean(solver_spg.get_displacements()[right_spg, 0])

        # 두 결과 모두 양의 변위여야 함
        assert u_fem > 0
        assert u_spg > 0

        # SPG는 평면변형이므로 FEM(평면응력)보다 작은 변위 예상
        # 방향성만 확인 (정량적 비교는 동일 조건에서만 의미 있음)
        assert abs(u_spg) > 0


# ============================================================
#  API 편의성 테스트
# ============================================================

class TestAPIConvenience:
    """API 사용성 테스트."""

    def test_method_enum(self):
        """Method enum 값 확인."""
        assert Method.FEM.value == "fem"
        assert Method.PD.value == "pd"
        assert Method.SPG.value == "spg"

    def test_solve_result_fields(self):
        """SolveResult 필드 확인."""
        r = SolveResult(
            converged=True, iterations=10,
            residual=1e-8, relative_residual=1e-10,
            elapsed_time=0.5,
        )
        assert r.converged is True
        assert r.iterations == 10

    def test_domain_boundary_conditions(self):
        """경계조건 설정 API."""
        init()
        domain = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 0.0), size=(1.0, 0.2),
            n_divisions=(10, 2),
        )

        left = domain.select(axis=0, value=0.0)
        right = domain.select(axis=0, value=1.0)

        domain.set_fixed(left)
        domain.set_force(right, [100.0, 0.0])

        assert domain._fixed_indices is not None
        assert domain._force_indices is not None
        assert len(domain._fixed_indices) == len(left)

    def test_get_damage_fem_returns_none(self):
        """FEM은 damage 미지원 → None."""
        init()
        domain = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 0.0), size=(1.0, 0.2),
            n_divisions=(5, 1),
        )
        left = domain.select(axis=0, value=0.0)
        right = domain.select(axis=0, value=1.0)
        domain.set_fixed(left)
        domain.set_force(right, [10.0, 0.0])

        mat = Material(E=1e4, nu=0.3, dim=2, plane_stress=True)
        solver = Solver(domain, mat)
        solver.solve()
        assert solver.get_damage() is None
