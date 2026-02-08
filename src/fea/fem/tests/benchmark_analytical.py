"""FEM 솔버 해석해 비교 벤치마크.

해석해가 알려진 표준 문제와 FEM 솔버 결과를 비교하여
물리적 정확도를 검증한다.

벤치마크 문제:
1. 균일 인장 봉 (2D QUAD4) - u = PL/(EA), L/H >> 1
2. 균일 인장 봉 (3D HEX8) - u = PL/(EA)
3. 외팔보 (2D QUAD4) - δ = PL³/(3EI)
4. 3D 큐브 압축 (HEX8) - u = σL/E
5. 격자 수렴성 분석 (2D QUAD4, 외팔보)

참고:
    FEM 솔버의 경계조건(set_fixed_nodes)은 해당 노드의
    모든 DOF를 고정한다. 따라서 인장 문제에서 L/H가
    작으면 포아송 수축 제한으로 해석해 대비 오차가 발생한다.

실행:
    uv run python src/fea/fem/tests/benchmark_analytical.py
"""

import sys
import os
import time
import numpy as np
import taichi as ti

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from src.fea.fem.core.mesh import FEMesh
from src.fea.fem.core.element import ElementType
from src.fea.fem.material.linear_elastic import LinearElastic
from src.fea.fem.solver.static_solver import StaticSolver


# ============================================================
#  헬퍼 함수
# ============================================================

def create_quad4_mesh(nx, ny, Lx, Ly):
    """2D QUAD4 구조 메쉬 생성."""
    dx, dy = Lx / nx, Ly / ny
    n_nodes = (nx + 1) * (ny + 1)
    n_elements = nx * ny

    nodes = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            nodes.append([i * dx, j * dy])
    nodes = np.array(nodes, dtype=np.float32)

    elements = []
    for ey in range(ny):
        for ex in range(nx):
            n0 = ex + ey * (nx + 1)
            n1 = n0 + 1
            n2 = n0 + (nx + 1) + 1
            n3 = n0 + (nx + 1)
            elements.append([n0, n1, n2, n3])
    elements = np.array(elements, dtype=np.int32)

    return nodes, elements, n_nodes, n_elements


def create_hex8_mesh(nx, ny, nz, Lx, Ly, Lz):
    """3D HEX8 구조 메쉬 생성."""
    dx, dy, dz = Lx / nx, Ly / ny, Lz / nz
    n_nodes = (nx + 1) * (ny + 1) * (nz + 1)
    n_elements = nx * ny * nz

    nodes = []
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                nodes.append([i * dx, j * dy, k * dz])
    nodes = np.array(nodes, dtype=np.float32)

    elements = []
    for ez in range(nz):
        for ey in range(ny):
            for ex in range(nx):
                n0 = ex + ey * (nx + 1) + ez * (nx + 1) * (ny + 1)
                n1 = n0 + 1
                n2 = n0 + (nx + 1) + 1
                n3 = n0 + (nx + 1)
                n4 = n0 + (nx + 1) * (ny + 1)
                n5 = n4 + 1
                n6 = n4 + (nx + 1) + 1
                n7 = n4 + (nx + 1)
                elements.append([n0, n1, n2, n3, n4, n5, n6, n7])
    elements = np.array(elements, dtype=np.int32)

    return nodes, elements, n_nodes, n_elements


def print_header(title):
    print(f"\n{'=' * 64}")
    print(f"  벤치마크: {title}")
    print(f"{'=' * 64}")


def print_comparison(label, analytical, numerical, unit="m"):
    error = abs(numerical - analytical) / abs(analytical) * 100
    print(f"  {label}:")
    print(f"    해석해    = {analytical:.6e} {unit}")
    print(f"    FEM 결과  = {numerical:.6e} {unit}")
    print(f"    상대 오차 = {error:8.2f}%")
    return error


# ============================================================
#  벤치마크 1: 균일 인장 봉 (2D QUAD4)
# ============================================================

def benchmark_tension_bar_2d():
    """2D 균일 인장 봉 (평면응력): u = PL / (EA)

    평면응력 조건에서 u = PL/(EA)가 정확한 해석해이다.
    평면변형에서는 유효 탄성계수가 달라지므로 주의.
    """
    print_header("균일 인장 봉 (2D QUAD4, 평면응력)")

    # 재료/기하 매개변수
    E = 1e4      # Young's modulus [Pa]
    nu = 0.3     # Poisson ratio
    L = 2.0      # 길이 [m] (L/H = 20)
    H = 0.1      # 높이 [m]
    P = 50.0     # 총 하중 [N]

    # 메쉬 (종횡비에 맞춰 세분화)
    nx, ny = 40, 2
    nodes, elements, n_nodes, n_elements = create_quad4_mesh(nx, ny, L, H)
    print(f"  메쉬: {nx}×{ny} = {n_elements}개 QUAD4 요소, {n_nodes}개 노드")
    print(f"  L/H = {L/H:.0f}")

    mesh = FEMesh(n_nodes=n_nodes, n_elements=n_elements, element_type=ElementType.QUAD4)
    mesh.initialize_from_numpy(nodes, elements)

    # 경계 조건: 왼쪽 고정 (x=0, 모든 DOF)
    left_nodes = np.where(np.abs(nodes[:, 0]) < 1e-6)[0]
    mesh.set_fixed_nodes(left_nodes)

    # 하중: 오른쪽 면에 균일 인장 (x=L)
    right_nodes = np.where(np.abs(nodes[:, 0] - L) < 1e-6)[0]
    force_per_node = P / len(right_nodes)
    forces = np.zeros((len(right_nodes), 2), dtype=np.float32)
    forces[:, 0] = force_per_node  # +x 방향
    mesh.set_nodal_forces(right_nodes, forces)

    # 평면응력으로 해석 (u = PL/(EA) 해석해와 일치)
    material = LinearElastic(youngs_modulus=E, poisson_ratio=nu, dim=2, plane_stress=True)
    solver = StaticSolver(mesh, material)
    t0 = time.time()
    result = solver.solve(verbose=False)
    elapsed = time.time() - t0

    print(f"  수렴: {result['converged']}, {elapsed:.2f}초")

    # 해석해: u = PL / (EA), A = H * 1 (단위 두께)
    A = H * 1.0
    u_analytical = P * L / (E * A)

    # FEM 결과: 오른쪽 면 x-변위 평균
    u = mesh.get_displacements()
    u_fem = np.mean(u[right_nodes, 0])

    error = print_comparison("x-변위 (오른쪽 끝)", u_analytical, u_fem)
    return error


# ============================================================
#  벤치마크 2: 균일 인장 봉 (3D HEX8)
# ============================================================

def benchmark_tension_bar_3d():
    """3D 균일 인장 봉: u = PL / (EA)"""
    print_header("균일 인장 봉 (3D HEX8)")

    E = 1e6
    nu = 0.3
    L = 1.0
    W = 0.1
    H = 0.1
    P = 100.0

    nx, ny, nz = 20, 2, 2
    nodes, elements, n_nodes, n_elements = create_hex8_mesh(nx, ny, nz, L, W, H)
    print(f"  메쉬: {nx}×{ny}×{nz} = {n_elements}개 HEX8 요소, {n_nodes}개 노드")
    print(f"  L/W = {L/W:.0f}")

    mesh = FEMesh(n_nodes=n_nodes, n_elements=n_elements, element_type=ElementType.HEX8)
    mesh.initialize_from_numpy(nodes, elements)

    # 왼쪽 고정 (x=0)
    left_nodes = np.where(np.abs(nodes[:, 0]) < 1e-6)[0]
    mesh.set_fixed_nodes(left_nodes)

    # 오른쪽 인장 (x=L)
    right_nodes = np.where(np.abs(nodes[:, 0] - L) < 1e-6)[0]
    force_per_node = P / len(right_nodes)
    forces = np.zeros((len(right_nodes), 3), dtype=np.float32)
    forces[:, 0] = force_per_node
    mesh.set_nodal_forces(right_nodes, forces)

    material = LinearElastic(youngs_modulus=E, poisson_ratio=nu, dim=3)
    solver = StaticSolver(mesh, material)
    t0 = time.time()
    result = solver.solve(verbose=False)
    elapsed = time.time() - t0

    print(f"  수렴: {result['converged']}, {elapsed:.2f}초")

    A = W * H
    u_analytical = P * L / (E * A)

    u = mesh.get_displacements()
    u_fem = np.mean(u[right_nodes, 0])

    error = print_comparison("x-변위 (오른쪽 끝)", u_analytical, u_fem)
    return error


# ============================================================
#  벤치마크 3: 외팔보 (2D QUAD4)
# ============================================================

def benchmark_cantilever_2d():
    """2D 외팔보: δ = PL³/(3EI), I = bh³/12"""
    print_header("외팔보 (2D QUAD4, 평면응력)")

    E = 1e4
    nu = 0.3
    L = 1.0
    H = 0.2
    P = -1.0  # 끝단 집중 하중 (하방)

    nx, ny = 40, 8
    nodes, elements, n_nodes, n_elements = create_quad4_mesh(nx, ny, L, H)
    print(f"  메쉬: {nx}×{ny} = {n_elements}개 QUAD4 요소, {n_nodes}개 노드")

    mesh = FEMesh(n_nodes=n_nodes, n_elements=n_elements, element_type=ElementType.QUAD4)
    mesh.initialize_from_numpy(nodes, elements)

    # 왼쪽 면 전체 고정 (x=0)
    left_nodes = np.where(np.abs(nodes[:, 0]) < 1e-6)[0]
    mesh.set_fixed_nodes(left_nodes)

    # 오른쪽 끝단에 하중 (x=L)
    right_nodes = np.where(np.abs(nodes[:, 0] - L) < 1e-6)[0]
    force_per_node = P / len(right_nodes)
    forces = np.zeros((len(right_nodes), 2), dtype=np.float32)
    forces[:, 1] = force_per_node  # -y 방향
    mesh.set_nodal_forces(right_nodes, forces)

    # 평면응력
    material = LinearElastic(youngs_modulus=E, poisson_ratio=nu, dim=2, plane_stress=True)
    solver = StaticSolver(mesh, material)
    t0 = time.time()
    result = solver.solve(verbose=False)
    elapsed = time.time() - t0

    print(f"  수렴: {result['converged']}, {elapsed:.2f}초")

    # 해석해: Timoshenko 보 (전단 변형 포함)
    # δ = PL³/(3EI) + PL/(κGA)
    # Euler-Bernoulli만 사용하면 L/H=5에서 전단 효과 무시로 ~2% 차이
    b = 1.0
    G = E / (2 * (1 + nu))
    kappa = 5.0 / 6.0  # 직사각형 전단 보정 계수
    I = b * H**3 / 12
    A = H * b
    delta_bending = P * L**3 / (3 * E * I)
    delta_shear = P * L / (kappa * G * A)
    delta_analytical = delta_bending + delta_shear

    u = mesh.get_displacements()
    delta_fem = np.mean(u[right_nodes, 1])

    print(f"  (참고: Euler-Bernoulli = {delta_bending:.6e}, 전단 보정 = {delta_shear:.6e})")
    error = print_comparison("끝단 처짐 (Timoshenko)", delta_analytical, delta_fem)
    return error


# ============================================================
#  벤치마크 4: 3D 큐브 압축 (HEX8)
# ============================================================

def benchmark_cube_compression_3d():
    """3D 정육면체 압축: u_z = -σL/E (구속 조건에 따라 범위)"""
    print_header("3D 큐브 압축 (HEX8)")

    E = 1e6
    nu = 0.3
    L = 0.5
    sigma = -1000.0  # 압축 응력

    nx, ny, nz = 6, 6, 6
    nodes, elements, n_nodes, n_elements = create_hex8_mesh(nx, ny, nz, L, L, L)
    print(f"  메쉬: {nx}×{ny}×{nz} = {n_elements}개 HEX8 요소, {n_nodes}개 노드")

    mesh = FEMesh(n_nodes=n_nodes, n_elements=n_elements, element_type=ElementType.HEX8)
    mesh.initialize_from_numpy(nodes, elements)

    # 바닥 고정 (z=0)
    bottom_nodes = np.where(np.abs(nodes[:, 2]) < 1e-6)[0]
    mesh.set_fixed_nodes(bottom_nodes)

    # 상단에 균일 압축 (z=L)
    top_nodes = np.where(np.abs(nodes[:, 2] - L) < 1e-6)[0]
    A_top = L * L
    total_force = sigma * A_top
    force_per_node = total_force / len(top_nodes)
    forces = np.zeros((len(top_nodes), 3), dtype=np.float32)
    forces[:, 2] = force_per_node  # z 방향 (음)
    mesh.set_nodal_forces(top_nodes, forces)

    material = LinearElastic(youngs_modulus=E, poisson_ratio=nu, dim=3)
    solver = StaticSolver(mesh, material)
    t0 = time.time()
    result = solver.solve(verbose=False)
    elapsed = time.time() - t0

    print(f"  수렴: {result['converged']}, {elapsed:.2f}초")

    # 해석해: 자유 압축 u = σL/E, 구속 압축은 E_eff로
    u_free = sigma * L / E
    E_eff = E * (1 - nu) / ((1 + nu) * (1 - 2 * nu))
    u_constrained = sigma * L / E_eff

    u = mesh.get_displacements()
    u_fem = np.mean(u[top_nodes, 2])

    print(f"  해석해 범위: [{u_constrained:.6e}, {u_free:.6e}]")
    error = abs(u_fem - u_free) / abs(u_free) * 100
    print(f"  z-변위 (윗면, 자유 압축 대비):")
    print(f"    해석해    = {u_free:.6e} m")
    print(f"    FEM 결과  = {u_fem:.6e} m")
    print(f"    상대 오차 = {error:8.2f}%")

    in_range = u_constrained <= u_fem <= u_free or u_free <= u_fem <= u_constrained
    if in_range:
        print(f"  → FEM 결과가 해석해 범위 내에 있음 (양호)")
    return error


# ============================================================
#  벤치마크 5: 격자 수렴성 분석 (2D QUAD4, 외팔보)
# ============================================================

def benchmark_convergence_2d():
    """격자 수렴성: 외팔보 끝단 처짐의 메쉬 밀도별 오차 변화.

    외팔보는 굽힘 구배가 있어 격자 수렴성 관찰에 적합하다.
    인장 봉은 BC 제약으로 격자 무관한 오차 바닥이 존재한다.
    """
    print_header("격자 수렴성 분석 (2D QUAD4 외팔보)")

    E = 1e4
    nu = 0.3
    L = 1.0
    H = 0.2
    P = -1.0  # 끝단 하중

    # Timoshenko 해석해 (전단 포함): δ = PL³/(3EI) + PL/(κGA)
    b = 1.0
    G = E / (2 * (1 + nu))
    kappa = 5.0 / 6.0
    I = b * H**3 / 12
    A_beam = H * b
    delta_bending = P * L**3 / (3 * E * I)
    delta_shear = P * L / (kappa * G * A_beam)
    delta_analytical = delta_bending + delta_shear
    print(f"  Timoshenko 해석해 (끝단 처짐): {delta_analytical:.6e} m")
    print(f"    (굽힘: {delta_bending:.6e}, 전단: {delta_shear:.6e})\n")

    # ny/nx = H/L = 0.2 비율 유지
    mesh_sizes = [(10, 2), (20, 4), (40, 8), (60, 12), (80, 16)]
    results = []

    for nx, ny in mesh_sizes:
        nodes, elements, n_nodes, n_elements = create_quad4_mesh(nx, ny, L, H)
        mesh = FEMesh(n_nodes=n_nodes, n_elements=n_elements, element_type=ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        left_nodes = np.where(np.abs(nodes[:, 0]) < 1e-6)[0]
        mesh.set_fixed_nodes(left_nodes)

        right_nodes = np.where(np.abs(nodes[:, 0] - L) < 1e-6)[0]
        force_per_node = P / len(right_nodes)
        forces = np.zeros((len(right_nodes), 2), dtype=np.float32)
        forces[:, 1] = force_per_node
        mesh.set_nodal_forces(right_nodes, forces)

        material = LinearElastic(youngs_modulus=E, poisson_ratio=nu, dim=2, plane_stress=True)
        solver = StaticSolver(mesh, material)
        t0 = time.time()
        result = solver.solve(verbose=False)
        elapsed = time.time() - t0

        u = mesh.get_displacements()
        delta_fem = np.mean(u[right_nodes, 1])
        error = abs(delta_fem - delta_analytical) / abs(delta_analytical) * 100
        h = L / nx

        print(f"  --- {nx}×{ny} ({n_elements}개 요소, h={h:.4f}) ---")
        print(f"    FEM 처짐  = {delta_fem:.6e} m, 오차 = {error:.2f}%, {elapsed:.2f}초")

        results.append((h, n_elements, delta_fem, error))

    # 수렴율 계산
    rates = []
    for i in range(1, len(results)):
        h1, _, _, e1 = results[i - 1]
        h2, _, _, e2 = results[i]
        if e2 > 1e-10 and e1 > 1e-10:
            rate = np.log(e1 / e2) / np.log(h1 / h2)
            rates.append(rate)

    avg_rate = np.mean(rates) if rates else 0.0
    if rates:
        print(f"\n  평균 수렴율: {avg_rate:.2f}")
        for i, r in enumerate(rates):
            print(f"    h={results[i][0]:.4f}→{results[i+1][0]:.4f}: rate={r:.2f}")

    print(f"\n  {'h':>8}  {'요소수':>8}  {'처짐':>14}  {'오차(%)':>8}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*14}  {'-'*8}")
    for h, ne, u, err in results:
        print(f"  {h:8.4f}  {ne:8d}  {u:14.6e}  {err:8.2f}")

    return avg_rate


# ============================================================
#  메인
# ============================================================

def main():
    ti.init(arch=ti.cpu, default_fp=ti.f32)

    print("\n################################################################")
    print("  FEM 솔버 해석해 비교 벤치마크")
    print("################################################################")

    t_total = time.time()
    summary = []

    e1 = benchmark_tension_bar_2d()
    summary.append(("균일 인장 봉 (2D)", e1))

    e2 = benchmark_tension_bar_3d()
    summary.append(("균일 인장 봉 (3D)", e2))

    e3 = benchmark_cantilever_2d()
    summary.append(("외팔보 (2D)", e3))

    e4 = benchmark_cube_compression_3d()
    summary.append(("3D 큐브 압축", e4))

    rate = benchmark_convergence_2d()

    elapsed_total = time.time() - t_total

    # 최종 요약
    print(f"\n{'=' * 64}")
    print(f"  최종 요약")
    print(f"{'=' * 64}\n")
    print(f"  {'벤치마크':<24}  {'주요 오차(%)':>12}  {'평가':>8}")
    print(f"  {'-'*24}  {'-'*12}  {'-'*8}")
    for name, err in summary:
        grade = "양호" if err < 5 else ("보통" if err < 15 else "미흡")
        print(f"  {name:<24}  {err:12.2f}  {grade:>8}")
    print(f"  {'격자 수렴성':<24}  {'rate='+f'{rate:.2f}':>12}  {'양호' if rate > 1.5 else '보통':>8}")

    print(f"\n  총 실행 시간: {elapsed_total:.1f}초")
    print(f"{'=' * 64}")


if __name__ == "__main__":
    main()
