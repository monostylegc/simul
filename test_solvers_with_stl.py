#!/usr/bin/env python
"""STL 모델을 사용한 FEM/Peridynamics 솔버 테스트.

실제 척추 모델(L4, L5)에 대해 구조 해석을 수행합니다.
"""

import taichi as ti
import numpy as np
from pathlib import Path
import time

# Taichi 초기화
ti.init(arch=ti.cpu)  # 솔버는 CPU에서 실행

from spine_sim.core.mesh import TriangleMesh


def load_and_center_mesh(filepath: str) -> TriangleMesh:
    """메쉬 로드 및 중심 정렬."""
    mesh = TriangleMesh.load(filepath)

    # 중심을 원점으로 이동
    center = (mesh.vertices.min(axis=0) + mesh.vertices.max(axis=0)) / 2
    mesh.vertices = mesh.vertices - center
    mesh.compute_normals()

    return mesh


def mesh_to_surface_particles(mesh: TriangleMesh, spacing: float = 2.0) -> np.ndarray:
    """삼각형 메쉬를 표면 입자로 변환.

    Args:
        mesh: 삼각형 메쉬
        spacing: 입자 간격 (mm)

    Returns:
        입자 위치 배열 (N, 3)
    """
    particles = []

    for face in mesh.faces:
        v0, v1, v2 = mesh.vertices[face]

        # 삼각형 면적
        edge1 = v1 - v0
        edge2 = v2 - v0
        area = 0.5 * np.linalg.norm(np.cross(edge1, edge2))

        # 면적에 비례한 샘플 수
        n_samples = max(1, int(area / (spacing * spacing)))

        for _ in range(n_samples):
            # 삼각형 내 무작위 점 (barycentric coordinates)
            r1, r2 = np.random.random(2)
            if r1 + r2 > 1:
                r1, r2 = 1 - r1, 1 - r2

            point = v0 + r1 * edge1 + r2 * edge2
            particles.append(point)

    particles = np.array(particles, dtype=np.float32)

    # 중복 제거 (간단한 그리드 기반)
    unique_particles = []
    grid = set()
    grid_size = spacing * 0.5

    for p in particles:
        key = (int(p[0] / grid_size), int(p[1] / grid_size), int(p[2] / grid_size))
        if key not in grid:
            grid.add(key)
            unique_particles.append(p)

    return np.array(unique_particles, dtype=np.float32)


def test_peridynamics_with_mesh():
    """Peridynamics 솔버로 뼈 모델 테스트."""
    from spine_sim.analysis.peridynamics.core.particles import ParticleSystem
    from spine_sim.analysis.peridynamics.core.neighbor import NeighborSearch
    from spine_sim.analysis.peridynamics.core.bonds import BondSystem

    print("\n" + "=" * 60)
    print("Peridynamics 테스트")
    print("=" * 60)

    # L5 모델 로드
    stl_dir = Path("stl")
    mesh = load_and_center_mesh(str(stl_dir / "L5.stl"))

    print(f"\n원본 메쉬: {mesh.n_vertices:,} 정점, {mesh.n_faces:,} 삼각형")

    # 표면 입자 생성
    spacing = 3.0  # mm
    particles_pos = mesh_to_surface_particles(mesh, spacing)
    n_particles = len(particles_pos)

    print(f"생성된 입자 수: {n_particles:,} (spacing={spacing}mm)")

    if n_particles > 50000:
        print("경고: 입자 수가 너무 많음. spacing 증가 필요.")
        spacing = 5.0
        particles_pos = mesh_to_surface_particles(mesh, spacing)
        n_particles = len(particles_pos)
        print(f"재샘플링: {n_particles:,} 입자 (spacing={spacing}mm)")

    # Peridynamics 시스템 초기화
    horizon = spacing * 3.0  # 영향 반경

    print(f"\nPeridynamics 파라미터:")
    print(f"  Horizon: {horizon:.1f} mm")

    # 입자 시스템 생성
    ps = ParticleSystem(n_particles=n_particles)
    ps.x.from_numpy(particles_pos)

    # 뼈 재료 속성 설정
    E = 17000.0  # 영률 (MPa) - 피질골
    rho = 1900.0  # 밀도 (kg/m³)

    # 질량 계산 (간단히 균일 분포)
    volume_per_particle = (spacing ** 3) * 0.5  # 대략적 체적
    mass = rho * volume_per_particle * 1e-9  # kg

    mass_np = np.full(n_particles, mass, dtype=np.float32)
    ps.mass.from_numpy(mass_np)

    # 이웃 탐색
    print("\n이웃 탐색 중...")
    t0 = time.time()

    neighbor = NeighborSearch(ps, horizon)
    neighbor.build()

    t1 = time.time()
    print(f"  소요 시간: {t1-t0:.2f}초")

    # 본드 생성
    print("\n본드 생성 중...")
    t0 = time.time()

    bonds = BondSystem(ps, neighbor, horizon)
    bonds.init_bonds()

    t1 = time.time()
    n_bonds = bonds.bond_count[None]
    print(f"  생성된 본드 수: {n_bonds:,}")
    print(f"  소요 시간: {t1-t0:.2f}초")
    print(f"  평균 이웃 수: {n_bonds / n_particles:.1f}")

    print("\nPeridynamics 초기화 완료!")

    return ps, bonds


def test_simple_loading():
    """간단한 압축 하중 시뮬레이션."""
    from spine_sim.analysis.peridynamics.core.particles import ParticleSystem

    print("\n" + "=" * 60)
    print("간단한 압축 하중 테스트")
    print("=" * 60)

    # 간단한 직육면체 입자 생성
    spacing = 2.0
    nx, ny, nz = 10, 10, 20  # 20x20x40mm 블록

    positions = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                x = (i - nx/2) * spacing
                y = (j - ny/2) * spacing
                z = k * spacing
                positions.append([x, y, z])

    positions = np.array(positions, dtype=np.float32)
    n_particles = len(positions)

    print(f"입자 수: {n_particles}")
    print(f"블록 크기: {nx*spacing} x {ny*spacing} x {nz*spacing} mm")

    # 입자 시스템
    ps = ParticleSystem(n_particles=n_particles)
    ps.x.from_numpy(positions)

    # 하단 고정
    fixed = np.zeros(n_particles, dtype=np.int32)
    bottom_z = positions[:, 2].min()
    fixed[positions[:, 2] < bottom_z + spacing] = 1
    ps.fixed.from_numpy(fixed)

    n_fixed = np.sum(fixed)
    print(f"고정된 입자: {n_fixed}")

    # 상단에 하중 (간단한 변위 적용)
    disp = np.zeros_like(positions)
    top_z = positions[:, 2].max()
    top_mask = positions[:, 2] > top_z - spacing

    # 상단 1mm 압축
    disp[top_mask, 2] = -1.0

    print(f"상단 입자: {np.sum(top_mask)}")
    print(f"적용 변위: -1.0 mm (Z)")

    ps.u.from_numpy(disp)

    print("\n하중 조건 설정 완료!")

    return ps


def analyze_mesh_quality(mesh: TriangleMesh):
    """메쉬 품질 분석."""
    print("\n메쉬 품질 분석:")

    # 삼각형 면적 분포
    areas = []
    for face in mesh.faces:
        v0, v1, v2 = mesh.vertices[face]
        edge1 = v1 - v0
        edge2 = v2 - v0
        area = 0.5 * np.linalg.norm(np.cross(edge1, edge2))
        areas.append(area)

    areas = np.array(areas)
    print(f"  삼각형 면적 - 최소: {areas.min():.4f}, 최대: {areas.max():.2f}, 평균: {areas.mean():.2f} mm²")

    # 엣지 길이 분포
    edge_lengths = []
    for face in mesh.faces:
        v0, v1, v2 = mesh.vertices[face]
        edge_lengths.append(np.linalg.norm(v1 - v0))
        edge_lengths.append(np.linalg.norm(v2 - v1))
        edge_lengths.append(np.linalg.norm(v0 - v2))

    edge_lengths = np.array(edge_lengths)
    print(f"  엣지 길이 - 최소: {edge_lengths.min():.4f}, 최대: {edge_lengths.max():.2f}, 평균: {edge_lengths.mean():.2f} mm")

    # 법선 일관성
    normals = mesh.normals
    if len(normals) > 0:
        norm_lengths = np.linalg.norm(normals, axis=1)
        print(f"  법선 벡터 - 평균 길이: {norm_lengths.mean():.4f} (1.0이 정상)")


def main():
    """메인 테스트."""
    stl_dir = Path("stl")

    print("=" * 60)
    print("STL 모델 솔버 테스트")
    print("=" * 60)

    # 모델 로드 및 분석
    for filename in ["L4.stl", "L5.stl", "disc.stl"]:
        filepath = stl_dir / filename
        if filepath.exists():
            mesh = load_and_center_mesh(str(filepath))
            print(f"\n{filename}:")
            print(f"  정점: {mesh.n_vertices:,}, 삼각형: {mesh.n_faces:,}")
            analyze_mesh_quality(mesh)

    # 간단한 하중 테스트
    test_simple_loading()

    # Peridynamics 테스트 (메모리 주의)
    print("\nPeridynamics 테스트를 실행하시겠습니까? (y/n)")
    response = input().strip().lower()
    if response == 'y':
        test_peridynamics_with_mesh()


if __name__ == "__main__":
    main()
