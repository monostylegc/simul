"""횡이방성 재료 모델 테스트.

Phase 1-A: 피질골 물성 적용, 등방성 극한, Voigt 탄성 텐서 검증.
"""

import pytest
import numpy as np
import taichi as ti

ti.init(arch=ti.cpu, default_fp=ti.f64)

from backend.fea.fem.material.transverse_isotropic import TransverseIsotropic
from backend.fea.fem.material.linear_elastic import LinearElastic
from backend.fea.fem.validation import FEAValidationError


# ───────────────── 기본 생성/속성 ─────────────────


class TestTransverseIsotropicBasic:
    """횡이방성 재료 기본 속성 테스트."""

    def test_create_cortical_bone(self):
        """피질골 물성으로 생성."""
        mat = TransverseIsotropic(
            E1=17e9, E2=11.5e9, nu12=0.32, nu23=0.33, G12=3.3e9, dim=3,
        )
        assert mat.E1 == 17e9
        assert mat.E2 == 11.5e9
        assert mat.nu12 == 0.32
        assert mat.nu23 == 0.33
        assert mat.G12 == 3.3e9
        assert mat.is_linear

    def test_create_2d(self):
        """2D 횡이방성 생성."""
        mat = TransverseIsotropic(
            E1=17e9, E2=11.5e9, nu12=0.32, nu23=0.33, G12=3.3e9, dim=2,
        )
        assert mat.dim == 2

    def test_derived_constants(self):
        """유도 상수 (G23, ν21) 계산 확인."""
        mat = TransverseIsotropic(
            E1=17e9, E2=11.5e9, nu12=0.32, nu23=0.33, G12=3.3e9,
        )
        # G23 = E2 / (2(1+ν23))
        expected_G23 = 11.5e9 / (2.0 * (1.0 + 0.33))
        assert np.isclose(mat.G23, expected_G23, rtol=1e-10)

        # ν21 = ν12 * E2/E1
        expected_nu21 = 0.32 * 11.5e9 / 17e9
        assert np.isclose(mat.nu21, expected_nu21, rtol=1e-10)

    def test_elasticity_tensor_3d_shape(self):
        """3D 탄성 텐서 6×6."""
        mat = TransverseIsotropic(17e9, 11.5e9, 0.32, 0.33, 3.3e9, dim=3)
        C = mat.get_elasticity_tensor()
        assert C.shape == (6, 6)

    def test_elasticity_tensor_2d_shape(self):
        """2D 탄성 텐서 3×3."""
        mat = TransverseIsotropic(17e9, 11.5e9, 0.32, 0.33, 3.3e9, dim=2)
        C = mat.get_elasticity_tensor()
        assert C.shape == (3, 3)

    def test_elasticity_tensor_symmetry(self):
        """탄성 텐서 대칭: C = Cᵀ."""
        mat = TransverseIsotropic(17e9, 11.5e9, 0.32, 0.33, 3.3e9, dim=3)
        C = mat.get_elasticity_tensor()
        np.testing.assert_allclose(C, C.T, atol=1e-2,
                                   err_msg="탄성 텐서가 대칭이 아님")

    def test_elasticity_tensor_positive_definite(self):
        """탄성 텐서 양정치 확인."""
        mat = TransverseIsotropic(17e9, 11.5e9, 0.32, 0.33, 3.3e9, dim=3)
        C = mat.get_elasticity_tensor()
        eigvals = np.linalg.eigvalsh(C)
        assert np.all(eigvals > 0), f"음의 고유값 존재: {eigvals}"

    def test_repr(self):
        """문자열 표현."""
        mat = TransverseIsotropic(17e9, 11.5e9, 0.32, 0.33, 3.3e9)
        s = repr(mat)
        assert "TransverseIsotropic" in s

    def test_custom_fiber_direction(self):
        """사용자 지정 이방 축 방향."""
        mat = TransverseIsotropic(
            17e9, 11.5e9, 0.32, 0.33, 3.3e9,
            fiber_direction=(0, 0, 1),  # z축
            dim=3,
        )
        # 정규화된 방향 벡터
        np.testing.assert_allclose(mat._fiber_dir, [0, 0, 1])


# ───────────────── 검증 테스트 ─────────────────


class TestTransverseIsotropicValidation:
    """횡이방성 입력 검증 테스트."""

    def test_negative_E1_raises(self):
        with pytest.raises(FEAValidationError, match="E1"):
            TransverseIsotropic(-17e9, 11.5e9, 0.32, 0.33, 3.3e9)

    def test_negative_G12_raises(self):
        with pytest.raises(FEAValidationError, match="G12"):
            TransverseIsotropic(17e9, 11.5e9, 0.32, 0.33, -3.3e9)

    def test_thermodynamic_instability_raises(self):
        """열역학적 불안정 조합."""
        with pytest.raises(FEAValidationError, match="양정치"):
            TransverseIsotropic(17e9, 11.5e9, 0.99, 0.99, 3.3e9)


# ───────────────── 등방성 극한 ─────────────────


class TestIsotropicLimit:
    """등방 물성일 때 LinearElastic과 일치."""

    def test_isotropic_elasticity_tensor_3d(self):
        """E1=E2, G12=G일 때 등방 탄성 텐서와 일치."""
        E, nu = 200e9, 0.3
        G = E / (2 * (1 + nu))
        mat_ti = TransverseIsotropic(E, E, nu, nu, G, dim=3)
        mat_le = LinearElastic(E, nu, dim=3)

        C_ti = mat_ti.get_elasticity_tensor()
        C_le = mat_le.get_elasticity_tensor()

        np.testing.assert_allclose(
            C_ti, C_le, rtol=1e-8,
            err_msg="등방 극한에서 탄성 텐서 불일치",
        )

    def test_isotropic_elasticity_tensor_2d(self):
        """2D 등방 극한."""
        E, nu = 200e9, 0.3
        G = E / (2 * (1 + nu))
        mat_ti = TransverseIsotropic(E, E, nu, nu, G, dim=2)
        mat_le = LinearElastic(E, nu, dim=2)

        C_ti = mat_ti.get_elasticity_tensor()
        C_le = mat_le.get_elasticity_tensor()

        np.testing.assert_allclose(
            C_ti, C_le, rtol=1e-8,
            err_msg="2D 등방 극한에서 탄성 텐서 불일치",
        )

    def test_isotropic_stress_matches_3d(self):
        """등방 극한: 응력이 LinearElastic과 동일."""
        from backend.fea.fem.core.mesh import FEMesh
        from backend.fea.fem.core.element import ElementType

        E, nu = 200e9, 0.3
        G = E / (2 * (1 + nu))
        mat_ti = TransverseIsotropic(E, E, nu, nu, G, dim=3)
        mat_le = LinearElastic(E, nu, dim=3)

        # 3D HEX8 단일 요소
        nodes = np.array([
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        ], dtype=np.float64)
        elems = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)

        # 임의 변형
        F = np.eye(3)
        F[0, 0] = 1.001
        F[0, 1] = 0.0002

        mesh1 = FEMesh(8, 1, ElementType.HEX8)
        mesh1.initialize_from_numpy(nodes, elems)
        n_gp = mesh1.n_gauss
        mesh1.F.from_numpy(np.tile(F, (n_gp, 1, 1)))
        mat_ti.compute_stress(mesh1)
        s_ti = mesh1.stress.to_numpy()

        mesh2 = FEMesh(8, 1, ElementType.HEX8)
        mesh2.initialize_from_numpy(nodes, elems)
        mesh2.F.from_numpy(np.tile(F, (n_gp, 1, 1)))
        mat_le.compute_stress(mesh2)
        s_le = mesh2.stress.to_numpy()

        np.testing.assert_allclose(
            s_ti, s_le, rtol=1e-8,
            err_msg="등방 극한에서 응력 불일치",
        )


# ───────────────── 이방성 응력 검증 ─────────────────


class TestAnisotropicStress:
    """횡이방성 응력 방향 의존성 검증."""

    def test_different_stiffness_directions(self):
        """이방 축(1) 방향과 등방면(2) 방향의 강성 차이."""
        mat = TransverseIsotropic(17e9, 11.5e9, 0.32, 0.33, 3.3e9, dim=3)

        from backend.fea.fem.core.mesh import FEMesh
        from backend.fea.fem.core.element import ElementType

        nodes = np.array([
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        ], dtype=np.float64)
        elems = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)

        # 1방향 인장 (이방 축, 더 강함)
        F1 = np.eye(3)
        F1[0, 0] = 1.001
        mesh1 = FEMesh(8, 1, ElementType.HEX8)
        mesh1.initialize_from_numpy(nodes, elems)
        n_gp = mesh1.n_gauss
        mesh1.F.from_numpy(np.tile(F1, (n_gp, 1, 1)))
        mat.compute_stress(mesh1)
        s1 = mesh1.stress.to_numpy()
        sigma_11 = np.mean([s1[i, 0, 0] for i in range(n_gp)])

        # 2방향 인장 (등방면, 더 부드러움)
        F2 = np.eye(3)
        F2[1, 1] = 1.001
        mesh2 = FEMesh(8, 1, ElementType.HEX8)
        mesh2.initialize_from_numpy(nodes, elems)
        mesh2.F.from_numpy(np.tile(F2, (n_gp, 1, 1)))
        mat.compute_stress(mesh2)
        s2 = mesh2.stress.to_numpy()
        sigma_22 = np.mean([s2[i, 1, 1] for i in range(n_gp)])

        # E1 > E2이므로 동일 변형에서 σ11 > σ22
        assert sigma_11 > sigma_22, (
            f"이방성 방향 응력: σ11={sigma_11:.2e} ≤ σ22={sigma_22:.2e}"
        )

    def test_rotated_fiber_direction(self):
        """이방 축을 z축으로 회전 시 z방향이 더 강함."""
        mat = TransverseIsotropic(
            17e9, 11.5e9, 0.32, 0.33, 3.3e9,
            fiber_direction=(0, 0, 1), dim=3,
        )

        from backend.fea.fem.core.mesh import FEMesh
        from backend.fea.fem.core.element import ElementType

        nodes = np.array([
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        ], dtype=np.float64)
        elems = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)

        # z방향 인장 (fiber 방향)
        F_z = np.eye(3)
        F_z[2, 2] = 1.001
        mesh_z = FEMesh(8, 1, ElementType.HEX8)
        mesh_z.initialize_from_numpy(nodes, elems)
        n_gp = mesh_z.n_gauss
        mesh_z.F.from_numpy(np.tile(F_z, (n_gp, 1, 1)))
        mat.compute_stress(mesh_z)
        s_z = mesh_z.stress.to_numpy()
        sigma_33 = np.mean([s_z[i, 2, 2] for i in range(n_gp)])

        # x방향 인장 (등방면)
        F_x = np.eye(3)
        F_x[0, 0] = 1.001
        mesh_x = FEMesh(8, 1, ElementType.HEX8)
        mesh_x.initialize_from_numpy(nodes, elems)
        mesh_x.F.from_numpy(np.tile(F_x, (n_gp, 1, 1)))
        mat.compute_stress(mesh_x)
        s_x = mesh_x.stress.to_numpy()
        sigma_11 = np.mean([s_x[i, 0, 0] for i in range(n_gp)])

        # z=fiber, E1>E2이므로 σ33(z) > σ11(x)
        assert sigma_33 > sigma_11, (
            f"회전된 이방 축: σ33={sigma_33:.2e} ≤ σ11={sigma_11:.2e}"
        )


# ───────────────── 프레임워크 통합 ─────────────────


class TestFrameworkIntegration:
    """프레임워크 Material 디스패치 테스트."""

    def test_dispatch_creates_transverse_isotropic(self):
        """Material(constitutive_model='transverse_isotropic') 디스패치."""
        from backend.fea.framework.material import Material
        mat = Material(
            E=17e9, nu=0.32,
            constitutive_model="transverse_isotropic",
            E1=17e9, E2=11.5e9, nu12=0.32, nu23=0.33, G12=3.3e9,
            dim=3,
        )
        fem_mat = mat._create_fem_material()
        assert isinstance(fem_mat, TransverseIsotropic)
        assert fem_mat.E1 == 17e9
        assert fem_mat.E2 == 11.5e9

    def test_dispatch_defaults_to_isotropic(self):
        """횡이방성 파라미터 미지정 시 E/ν로 대체."""
        from backend.fea.framework.material import Material
        mat = Material(
            E=200e9, nu=0.3,
            constitutive_model="transverse_isotropic",
            dim=3,
        )
        fem_mat = mat._create_fem_material()
        assert isinstance(fem_mat, TransverseIsotropic)
        # E1=E, E2=E일 때 등방성
        assert fem_mat.E1 == 200e9
        assert fem_mat.E2 == 200e9


# ───────────────── 솔버 통합 ─────────────────


class TestSolverIntegration:
    """횡이방성 재료 + StaticSolver 통합 테스트."""

    def test_cantilever_anisotropic(self):
        """외팔보 횡이방성 해석 실행 확인."""
        from backend.fea.fem.core.mesh import FEMesh
        from backend.fea.fem.core.element import ElementType
        from backend.fea.fem.solver.static_solver import StaticSolver

        # 2D 외팔보: 10×2 QUAD4
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

        # 오른쪽 하중
        right = np.where(nodes[:, 0] > Lx - 1e-10)[0]
        forces = np.zeros((len(right), 2))
        forces[:, 1] = -1e6 / len(right)
        mesh.set_nodal_forces(right, forces)

        # 횡이방성 (x축 = fiber)
        mat = TransverseIsotropic(
            17e9, 11.5e9, 0.32, 0.33, 3.3e9, dim=2,
        )

        solver = StaticSolver(mesh, mat)
        result = solver.solve(verbose=False)
        assert result["converged"]

        disp = mesh.get_displacements()
        assert np.max(np.abs(disp)) > 0
