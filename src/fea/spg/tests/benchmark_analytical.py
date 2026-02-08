"""SPG 솔버 해석해 비교 벤치마크.

해석해가 알려진 5가지 표준 문제와 SPG 솔버 결과를 비교하여
물리적 정확도를 검증한다.

벤치마크 문제:
1. 균일 인장 봉 (Uniaxial Tension Bar) - 2D
2. 외팔보 (Cantilever Beam) - 2D
3. 양단 고정 보 (Simply Supported Beam) - 2D
4. 3D 정육면체 압축 (Cube Compression) - 3D
5. 격자 수렴성 분석 (Convergence Study) - 2D

실행:
    uv run python src/fea/spg/tests/benchmark_analytical.py

참고:
    SPG(Smoothed Particle Galerkin)는 메쉬프리 방법으로, 경계 입자의
    형상함수 지지 영역이 잘려 inherent한 경계 오차가 있다.
    안정화력(zero-energy mode stabilization)도 수치 변형을 추가한다.
    따라서 동일 해상도에서 FEM보다 큰 오차가 예상되며,
    격자가 밀어질수록 수렴하는 것이 핵심 검증 포인트다.
"""

import sys
import os
import time
import numpy as np
import taichi as ti

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from src.fea.spg.core.particles import SPGParticleSystem
from src.fea.spg.core.kernel import SPGKernel
from src.fea.spg.core.bonds import SPGBondSystem
from src.fea.spg.solver.explicit_solver import SPGExplicitSolver
from src.fea.spg.material.elastic import SPGElasticMaterial


# ============================================================
#  헬퍼 함수
# ============================================================

def create_2d_system(nx, ny, spacing, E, nu, density=1000.0, support_factor=2.5):
    """2D SPG 시스템 생성."""
    n_particles = nx * ny
    support_radius = spacing * support_factor

    ps = SPGParticleSystem(n_particles=n_particles, dim=2)
    ps.initialize_from_grid(
        origin=(0.0, 0.0),
        spacing=spacing,
        n_points=(nx, ny),
        density=density
    )

    kernel = SPGKernel(
        n_particles=n_particles, dim=2,
        support_radius=support_radius
    )
    kernel.build_neighbor_list(ps.X.to_numpy(), support_radius)
    kernel.compute_shape_functions(ps.X, ps.volume)

    bonds = SPGBondSystem(n_particles=n_particles, dim=2)
    bonds.build_from_kernel(ps, kernel)

    material = SPGElasticMaterial(E, nu, density, dim=2)

    return ps, kernel, bonds, material


def create_3d_system(nx, ny, nz, spacing, E, nu, density=1000.0, support_factor=2.5):
    """3D SPG 시스템 생성."""
    n_particles = nx * ny * nz
    support_radius = spacing * support_factor

    ps = SPGParticleSystem(n_particles=n_particles, dim=3)
    ps.initialize_from_grid(
        origin=(0.0, 0.0, 0.0),
        spacing=spacing,
        n_points=(nx, ny, nz),
        density=density
    )

    kernel = SPGKernel(
        n_particles=n_particles, dim=3,
        support_radius=support_radius
    )
    kernel.build_neighbor_list(ps.X.to_numpy(), support_radius)
    kernel.compute_shape_functions(ps.X, ps.volume)

    bonds = SPGBondSystem(n_particles=n_particles, dim=3)
    bonds.build_from_kernel(ps, kernel)

    material = SPGElasticMaterial(E, nu, density, dim=3)

    return ps, kernel, bonds, material


def run_solver(ps, kernel, bonds, material, stab=0.01, damp=0.05,
               max_iter=80000, tol=1e-3, verbose=False):
    """SPG 솔버 실행."""
    solver = SPGExplicitSolver(
        particles=ps,
        kernel=kernel,
        bonds=bonds,
        material=material,
        stabilization=stab,
        viscous_damping=damp
    )

    t0 = time.time()
    result = solver.solve(
        max_iterations=max_iter,
        tol=tol,
        verbose=verbose,
        print_interval=10000
    )
    elapsed = time.time() - t0

    return result, elapsed


def print_header(title):
    """벤치마크 제목 출력."""
    width = 64
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def print_result(label, analytical, spg, unit=""):
    """해석해 vs SPG 결과 비교 출력."""
    if abs(analytical) > 1e-30:
        error = abs(spg - analytical) / abs(analytical) * 100
    else:
        error = abs(spg - analytical) * 100
    unit_str = f" {unit}" if unit else ""
    print(f"  {label}:")
    print(f"    해석해    = {analytical:12.6e}{unit_str}")
    print(f"    SPG 결과  = {spg:12.6e}{unit_str}")
    print(f"    상대 오차 = {error:8.2f}%")
    return error


def compute_2d_plane_strain_E_eff(E, nu):
    """2D 평면변형 유효 영 계수 계산.

    SPG 2D는 평면변형 Lamé 매개변수를 사용한다:
        λ = Eν/((1+ν)(1-ν)), μ = E/(2(1+ν))
    측면 자유(σ_yy=0) 조건에서 유효 영 계수:
        E_eff = 4μ(λ+μ)/(λ+2μ)
    """
    mu = E / (2 * (1 + nu))
    lam = E * nu / ((1 + nu) * (1 - nu))
    return 4 * mu * (lam + mu) / (lam + 2 * mu)


# ============================================================
#  벤치마크 1: 균일 인장 봉 (Uniaxial Tension Bar)
# ============================================================

def benchmark_uniaxial_tension():
    """균일 인장 봉 문제.

    설정:
        - 직사각형 도메인 L=1.0, H=0.2 (2D 평면변형)
        - 왼쪽 끝 고정, 오른쪽 끝 인장력
    해석해:
        δ = PL/(A·E_eff), σ_xx = P/A
    """
    print_header("벤치마크 1: 균일 인장 봉 (Uniaxial Tension Bar)")

    L, H = 1.0, 0.2
    E, nu = 1e4, 0.3
    density = 1000.0
    thickness = 1.0

    # 세밀한 격자 (경계 효과 최소화)
    spacing = 0.015
    nx = int(L / spacing) + 1
    ny = int(H / spacing) + 1

    print(f"  격자: {nx}×{ny} = {nx*ny}개 입자, 간격={spacing}")

    ps, kernel, bonds, material = create_2d_system(
        nx, ny, spacing, E, nu, density
    )

    pos = ps.X.to_numpy()

    # 왼쪽 끝 고정
    fixed_idx = np.where(pos[:, 0] < spacing * 0.5)[0]
    ps.set_fixed_particles(fixed_idx)

    # 오른쪽 끝 인장력
    right_idx = np.where(pos[:, 0] > (nx - 1) * spacing - spacing * 0.5)[0]
    n_right = len(right_idx)
    P_total = 10.0
    ps.set_external_force(right_idx, np.array([P_total / n_right, 0.0]))

    result, elapsed = run_solver(ps, kernel, bonds, material,
                                 stab=0.01, max_iter=100000, tol=1e-4)

    print(f"  수렴: {result['converged']}, {result['iterations']}회, {elapsed:.1f}초")

    disp = ps.get_displacements()
    stress = ps.get_stress()

    spg_disp = np.mean(disp[right_idx, 0])

    # 내부 영역 응력
    x_min, x_max = pos[:, 0].min(), pos[:, 0].max()
    y_min, y_max = pos[:, 1].min(), pos[:, 1].max()
    interior = np.where(
        (pos[:, 0] > x_min + L * 0.3) &
        (pos[:, 0] < x_max - L * 0.3) &
        (pos[:, 1] > y_min + H * 0.3) &
        (pos[:, 1] < y_max - H * 0.3)
    )[0]
    spg_stress_xx = np.mean(stress[interior, 0, 0]) if len(interior) > 0 else 0.0

    # 해석해
    A = H * thickness
    analytical_stress = P_total / A
    E_eff = compute_2d_plane_strain_E_eff(E, nu)
    analytical_disp = analytical_stress / E_eff * L

    errors = []
    errors.append(print_result("x-변위 (오른쪽 끝)", analytical_disp, spg_disp, "m"))
    errors.append(print_result("σ_xx (내부 평균)", analytical_stress, spg_stress_xx, "Pa"))

    return errors


# ============================================================
#  벤치마크 2: 외팔보 (Cantilever Beam)
# ============================================================

def benchmark_cantilever_beam():
    """외팔보 끝단 점하중 문제.

    설정:
        - L=1.0, H=0.2 (2D 평면변형)
        - 왼쪽 끝 고정, 오른쪽 끝 하향 점하중
    해석해 (Timoshenko):
        δ = PL³/(3·E_eff·I) + PL/(κGA)
    """
    print_header("벤치마크 2: 외팔보 (Cantilever Beam)")

    L, H = 1.0, 0.2
    E, nu = 1e4, 0.3
    density = 1000.0
    thickness = 1.0

    spacing = 0.015
    nx = int(L / spacing) + 1
    ny = int(H / spacing) + 1

    print(f"  격자: {nx}×{ny} = {nx*ny}개 입자, 간격={spacing}")

    ps, kernel, bonds, material = create_2d_system(
        nx, ny, spacing, E, nu, density
    )

    pos = ps.X.to_numpy()

    # 왼쪽 끝 고정 (1열)
    fixed_idx = np.where(pos[:, 0] < spacing * 0.5)[0]
    ps.set_fixed_particles(fixed_idx)

    # 오른쪽 끝 하향 하중
    right_idx = np.where(pos[:, 0] > (nx - 1) * spacing - spacing * 0.5)[0]
    n_right = len(right_idx)
    P_total = 0.5
    ps.set_external_force(right_idx, np.array([0.0, -P_total / n_right]))

    # 감쇠를 낮춰야 외팔보 수렴이 향상됨
    result, elapsed = run_solver(ps, kernel, bonds, material,
                                 stab=0.01, damp=0.01,
                                 max_iter=150000, tol=1e-3)

    print(f"  수렴: {result['converged']}, {result['iterations']}회, {elapsed:.1f}초")

    disp = ps.get_displacements()
    spg_tip_deflection = np.mean(disp[right_idx, 1])

    # 해석해
    I = thickness * H**3 / 12.0
    G = E / (2 * (1 + nu))
    kappa = 5.0 / 6.0
    A = H * thickness
    E_eff = compute_2d_plane_strain_E_eff(E, nu)

    delta_bending = P_total * L**3 / (3 * E_eff * I)
    delta_shear = P_total * L / (kappa * G * A)
    analytical_deflection = -(delta_bending + delta_shear)

    errors = []
    errors.append(print_result("끝단 처짐", analytical_deflection, spg_tip_deflection, "m"))

    return errors


# ============================================================
#  벤치마크 3: 양단 지지 보 (Simply Supported Beam)
# ============================================================

def benchmark_simply_supported_beam():
    """양단 고정 보 (clamped-clamped), 균일 분포 하중.

    설정:
        - L=1.0, H=0.2 (2D 평면변형)
        - 양 끝 1열 완전 고정 (clamped: u=0)
        - 자유 입자에 균일 체적력

    참고: set_fixed_particles는 u=0을 강제 → clamped 경계조건
    해석해 (양단 고정보):
        δ_mid = wL⁴/(384·E_eff·I)  (전단 보정 포함)
    """
    print_header("벤치마크 3: 양단 고정 보 (Clamped Beam)")

    L, H = 1.0, 0.2
    E, nu = 1e4, 0.3
    density = 1000.0
    thickness = 1.0

    spacing = 0.015
    nx = int(L / spacing) + 1
    ny = int(H / spacing) + 1

    print(f"  격자: {nx}×{ny} = {nx*ny}개 입자, 간격={spacing}")

    ps, kernel, bonds, material = create_2d_system(
        nx, ny, spacing, E, nu, density
    )

    pos = ps.X.to_numpy()
    x_min = pos[:, 0].min()
    x_max = pos[:, 0].max()

    # 양 끝 1열 고정
    left_support = np.where(pos[:, 0] < x_min + spacing * 0.5)[0]
    right_support = np.where(pos[:, 0] > x_max - spacing * 0.5)[0]
    fixed_idx = np.concatenate([left_support, right_support])
    ps.set_fixed_particles(fixed_idx)

    # 자유 입자 전체에 균일 하향 체적력
    free_mask = np.ones(len(pos), dtype=bool)
    free_mask[fixed_idx] = False
    free_idx = np.where(free_mask)[0]
    n_free = len(free_idx)

    w_total = 1.0  # 총 하중
    ps.set_external_force(free_idx, np.array([0.0, -w_total / n_free]))

    result, elapsed = run_solver(ps, kernel, bonds, material,
                                 stab=0.01, max_iter=100000, tol=1e-3)

    print(f"  수렴: {result['converged']}, {result['iterations']}회, {elapsed:.1f}초")

    disp = ps.get_displacements()

    # 중앙 부근 입자 처짐
    mid_x = (x_min + x_max) / 2.0
    y_mid = (pos[:, 1].min() + pos[:, 1].max()) / 2.0
    mid_idx = np.where(
        (np.abs(pos[:, 0] - mid_x) < spacing * 1.0) &
        (np.abs(pos[:, 1] - y_mid) < spacing * 1.5)
    )[0]

    spg_mid_deflection = np.mean(disp[mid_idx, 1]) if len(mid_idx) > 0 else 0.0

    # 해석해 (양단 고정보: δ_max = wL⁴/(384EI))
    w_per_length = w_total / L
    I = thickness * H**3 / 12.0
    G = E / (2 * (1 + nu))
    kappa = 5.0 / 6.0
    A = H * thickness
    E_eff = compute_2d_plane_strain_E_eff(E, nu)

    # 양단 고정보 중앙 처짐 (simply supported의 1/5)
    delta_bending = w_per_length * L**4 / (384 * E_eff * I)
    # 양단 고정보 전단 처짐 (simply supported와 동일)
    delta_shear = w_per_length * L**2 / (8 * kappa * G * A)
    analytical_deflection = -(delta_bending + delta_shear)

    errors = []
    errors.append(print_result("중앙 처짐", analytical_deflection, spg_mid_deflection, "m"))

    return errors


# ============================================================
#  벤치마크 4: 3D 정육면체 압축 (Cube Compression)
# ============================================================

def benchmark_cube_compression():
    """3D 정육면체 균일 압축.

    설정:
        - L×L×L 정육면체
        - 아래면 (z=0) 완전 고정 (u=0)
        - 윗면 균일 압축력

    참고: 아래면 전면 고정은 측면 변위도 구속하므로 순수 단축 압축이 아님.
         해석적으로 정확한 해를 구하기 어려우므로, 상한/하한 추정으로 검증.
         상한: 자유 단축 압축 δ = σ/E × L
         하한: 구속 압축 δ = σ/(λ+2μ) × L
         실제 해는 이 사이에 있음.
    """
    print_header("벤치마크 4: 3D 정육면체 압축 (Cube Compression)")

    L = 0.5
    E, nu = 1e4, 0.3
    density = 1000.0

    spacing = 0.05
    n = int(L / spacing) + 1

    print(f"  격자: {n}×{n}×{n} = {n**3}개 입자, 간격={spacing}")

    ps, kernel, bonds, material = create_3d_system(
        n, n, n, spacing, E, nu, density, support_factor=2.5
    )

    pos = ps.X.to_numpy()

    # 아래면 고정
    fixed_idx = np.where(pos[:, 2] < spacing * 0.5)[0]
    ps.set_fixed_particles(fixed_idx)

    # 윗면 압축력
    top_idx = np.where(pos[:, 2] > (n - 1) * spacing - spacing * 0.5)[0]
    n_top = len(top_idx)
    p_total = 5.0
    ps.set_external_force(top_idx, np.array([0.0, 0.0, -p_total / n_top]))

    result, elapsed = run_solver(ps, kernel, bonds, material,
                                 stab=0.01, max_iter=80000, tol=1e-3)

    print(f"  수렴: {result['converged']}, {result['iterations']}회, {elapsed:.1f}초")

    disp = ps.get_displacements()
    spg_top_disp_z = np.mean(disp[top_idx, 2])

    # 해석해 범위
    A_top = L * L
    sigma_zz = -p_total / A_top
    lam = material.lam
    mu = material.mu

    # 상한 (자유 단축): δ = σ/E × L
    upper_bound = sigma_zz / E * L
    # 하한 (완전 구속): δ = σ/(λ+2μ) × L
    lower_bound = sigma_zz / (lam + 2 * mu) * L
    # 중간값을 해석해로 사용
    analytical_disp_z = (upper_bound + lower_bound) / 2.0

    print(f"  해석해 범위: [{lower_bound:.6e}, {upper_bound:.6e}]")
    print(f"  중간값     : {analytical_disp_z:.6e}")

    # SPG가 범위 안에 있는지 확인
    in_range = lower_bound <= spg_top_disp_z <= upper_bound or \
               upper_bound <= spg_top_disp_z <= lower_bound  # 부호 고려

    errors = []
    err = print_result("z-변위 (윗면, 중간값 대비)", analytical_disp_z, spg_top_disp_z, "m")
    errors.append(err)

    if in_range:
        print(f"  → SPG 결과가 해석해 범위 내에 있음 (양호)")
    else:
        print(f"  → SPG 결과가 해석해 범위를 벗어남")

    return errors


# ============================================================
#  벤치마크 5: 격자 수렴성 분석 (Convergence Study)
# ============================================================

def benchmark_convergence_study():
    """인장 봉 문제의 격자 수렴성 분석.

    4가지 해상도로 균일 인장 봉 문제를 풀고,
    격자를 밀게 하면 오차가 줄어드는 h-수렴을 확인한다.
    """
    print_header("벤치마크 5: 격자 수렴성 분석 (Convergence Study)")

    L, H = 1.0, 0.2
    E, nu = 1e4, 0.3
    density = 1000.0
    thickness = 1.0
    P_total = 10.0

    E_eff = compute_2d_plane_strain_E_eff(E, nu)
    A = H * thickness
    analytical_stress = P_total / A
    analytical_disp = analytical_stress / E_eff * L

    print(f"  해석해 (x-변위): {analytical_disp:.6e} m")
    print(f"  E_eff(2D)      : {E_eff:.2e}\n")

    spacings = [0.04, 0.025, 0.02, 0.015]
    results_list = []

    for spacing in spacings:
        nx = int(L / spacing) + 1
        ny = int(H / spacing) + 1
        n = nx * ny

        print(f"  --- 간격 h={spacing:.3f} ({nx}×{ny} = {n}개 입자) ---")

        ps, kernel, bonds, material = create_2d_system(
            nx, ny, spacing, E, nu, density
        )

        pos = ps.X.to_numpy()
        fixed_idx = np.where(pos[:, 0] < spacing * 0.5)[0]
        ps.set_fixed_particles(fixed_idx)

        right_idx = np.where(pos[:, 0] > (nx - 1) * spacing - spacing * 0.5)[0]
        ps.set_external_force(right_idx, np.array([P_total / len(right_idx), 0.0]))

        result, elapsed = run_solver(ps, kernel, bonds, material,
                                     stab=0.01, max_iter=100000, tol=1e-4)

        disp = ps.get_displacements()
        spg_disp = np.mean(disp[right_idx, 0])
        error = abs(spg_disp - analytical_disp) / abs(analytical_disp) * 100

        print(f"    SPG 변위  = {spg_disp:.6e} m")
        print(f"    상대 오차 = {error:.2f}%")
        print(f"    수렴: {result['converged']}, {result['iterations']}회, {elapsed:.1f}초\n")

        results_list.append({
            "spacing": spacing,
            "nx": nx,
            "ny": ny,
            "n_particles": n,
            "displacement": spg_disp,
            "error_pct": error,
            "converged": result["converged"]
        })

    # 수렴율 계산 (인접 쌍들의 평균)
    convergence_rate = None
    rates = []
    for i in range(len(results_list) - 1):
        h1 = results_list[i]["spacing"]
        h2 = results_list[i + 1]["spacing"]
        e1 = results_list[i]["error_pct"]
        e2 = results_list[i + 1]["error_pct"]
        if e1 > 1e-10 and e2 > 1e-10:
            r = np.log(e1 / e2) / np.log(h1 / h2)
            rates.append(r)

    if rates:
        convergence_rate = np.mean(rates)
        print(f"  평균 수렴율: {convergence_rate:.2f}")
        for i, r in enumerate(rates):
            h1 = results_list[i]["spacing"]
            h2 = results_list[i + 1]["spacing"]
            print(f"    h={h1:.3f}→{h2:.3f}: rate={r:.2f}")
        print(f"  (1차 이상이면 양호)")

    # 수렴 테이블
    print(f"\n  {'h':>8s}  {'입자수':>8s}  {'변위':>14s}  {'오차(%)':>8s}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*14}  {'-'*8}")
    for r in results_list:
        print(f"  {r['spacing']:8.4f}  {r['n_particles']:8d}  "
              f"{r['displacement']:14.6e}  {r['error_pct']:8.2f}")

    return results_list, convergence_rate


# ============================================================
#  메인 실행
# ============================================================

def main():
    """전체 벤치마크 실행."""
    ti.init(arch=ti.cpu, default_fp=ti.f64)

    print("\n" + "#" * 64)
    print("  SPG 솔버 해석해 비교 벤치마크")
    print("#" * 64)

    all_errors = {}
    t_total = time.time()

    # 1. 균일 인장 봉
    try:
        errors = benchmark_uniaxial_tension()
        all_errors["균일 인장 봉"] = errors
    except Exception as e:
        print(f"  오류: {e}")
        import traceback; traceback.print_exc()
        all_errors["균일 인장 봉"] = [float("nan")]

    # 2. 외팔보
    try:
        errors = benchmark_cantilever_beam()
        all_errors["외팔보"] = errors
    except Exception as e:
        print(f"  오류: {e}")
        import traceback; traceback.print_exc()
        all_errors["외팔보"] = [float("nan")]

    # 3. 양단 지지 보
    try:
        errors = benchmark_simply_supported_beam()
        all_errors["양단 지지 보"] = errors
    except Exception as e:
        print(f"  오류: {e}")
        import traceback; traceback.print_exc()
        all_errors["양단 지지 보"] = [float("nan")]

    # 4. 3D 정육면체 압축
    try:
        errors = benchmark_cube_compression()
        all_errors["3D 큐브 압축"] = errors
    except Exception as e:
        print(f"  오류: {e}")
        import traceback; traceback.print_exc()
        all_errors["3D 큐브 압축"] = [float("nan")]

    # 5. 격자 수렴성
    conv_rate = None
    try:
        conv_results, conv_rate = benchmark_convergence_study()
        all_errors["격자 수렴성"] = [r["error_pct"] for r in conv_results]
    except Exception as e:
        print(f"  오류: {e}")
        import traceback; traceback.print_exc()
        all_errors["격자 수렴성"] = [float("nan")]

    elapsed_total = time.time() - t_total

    # ============================================================
    #  최종 요약
    # ============================================================
    print("\n" + "=" * 64)
    print("  최종 요약")
    print("=" * 64)

    print(f"\n  {'벤치마크':<20s}  {'주요 오차(%)':>12s}  {'평가':>8s}")
    print(f"  {'-'*20}  {'-'*12}  {'-'*8}")

    for name, errs in all_errors.items():
        if name == "격자 수렴성":
            continue
        max_err = max(errs) if errs else float("nan")
        if np.isnan(max_err):
            grade = "실패"
        elif max_err < 5:
            grade = "우수"
        elif max_err < 10:
            grade = "양호"
        elif max_err < 20:
            grade = "보통"
        elif max_err < 40:
            grade = "미흡"
        else:
            grade = "매우 미흡"
        print(f"  {name:<20s}  {max_err:12.2f}  {grade:>8s}")

    if conv_rate is not None:
        grade = "양호" if conv_rate > 0.5 else "미흡"
        print(f"  {'격자 수렴성':<20s}  rate={conv_rate:5.2f}  {grade:>8s}")

    print(f"\n  총 실행 시간: {elapsed_total:.1f}초")
    print(f"\n  참고: SPG는 메쉬프리 방법으로, 경계 형상함수 잘림과")
    print(f"       안정화력 때문에 FEM 대비 상대적으로 큰 오차가 발생한다.")
    print(f"       격자 수렴(오차가 h→0에서 줄어드는 것)이 핵심 검증 포인트.")
    print("=" * 64)


if __name__ == "__main__":
    main()
