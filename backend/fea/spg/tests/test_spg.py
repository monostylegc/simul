"""SPG 모듈 단위 테스트.

커널 함수, 형상함수, 본드, 솔버의 기본 동작을 검증한다.
"""

import pytest
import numpy as np
import taichi as ti


# Taichi 초기화 (테스트 세션에서 한 번만)
@pytest.fixture(scope="session", autouse=True)
def init_taichi():
    try:
        ti.init(arch=ti.cpu, default_fp=ti.f64)
    except RuntimeError:
        pass  # 이미 초기화된 경우


class TestCubicBSplineKernel:
    """Cubic B-spline 커널 함수 테스트."""

    def test_kernel_at_center(self):
        """r=0에서 커널 값이 최대."""
        from ..core.kernel import SPGKernel
        kernel = SPGKernel(n_particles=1, dim=2, support_radius=1.0)

        # r=0에서 W(0) = C_d * 1.0
        import math
        C_d = 10.0 / (7.0 * math.pi)
        expected = C_d * 1.0

        # Taichi 커널로 검증
        @ti.kernel
        def eval_kernel() -> ti.f64:
            return kernel.cubic_bspline(0.0)

        val = eval_kernel()
        assert abs(val - expected) < 1e-10, f"W(0) = {val}, expected {expected}"

    def test_kernel_at_boundary(self):
        """r=1에서 커널 값이 0."""
        from ..core.kernel import SPGKernel
        kernel = SPGKernel(n_particles=1, dim=2, support_radius=1.0)

        @ti.kernel
        def eval_kernel() -> ti.f64:
            return kernel.cubic_bspline(1.0)

        val = eval_kernel()
        assert abs(val) < 1e-10, f"W(1) = {val}, expected 0"

    def test_kernel_outside(self):
        """r>1에서 커널 값이 0."""
        from ..core.kernel import SPGKernel
        kernel = SPGKernel(n_particles=1, dim=2, support_radius=1.0)

        @ti.kernel
        def eval_kernel() -> ti.f64:
            return kernel.cubic_bspline(1.5)

        val = eval_kernel()
        assert abs(val) < 1e-10

    def test_kernel_continuity(self):
        """r=0.5에서 연속성 검증."""
        from ..core.kernel import SPGKernel
        kernel = SPGKernel(n_particles=1, dim=2, support_radius=1.0)

        @ti.kernel
        def eval_left() -> ti.f64:
            return kernel.cubic_bspline(0.4999)

        @ti.kernel
        def eval_right() -> ti.f64:
            return kernel.cubic_bspline(0.5001)

        left = eval_left()
        right = eval_right()
        assert abs(left - right) < 1e-3, f"불연속: left={left}, right={right}"

    def test_kernel_positive(self):
        """지지 영역 내에서 커널 값이 양수."""
        from ..core.kernel import SPGKernel
        kernel = SPGKernel(n_particles=1, dim=2, support_radius=1.0)

        @ti.kernel
        def eval_all() -> ti.f64:
            min_val = 1.0
            for _ in range(1):
                for step in range(100):
                    r = ti.cast(step, ti.f64) / 100.0
                    val = kernel.cubic_bspline(r)
                    if val < min_val:
                        min_val = val
            return min_val

        min_val = eval_all()
        assert min_val >= 0.0, f"음수 커널 값 발견: {min_val}"


class TestSPGParticles:
    """SPG 입자 시스템 테스트."""

    def test_2d_grid_creation(self):
        """2D 격자 입자 생성."""
        from ..core.particles import SPGParticleSystem

        nx, ny = 5, 5
        ps = SPGParticleSystem(n_particles=nx * ny, dim=2)
        ps.initialize_from_grid(
            origin=(0.0, 0.0),
            spacing=0.1,
            n_points=(nx, ny),
            density=1000.0
        )

        pos = ps.get_positions()
        assert pos.shape == (25, 2)
        assert np.allclose(pos[0], [0.0, 0.0])

    def test_3d_grid_creation(self):
        """3D 격자 입자 생성."""
        from ..core.particles import SPGParticleSystem

        nx, ny, nz = 3, 3, 3
        ps = SPGParticleSystem(n_particles=nx * ny * nz, dim=3)
        ps.initialize_from_grid(
            origin=(0.0, 0.0, 0.0),
            spacing=0.1,
            n_points=(nx, ny, nz),
            density=1000.0
        )

        pos = ps.get_positions()
        assert pos.shape == (27, 3)

    def test_volume_computation(self):
        """격자 입자 부피 확인."""
        from ..core.particles import SPGParticleSystem

        spacing = 0.2
        ps = SPGParticleSystem(n_particles=4, dim=2)
        ps.initialize_from_grid(
            origin=(0.0, 0.0),
            spacing=spacing,
            n_points=(2, 2),
            density=1000.0
        )

        vol = ps.volume.to_numpy()
        expected_vol = spacing ** 2
        assert np.allclose(vol, expected_vol), f"vol={vol}, expected={expected_vol}"

    def test_mass_computation(self):
        """질량 = 밀도 × 부피 확인."""
        from ..core.particles import SPGParticleSystem

        spacing = 0.1
        density = 2000.0
        ps = SPGParticleSystem(n_particles=4, dim=2)
        ps.initialize_from_grid(
            origin=(0.0, 0.0),
            spacing=spacing,
            n_points=(2, 2),
            density=density
        )

        mass = ps.mass.to_numpy()
        expected = density * spacing ** 2
        assert np.allclose(mass, expected)

    def test_fixed_particles(self):
        """고정 입자 설정."""
        from ..core.particles import SPGParticleSystem

        ps = SPGParticleSystem(n_particles=9, dim=2)
        ps.initialize_from_grid(
            origin=(0.0, 0.0),
            spacing=0.1,
            n_points=(3, 3),
            density=1000.0
        )

        ps.set_fixed_particles(np.array([0, 1, 2]))
        fixed = ps.fixed.to_numpy()
        assert fixed[0] == 1 and fixed[1] == 1 and fixed[2] == 1
        assert fixed[3] == 0


class TestSPGShapeFunctions:
    """형상함수 테스트."""

    def test_partition_of_unity(self):
        """형상함수 합 = 1 (partition of unity)."""
        from ..core.particles import SPGParticleSystem
        from ..core.kernel import SPGKernel

        nx, ny = 5, 5
        spacing = 0.1
        n_particles = nx * ny
        support_radius = spacing * 2.5

        ps = SPGParticleSystem(n_particles=n_particles, dim=2)
        ps.initialize_from_grid(
            origin=(0.0, 0.0),
            spacing=spacing,
            n_points=(nx, ny),
            density=1000.0
        )

        kernel = SPGKernel(
            n_particles=n_particles,
            max_neighbors=64,
            dim=2,
            support_radius=support_radius
        )

        # 이웃 탐색
        positions = ps.X.to_numpy()
        kernel.build_neighbor_list(positions, support_radius)

        # 형상함수 계산
        kernel.compute_shape_functions(ps.X, ps.volume)

        # 내부 입자에서 합 ≈ 1 확인 (경계 입자는 정확하지 않을 수 있음)
        sums = kernel.get_shape_function_sum()

        # 중앙 입자 (경계 효과 없음)
        center_idx = (nx // 2) * ny + ny // 2
        assert abs(sums[center_idx] - 1.0) < 0.15, (
            f"중앙 입자 형상함수 합 = {sums[center_idx]}, 기대값 1.0"
        )

    def test_neighbor_count(self):
        """적절한 이웃 수 확인."""
        from ..core.particles import SPGParticleSystem
        from ..core.kernel import SPGKernel

        nx, ny = 5, 5
        spacing = 0.1
        n_particles = nx * ny

        ps = SPGParticleSystem(n_particles=n_particles, dim=2)
        ps.initialize_from_grid(
            origin=(0.0, 0.0),
            spacing=spacing,
            n_points=(nx, ny),
            density=1000.0
        )

        support_radius = spacing * 2.5
        kernel = SPGKernel(
            n_particles=n_particles,
            max_neighbors=64,
            dim=2,
            support_radius=support_radius
        )

        positions = ps.X.to_numpy()
        kernel.build_neighbor_list(positions, support_radius)

        n_nbr = kernel.n_neighbors.to_numpy()
        # 내부 입자는 충분한 이웃을 가져야 함
        center_idx = (nx // 2) * ny + ny // 2
        assert n_nbr[center_idx] >= 8, f"이웃 수 = {n_nbr[center_idx]}, 최소 8 필요"


class TestSPGBonds:
    """본드 시스템 테스트."""

    def test_bond_creation(self):
        """본드 생성 확인."""
        from ..core.particles import SPGParticleSystem
        from ..core.kernel import SPGKernel
        from ..core.bonds import SPGBondSystem

        n_particles = 9
        spacing = 0.1
        ps = SPGParticleSystem(n_particles=n_particles, dim=2)
        ps.initialize_from_grid(
            origin=(0.0, 0.0),
            spacing=spacing,
            n_points=(3, 3),
            density=1000.0
        )

        kernel = SPGKernel(
            n_particles=n_particles, dim=2,
            support_radius=spacing * 2.5
        )
        kernel.build_neighbor_list(ps.X.to_numpy(), spacing * 2.5)

        bonds = SPGBondSystem(n_particles=n_particles, dim=2)
        bonds.build_from_kernel(ps, kernel)

        # 모든 본드가 건전
        intact = bonds.count_intact_bonds(kernel.n_neighbors)
        assert intact > 0

    def test_bond_failure(self):
        """본드 파괴 테스트."""
        from ..core.particles import SPGParticleSystem
        from ..core.kernel import SPGKernel
        from ..core.bonds import SPGBondSystem

        n_particles = 4
        spacing = 0.1
        ps = SPGParticleSystem(n_particles=n_particles, dim=2)
        ps.initialize_from_grid(
            origin=(0.0, 0.0),
            spacing=spacing,
            n_points=(2, 2),
            density=1000.0
        )

        kernel = SPGKernel(
            n_particles=n_particles, dim=2,
            support_radius=spacing * 2.5
        )
        kernel.build_neighbor_list(ps.X.to_numpy(), spacing * 2.5)

        bonds = SPGBondSystem(n_particles=n_particles, dim=2)
        bonds.build_from_kernel(ps, kernel)

        # 큰 변위를 주어 본드 파괴 유도
        disp = np.array([
            [0.0, 0.0],
            [0.5, 0.0],  # 크게 이동
            [0.0, 0.0],
            [0.5, 0.0],
        ], dtype=np.float64)
        new_pos = ps.X.to_numpy() + disp
        ps.x.from_numpy(new_pos)

        # 아주 작은 임계 신장으로 파괴 유도
        broken_count = bonds.check_bond_failure_stretch(
            ps.x, kernel.neighbors, kernel.n_neighbors, 0.01
        )
        assert broken_count > 0, "본드가 파괴되어야 함"


class TestSPGMaterial:
    """재료 모델 테스트."""

    def test_lame_parameters(self):
        """라메 매개변수 계산 확인."""
        from ..material.elastic import SPGElasticMaterial

        mat = SPGElasticMaterial(
            youngs_modulus=1e4,
            poisson_ratio=0.3,
            density=1000.0,
            dim=3
        )

        # μ = E / (2(1+ν))
        expected_mu = 1e4 / (2 * 1.3)
        assert abs(mat.mu - expected_mu) < 1e-6

        # λ = Eν / ((1+ν)(1-2ν))
        expected_lam = 1e4 * 0.3 / (1.3 * 0.4)
        assert abs(mat.lam - expected_lam) < 1e-6

    def test_wave_speed(self):
        """파속도 계산 확인."""
        from ..material.elastic import SPGElasticMaterial

        mat = SPGElasticMaterial(
            youngs_modulus=1e6,
            poisson_ratio=0.25,
            density=1000.0,
            dim=3
        )

        c_p = mat.get_wave_speed()
        assert c_p > 0, "파속도는 양수"

    def test_stable_dt(self):
        """안정 시간 간격 추정."""
        from ..material.elastic import SPGElasticMaterial

        mat = SPGElasticMaterial(
            youngs_modulus=1e6,
            poisson_ratio=0.25,
            density=1000.0,
            dim=3
        )

        dt = mat.estimate_stable_dt(spacing=0.01)
        assert dt > 0 and dt < 0.01, f"dt = {dt}"


class TestSPGSolver:
    """SPG 솔버 통합 테스트."""

    def test_zero_displacement_zero_force(self):
        """변위 없으면 내부력 0."""
        from ..core.particles import SPGParticleSystem
        from ..core.kernel import SPGKernel
        from ..core.bonds import SPGBondSystem
        from ..core.spg_compute import SPGCompute
        from ..material.elastic import SPGElasticMaterial

        nx, ny = 5, 5
        spacing = 0.1
        n_particles = nx * ny

        ps = SPGParticleSystem(n_particles=n_particles, dim=2)
        ps.initialize_from_grid(
            origin=(0.0, 0.0),
            spacing=spacing,
            n_points=(nx, ny),
            density=1000.0
        )

        support_radius = spacing * 2.5
        kernel = SPGKernel(
            n_particles=n_particles, dim=2,
            support_radius=support_radius
        )
        kernel.build_neighbor_list(ps.X.to_numpy(), support_radius)
        kernel.compute_shape_functions(ps.X, ps.volume)

        bonds = SPGBondSystem(n_particles=n_particles, dim=2)
        bonds.build_from_kernel(ps, kernel)

        mat = SPGElasticMaterial(1e4, 0.3, 1000.0, dim=2)
        compute = SPGCompute(ps, kernel, bonds, stabilization=0.1)

        # 변위 없음 → F = I → ε = 0 → σ = 0 → f_int = 0
        compute.compute_deformation_gradient()
        compute.compute_strain()
        ps.set_material_constants(mat.lam, mat.mu)
        compute.compute_internal_force_with_stabilization()

        f_int = ps.f_int.to_numpy()
        max_force = np.max(np.abs(f_int))
        assert max_force < 1e-10, f"변위 없는데 내부력 = {max_force}"

    def test_uniform_strain_constant_stress(self):
        """균일 변형률 → 균일 응력."""
        from ..core.particles import SPGParticleSystem
        from ..core.kernel import SPGKernel
        from ..core.bonds import SPGBondSystem
        from ..core.spg_compute import SPGCompute
        from ..material.elastic import SPGElasticMaterial

        nx, ny = 7, 7
        spacing = 0.1
        n_particles = nx * ny

        ps = SPGParticleSystem(n_particles=n_particles, dim=2)
        ps.initialize_from_grid(
            origin=(0.0, 0.0),
            spacing=spacing,
            n_points=(nx, ny),
            density=1000.0
        )

        support_radius = spacing * 2.5
        kernel = SPGKernel(
            n_particles=n_particles, dim=2,
            support_radius=support_radius
        )
        kernel.build_neighbor_list(ps.X.to_numpy(), support_radius)
        kernel.compute_shape_functions(ps.X, ps.volume)

        bonds = SPGBondSystem(n_particles=n_particles, dim=2)
        bonds.build_from_kernel(ps, kernel)

        # 균일 인장 변위: u_x = 0.01 * X, u_y = 0
        positions = ps.X.to_numpy()
        strain_xx = 0.01
        displacements = np.zeros_like(positions)
        displacements[:, 0] = strain_xx * positions[:, 0]
        ps.u.from_numpy(displacements)
        ps.x.from_numpy(positions + displacements)

        mat = SPGElasticMaterial(1e4, 0.3, 1000.0, dim=2)
        compute = SPGCompute(ps, kernel, bonds, stabilization=0.1)

        compute.compute_deformation_gradient()
        compute.compute_strain()

        # 내부 입자의 변형률 확인
        strain = ps.strain.to_numpy()
        center = (nx // 2) * ny + ny // 2

        # ε_xx ≈ 0.01 (내부 입자)
        assert abs(strain[center, 0, 0] - strain_xx) < 0.005, (
            f"ε_xx = {strain[center, 0, 0]}, expected {strain_xx}"
        )
