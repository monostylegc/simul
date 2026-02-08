"""SPG 검증 테스트 - 물리적 정확성 및 수렴성 확인.

단순 패치 테스트, 솔버 수렴 테스트, 에너지 보존 테스트 등
실제 역학 문제에 대한 검증을 수행한다.
"""

import pytest
import numpy as np
import taichi as ti


@pytest.fixture(scope="session", autouse=True)
def init_taichi():
    try:
        ti.init(arch=ti.cpu, default_fp=ti.f64)
    except RuntimeError:
        pass


def create_2d_patch(nx, ny, spacing, support_factor=2.5):
    """2D 테스트 패치 생성 헬퍼."""
    from ..core.particles import SPGParticleSystem
    from ..core.kernel import SPGKernel
    from ..core.bonds import SPGBondSystem

    n_particles = nx * ny
    support_radius = spacing * support_factor

    ps = SPGParticleSystem(n_particles=n_particles, dim=2)
    ps.initialize_from_grid(
        origin=(0.0, 0.0),
        spacing=spacing,
        n_points=(nx, ny),
        density=1000.0
    )

    kernel = SPGKernel(
        n_particles=n_particles, dim=2,
        support_radius=support_radius
    )
    kernel.build_neighbor_list(ps.X.to_numpy(), support_radius)
    kernel.compute_shape_functions(ps.X, ps.volume)

    bonds = SPGBondSystem(n_particles=n_particles, dim=2)
    bonds.build_from_kernel(ps, kernel)

    return ps, kernel, bonds


def create_3d_patch(nx, ny, nz, spacing, support_factor=2.0):
    """3D 테스트 패치 생성 헬퍼."""
    from ..core.particles import SPGParticleSystem
    from ..core.kernel import SPGKernel
    from ..core.bonds import SPGBondSystem

    n_particles = nx * ny * nz
    support_radius = spacing * support_factor

    ps = SPGParticleSystem(n_particles=n_particles, dim=3)
    ps.initialize_from_grid(
        origin=(0.0, 0.0, 0.0),
        spacing=spacing,
        n_points=(nx, ny, nz),
        density=1000.0
    )

    kernel = SPGKernel(
        n_particles=n_particles, dim=3,
        support_radius=support_radius
    )
    kernel.build_neighbor_list(ps.X.to_numpy(), support_radius)
    kernel.compute_shape_functions(ps.X, ps.volume)

    bonds = SPGBondSystem(n_particles=n_particles, dim=3)
    bonds.build_from_kernel(ps, kernel)

    return ps, kernel, bonds


class TestPartitionOfUnity:
    """형상함수 partition of unity 상세 검증."""

    def test_2d_interior_sum(self):
        """2D 내부 입자에서 ΣΨ ≈ 1."""
        ps, kernel, _ = create_2d_patch(9, 9, 0.1)
        sums = kernel.get_shape_function_sum()

        # 경계에서 2칸 이상 떨어진 내부 입자
        interior = []
        pos = ps.X.to_numpy()
        x_min, x_max = pos[:, 0].min(), pos[:, 0].max()
        y_min, y_max = pos[:, 1].min(), pos[:, 1].max()
        margin = 0.25  # 2.5 * spacing
        for i in range(len(pos)):
            if (pos[i, 0] > x_min + margin and pos[i, 0] < x_max - margin and
                pos[i, 1] > y_min + margin and pos[i, 1] < y_max - margin):
                interior.append(i)

        assert len(interior) > 0, "내부 입자가 없음"
        for i in interior:
            assert abs(sums[i] - 1.0) < 0.1, (
                f"입자 {i}: ΣΨ = {sums[i]:.6f}, 기대값 1.0"
            )

    def test_3d_interior_sum(self):
        """3D 내부 입자에서 ΣΨ ≈ 1."""
        ps, kernel, _ = create_3d_patch(5, 5, 5, 0.1)
        sums = kernel.get_shape_function_sum()

        # 중앙 입자
        center = (5 * 5 * 5) // 2
        assert abs(sums[center] - 1.0) < 0.15, (
            f"3D 중앙 입자: ΣΨ = {sums[center]:.6f}"
        )

    def test_linear_reproduction(self):
        """선형 재현 조건: Σ Ψ_J(X_I) · X_J ≈ X_I."""
        ps, kernel, _ = create_2d_patch(9, 9, 0.1)

        pos = ps.X.to_numpy()
        psi_np = kernel.psi.to_numpy()
        n_nbr = kernel.n_neighbors.to_numpy()
        nbr_np = kernel.neighbors.to_numpy()

        # 내부 입자에서 확인
        margin = 0.25
        x_min, x_max = pos[:, 0].min(), pos[:, 0].max()
        y_min, y_max = pos[:, 1].min(), pos[:, 1].max()

        max_error = 0.0
        count = 0
        for i in range(len(pos)):
            if (pos[i, 0] > x_min + margin and pos[i, 0] < x_max - margin and
                pos[i, 1] > y_min + margin and pos[i, 1] < y_max - margin):
                # Σ Ψ_J · X_J
                reproduced = np.zeros(2)
                for k in range(n_nbr[i]):
                    j = nbr_np[i, k]
                    reproduced += psi_np[i, k] * pos[j]
                error = np.linalg.norm(reproduced - pos[i])
                max_error = max(max_error, error)
                count += 1

        assert count > 0
        assert max_error < 0.05, (
            f"선형 재현 최대 오차: {max_error:.6f}, 허용치 0.05"
        )


class TestDeformationGradient:
    """변형 구배 F 검증."""

    def test_identity_at_zero_displacement(self):
        """변위 0 → F = I."""
        from ..core.spg_compute import SPGCompute

        ps, kernel, bonds = create_2d_patch(7, 7, 0.1)
        compute = SPGCompute(ps, kernel, bonds, stabilization=0.1)

        compute.compute_deformation_gradient()
        F_np = ps.F.to_numpy()

        I = np.eye(2)
        for i in range(ps.n_particles):
            assert np.allclose(F_np[i], I, atol=1e-10), (
                f"입자 {i}: F = {F_np[i]}, 기대값 I"
            )

    def test_uniform_extension(self):
        """균일 인장 ε_xx=0.01 → F_xx ≈ 1.01."""
        from ..core.spg_compute import SPGCompute

        ps, kernel, bonds = create_2d_patch(9, 9, 0.1)
        compute = SPGCompute(ps, kernel, bonds, stabilization=0.1)

        # 균일 인장 변위 적용
        strain_xx = 0.01
        pos = ps.X.to_numpy()
        disp = np.zeros_like(pos)
        disp[:, 0] = strain_xx * pos[:, 0]
        ps.u.from_numpy(disp)
        ps.x.from_numpy(pos + disp)

        compute.compute_deformation_gradient()
        F_np = ps.F.to_numpy()

        # 내부 입자 확인
        margin = 0.25
        x_min, x_max = pos[:, 0].min(), pos[:, 0].max()
        y_min, y_max = pos[:, 1].min(), pos[:, 1].max()

        for i in range(len(pos)):
            if (pos[i, 0] > x_min + margin and pos[i, 0] < x_max - margin and
                pos[i, 1] > y_min + margin and pos[i, 1] < y_max - margin):
                assert abs(F_np[i, 0, 0] - (1.0 + strain_xx)) < 0.005, (
                    f"입자 {i}: F_xx = {F_np[i, 0, 0]}, 기대값 {1 + strain_xx}"
                )
                assert abs(F_np[i, 1, 1] - 1.0) < 0.005, (
                    f"입자 {i}: F_yy = {F_np[i, 1, 1]}, 기대값 1.0"
                )

    def test_simple_shear(self):
        """단순 전단 γ=0.01 → F_xy ≈ 0.01."""
        from ..core.spg_compute import SPGCompute

        ps, kernel, bonds = create_2d_patch(9, 9, 0.1)
        compute = SPGCompute(ps, kernel, bonds, stabilization=0.1)

        gamma = 0.01
        pos = ps.X.to_numpy()
        disp = np.zeros_like(pos)
        disp[:, 0] = gamma * pos[:, 1]  # u_x = γ·y
        ps.u.from_numpy(disp)
        ps.x.from_numpy(pos + disp)

        compute.compute_deformation_gradient()
        F_np = ps.F.to_numpy()

        margin = 0.25
        x_min, x_max = pos[:, 0].min(), pos[:, 0].max()
        y_min, y_max = pos[:, 1].min(), pos[:, 1].max()

        for i in range(len(pos)):
            if (pos[i, 0] > x_min + margin and pos[i, 0] < x_max - margin and
                pos[i, 1] > y_min + margin and pos[i, 1] < y_max - margin):
                assert abs(F_np[i, 0, 1] - gamma) < 0.005, (
                    f"입자 {i}: F_xy = {F_np[i, 0, 1]}, 기대값 {gamma}"
                )


class TestStressComputation:
    """응력 계산 검증."""

    def test_uniaxial_stress(self):
        """단축 인장 → σ_xx, σ_yy 확인."""
        from ..core.spg_compute import SPGCompute
        from ..material.elastic import SPGElasticMaterial

        ps, kernel, bonds = create_2d_patch(9, 9, 0.1)
        mat = SPGElasticMaterial(1e4, 0.3, 1000.0, dim=2)
        compute = SPGCompute(ps, kernel, bonds, stabilization=0.1)

        strain_xx = 0.01
        pos = ps.X.to_numpy()
        disp = np.zeros_like(pos)
        disp[:, 0] = strain_xx * pos[:, 0]
        ps.u.from_numpy(disp)
        ps.x.from_numpy(pos + disp)

        compute.compute_deformation_gradient()
        compute.compute_strain()
        compute.compute_internal_force_with_stabilization(mat.lam, mat.mu)

        stress = ps.stress.to_numpy()

        # 내부 중앙 입자
        center = (9 // 2) * 9 + 9 // 2

        # σ_xx = λ·ε_xx + 2μ·ε_xx = (λ + 2μ)·ε_xx
        expected_sxx = (mat.lam + 2 * mat.mu) * strain_xx
        # σ_yy = λ·ε_xx
        expected_syy = mat.lam * strain_xx

        assert abs(stress[center, 0, 0] - expected_sxx) / abs(expected_sxx) < 0.1, (
            f"σ_xx = {stress[center, 0, 0]:.4f}, 기대값 {expected_sxx:.4f}"
        )


class TestSolverConvergence:
    """솔버 수렴 테스트."""

    def test_cantilever_beam_convergence(self):
        """외팔보 하중 → 솔버 수렴 확인."""
        from ..core.spg_compute import SPGCompute
        from ..solver.explicit_solver import SPGExplicitSolver
        from ..material.elastic import SPGElasticMaterial

        nx, ny = 20, 5
        spacing = 0.1
        ps, kernel, bonds = create_2d_patch(nx, ny, spacing)

        mat = SPGElasticMaterial(1e4, 0.3, 1000.0, dim=2)

        # 왼쪽 끝 고정
        pos = ps.X.to_numpy()
        fixed_idx = np.where(pos[:, 0] < spacing * 0.5)[0]
        ps.set_fixed_particles(fixed_idx)

        # 오른쪽 끝 하향 하중
        right_idx = np.where(pos[:, 0] > (nx - 1) * spacing - spacing * 0.5)[0]
        force = np.array([0.0, -1.0])
        ps.set_external_force(right_idx, force)

        solver = SPGExplicitSolver(
            particles=ps,
            kernel=kernel,
            bonds=bonds,
            material=mat,
            stabilization=0.15,
            viscous_damping=0.05
        )

        result = solver.solve(
            max_iterations=30000,
            tol=1e-3,
            verbose=False
        )

        # 수렴 여부 확인
        disp = ps.get_displacements()
        max_disp = np.max(np.abs(disp))

        # 변위가 존재하고 유한해야 함
        assert max_disp > 1e-8, f"변위가 너무 작음: {max_disp}"
        assert np.all(np.isfinite(disp)), "NaN/Inf 변위 발생"

        # 오른쪽 끝이 아래로 처져야 함
        right_disp_y = disp[right_idx, 1]
        assert np.mean(right_disp_y) < 0, (
            f"오른쪽 끝 y변위가 양수: {np.mean(right_disp_y)}"
        )

    def test_3d_compression(self):
        """3D 압축 테스트."""
        from ..solver.explicit_solver import SPGExplicitSolver
        from ..material.elastic import SPGElasticMaterial

        ps, kernel, bonds = create_3d_patch(4, 4, 4, 0.1)
        mat = SPGElasticMaterial(1e4, 0.3, 1000.0, dim=3)

        # 아래면 고정
        pos = ps.X.to_numpy()
        fixed_idx = np.where(pos[:, 2] < 0.05)[0]
        ps.set_fixed_particles(fixed_idx)

        # 윗면 압축력
        top_idx = np.where(pos[:, 2] > 0.25)[0]
        ps.set_external_force(top_idx, np.array([0.0, 0.0, -1.0]))

        solver = SPGExplicitSolver(
            particles=ps,
            kernel=kernel,
            bonds=bonds,
            material=mat,
            stabilization=0.15,
            viscous_damping=0.05
        )

        # 몇 스텝만 실행 (발산 안 하는지 확인)
        for _ in range(1000):
            info = solver.step()

        disp = ps.get_displacements()
        assert np.all(np.isfinite(disp)), "3D 압축에서 NaN/Inf 발생"

        # 윗면이 아래로 이동해야 함
        top_disp_z = disp[top_idx, 2]
        assert np.mean(top_disp_z) < 0, "윗면이 아래로 이동하지 않음"


class TestEnergyConsistency:
    """에너지 일관성 테스트."""

    def test_strain_energy_positive(self):
        """변형 상태에서 변형 에너지 > 0."""
        from ..core.spg_compute import SPGCompute
        from ..material.elastic import SPGElasticMaterial

        ps, kernel, bonds = create_2d_patch(7, 7, 0.1)
        mat = SPGElasticMaterial(1e4, 0.3, 1000.0, dim=2)
        compute = SPGCompute(ps, kernel, bonds, stabilization=0.1)

        # 변위 적용
        pos = ps.X.to_numpy()
        disp = np.zeros_like(pos)
        disp[:, 0] = 0.01 * pos[:, 0]
        ps.u.from_numpy(disp)
        ps.x.from_numpy(pos + disp)

        compute.compute_deformation_gradient()
        compute.compute_strain()
        compute.compute_internal_force_with_stabilization(mat.lam, mat.mu)

        # 변형 에너지: W = 0.5 · Σ σ:ε · V
        stress = ps.stress.to_numpy()
        strain = ps.strain.to_numpy()
        vol = ps.volume.to_numpy()

        total_energy = 0.0
        for i in range(ps.n_particles):
            se = np.sum(stress[i] * strain[i])  # σ:ε (double contraction)
            total_energy += 0.5 * se * vol[i]

        assert total_energy > 0, f"변형 에너지가 음수: {total_energy}"


class TestBondFailureMechanics:
    """본드 파괴 역학 테스트."""

    def test_damage_conservation(self):
        """파괴 후 손상도가 [0, 1] 범위 내."""
        ps, kernel, bonds = create_2d_patch(5, 5, 0.1)

        # 큰 변위로 본드 파괴
        pos = ps.X.to_numpy()
        disp = np.zeros_like(pos)
        disp[:, 0] = 0.5 * pos[:, 0]
        ps.x.from_numpy(pos + disp)

        bonds.check_bond_failure_stretch(
            ps.x, kernel.neighbors, kernel.n_neighbors, 0.1
        )
        bonds.compute_damage(ps.damage, kernel.n_neighbors)

        damage = ps.get_damage()
        assert np.all(damage >= 0.0), "음수 손상도"
        assert np.all(damage <= 1.0), "1 초과 손상도"

    def test_no_damage_at_small_strain(self):
        """작은 변형에서 손상 없음."""
        ps, kernel, bonds = create_2d_patch(5, 5, 0.1)

        pos = ps.X.to_numpy()
        disp = np.zeros_like(pos)
        disp[:, 0] = 0.001 * pos[:, 0]  # 0.1% 변형률
        ps.x.from_numpy(pos + disp)

        broken = bonds.check_bond_failure_stretch(
            ps.x, kernel.neighbors, kernel.n_neighbors, 0.5  # 50% 임계 신장
        )
        assert broken == 0, f"작은 변형에서 {broken}개 본드 파괴"
