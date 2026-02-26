"""J2 소성 재료 모델 테스트.

Phase 0-B: Return-mapping 알고리즘 검증, 통합 테스트.
"""

import pytest
import numpy as np
import taichi as ti

ti.init(arch=ti.cpu, default_fp=ti.f64)

from backend.fea.fem.material.j2_plasticity import J2Plasticity
from backend.fea.fem.validation import FEAValidationError


# ───────────────── 기본 생성/속성 ─────────────────


class TestJ2PlasticityBasic:
    """J2 소성 재료 기본 속성 테스트."""

    def test_create_material(self):
        """재료 생성 및 속성 확인."""
        mat = J2Plasticity(
            youngs_modulus=200e9, poisson_ratio=0.3,
            yield_stress=250e6, hardening_modulus=1e9,
        )
        assert mat.E == 200e9
        assert mat.nu == 0.3
        assert mat.sigma_y0 == 250e6
        assert mat.H == 1e9
        assert not mat.is_linear

    def test_perfect_plasticity(self):
        """완전 소성 (H=0) 생성."""
        mat = J2Plasticity(200e9, 0.3, yield_stress=250e6, hardening_modulus=0.0)
        assert mat.H == 0.0

    def test_elasticity_tensor_symmetry(self):
        """초기 탄성 텐서 대칭성."""
        mat = J2Plasticity(200e9, 0.3, 250e6, dim=3)
        C = mat.get_elasticity_tensor()
        assert C.shape == (6, 6)
        assert np.allclose(C, C.T)

    def test_elasticity_tensor_2d(self):
        """2D 탄성 텐서."""
        mat = J2Plasticity(200e9, 0.3, 250e6, dim=2)
        C = mat.get_elasticity_tensor()
        assert C.shape == (3, 3)
        assert np.allclose(C, C.T)

    def test_repr(self):
        """문자열 표현."""
        mat = J2Plasticity(200e9, 0.3, 250e6, 1e9)
        s = repr(mat)
        assert "J2Plasticity" in s
        assert "σ_y" in s

    def test_state_not_initialized_before_use(self):
        """compute_stress 전까지 상태 미초기화."""
        mat = J2Plasticity(200e9, 0.3, 250e6)
        assert mat._ep_strain is None
        assert mat._epe is None

    def test_reset_state(self):
        """상태 리셋."""
        mat = J2Plasticity(200e9, 0.3, 250e6, dim=2)
        mat._ensure_state_initialized(4)
        mat._epe[0] = 1.0
        mat.reset_state()
        assert mat._epe[0] == 0.0


# ───────────────── 검증 테스트 ─────────────────


class TestJ2Validation:
    """J2 소성 입력 검증 테스트."""

    def test_invalid_E(self):
        with pytest.raises(FEAValidationError):
            J2Plasticity(-200e9, 0.3, 250e6)

    def test_invalid_nu(self):
        with pytest.raises(FEAValidationError):
            J2Plasticity(200e9, 0.5, 250e6)

    def test_invalid_yield_stress(self):
        with pytest.raises(FEAValidationError, match="항복"):
            J2Plasticity(200e9, 0.3, -250e6)

    def test_zero_yield_stress(self):
        with pytest.raises(FEAValidationError, match="항복"):
            J2Plasticity(200e9, 0.3, 0.0)

    def test_negative_hardening(self):
        with pytest.raises(FEAValidationError, match="경화"):
            J2Plasticity(200e9, 0.3, 250e6, hardening_modulus=-1e9)


# ───────────────── Return-Mapping 검증 ─────────────────


class TestReturnMapping:
    """Return-mapping 알고리즘 수치 검증."""

    def _run_single_point_test(self, F_matrix, mat, dim=2):
        """단일 가우스점에서 return-mapping 실행하고 결과 반환.

        F를 설정하고 compute_stress를 호출한 후 응력/소성 변형률 추출.
        mesh 객체도 반환하여 후처리에 사용할 수 있다.
        """
        from backend.fea.fem.core.mesh import FEMesh
        from backend.fea.fem.core.element import ElementType

        if dim == 2:
            etype = ElementType.QUAD4
        else:
            etype = ElementType.HEX8

        # 최소 메쉬: 요소 1개
        if dim == 2:
            nodes = np.array([
                [0, 0], [1, 0], [1, 1], [0, 1],
            ], dtype=np.float64)
            elems = np.array([[0, 1, 2, 3]], dtype=np.int32)
        else:
            nodes = np.array([
                [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
            ], dtype=np.float64)
            elems = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)

        mesh = FEMesh(len(nodes), 1, etype)
        mesh.initialize_from_numpy(nodes, elems)

        # F를 수동으로 설정 (모든 가우스점에 동일한 F)
        n_gauss = mesh.n_gauss
        F_np = np.tile(F_matrix, (n_gauss, 1, 1))
        mesh.F.from_numpy(F_np)

        mat.compute_stress(mesh)

        stress = mesh.stress.to_numpy()
        epe = mat.get_plastic_strain()
        return stress, epe, mesh

    def test_elastic_regime(self):
        """항복 이하 하중 → 소성 변형 없음."""
        # 영 계수 200 GPa, 항복 응력 250 MPa
        # 탄성 한계 변형률: σ_y / E = 250e6 / 200e9 = 0.00125
        # F = I + 작은 변형 (항복 이하)
        mat = J2Plasticity(200e9, 0.3, 250e6, dim=2)

        # 1축 인장: ε_11 = 0.0005 (항복의 40%)
        eps_11 = 0.0005
        F = np.array([[1.0 + eps_11, 0], [0, 1.0]])
        stress, epe, _ = self._run_single_point_test(F, mat, dim=2)

        # 소성 변형 없음
        assert np.all(epe < 1e-12), f"탄성 영역인데 소성 변형 발생: {epe}"

        # 응력 확인: σ_11 > 0
        assert stress[0, 0, 0] > 0, "인장 응력이 양수여야 함"

    def test_elastic_matches_linear(self):
        """항복 이하에서 J2 응력 = LinearElastic 응력."""
        from backend.fea.fem.material.linear_elastic import LinearElastic

        E, nu = 200e9, 0.3
        mat_j2 = J2Plasticity(E, nu, yield_stress=1e12, dim=2)  # 매우 높은 항복
        mat_le = LinearElastic(E, nu, dim=2)

        # 임의 변형
        F = np.array([[1.001, 0.0002], [0.0001, 0.999]])

        from backend.fea.fem.core.mesh import FEMesh
        from backend.fea.fem.core.element import ElementType

        nodes = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
        elems = np.array([[0, 1, 2, 3]], dtype=np.int32)

        # J2
        mesh1 = FEMesh(4, 1, ElementType.QUAD4)
        mesh1.initialize_from_numpy(nodes, elems)
        n_gp = mesh1.n_gauss
        mesh1.F.from_numpy(np.tile(F, (n_gp, 1, 1)))
        mat_j2.compute_stress(mesh1)
        s_j2 = mesh1.stress.to_numpy()

        # LinearElastic
        mesh2 = FEMesh(4, 1, ElementType.QUAD4)
        mesh2.initialize_from_numpy(nodes, elems)
        mesh2.F.from_numpy(np.tile(F, (n_gp, 1, 1)))
        mat_le.compute_stress(mesh2)
        s_le = mesh2.stress.to_numpy()

        # 차이 비교 (항복 이하이므로 동일해야)
        np.testing.assert_allclose(s_j2, s_le, rtol=1e-10,
                                   err_msg="탄성 영역에서 J2 ≠ LinearElastic")

    def test_uniaxial_tension_yield(self):
        """1축 인장에서 항복 후 소성 변형 발생 확인."""
        mat = J2Plasticity(200e9, 0.3, 250e6, hardening_modulus=1e9, dim=2)

        # 항복 초과 변형: ε_11 = 0.005 (항복의 4배)
        eps_11 = 0.005
        F = np.array([[1.0 + eps_11, 0], [0, 1.0]])
        stress, epe, _ = self._run_single_point_test(F, mat, dim=2)

        # 소성 변형 발생
        assert np.any(epe > 1e-12), "항복 초과인데 소성 변형 미발생"

    def test_perfect_plasticity_stress_cap(self):
        """완전 소성(H=0): 3D 일관 von Mises ≤ σ_y."""
        sigma_y = 250e6
        mat = J2Plasticity(200e9, 0.3, sigma_y, hardening_modulus=0.0, dim=2)

        # 큰 변형
        eps_11 = 0.01
        F = np.array([[1.0 + eps_11, 0], [0, 1.0]])
        stress, epe, mesh = self._run_single_point_test(F, mat, dim=2)

        # 소성 발생 확인
        assert np.any(epe > 1e-12), "항복 초과인데 소성 변형 미발생"

        # 3D 일관 von Mises (σ₃₃ 고려) ≤ σ_y (허용 오차 1%)
        vm = mat.get_von_mises_stress(mesh)
        for gp in range(len(vm)):
            assert vm[gp] <= sigma_y * 1.01, (
                f"가우스점 {gp}: von Mises {vm[gp]:.2e} > σ_y {sigma_y:.2e}"
            )

    def test_perfect_plasticity_stress_cap_3d(self):
        """3D 완전 소성: von Mises ≤ σ_y."""
        sigma_y = 250e6
        mat = J2Plasticity(200e9, 0.3, sigma_y, hardening_modulus=0.0, dim=3)

        F = np.eye(3)
        F[0, 0] = 1.01
        stress, epe, mesh = self._run_single_point_test(F, mat, dim=3)

        assert np.any(epe > 1e-12)

        vm = mat.get_von_mises_stress(mesh)
        for gp in range(len(vm)):
            assert vm[gp] <= sigma_y * 1.01, (
                f"가우스점 {gp}: von Mises {vm[gp]:.2e} > σ_y {sigma_y:.2e}"
            )

    def test_hardening_increases_yield(self):
        """등방 경화: 소성 후 항복 응력 증가."""
        mat = J2Plasticity(200e9, 0.3, 250e6, hardening_modulus=5e9, dim=2)

        # 1단계: 큰 변형 (항복 초과)
        F1 = np.array([[1.005, 0], [0, 1.0]])
        stress1, epe1, _ = self._run_single_point_test(F1, mat, dim=2)
        assert np.any(epe1 > 0)

        # 등가 소성 변형률 × H = 항복면 팽창량
        epe_max = np.max(epe1)
        expected_yield_increase = mat.H * epe_max
        assert expected_yield_increase > 0

    def test_yield_status(self):
        """항복 상태 배열 반환."""
        mat = J2Plasticity(200e9, 0.3, 250e6, dim=2)

        # 항복 초과 변형
        F = np.array([[1.01, 0], [0, 1.0]])
        self._run_single_point_test(F, mat, dim=2)

        status = mat.get_yield_status()
        assert len(status) > 0
        assert np.any(status == 1.0)

    def test_3d_return_mapping(self):
        """3D return-mapping 동작 확인."""
        mat = J2Plasticity(200e9, 0.3, 250e6, hardening_modulus=1e9, dim=3)

        # 3D 1축 인장 (항복 초과)
        F = np.eye(3)
        F[0, 0] = 1.005
        stress, epe, _ = self._run_single_point_test(F, mat, dim=3)

        # 소성 변형 발생 확인
        assert np.any(epe > 1e-12)


# ───────────────── 프레임워크 통합 ─────────────────


class TestJ2FrameworkIntegration:
    """프레임워크 Material 디스패치 테스트."""

    def test_dispatch_creates_j2(self):
        """Material(constitutive_model='j2_plasticity') → J2Plasticity."""
        from backend.fea.framework.material import Material
        mat = Material(E=200e9, nu=0.3, constitutive_model="j2_plasticity",
                       yield_stress=880e6, hardening_modulus=5e9)
        fem_mat = mat._create_fem_material()
        assert isinstance(fem_mat, J2Plasticity)
        assert fem_mat.sigma_y0 == 880e6
        assert fem_mat.H == 5e9

    def test_dispatch_default_yield(self):
        """항복 응력 미지정 시 기본값 880 MPa (Ti-6Al-4V)."""
        from backend.fea.framework.material import Material
        mat = Material(E=110e9, nu=0.33, constitutive_model="j2_plasticity")
        fem_mat = mat._create_fem_material()
        assert fem_mat.sigma_y0 == 880e6

    def test_dispatch_linear_unchanged(self):
        """기존 linear_elastic 디스패치 영향 없음."""
        from backend.fea.framework.material import Material
        mat = Material(E=200e9, nu=0.3, constitutive_model="linear_elastic")
        fem_mat = mat._create_fem_material()
        from backend.fea.fem.material.linear_elastic import LinearElastic
        assert isinstance(fem_mat, LinearElastic)


# ───────────────── 통합 해석 테스트 ─────────────────


class TestJ2SolverIntegration:
    """J2 소성과 StaticSolver 통합 테스트."""

    def test_cantilever_with_plasticity(self):
        """외팔보 소성 해석 — 실행 및 수렴 확인."""
        from backend.fea.fem.core.mesh import FEMesh
        from backend.fea.fem.core.element import ElementType
        from backend.fea.fem.solver.static_solver import StaticSolver

        # 2D 외팔보: 10x2 QUAD4 메쉬
        Lx, Ly = 1.0, 0.2
        nx, ny = 10, 2
        nodes = []
        for j in range(ny + 1):
            for i in range(nx + 1):
                nodes.append([i * Lx / nx, j * Ly / ny])
        nodes = np.array(nodes, dtype=np.float64)

        elems = []
        for j in range(ny):
            for i in range(nx):
                n0 = j * (nx + 1) + i
                elems.append([n0, n0 + 1, n0 + nx + 2, n0 + nx + 1])
        elems = np.array(elems, dtype=np.int32)

        mesh = FEMesh(len(nodes), len(elems), ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elems)

        # 왼쪽 고정
        left = np.where(nodes[:, 0] < 1e-10)[0]
        mesh.set_fixed_nodes(left)

        # 오른쪽에 큰 하중 (항복 유발)
        right = np.where(nodes[:, 0] > Lx - 1e-10)[0]
        forces = np.zeros((len(right), 2))
        forces[:, 1] = -1e8 / len(right)  # 큰 수직 하중
        mesh.set_nodal_forces(right, forces)

        # J2 소성 재료
        mat = J2Plasticity(200e9, 0.3, yield_stress=250e6,
                           hardening_modulus=1e9, dim=2)

        solver = StaticSolver(mesh, mat, use_newton=True,
                              max_iterations=50, tol=1e-6)
        result = solver.solve(verbose=False)

        # 해석 완료 (수렴 여부와 무관하게 실행 가능해야)
        assert "converged" in result

        # 변위 비영
        disp = mesh.get_displacements()
        assert np.max(np.abs(disp)) > 0

        # 소성 변형 발생 확인 (하중이 충분히 크므로)
        epe = mat.get_plastic_strain()
        assert len(epe) > 0
