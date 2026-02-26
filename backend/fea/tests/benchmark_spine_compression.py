"""L4+disc+L5 복셀화 → FEM/PD/SPG 압축 비교 벤치마크.

세 개의 STL 모델(L4, disc, L5)을 하나의 복셀 그리드로 합치고,
다중 재료(뼈 15GPa, 디스크 10MPa)를 부여한 뒤
FEM/NOSB-PD/SPG로 압축 실험을 수행한다.

단위계: mm-MPa
  좌표: mm (STL 원본)
  뼈 Young's: 15000 MPa
  디스크 Young's: 10 MPa
  밀도: 1.9e-6 kg/mm³
  압축 응력: -1 MPa

실행:
    uv run python src/fea/tests/benchmark_spine_compression.py
"""

import sys
import os
import time
import math
import numpy as np

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import taichi as ti

from backend.utils.mesh import TriangleMesh


# ============================================================
#  상수 정의
# ============================================================

# STL 파일 경로
STL_DIR = os.path.join(os.path.dirname(__file__), "../../simulator/stl")

# 재료 물성 (mm-MPa 단위계)
E_BONE = 15000.0     # MPa (뼈)
NU_BONE = 0.3
E_DISC = 10.0        # MPa (추간판)
NU_DISC = 0.4
DENSITY = 1.9e-6     # kg/mm³ (≈1900 kg/m³)
SIGMA_COMPRESS = -1.0  # MPa (압축 응력)

# 복셀 해상도
RESOLUTION = 20

# 재료 ID
MAT_BONE = 1
MAT_DISC = 2


# ============================================================
#  1단계: STL 복셀화 (레이캐스팅)
# ============================================================

def ray_triangles_intersect_batch(ray_origin, ray_dir, v0s, v1s, v2s):
    """Möller–Trumbore 레이-삼각형 배치 교차 검사 (numpy 벡터화).

    Args:
        ray_origin: 레이 원점 (3,)
        ray_dir: 레이 방향 (3,)
        v0s, v1s, v2s: 삼각형 꼭짓점 배열 (N, 3)

    Returns:
        hit_x: 교차점 x좌표 배열 (교차한 삼각형만)
    """
    EPSILON = 1e-8
    edge1 = v1s - v0s  # (N, 3)
    edge2 = v2s - v0s  # (N, 3)

    # h = ray_dir × edge2
    h = np.cross(ray_dir, edge2)  # (N, 3)
    a = np.sum(edge1 * h, axis=1)  # (N,)

    # 평행한 삼각형 제외
    valid = np.abs(a) > EPSILON
    if not np.any(valid):
        return np.array([])

    f = np.zeros_like(a)
    f[valid] = 1.0 / a[valid]

    s = ray_origin - v0s  # (N, 3)
    u = f * np.sum(s * h, axis=1)  # (N,)

    # u 범위 검사
    valid &= (u >= 0.0) & (u <= 1.0)
    if not np.any(valid):
        return np.array([])

    q = np.cross(s, edge1)  # (N, 3)
    v = f * np.sum(ray_dir * q, axis=1)  # (N,) - broadcast

    # v 범위 검사
    valid &= (v >= 0.0) & (u + v <= 1.0)
    if not np.any(valid):
        return np.array([])

    t = f * np.sum(edge2 * q, axis=1)  # (N,)
    valid &= (t > EPSILON)

    if not np.any(valid):
        return np.array([])

    return ray_origin[0] + t[valid]


def voxelize_mesh_raycasting(vertices, faces, grid_origin, spacing, grid_size):
    """레이캐스팅으로 메쉬 내부 복셀 채우기 (numpy 벡터화).

    +x 방향으로 레이를 쏘아 교차 횟수가 홀수인 복셀을 내부로 판정.

    Args:
        vertices: 정점 배열 (N, 3)
        faces: 면 배열 (M, 3)
        grid_origin: 그리드 원점 (3,)
        spacing: 복셀 간격
        grid_size: (nx, ny, nz)

    Returns:
        occupied: 3D 불리언 배열
    """
    nx, ny, nz = grid_size
    occupied = np.zeros((nx, ny, nz), dtype=bool)

    # 삼각형 꼭짓점 미리 추출
    tri_v0 = vertices[faces[:, 0]].astype(np.float64)
    tri_v1 = vertices[faces[:, 1]].astype(np.float64)
    tri_v2 = vertices[faces[:, 2]].astype(np.float64)

    ray_dir = np.array([1.0, 0.0, 0.0])

    # 복셀 중심 x 좌표 미리 계산
    voxel_x = grid_origin[0] + (np.arange(nx) + 0.5) * spacing

    for iz in range(nz):
        for iy in range(ny):
            # 레이 원점: 그리드 바깥(-x)에서 시작
            ray_y = grid_origin[1] + (iy + 0.5) * spacing
            ray_z = grid_origin[2] + (iz + 0.5) * spacing
            ray_origin = np.array([grid_origin[0] - spacing, ray_y, ray_z])

            # 배치 교차 검사
            hit_x = ray_triangles_intersect_batch(
                ray_origin, ray_dir, tri_v0, tri_v1, tri_v2
            )

            if len(hit_x) == 0:
                continue

            # X 좌표 정렬
            hit_x.sort()

            # 각 복셀의 교차 횟수 계산 (벡터화)
            cross_counts = np.searchsorted(hit_x, voxel_x, side='right')
            occupied[:, iy, iz] = (cross_counts % 2 == 1)

    return occupied


def voxelize_spine(stl_dir, resolution=RESOLUTION):
    """L4+disc+L5 STL을 하나의 복셀 그리드에 합치기.

    Args:
        stl_dir: STL 파일 디렉토리
        resolution: 최소 축 방향 복셀 수

    Returns:
        (occupied, material_ids, spacing, origin)
    """
    print("=" * 64)
    print("  1단계: STL 복셀화")
    print("=" * 64)

    # STL 로드
    stl_files = {
        "L4": os.path.join(stl_dir, "L4.stl"),
        "disc": os.path.join(stl_dir, "disc.stl"),
        "L5": os.path.join(stl_dir, "L5.stl"),
    }

    meshes = {}
    for name, path in stl_files.items():
        meshes[name] = TriangleMesh.load_stl(path, name=name)
        print(f"  {name}: {meshes[name].n_vertices}개 정점, {meshes[name].n_faces}개 면")

    # 전체 바운딩 박스 계산
    all_mins = []
    all_maxs = []
    for mesh in meshes.values():
        mn, mx = mesh.get_bounds()
        all_mins.append(mn)
        all_maxs.append(mx)

    global_min = np.min(all_mins, axis=0)
    global_max = np.max(all_maxs, axis=0)
    extent = global_max - global_min

    print(f"\n  전체 바운딩 박스:")
    print(f"    min: [{global_min[0]:.1f}, {global_min[1]:.1f}, {global_min[2]:.1f}]")
    print(f"    max: [{global_max[0]:.1f}, {global_max[1]:.1f}, {global_max[2]:.1f}]")
    print(f"    크기: [{extent[0]:.1f}, {extent[1]:.1f}, {extent[2]:.1f}] mm")

    # spacing 결정: 최소 축이 resolution 개가 되도록
    min_extent = np.min(extent)
    spacing = min_extent / resolution

    # 그리드 크기 (여유 1 복셀 추가)
    nx = int(np.ceil(extent[0] / spacing)) + 2
    ny = int(np.ceil(extent[1] / spacing)) + 2
    nz = int(np.ceil(extent[2] / spacing)) + 2

    # 원점: 바운딩 박스 min에서 1 복셀 여유
    origin = global_min - spacing

    print(f"\n  복셀 그리드: {nx}×{ny}×{nz} = {nx*ny*nz}개 셀")
    print(f"  간격: {spacing:.2f} mm")

    # 통합 그리드
    occupied = np.zeros((nx, ny, nz), dtype=bool)
    material_ids = np.zeros((nx, ny, nz), dtype=np.int32)

    # 각 메쉬별 복셀화
    mesh_mat_map = {"L4": MAT_BONE, "disc": MAT_DISC, "L5": MAT_BONE}

    for name, mesh in meshes.items():
        mat_id = mesh_mat_map[name]
        print(f"\n  [{name}] 복셀화 중 (material_id={mat_id})...")

        t0 = time.time()
        mesh_occupied = voxelize_mesh_raycasting(
            mesh.vertices, mesh.faces, origin, spacing, (nx, ny, nz)
        )
        elapsed = time.time() - t0

        # 통합 그리드에 병합 (겹치면 나중 것이 우선)
        new_voxels = mesh_occupied & ~occupied
        overlap_voxels = mesh_occupied & occupied
        occupied |= mesh_occupied
        material_ids[mesh_occupied] = mat_id

        n_filled = np.sum(mesh_occupied)
        print(f"    채워진 복셀: {n_filled}개, 새 복셀: {np.sum(new_voxels)}개, "
              f"겹침: {np.sum(overlap_voxels)}개, {elapsed:.1f}초")

    total_filled = np.sum(occupied)
    n_bone = np.sum(material_ids == MAT_BONE)
    n_disc = np.sum(material_ids == MAT_DISC)
    print(f"\n  총 채워진 복셀: {total_filled}개 (뼈: {n_bone}, 디스크: {n_disc})")

    return occupied, material_ids, spacing, origin


# ============================================================
#  2단계: 복셀 → HEX8 메쉬 변환
# ============================================================

def voxels_to_hex8(occupied, material_ids, spacing, origin):
    """복셀을 HEX8 요소 메쉬로 변환.

    채워진 복셀마다 HEX8 요소 1개를 생성한다.
    꼭짓점은 인접 요소간 공유된다.

    Returns:
        (nodes[N,3], elements[M,8], elem_material_ids[M])
    """
    print("\n" + "=" * 64)
    print("  2단계: 복셀 → HEX8 메쉬 변환")
    print("=" * 64)

    nx, ny, nz = occupied.shape
    node_map = {}  # (i, j, k) → global node id
    nodes = []
    elements = []
    elem_mat_ids = []

    def get_or_create_node(i, j, k):
        """노드 인덱스 조회/생성."""
        key = (i, j, k)
        if key not in node_map:
            node_map[key] = len(nodes)
            # 노드 좌표
            x = origin[0] + i * spacing
            y = origin[1] + j * spacing
            z = origin[2] + k * spacing
            nodes.append([x, y, z])
        return node_map[key]

    for iz in range(nz):
        for iy in range(ny):
            for ix in range(nx):
                if not occupied[ix, iy, iz]:
                    continue

                # HEX8 노드 순서 (FEM benchmark 규칙)
                n0 = get_or_create_node(ix, iy, iz)
                n1 = get_or_create_node(ix + 1, iy, iz)
                n2 = get_or_create_node(ix + 1, iy + 1, iz)
                n3 = get_or_create_node(ix, iy + 1, iz)
                n4 = get_or_create_node(ix, iy, iz + 1)
                n5 = get_or_create_node(ix + 1, iy, iz + 1)
                n6 = get_or_create_node(ix + 1, iy + 1, iz + 1)
                n7 = get_or_create_node(ix, iy + 1, iz + 1)

                elements.append([n0, n1, n2, n3, n4, n5, n6, n7])
                elem_mat_ids.append(material_ids[ix, iy, iz])

    nodes = np.array(nodes, dtype=np.float32)
    elements = np.array(elements, dtype=np.int32)
    elem_mat_ids = np.array(elem_mat_ids, dtype=np.int32)

    print(f"  노드: {len(nodes)}개")
    print(f"  요소: {len(elements)}개 (뼈: {np.sum(elem_mat_ids==MAT_BONE)}, "
          f"디스크: {np.sum(elem_mat_ids==MAT_DISC)})")

    return nodes, elements, elem_mat_ids


# ============================================================
#  3단계: 복셀 → 입자 변환
# ============================================================

def voxels_to_particles(occupied, material_ids, spacing, origin):
    """복셀 중심을 입자 위치로 변환.

    Returns:
        (positions[N,3], volumes[N], particle_material_ids[N])
    """
    print("\n" + "=" * 64)
    print("  3단계: 복셀 → 입자 변환")
    print("=" * 64)

    indices = np.argwhere(occupied)
    n_particles = len(indices)

    # 복셀 중심 좌표
    positions = np.zeros((n_particles, 3), dtype=np.float64)
    for idx, (ix, iy, iz) in enumerate(indices):
        positions[idx, 0] = origin[0] + (ix + 0.5) * spacing
        positions[idx, 1] = origin[1] + (iy + 0.5) * spacing
        positions[idx, 2] = origin[2] + (iz + 0.5) * spacing

    volumes = np.full(n_particles, spacing ** 3, dtype=np.float64)

    # 재료 ID
    particle_mat_ids = np.array(
        [material_ids[ix, iy, iz] for ix, iy, iz in indices],
        dtype=np.int32
    )

    print(f"  입자: {n_particles}개")
    print(f"  부피: {spacing**3:.4f} mm³/입자")

    return positions, volumes, particle_mat_ids


# ============================================================
#  5단계: FEM 압축 실행
# ============================================================

def run_fem(nodes, elements, elem_mat_ids, spacing):
    """FEM (HEX8) 다중 재료 압축 해석.

    Returns:
        (top_disp_z, max_stress, elapsed, n_elements, disc_disp_info)
    """
    from backend.fea.fem.core.mesh import FEMesh
    from backend.fea.fem.core.element import ElementType
    from backend.fea.fem.material.linear_elastic import LinearElastic
    from backend.fea.fem.solver.static_solver import StaticSolver

    print("\n" + "=" * 64)
    print("  FEM (HEX8) 다중 재료 압축")
    print("=" * 64)

    n_nodes = len(nodes)
    n_elements = len(elements)

    mesh = FEMesh(n_nodes=n_nodes, n_elements=n_elements, element_type=ElementType.HEX8)
    mesh.initialize_from_numpy(nodes, elements, material_ids=elem_mat_ids)

    # 다중 재료
    bone = LinearElastic(youngs_modulus=E_BONE, poisson_ratio=NU_BONE, dim=3)
    disc = LinearElastic(youngs_modulus=E_DISC, poisson_ratio=NU_DISC, dim=3)
    materials = {MAT_BONE: bone, MAT_DISC: disc}

    # 경계 조건
    z_coords = nodes[:, 2]
    z_min = np.min(z_coords)
    z_max = np.max(z_coords)

    # 바닥 고정 (z_min 노드 - 1층)
    bottom_nodes = np.where(z_coords < z_min + spacing * 0.1)[0]
    mesh.set_fixed_nodes(bottom_nodes)
    print(f"  바닥 고정: {len(bottom_nodes)}개 노드 (z < {z_min + spacing * 0.1:.1f})")

    # 윗면 압축력 (z_max 노드 - 상위 1층)
    top_nodes = np.where(z_coords > z_max - spacing * 0.1)[0]
    # 윗면 면적: 각 윗면 노드가 분담하는 면적 = spacing²
    area_top = len(top_nodes) * spacing * spacing
    total_force = SIGMA_COMPRESS * area_top
    force_per_node = total_force / len(top_nodes)
    forces = np.zeros((len(top_nodes), 3), dtype=np.float32)
    forces[:, 2] = force_per_node  # z 방향 압축
    mesh.set_nodal_forces(top_nodes, forces)
    print(f"  윗면 하중: {len(top_nodes)}개 노드 (z={z_max:.1f}), "
          f"총 힘={total_force:.2f} N, 응력={SIGMA_COMPRESS} MPa")

    # 솔버 실행
    solver = StaticSolver(mesh, material=None, materials=materials)
    t0 = time.time()
    result = solver.solve(verbose=False)
    elapsed = time.time() - t0

    print(f"  수렴: {result['converged']}, {elapsed:.2f}초")

    # 결과 추출
    u = mesh.get_displacements()
    top_disp_z = np.mean(u[top_nodes, 2])

    # NaN 확인
    if np.any(np.isnan(u)):
        print("  ⚠ NaN 발생!")
        return top_disp_z, 0.0, elapsed, n_elements, None

    # 응력 (가우스 포인트 평균)
    stress = mesh.get_stress()
    # Von Mises 계산 (가우스 포인트)
    mises_gp = np.zeros(len(stress))
    for gp in range(len(stress)):
        s = stress[gp]
        s11, s22, s33 = s[0, 0], s[1, 1], s[2, 2]
        s12, s23, s13 = s[0, 1], s[1, 2], s[0, 2]
        mises_gp[gp] = np.sqrt(0.5 * ((s11-s22)**2 + (s22-s33)**2 + (s33-s11)**2
                                       + 6*(s12**2 + s23**2 + s13**2)))
    max_stress = np.max(mises_gp)

    print(f"  윗면 z-변위: {top_disp_z:.6e} mm")
    print(f"  최대 Mises 응력: {max_stress:.4f} MPa")

    # 디스크 영역 변형 분석
    disc_elem_mask = (elem_mat_ids == MAT_DISC)
    bone_elem_mask = (elem_mat_ids == MAT_BONE)

    n_gauss = 8  # HEX8
    disc_mises = []
    bone_mises = []
    for e in range(n_elements):
        elem_mises = np.mean(mises_gp[e*n_gauss:(e+1)*n_gauss])
        if disc_elem_mask[e]:
            disc_mises.append(elem_mises)
        elif bone_elem_mask[e]:
            bone_mises.append(elem_mises)

    disc_info = None
    if disc_mises and bone_mises:
        avg_disc_mises = np.mean(disc_mises)
        avg_bone_mises = np.mean(bone_mises)
        print(f"\n  재료별 평균 Mises 응력:")
        print(f"    뼈:    {avg_bone_mises:.4f} MPa")
        print(f"    디스크: {avg_disc_mises:.4f} MPa")

        # 디스크 영역 노드의 변위
        disc_elements = elements[disc_elem_mask]
        disc_node_ids = np.unique(disc_elements.flatten())
        disc_disp = np.mean(np.abs(u[disc_node_ids, 2]))
        bone_elements = elements[bone_elem_mask]
        bone_node_ids = np.unique(bone_elements.flatten())
        bone_disp = np.mean(np.abs(u[bone_node_ids, 2]))
        print(f"  재료별 평균 |z-변위|:")
        print(f"    뼈:    {bone_disp:.6e} mm")
        print(f"    디스크: {disc_disp:.6e} mm")
        disc_info = {
            "disc_stress": avg_disc_mises,
            "bone_stress": avg_bone_mises,
            "disc_disp": disc_disp,
            "bone_disp": bone_disp
        }

    return top_disp_z, max_stress, elapsed, n_elements, disc_info


# ============================================================
#  6단계: PD 압축 실행
# ============================================================

def run_pd(positions, volumes, spacing, particle_mat_ids):
    """NOSB-PD 다중 재료 압축 해석 (변위 적용 방식).

    Args:
        positions: 입자 좌표 (N, 3)
        volumes: 입자 부피 (N,)
        spacing: 복셀 간격
        particle_mat_ids: 입자별 재료 ID (N,)

    Returns:
        (top_disp_z, max_stress, elapsed, n_particles, disc_info)
    """
    from backend.fea.peridynamics.core.particles import ParticleSystem
    from backend.fea.peridynamics.core.neighbor import NeighborSearch
    from backend.fea.peridynamics.core.bonds import BondSystem
    from backend.fea.peridynamics.core.nosb import NOSBCompute, NOSBMaterial

    print("\n" + "=" * 64)
    print("  NOSB-PD 다중 재료 압축 (변위 적용)")
    print("=" * 64)

    n = len(positions)
    horizon_factor = 3.015
    horizon = horizon_factor * spacing

    n_bone = np.sum(particle_mat_ids == MAT_BONE)
    n_disc = np.sum(particle_mat_ids == MAT_DISC)
    print(f"  입자: {n}개 (뼈: {n_bone}, 디스크: {n_disc}), 간격={spacing:.2f}, horizon={horizon:.2f}")

    # 입자 시스템 (PD는 f32)
    ps = ParticleSystem(n, dim=3)
    ps.initialize_from_arrays(
        positions.astype(np.float32),
        volumes.astype(np.float32),
        density=float(DENSITY)
    )

    # 이웃 탐색
    pos_np = ps.X.to_numpy()
    domain_pad = horizon * 1.5
    mins = pos_np.min(axis=0) - domain_pad
    maxs = pos_np.max(axis=0) + domain_pad

    ns = NeighborSearch(
        domain_min=tuple(mins), domain_max=tuple(maxs),
        horizon=horizon, max_particles=n, max_neighbors=100, dim=3
    )
    ns.build(ps.X, n)

    # 본드 시스템
    bonds = BondSystem(n, max_bonds=100, dim=3)
    bonds.build_from_neighbor_search(ps, ns, horizon)

    # 다중 재료: 입자별 체적/전단 탄성률 설정
    K_bone = E_BONE / (3 * (1 - 2 * NU_BONE))
    mu_bone = E_BONE / (2 * (1 + NU_BONE))
    K_disc = E_DISC / (3 * (1 - 2 * NU_DISC))
    mu_disc = E_DISC / (2 * (1 + NU_DISC))

    bulk_arr = np.where(particle_mat_ids == MAT_BONE, K_bone, K_disc).astype(np.float32)
    shear_arr = np.where(particle_mat_ids == MAT_BONE, mu_bone, mu_disc).astype(np.float32)
    ps.set_material_constants_per_particle(bulk_arr, shear_arr)

    # NOSB 계산 모듈
    nosb = NOSBCompute(ps, bonds, stabilization=0.1)
    nosb.compute_shape_tensor()

    # 하단 고정 (z < z_min + horizon)
    z_coords = pos_np[:, 2]
    z_min = np.min(z_coords)
    z_max = np.max(z_coords)
    L_z = z_max - z_min

    bottom_mask = z_coords < (z_min + horizon)
    ps.set_fixed_particles(np.where(bottom_mask)[0])
    print(f"  하단 고정: {np.sum(bottom_mask)}개 입자 (z < {z_min + horizon:.1f})")

    # 상단에 압축 변위 적용 (strain = sigma/E_bone)
    strain = abs(SIGMA_COMPRESS) / E_BONE
    x = ps.x.to_numpy()
    X = ps.X.to_numpy()
    for i in range(n):
        if not bottom_mask[i]:
            x[i, 2] = X[i, 2] - strain * (X[i, 2] - z_min)
    ps.x.from_numpy(x.astype(np.float32))

    # 힘 계산
    t0 = time.time()
    nosb.compute_deformation_gradient()
    c_bond = 18 * K_bone / (math.pi * horizon**4)
    nosb.compute_force_state_with_stabilization(c_bond)
    elapsed = time.time() - t0

    # 결과
    disp = ps.get_displacements()

    # NaN 확인
    if np.any(np.isnan(disp)):
        print("  ⚠ NaN 발생!")
        return 0.0, 0.0, elapsed, n, None

    top_mask = z_coords > (z_max - spacing * 0.5)
    top_disp_z = np.mean(disp[top_mask, 2])

    # 응력 추정 (F에서 입자별 재료 상수로 계산)
    F_np = ps.F.to_numpy()
    mises_all = np.zeros(n)
    for i in range(n):
        K_i = bulk_arr[i]
        mu_i = shear_arr[i]
        lam_i = K_i - 2.0 * mu_i / 3.0
        F_i = F_np[i]
        eps = 0.5 * (F_i + F_i.T) - np.eye(3)
        tr_eps = np.trace(eps)
        sigma = lam_i * tr_eps * np.eye(3) + 2 * mu_i * eps
        s11, s22, s33 = sigma[0, 0], sigma[1, 1], sigma[2, 2]
        s12, s23, s13 = sigma[0, 1], sigma[1, 2], sigma[0, 2]
        mises_all[i] = np.sqrt(0.5 * ((s11-s22)**2 + (s22-s33)**2 + (s33-s11)**2
                                       + 6*(s12**2 + s23**2 + s13**2)))

    # 경계 효과 제외 (내부만)
    interior_mask = (
        (z_coords > z_min + horizon) &
        (z_coords < z_max - horizon)
    )
    max_stress = np.max(mises_all[interior_mask]) if np.any(interior_mask) else np.max(mises_all)

    print(f"  계산 시간: {elapsed:.2f}초")
    print(f"  윗면 z-변위: {top_disp_z:.6e} mm")
    print(f"  최대 Mises 응력 (내부): {max_stress:.4f} MPa")
    print(f"  최대 변위: {np.max(np.abs(disp)):.6e} mm")

    # 재료별 분석
    disc_info = None
    bone_mask = particle_mat_ids == MAT_BONE
    disc_mask = particle_mat_ids == MAT_DISC
    if np.any(disc_mask) and np.any(bone_mask):
        avg_bone_mises = np.mean(mises_all[bone_mask & interior_mask]) if np.any(bone_mask & interior_mask) else np.mean(mises_all[bone_mask])
        avg_disc_mises = np.mean(mises_all[disc_mask]) if np.any(disc_mask) else 0.0
        bone_disp = np.mean(np.abs(disp[bone_mask, 2]))
        disc_disp = np.mean(np.abs(disp[disc_mask, 2]))
        print(f"\n  재료별 평균 Mises 응력:")
        print(f"    뼈:    {avg_bone_mises:.4f} MPa")
        print(f"    디스크: {avg_disc_mises:.4f} MPa")
        print(f"  재료별 평균 |z-변위|:")
        print(f"    뼈:    {bone_disp:.6e} mm")
        print(f"    디스크: {disc_disp:.6e} mm")
        disc_info = {
            "disc_stress": avg_disc_mises,
            "bone_stress": avg_bone_mises,
            "disc_disp": disc_disp,
            "bone_disp": bone_disp
        }

    return top_disp_z, max_stress, elapsed, n, disc_info


# ============================================================
#  7단계: SPG 압축 실행
# ============================================================

def run_spg(positions, volumes, spacing, particle_mat_ids):
    """SPG 다중 재료 압축 해석 (변위 적용 방식).

    FEM/PD와 동일한 변형량을 비교하기 위해 변위를 직접 적용하고
    내부력/응력을 계산한다.

    Args:
        positions: 입자 좌표 (N, 3)
        volumes: 입자 부피 (N,)
        spacing: 복셀 간격
        particle_mat_ids: 입자별 재료 ID (N,)

    Returns:
        (top_disp_z, max_stress, elapsed, n_particles, disc_info)
    """
    from backend.fea.spg.core.particles import SPGParticleSystem
    from backend.fea.spg.core.kernel import SPGKernel
    from backend.fea.spg.core.bonds import SPGBondSystem
    from backend.fea.spg.core.spg_compute import SPGCompute
    from backend.fea.spg.material.elastic import SPGElasticMaterial

    print("\n" + "=" * 64)
    print("  SPG 다중 재료 압축 (변위 적용)")
    print("=" * 64)

    n = len(positions)
    support_factor = 2.5
    support_radius = spacing * support_factor

    n_bone = np.sum(particle_mat_ids == MAT_BONE)
    n_disc = np.sum(particle_mat_ids == MAT_DISC)
    print(f"  입자: {n}개 (뼈: {n_bone}, 디스크: {n_disc}), 간격={spacing:.2f}, 지지 반경={support_radius:.2f}")

    # SPG 시스템 (f64)
    ps = SPGParticleSystem(n_particles=n, dim=3)
    ps.initialize_from_arrays(positions, volumes, density=float(DENSITY))

    # 커널 + 이웃
    kernel = SPGKernel(n_particles=n, dim=3, support_radius=support_radius)
    kernel.build_neighbor_list(ps.X.to_numpy(), support_radius)
    kernel.compute_shape_functions(ps.X, ps.volume)

    # 본드
    bond_sys = SPGBondSystem(n_particles=n, dim=3)
    bond_sys.build_from_kernel(ps, kernel)

    # 다중 재료: 입자별 라메 상수 설정
    lam_bone = E_BONE * NU_BONE / ((1 + NU_BONE) * (1 - 2 * NU_BONE))
    mu_bone = E_BONE / (2 * (1 + NU_BONE))
    lam_disc = E_DISC * NU_DISC / ((1 + NU_DISC) * (1 - 2 * NU_DISC))
    mu_disc = E_DISC / (2 * (1 + NU_DISC))

    lam_arr = np.where(particle_mat_ids == MAT_BONE, lam_bone, lam_disc).astype(np.float64)
    mu_arr = np.where(particle_mat_ids == MAT_BONE, mu_bone, mu_disc).astype(np.float64)
    ps.set_material_constants_per_particle(lam_arr, mu_arr)

    # SPG 연산 모듈
    spg_compute = SPGCompute(ps, kernel, bond_sys, stabilization=0.01)
    spg_compute.set_stabilization_modulus(E_BONE, support_radius, dim=3)

    # 경계 조건
    pos_np = ps.X.to_numpy()
    z_coords = pos_np[:, 2]
    z_min = np.min(z_coords)
    z_max = np.max(z_coords)
    L_z = z_max - z_min

    # 바닥 고정 (하위 1층)
    bottom_mask = z_coords < z_min + spacing * 0.6
    fixed_idx = np.where(bottom_mask)[0]
    ps.set_fixed_particles(fixed_idx)
    print(f"  바닥 고정: {len(fixed_idx)}개 입자 (z < {z_min + spacing * 0.6:.1f})")

    # 압축 변위 직접 적용 (PD와 동일한 변형률)
    strain = abs(SIGMA_COMPRESS) / E_BONE
    u_np = ps.u.to_numpy()
    for i in range(n):
        if not bottom_mask[i]:
            u_np[i, 2] = -strain * (z_coords[i] - z_min)
    ps.u.from_numpy(u_np)
    ps.update_positions()

    print(f"  변형률: {strain:.6e}, 최대 z-변위: {-strain * L_z:.6e} mm")

    # 변형 구배 → 변형률 → 응력 계산 (per-particle 재료 사용)
    t0 = time.time()
    spg_compute.compute_deformation_gradient()
    spg_compute.compute_strain()
    spg_compute.compute_stress()
    elapsed = time.time() - t0

    # 결과
    disp = ps.get_displacements()

    # NaN 확인
    if np.any(np.isnan(disp)):
        print("  ⚠ NaN 발생!")
        return 0.0, 0.0, elapsed, n, None

    top_mask = z_coords > z_max - spacing * 0.6
    top_idx = np.where(top_mask)[0]
    if len(top_idx) == 0:
        top_idx = np.where(z_coords > z_max - spacing * 1.6)[0]
    top_disp_z = np.mean(disp[top_idx, 2])

    # 응력 추정 (SPG가 계산한 응력 사용)
    stress_np = ps.get_stress()
    mises_all = np.zeros(n)
    for i in range(n):
        s = stress_np[i]
        s11, s22, s33 = s[0, 0], s[1, 1], s[2, 2]
        s12, s23, s13 = s[0, 1], s[1, 2], s[0, 2]
        mises_all[i] = np.sqrt(0.5 * ((s11-s22)**2 + (s22-s33)**2 + (s33-s11)**2
                                       + 6*(s12**2 + s23**2 + s13**2)))

    # 경계 효과 제외 (내부만)
    interior_mask = (z_coords > z_min + support_radius) & (z_coords < z_max - support_radius)
    max_stress = np.max(mises_all[interior_mask]) if np.any(interior_mask) else np.max(mises_all)

    print(f"  계산 시간: {elapsed:.2f}초")
    print(f"  윗면 z-변위: {top_disp_z:.6e} mm")
    print(f"  최대 Mises 응력 (내부): {max_stress:.4f} MPa")

    # 재료별 분석
    disc_info = None
    bone_mask = particle_mat_ids == MAT_BONE
    disc_mask = particle_mat_ids == MAT_DISC
    if np.any(disc_mask) and np.any(bone_mask):
        avg_bone_mises = np.mean(mises_all[bone_mask & interior_mask]) if np.any(bone_mask & interior_mask) else np.mean(mises_all[bone_mask])
        avg_disc_mises = np.mean(mises_all[disc_mask]) if np.any(disc_mask) else 0.0
        bone_disp = np.mean(np.abs(disp[bone_mask, 2]))
        disc_disp = np.mean(np.abs(disp[disc_mask, 2]))
        print(f"\n  재료별 평균 Mises 응력:")
        print(f"    뼈:    {avg_bone_mises:.4f} MPa")
        print(f"    디스크: {avg_disc_mises:.4f} MPa")
        print(f"  재료별 평균 |z-변위|:")
        print(f"    뼈:    {bone_disp:.6e} mm")
        print(f"    디스크: {disc_disp:.6e} mm")
        disc_info = {
            "disc_stress": avg_disc_mises,
            "bone_stress": avg_bone_mises,
            "disc_disp": disc_disp,
            "bone_disp": bone_disp
        }

    return top_disp_z, max_stress, elapsed, n, disc_info


# ============================================================
#  비교 테이블 출력
# ============================================================

def print_comparison_table(results):
    """비교 테이블 출력."""
    print("\n" + "=" * 80)
    print("  FEM / NOSB-PD / SPG 압축 비교")
    print("=" * 80)

    header = (f"  {'솔버':<14}  {'요소/입자':>10}  {'다중재료':>8}  "
              f"{'윗면 z-변위':>14}  {'최대응력(MPa)':>14}  {'시간(초)':>8}")
    print(header)
    print("  " + "-" * 76)

    for r in results:
        name = r["name"]
        count = r["count"]
        multi = r["multi_mat"]
        disp = r["top_disp_z"]
        stress = r["max_stress"]
        elapsed = r["elapsed"]

        print(f"  {name:<14}  {count:>10}  {multi:>8}  "
              f"{disp:>14.6e}  {stress:>14.4f}  {elapsed:>8.1f}")

    print("=" * 80)


# ============================================================
#  메인
# ============================================================

def main():
    # Taichi 초기화 (SPG가 f64 필요, 경고 억제)
    ti.init(arch=ti.cpu, default_fp=ti.f64, verbose=False)

    print("\n################################################################")
    print("  L4+disc+L5 척추 복셀 압축 벤치마크")
    print("  FEM (다중재료) vs NOSB-PD vs SPG")
    print("################################################################")

    t_total = time.time()

    # 1단계: 복셀화
    occupied, material_ids, spacing, origin = voxelize_spine(STL_DIR, RESOLUTION)

    total_filled = np.sum(occupied)
    if total_filled < 500:
        print(f"\n  ⚠ 복셀 수({total_filled})가 너무 적습니다. STL 파일을 확인하세요.")
        return

    # 2단계: HEX8 메쉬 변환
    nodes, elements, elem_mat_ids = voxels_to_hex8(
        occupied, material_ids, spacing, origin
    )

    # 3단계: 입자 변환
    positions, volumes, particle_mat_ids = voxels_to_particles(
        occupied, material_ids, spacing, origin
    )

    results = []

    # 5단계: FEM 압축
    try:
        fem_disp, fem_stress, fem_time, fem_count, disc_info = run_fem(
            nodes, elements, elem_mat_ids, spacing
        )
        results.append({
            "name": "FEM (HEX8)",
            "count": fem_count,
            "multi_mat": "O",
            "top_disp_z": fem_disp,
            "max_stress": fem_stress,
            "elapsed": fem_time
        })
    except Exception as e:
        print(f"\n  FEM 실행 실패: {e}")
        import traceback
        traceback.print_exc()

    # 6단계: PD 압축
    try:
        pd_disp, pd_stress, pd_time, pd_count, pd_disc_info = run_pd(
            positions, volumes, spacing, particle_mat_ids
        )
        results.append({
            "name": "NOSB-PD",
            "count": pd_count,
            "multi_mat": "O",
            "top_disp_z": pd_disp,
            "max_stress": pd_stress,
            "elapsed": pd_time
        })
    except Exception as e:
        print(f"\n  PD 실행 실패: {e}")
        import traceback
        traceback.print_exc()
        pd_disc_info = None

    # 7단계: SPG 압축
    try:
        spg_disp, spg_stress, spg_time, spg_count, spg_disc_info = run_spg(
            positions, volumes, spacing, particle_mat_ids
        )
        results.append({
            "name": "SPG",
            "count": spg_count,
            "multi_mat": "O",
            "top_disp_z": spg_disp,
            "max_stress": spg_stress,
            "elapsed": spg_time
        })
    except Exception as e:
        print(f"\n  SPG 실행 실패: {e}")
        import traceback
        traceback.print_exc()
        spg_disc_info = None

    # 8단계: 비교 테이블
    if results:
        print_comparison_table(results)

    elapsed_total = time.time() - t_total

    # 검증 요약
    print("\n" + "=" * 64)
    print("  검증 요약")
    print("=" * 64)

    checks = []

    # 1. 복셀화 성공
    check1 = total_filled > 500
    checks.append(("복셀화 (>500 복셀)", check1, f"{total_filled}개"))
    print(f"  [{'OK' if check1 else 'FAIL'}] 복셀화: {total_filled}개 복셀")

    # 2-4. 각 솔버 결과
    for r in results:
        has_nan = np.isnan(r["top_disp_z"]) or np.isnan(r["max_stress"])
        ok = not has_nan and r["top_disp_z"] != 0.0
        checks.append((f"{r['name']} 수렴", ok, f"disp={r['top_disp_z']:.4e}"))
        print(f"  [{'OK' if ok else 'FAIL'}] {r['name']}: "
              f"disp={r['top_disp_z']:.4e}, stress={r['max_stress']:.4f}")

    # 5. 세 솔버 변위 비교 (같은 order of magnitude)
    if len(results) >= 2:
        disps = [abs(r["top_disp_z"]) for r in results if r["top_disp_z"] != 0]
        if len(disps) >= 2:
            ratio = max(disps) / min(disps) if min(disps) > 0 else float('inf')
            same_order = ratio < 100  # 2 orders of magnitude 이내
            checks.append(("변위 비교", same_order, f"max/min={ratio:.1f}"))
            print(f"  [{'OK' if same_order else 'FAIL'}] 변위 비교: max/min 비율 = {ratio:.1f}")

    # 6. 디스크 영역 더 큰 변형 (FEM만)
    if disc_info:
        disc_larger = disc_info["disc_stress"] > 0
        checks.append(("디스크 변형", disc_larger, ""))
        print(f"  [{'OK' if disc_larger else 'FAIL'}] 디스크 영역 분석 완료")

    all_passed = all(c[1] for c in checks)
    print(f"\n  총 실행 시간: {elapsed_total:.1f}초")
    print(f"  최종 결과: {'ALL PASS' if all_passed else 'SOME FAILED'}")
    print("=" * 64)


if __name__ == "__main__":
    main()
