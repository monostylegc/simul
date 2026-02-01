"""3D 큐브 압축 예제 - NOSB-PD 검증.

5×4×3 격자에서 바닥 고정, 상단 압축 변위 적용.
변위 경계조건 기반 해석.

Usage:
    uv run python -m spine_sim.analysis.peridynamics.examples.cube_3d
"""

import taichi as ti
import numpy as np
import math

# Taichi 초기화
ti.init(arch=ti.cpu, default_fp=ti.f32)


def create_3d_cube_simulation():
    """3D 큐브 압축 시뮬레이션 생성 및 실행."""
    from ..core.particles import ParticleSystem
    from ..core.bonds import BondSystem
    from ..core.neighbor import NeighborSearch
    from ..core.nosb import NOSBCompute, NOSBMaterial

    # 격자 설정
    nx, ny, nz = 5, 4, 3  # 60 입자
    spacing = 0.01  # 10mm
    horizon = 3.015 * spacing  # 표준 horizon factor
    n_particles = nx * ny * nz

    # 재료 속성
    E = 1e6  # Young's modulus [Pa] - 1 MPa
    nu = 0.3  # Poisson's ratio
    rho = 1000  # 밀도 [kg/m^3]

    print("=" * 60)
    print("3D CUBE COMPRESSION - NOSB-PD EXAMPLE")
    print("=" * 60)
    print(f"\n격자: {nx} x {ny} x {nz} = {n_particles} 입자")
    print(f"간격: {spacing*1000:.1f} mm")
    print(f"Horizon: {horizon*1000:.2f} mm (factor: {horizon/spacing:.3f})")
    print(f"\n재료:")
    print(f"  Young's modulus: {E/1e6:.1f} MPa")
    print(f"  Poisson's ratio: {nu:.2f}")
    print(f"  밀도: {rho:.0f} kg/m³")

    # NOSB 재료 생성
    material = NOSBMaterial(E, nu, dim=3)
    print(f"  Bulk modulus: {material.K/1e6:.2f} MPa")
    print(f"  Shear modulus: {material.mu/1e6:.2f} MPa")

    # 입자 시스템 생성
    particles = ParticleSystem(n_particles, dim=3)
    particles.initialize_from_grid(
        origin=(0.0, 0.0, 0.0),
        spacing=spacing,
        n_points=(nx, ny, nz),
        density=rho
    )

    # 이웃 탐색 설정
    domain_margin = horizon
    neighbor_search = NeighborSearch(
        domain_min=(-domain_margin, -domain_margin, -domain_margin),
        domain_max=(nx*spacing + domain_margin, ny*spacing + domain_margin, nz*spacing + domain_margin),
        horizon=horizon,
        max_particles=n_particles,
        max_neighbors=64,
        dim=3
    )
    neighbor_search.build(particles.X, n_particles)

    # 이웃 통계
    n_neighbors = neighbor_search.get_all_neighbor_counts()
    print(f"\n이웃 통계:")
    print(f"  최소: {n_neighbors.min()}")
    print(f"  최대: {n_neighbors.max()}")
    print(f"  평균: {n_neighbors.mean():.1f}")

    # 본드 시스템 생성
    bonds = BondSystem(n_particles, max_bonds=64, dim=3)
    bonds.build_from_neighbor_search(particles, neighbor_search, horizon)

    # NOSB 계산 객체
    nosb = NOSBCompute(particles, bonds, stabilization=0.1)

    # Shape tensor 계산
    nosb.compute_shape_tensor()

    # 경계 조건 설정
    positions = particles.X.to_numpy()

    # 바닥 고정 (z = 0)
    bottom_indices = np.where(positions[:, 2] < spacing * 0.5)[0]

    # 상단 입자 (변위 적용)
    top_indices = np.where(positions[:, 2] > (nz-1)*spacing - spacing*0.5)[0]

    # 바닥만 고정 (상단은 변위 적용 후 자유)
    particles.set_fixed_particles(bottom_indices)

    print(f"\n경계 조건:")
    print(f"  고정 입자 (z=0): {len(bottom_indices)}개")
    print(f"  하중 입자 (z=max): {len(top_indices)}개")

    # 압축 변위 적용 (선형 보간)
    compression_strain = 0.01  # 1% 압축
    height = (nz - 1) * spacing

    print(f"\n적용 변위:")
    print(f"  변형률: {compression_strain*100:.1f}%")
    print(f"  높이: {height*1000:.1f} mm")

    # 모든 입자에 선형 변위 적용 (z 비례)
    x = particles.x.to_numpy()
    X = particles.X.to_numpy()

    for i in range(n_particles):
        if i not in bottom_indices:
            # z 좌표에 비례한 압축 변위
            z_ratio = X[i, 2] / height
            x[i, 2] = X[i, 2] - compression_strain * X[i, 2]

    particles.x.from_numpy(x.astype(np.float32))

    # Deformation gradient 계산
    nosb.compute_deformation_gradient()

    # 응력 계산 (NOSB)
    nosb.compute_force_state_linear_elastic(material.K, material.mu)

    # 결과 출력
    print("\n" + "=" * 60)
    print("결과")
    print("=" * 60)

    disp = particles.get_displacements()

    print(f"\n변위 (mm):")
    print(f"  max |u_x|: {np.max(np.abs(disp[:, 0]))*1000:.4f}")
    print(f"  max |u_y|: {np.max(np.abs(disp[:, 1]))*1000:.4f}")
    print(f"  max |u_z|: {np.max(np.abs(disp[:, 2]))*1000:.4f}")

    # 예상 변위 (1D 해석)
    expected_z_disp = compression_strain * height
    actual_z_disp = np.max(np.abs(disp[:, 2]))

    print(f"\n검증:")
    print(f"  예상 z 변위 (상단): {expected_z_disp*1000:.4f} mm")
    print(f"  실제 최대 z 변위: {actual_z_disp*1000:.4f} mm")

    # Deformation gradient 확인
    F = particles.F.to_numpy()
    print(f"\n변형 기울기 (중심 입자):")
    center_idx = n_particles // 2
    print(f"  F[{center_idx}] =")
    print(f"    [{F[center_idx, 0, 0]:.4f}, {F[center_idx, 0, 1]:.4f}, {F[center_idx, 0, 2]:.4f}]")
    print(f"    [{F[center_idx, 1, 0]:.4f}, {F[center_idx, 1, 1]:.4f}, {F[center_idx, 1, 2]:.4f}]")
    print(f"    [{F[center_idx, 2, 0]:.4f}, {F[center_idx, 2, 1]:.4f}, {F[center_idx, 2, 2]:.4f}]")

    # 예상 F (단축 압축)
    print(f"\n  예상 F_zz = 1 - strain = {1 - compression_strain:.4f}")

    # 1st Piola-Kirchhoff 응력 확인
    P = particles.P.to_numpy()
    print(f"\n응력 (중심 입자):")
    print(f"  P_zz[{center_idx}] = {P[center_idx, 2, 2]/1e6:.4f} MPa")

    # 예상 응력 (1D): sigma = E * epsilon
    expected_stress = E * compression_strain
    print(f"  예상 sigma_zz (1D) = {expected_stress/1e6:.4f} MPa")

    # 힘 확인
    f = particles.f.to_numpy()
    print(f"\n내부 힘:")
    print(f"  max |f_x|: {np.max(np.abs(f[:, 0])):.2e} N")
    print(f"  max |f_y|: {np.max(np.abs(f[:, 1])):.2e} N")
    print(f"  max |f_z|: {np.max(np.abs(f[:, 2])):.2e} N")

    return particles, bonds


def main():
    """3D 큐브 예제 실행."""
    particles, bonds = create_3d_cube_simulation()


if __name__ == "__main__":
    main()
