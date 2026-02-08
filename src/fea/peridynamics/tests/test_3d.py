"""3D Peridynamics 테스트.

3D 격자 생성, 이웃 탐색, 본드 시스템, NOSB shape tensor, 준정적 압축 해석 테스트.
"""

import pytest
import numpy as np
import taichi as ti


@pytest.fixture(scope="module", autouse=True)
def init_taichi():
    """모듈당 한 번 Taichi 초기화."""
    ti.init(arch=ti.cpu, default_fp=ti.f32)


class Test3DGridInitialization:
    """3D 격자 초기화 테스트."""

    def test_3d_grid_creation(self):
        """3D 격자 생성 테스트."""
        from src.fea.peridynamics.core.particles import ParticleSystem

        nx, ny, nz = 3, 3, 3
        n = nx * ny * nz
        spacing = 0.1
        origin = (0.0, 0.0, 0.0)

        ps = ParticleSystem(n, dim=3)
        ps.initialize_from_grid(origin, spacing, (nx, ny, nz), density=1000.0)

        positions = ps.get_positions()
        assert positions.shape == (n, 3)

        # 모서리 입자 확인
        assert np.allclose(positions[0], [0.0, 0.0, 0.0], atol=1e-6)
        # 마지막 입자는 (2*0.1, 2*0.1, 2*0.1) = (0.2, 0.2, 0.2)
        expected_last = [(nx-1)*spacing, (ny-1)*spacing, (nz-1)*spacing]
        assert np.allclose(positions[-1], expected_last, atol=1e-6)

    def test_3d_particle_volume(self):
        """3D 입자 부피 테스트."""
        from src.fea.peridynamics.core.particles import ParticleSystem

        nx, ny, nz = 2, 2, 2
        n = nx * ny * nz
        spacing = 0.1
        density = 1000.0

        ps = ParticleSystem(n, dim=3)
        ps.initialize_from_grid((0, 0, 0), spacing, (nx, ny, nz), density=density)

        # 입자 부피 = spacing^3
        expected_volume = spacing ** 3
        volumes = ps.volume.to_numpy()
        assert np.allclose(volumes, expected_volume, rtol=1e-6)

        # 질량 = 부피 * 밀도
        expected_mass = expected_volume * density
        masses = ps.mass.to_numpy()
        assert np.allclose(masses, expected_mass, rtol=1e-6)


class Test3DNeighborSearch:
    """3D 이웃 탐색 테스트."""

    def test_3d_neighbor_count(self):
        """3D 이웃 수 테스트 (직접 이웃만)."""
        from src.fea.peridynamics.core.particles import ParticleSystem
        from src.fea.peridynamics.core.neighbor import NeighborSearch

        # 3x3x3 격자
        nx, ny, nz = 3, 3, 3
        n = nx * ny * nz
        spacing = 1.0
        # horizon = 1.1: 직접 이웃만 포함 (1.0 < 1.1 < sqrt(2) ~ 1.414)
        horizon = 1.1

        ps = ParticleSystem(n, dim=3)
        ps.initialize_from_grid((0, 0, 0), spacing, (nx, ny, nz), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-1, -1, -1),
            domain_max=(3, 3, 3),
            horizon=horizon,
            max_particles=n,
            max_neighbors=30,
            dim=3
        )

        ns.build(ps.X, n)

        counts = ns.get_all_neighbor_counts()

        # 중심 입자 (1,1,1) -> 인덱스 13
        # horizon=1.1에서 직접 이웃만: 6개 (±x, ±y, ±z)
        center_idx = 13  # 1*9 + 1*3 + 1 = 13
        assert counts[center_idx] == 6, f"Center has {counts[center_idx]} neighbors, expected 6"

        # 모서리 입자 (0,0,0) -> 인덱스 0
        # 직접 이웃: 3개 (+x, +y, +z)
        assert counts[0] == 3, f"Corner has {counts[0]} neighbors, expected 3"

    def test_3d_diagonal_neighbors(self):
        """3D 대각선 이웃 포함 테스트."""
        from src.fea.peridynamics.core.particles import ParticleSystem
        from src.fea.peridynamics.core.neighbor import NeighborSearch

        # 3x3x3 격자
        nx, ny, nz = 3, 3, 3
        n = nx * ny * nz
        spacing = 1.0
        # horizon = 1.5: sqrt(2) ~ 1.414 < 1.5 < sqrt(3) ~ 1.732
        # face(6) + edge(12) = 18 이웃 포함
        horizon = 1.5

        ps = ParticleSystem(n, dim=3)
        ps.initialize_from_grid((0, 0, 0), spacing, (nx, ny, nz), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-1, -1, -1),
            domain_max=(3, 3, 3),
            horizon=horizon,
            max_particles=n,
            max_neighbors=30,
            dim=3
        )

        ns.build(ps.X, n)

        counts = ns.get_all_neighbor_counts()

        # 중심 입자: 6 (face) + 12 (edge) = 18
        center_idx = 13
        assert counts[center_idx] == 18, f"Center has {counts[center_idx]} neighbors, expected 18"

        # 모서리: 3 (face) + 3 (edge) = 6
        assert counts[0] == 6, f"Corner has {counts[0]} neighbors, expected 6"


class Test3DBondSystem:
    """3D 본드 시스템 테스트."""

    def test_3d_bond_creation(self):
        """3D 본드 생성 테스트."""
        from src.fea.peridynamics.core.particles import ParticleSystem
        from src.fea.peridynamics.core.neighbor import NeighborSearch
        from src.fea.peridynamics.core.bonds import BondSystem

        nx, ny, nz = 2, 2, 2
        n = nx * ny * nz
        spacing = 1.0
        horizon = 1.5

        ps = ParticleSystem(n, dim=3)
        ps.initialize_from_grid((0, 0, 0), spacing, (nx, ny, nz), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-1, -1, -1),
            domain_max=(2, 2, 2),
            horizon=horizon,
            max_particles=n,
            dim=3
        )
        ns.build(ps.X, n)

        bonds = BondSystem(n, max_bonds=30, dim=3)
        bonds.build_from_neighbor_search(ps, ns, horizon)

        # 본드 수가 이웃 수와 일치
        bond_counts = bonds.get_neighbor_count()
        neighbor_counts = ns.get_all_neighbor_counts()
        assert np.array_equal(bond_counts, neighbor_counts)

        # 모든 본드가 처음에는 intact
        broken = bonds.get_broken_bonds()
        assert np.sum(broken) == 0

    def test_3d_bond_vectors(self):
        """3D 본드 벡터 테스트."""
        from src.fea.peridynamics.core.particles import ParticleSystem
        from src.fea.peridynamics.core.neighbor import NeighborSearch
        from src.fea.peridynamics.core.bonds import BondSystem

        nx, ny, nz = 2, 2, 2
        n = nx * ny * nz
        spacing = 1.0
        # horizon = 1.1: 직접 이웃만 포함
        horizon = 1.1

        ps = ParticleSystem(n, dim=3)
        ps.initialize_from_grid((0, 0, 0), spacing, (nx, ny, nz), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-1, -1, -1),
            domain_max=(2, 2, 2),
            horizon=horizon,
            max_particles=n,
            dim=3
        )
        ns.build(ps.X, n)

        bonds = BondSystem(n, max_bonds=30, dim=3)
        bonds.build_from_neighbor_search(ps, ns, horizon)

        # 본드 길이 확인 (직접 이웃만이므로 길이 = spacing)
        xi_length = bonds.xi_length.to_numpy()
        for i in range(n):
            n_bonds = bonds.n_neighbors[i]
            for k in range(n_bonds):
                length = xi_length[i, k]
                # 직접 이웃만 있으므로 길이 = spacing
                assert np.isclose(length, spacing, atol=1e-5), f"Bond length {length} != {spacing}"


class Test3DNOSBShapeTensor:
    """3D NOSB shape tensor 테스트."""

    def test_3d_shape_tensor_symmetry(self):
        """Shape tensor 대칭성 테스트."""
        from src.fea.peridynamics.core.particles import ParticleSystem
        from src.fea.peridynamics.core.neighbor import NeighborSearch
        from src.fea.peridynamics.core.bonds import BondSystem
        from src.fea.peridynamics.core.nosb import NOSBCompute

        nx, ny, nz = 3, 3, 3
        n = nx * ny * nz
        spacing = 1.0
        horizon = 1.8  # 대각선 이웃 포함

        ps = ParticleSystem(n, dim=3)
        ps.initialize_from_grid((0, 0, 0), spacing, (nx, ny, nz), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-1, -1, -1),
            domain_max=(4, 4, 4),
            horizon=horizon,
            max_particles=n,
            max_neighbors=30,
            dim=3
        )
        ns.build(ps.X, n)

        bonds = BondSystem(n, max_bonds=30, dim=3)
        bonds.build_from_neighbor_search(ps, ns, horizon)

        nosb = NOSBCompute(ps, bonds)
        nosb.compute_shape_tensor()

        # Shape tensor K는 대칭이어야 함
        K = ps.K.to_numpy()
        for i in range(n):
            K_i = K[i]
            assert np.allclose(K_i, K_i.T, atol=1e-5), f"K[{i}] not symmetric"

    def test_3d_shape_tensor_positive_definite(self):
        """Shape tensor 양정치성 테스트 (중심 입자)."""
        from src.fea.peridynamics.core.particles import ParticleSystem
        from src.fea.peridynamics.core.neighbor import NeighborSearch
        from src.fea.peridynamics.core.bonds import BondSystem
        from src.fea.peridynamics.core.nosb import NOSBCompute

        nx, ny, nz = 3, 3, 3
        n = nx * ny * nz
        spacing = 1.0
        horizon = 1.8

        ps = ParticleSystem(n, dim=3)
        ps.initialize_from_grid((0, 0, 0), spacing, (nx, ny, nz), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-1, -1, -1),
            domain_max=(4, 4, 4),
            horizon=horizon,
            max_particles=n,
            max_neighbors=30,
            dim=3
        )
        ns.build(ps.X, n)

        bonds = BondSystem(n, max_bonds=30, dim=3)
        bonds.build_from_neighbor_search(ps, ns, horizon)

        nosb = NOSBCompute(ps, bonds)
        nosb.compute_shape_tensor()

        # 중심 입자의 shape tensor는 양정치여야 함
        K = ps.K.to_numpy()
        center_idx = 13
        eigvals = np.linalg.eigvalsh(K[center_idx])
        assert np.all(eigvals > 0), f"K[center] eigenvalues: {eigvals}"

    def test_3d_deformation_gradient_identity(self):
        """변형 없을 때 F = I 테스트."""
        from src.fea.peridynamics.core.particles import ParticleSystem
        from src.fea.peridynamics.core.neighbor import NeighborSearch
        from src.fea.peridynamics.core.bonds import BondSystem
        from src.fea.peridynamics.core.nosb import NOSBCompute

        nx, ny, nz = 3, 3, 3
        n = nx * ny * nz
        spacing = 1.0
        horizon = 1.8

        ps = ParticleSystem(n, dim=3)
        ps.initialize_from_grid((0, 0, 0), spacing, (nx, ny, nz), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-1, -1, -1),
            domain_max=(4, 4, 4),
            horizon=horizon,
            max_particles=n,
            max_neighbors=30,
            dim=3
        )
        ns.build(ps.X, n)

        bonds = BondSystem(n, max_bonds=30, dim=3)
        bonds.build_from_neighbor_search(ps, ns, horizon)

        nosb = NOSBCompute(ps, bonds)
        nosb.compute_shape_tensor()
        nosb.compute_deformation_gradient()

        # 변형 없으면 F = I
        F = ps.F.to_numpy()
        I = np.eye(3)
        for i in range(n):
            # 경계 입자는 이웃이 불완전해서 정확한 I가 아닐 수 있음
            # 중심 입자만 확인
            if i == 13:  # 중심
                assert np.allclose(F[i], I, atol=1e-4), f"F[{i}] = {F[i]}"


class Test3DQuasiStaticCompression:
    """3D 준정적 압축 해석 테스트."""

    def test_3d_compression_displacement(self):
        """3D 압축 시 변위 방향 테스트 (고정 입자만 검증)."""
        from src.fea.peridynamics.core.particles import ParticleSystem
        from src.fea.peridynamics.core.neighbor import NeighborSearch
        from src.fea.peridynamics.core.bonds import BondSystem

        # 2x2x2 격자 - 간단한 설정
        nx, ny, nz = 2, 2, 2
        n = nx * ny * nz
        spacing = 0.01  # 1cm
        horizon = 3.015 * spacing

        ps = ParticleSystem(n, dim=3)
        ps.initialize_from_grid((0, 0, 0), spacing, (nx, ny, nz), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-horizon, -horizon, -horizon),
            domain_max=(2*spacing + horizon, 2*spacing + horizon, 2*spacing + horizon),
            horizon=horizon,
            max_particles=n,
            max_neighbors=64,
            dim=3
        )
        ns.build(ps.X, n)

        bonds = BondSystem(n, max_bonds=64, dim=3)
        bonds.build_from_neighbor_search(ps, ns, horizon)

        # 하단 고정 (z = 0)
        positions = ps.X.to_numpy()
        bottom_indices = np.where(positions[:, 2] < spacing * 0.5)[0]
        ps.set_fixed_particles(bottom_indices)

        # 상단에 작은 압축 변위 적용 (직접)
        top_indices = np.where(positions[:, 2] > spacing * 0.5)[0]
        compression = -0.0001  # 0.1mm 압축

        x = ps.x.to_numpy()
        x[top_indices, 2] += compression
        ps.x.from_numpy(x.astype(np.float32))

        # 변위 확인 - 솔버 없이 직접 변위 확인
        disp = ps.get_displacements()

        # 하단 입자는 변위 0
        for idx in bottom_indices:
            assert np.isclose(disp[idx, 2], 0.0, atol=1e-6), \
                f"Bottom particle {idx} should have zero z displacement"

        # 상단 입자는 음의 z 변위
        for idx in top_indices:
            assert disp[idx, 2] < 0, \
                f"Top particle {idx} should have negative z displacement, got {disp[idx, 2]}"

    def test_3d_solver_stability(self):
        """3D 솔버 안정성 테스트 (에너지 발산 없음)."""
        from src.fea.peridynamics.core.particles import ParticleSystem
        from src.fea.peridynamics.core.neighbor import NeighborSearch
        from src.fea.peridynamics.core.bonds import BondSystem
        from src.fea.peridynamics.solver.quasi_static import QuasiStaticSolver

        nx, ny, nz = 2, 2, 2
        n = nx * ny * nz
        spacing = 0.01
        horizon = 3.015 * spacing

        ps = ParticleSystem(n, dim=3)
        ps.initialize_from_grid((0, 0, 0), spacing, (nx, ny, nz), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-horizon, -horizon, -horizon),
            domain_max=(2*spacing + horizon, 2*spacing + horizon, 2*spacing + horizon),
            horizon=horizon,
            max_particles=n,
            max_neighbors=64,
            dim=3
        )
        ns.build(ps.X, n)

        bonds = BondSystem(n, max_bonds=64, dim=3)
        bonds.build_from_neighbor_search(ps, ns, horizon)

        E = 1e6
        K = E / (3 * (1 - 2*0.25))
        import math
        c = 18 * K / (math.pi * horizon**4)

        solver = QuasiStaticSolver(ps, bonds, micromodulus=c)

        # 하단 고정
        ps.set_fixed_particles(np.array([0, 1, 2, 3]))

        # 작은 교란
        x = ps.x.to_numpy()
        x[4:, 2] += 0.0001
        ps.x.from_numpy(x.astype(np.float32))

        # 여러 스텝 후 발산하지 않음
        for _ in range(50):
            info = solver.step()

        # 변위가 합리적인 범위 내
        disp = ps.get_displacements()
        max_disp = np.max(np.abs(disp))
        assert max_disp < 0.1, f"Max displacement {max_disp} too large (unstable)"
        assert not np.any(np.isnan(disp)), "NaN in displacements"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
