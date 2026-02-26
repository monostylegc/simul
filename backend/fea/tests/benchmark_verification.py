"""통합 FEA 검증 벤치마크.

세 솔버(FEM, NOSB-PD, SPG)를 동일한 표준 문제로 교차 검증한다.
통합 프레임워크 API(create_domain/Solver/Material)를 사용하여
솔버 간 일관성과 해석해 대비 정확도를 평가한다.

벤치마크 문제:
  Part A: 외팔보 (Cantilever Beam)
    A-1. 2D 외팔보 — QUAD4(FEM), 입자(PD/SPG)
    A-2. 3D 외팔보 — HEX8(FEM), 입자(PD/SPG)
    A-3. 2D 외팔보 격자 수렴성 분석

  Part B: 실린더 압축 (Cylinder Compression)
    B-1. 3D 실린더 단축 압축 — 원형 단면 필터링

실행:
    uv run python src/fea/tests/benchmark_verification.py
"""

import sys
import os
import time
import math
import numpy as np

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.fea.framework import init, create_domain, Material, Solver, Method


# =============================================================================
#  해석해 함수
# =============================================================================

def timoshenko_cantilever_2d(P, L, H, E, nu, b=1.0, plane_stress=True):
    """2D Timoshenko 외팔보 해석해 (전단 보정 포함).

    Args:
        P: 끝단 집중하중 (하방이면 음수)
        L: 보 길이
        H: 보 높이
        E: 영 계수
        nu: 푸아송 비
        b: 보 폭 (2D 단위 두께)
        plane_stress: True이면 E 직접, False이면 평면변형 E_eff 사용

    Returns:
        끝단 처짐 (부호 포함)
    """
    if not plane_stress:
        # 평면변형 유효 탄성계수: E_eff = 4μ(λ+μ)/(λ+2μ)
        mu = E / (2.0 * (1.0 + nu))
        lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
        E_use = 4.0 * mu * (lam + mu) / (lam + 2.0 * mu)
    else:
        E_use = E

    I = b * H**3 / 12.0
    G = E_use / (2.0 * (1.0 + nu))
    kappa = 5.0 / 6.0  # 직사각형 전단 보정계수
    A = H * b

    delta_bending = P * L**3 / (3.0 * E_use * I)
    delta_shear = P * L / (kappa * G * A)

    return delta_bending + delta_shear


def timoshenko_cantilever_3d(P, L, W, H, E, nu):
    """3D Timoshenko 외팔보 해석해.

    Args:
        P: 끝단 집중하중 (z방향)
        L: 보 길이 (x방향)
        W: 보 폭 (y방향)
        H: 보 높이 (z방향, 하중 방향)
        E: 영 계수
        nu: 푸아송 비

    Returns:
        끝단 z-처짐
    """
    I = W * H**3 / 12.0
    G = E / (2.0 * (1.0 + nu))
    kappa = 5.0 / 6.0
    A = W * H

    delta_bending = P * L**3 / (3.0 * E * I)
    delta_shear = P * L / (kappa * G * A)

    return delta_bending + delta_shear


def cylinder_compression_analytical(sigma, L, E, nu):
    """실린더 단축 압축 해석해 (상하한).

    바닥 고정 + 상단 압축 시, 실제 변위는 자유/완전구속 사이에 위치한다.

    Args:
        sigma: 압축 응력 (음수)
        L: 실린더 높이
        E: 영 계수
        nu: 푸아송 비

    Returns:
        (u_free, u_constrained): 자유 측면/완전 구속 압축 변위
    """
    # 자유 측면 팽창
    u_free = sigma * L / E
    # 완전 측면 구속 (oedometric)
    E_eff = E * (1.0 - nu) / ((1.0 + nu) * (1.0 - 2.0 * nu))
    u_constrained = sigma * L / E_eff

    return u_free, u_constrained


# =============================================================================
#  유틸리티 함수
# =============================================================================

def print_header(title):
    """벤치마크 제목 출력."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def grade_error(error_pct):
    """오차에 따른 등급 반환."""
    if error_pct < 2.0:
        return "우수"
    elif error_pct < 5.0:
        return "양호"
    elif error_pct < 15.0:
        return "보통"
    elif error_pct < 30.0:
        return "미흡"
    else:
        return "매우 미흡"


def compute_error(analytical, numerical):
    """상대 오차(%) 계산."""
    if abs(analytical) < 1e-30:
        return 0.0
    return abs(numerical - analytical) / abs(analytical) * 100.0


def print_solver_row(name, analytical, numerical, unit="m"):
    """솔버 결과 한 줄 출력."""
    err = compute_error(analytical, numerical)
    grade = grade_error(err)
    print(f"  {name:<6} {analytical:>14.6e}  {numerical:>14.6e}  {err:>7.2f}%  {grade}")
    return err


def print_range_row(name, u_free, u_constrained, numerical, unit="m"):
    """범위 검증 결과 한 줄 출력."""
    lo = min(u_free, u_constrained)
    hi = max(u_free, u_constrained)
    in_range = lo <= numerical <= hi or hi <= numerical <= lo
    # 자유 압축 기준 오차
    err = compute_error(u_free, numerical)
    mark = "O" if in_range else "X"
    print(f"  {name:<6} [{lo:>11.4e}, {hi:>11.4e}]  {numerical:>12.4e}  {mark}  ({err:.1f}%)")
    return in_range, err


# =============================================================================
#  A-1: 2D 외팔보
# =============================================================================

def solve_cantilever_2d(method, E, nu, L, H, P, density, nx, ny, **solver_opts):
    """2D 외팔보 솔버 실행 (공통 로직).

    Returns:
        (끝단 평균 y-변위, 수렴 여부, 반복 횟수, 소요 시간)
    """
    plane_stress = (method == Method.FEM)
    domain = create_domain(method, dim=2, origin=(0, 0), size=(L, H),
                           n_divisions=(nx, ny))

    left = domain.select(axis=0, value=0.0)
    right = domain.select(axis=0, value=L)

    domain.set_fixed(left)

    # 총 하중을 우측 노드/입자에 균등 분배
    n_right = len(right)
    force_per_node = P / n_right
    domain.set_force(right, [0.0, force_per_node])

    mat = Material(E=E, nu=nu, density=density, dim=2, plane_stress=plane_stress)
    solver = Solver(domain, mat, **solver_opts)

    t0 = time.time()
    result = solver.solve()
    elapsed = time.time() - t0

    u = solver.get_displacements()
    delta = np.mean(u[right, 1])

    return delta, result.converged, result.iterations, elapsed


def benchmark_cantilever_2d():
    """A-1: 2D 외팔보 (세 솔버 비교)."""
    print_header("A-1: 2D 외팔보 (Cantilever Beam)")

    E, nu = 1e4, 0.3
    L, H = 1.0, 0.2
    P = -1.0  # 끝단 하향 하중 [N]
    density = 1000.0

    # 해석해
    delta_fem_ana = timoshenko_cantilever_2d(P, L, H, E, nu, plane_stress=True)
    delta_pd_ana = timoshenko_cantilever_2d(P, L, H, E, nu, plane_stress=False)

    print(f"\n  문제: L={L}m, H={H}m, E={E:.0e}Pa, ν={nu}, P={P}N")
    print(f"  FEM 해석해 (평면응력): {delta_fem_ana:.6e} m")
    print(f"  PD/SPG 해석해 (평면변형): {delta_pd_ana:.6e} m")
    print()
    print(f"  {'솔버':<6} {'해석해[m]':>14}  {'수치해[m]':>14}  {'오차':>7}  등급")
    print(f"  {'-'*6} {'-'*14}  {'-'*14}  {'-'*7}  {'-'*6}")

    results = {}

    # --- FEM ---
    delta, conv, iters, elapsed = solve_cantilever_2d(
        Method.FEM, E, nu, L, H, P, density, nx=50, ny=10)
    err = print_solver_row("FEM", delta_fem_ana, delta)
    results["FEM"] = {"delta": delta, "analytical": delta_fem_ana, "error": err,
                      "converged": conv, "time": elapsed}

    # --- PD ---
    delta, conv, iters, elapsed = solve_cantilever_2d(
        Method.PD, E, nu, L, H, P, density, nx=51, ny=11,
        damping=0.1, max_iterations=80000, tol=1e-4)
    err = print_solver_row("PD", delta_pd_ana, delta)
    results["PD"] = {"delta": delta, "analytical": delta_pd_ana, "error": err,
                     "converged": conv, "time": elapsed}

    # --- SPG ---
    delta, conv, iters, elapsed = solve_cantilever_2d(
        Method.SPG, E, nu, L, H, P, density, nx=51, ny=11,
        stabilization=0.01, viscous_damping=0.01, max_iterations=150000, tol=1e-3)
    err = print_solver_row("SPG", delta_pd_ana, delta)
    results["SPG"] = {"delta": delta, "analytical": delta_pd_ana, "error": err,
                      "converged": conv, "time": elapsed}

    # 시간 정보
    print()
    for name in ["FEM", "PD", "SPG"]:
        r = results[name]
        conv_str = "수렴" if r["converged"] else "미수렴"
        print(f"  {name}: {r['time']:.1f}초 ({conv_str})")

    return results


# =============================================================================
#  A-2: 3D 외팔보
# =============================================================================

def solve_cantilever_3d(method, E, nu, L, W, H, P, density, nx, ny, nz, **solver_opts):
    """3D 외팔보 솔버 실행 (공통 로직).

    Returns:
        (끝단 평균 z-변위, 수렴 여부, 반복 횟수, 소요 시간)
    """
    domain = create_domain(method, dim=3, origin=(0, 0, 0), size=(L, W, H),
                           n_divisions=(nx, ny, nz))

    left = domain.select(axis=0, value=0.0)
    right = domain.select(axis=0, value=L)

    domain.set_fixed(left)

    n_right = len(right)
    force_per_node = P / n_right
    domain.set_force(right, [0.0, 0.0, force_per_node])

    mat = Material(E=E, nu=nu, density=density, dim=3)
    solver = Solver(domain, mat, **solver_opts)

    t0 = time.time()
    result = solver.solve()
    elapsed = time.time() - t0

    u = solver.get_displacements()
    delta = np.mean(u[right, 2])

    return delta, result.converged, result.iterations, elapsed


def benchmark_cantilever_3d():
    """A-2: 3D 외팔보 (세 솔버 비교)."""
    print_header("A-2: 3D 외팔보 (Cantilever Beam)")

    E, nu = 1e4, 0.3
    L, W, H = 1.0, 0.2, 0.2  # 정사각 단면
    P = -1.0  # z방향 하향 [N]
    density = 1000.0

    delta_ana = timoshenko_cantilever_3d(P, L, W, H, E, nu)

    print(f"\n  문제: L={L}m, W={W}m, H={H}m, E={E:.0e}Pa, ν={nu}, P={P}N")
    print(f"  해석해 (Timoshenko): {delta_ana:.6e} m")
    print()
    print(f"  {'솔버':<6} {'해석해[m]':>14}  {'수치해[m]':>14}  {'오차':>7}  등급")
    print(f"  {'-'*6} {'-'*14}  {'-'*14}  {'-'*7}  {'-'*6}")

    results = {}

    # --- FEM (HEX8) ---
    delta, conv, iters, elapsed = solve_cantilever_3d(
        Method.FEM, E, nu, L, W, H, P, density, nx=20, ny=4, nz=4)
    err = print_solver_row("FEM", delta_ana, delta)
    results["FEM"] = {"delta": delta, "analytical": delta_ana, "error": err,
                      "converged": conv, "time": elapsed}

    # --- PD ---
    delta, conv, iters, elapsed = solve_cantilever_3d(
        Method.PD, E, nu, L, W, H, P, density, nx=21, ny=5, nz=5,
        damping=0.1, max_iterations=80000, tol=1e-4)
    err = print_solver_row("PD", delta_ana, delta)
    results["PD"] = {"delta": delta, "analytical": delta_ana, "error": err,
                     "converged": conv, "time": elapsed}

    # --- SPG ---
    delta, conv, iters, elapsed = solve_cantilever_3d(
        Method.SPG, E, nu, L, W, H, P, density, nx=21, ny=5, nz=5,
        stabilization=0.01, viscous_damping=0.01, max_iterations=150000, tol=1e-3)
    err = print_solver_row("SPG", delta_ana, delta)
    results["SPG"] = {"delta": delta, "analytical": delta_ana, "error": err,
                      "converged": conv, "time": elapsed}

    print()
    for name in ["FEM", "PD", "SPG"]:
        r = results[name]
        conv_str = "수렴" if r["converged"] else "미수렴"
        print(f"  {name}: {r['time']:.1f}초 ({conv_str})")

    return results


# =============================================================================
#  A-3: 2D 외팔보 격자 수렴성
# =============================================================================

def benchmark_cantilever_convergence_2d():
    """A-3: 2D 외팔보 격자 수렴성 분석."""
    print_header("A-3: 2D 외팔보 격자 수렴성")

    E, nu = 1e4, 0.3
    L, H = 1.0, 0.2
    P = -1.0
    density = 1000.0

    # 해석해
    delta_fem_ana = timoshenko_cantilever_2d(P, L, H, E, nu, plane_stress=True)
    delta_pd_ana = timoshenko_cantilever_2d(P, L, H, E, nu, plane_stress=False)

    # FEM 메쉬 레벨 (nx, ny) — H/L 비율 유지
    fem_levels = [(10, 2), (20, 4), (40, 8), (60, 12), (80, 16)]
    # PD/SPG 입자 레벨
    pd_levels = [(11, 3), (21, 5), (31, 7), (41, 9), (51, 11)]

    results = {"FEM": [], "PD": [], "SPG": []}

    # --- FEM 수렴성 ---
    print(f"\n  FEM (QUAD4, 평면응력):")
    print(f"  {'레벨':>4}  {'nx×ny':>8}  {'h':>10}  {'수치해':>14}  {'오차':>7}")

    for nx, ny in fem_levels:
        h = L / nx
        delta, conv, _, elapsed = solve_cantilever_2d(
            Method.FEM, E, nu, L, H, P, density, nx=nx, ny=ny)
        err = compute_error(delta_fem_ana, delta)
        print(f"  {nx:>4}  {nx}×{ny:<3}  {h:>10.4f}  {delta:>14.6e}  {err:>6.2f}%")
        results["FEM"].append((h, err))

    # --- PD 수렴성 ---
    print(f"\n  PD (NOSB, 평면변형):")
    print(f"  {'레벨':>4}  {'nx×ny':>8}  {'h':>10}  {'수치해':>14}  {'오차':>7}")

    for nx, ny in pd_levels:
        spacing = L / (nx - 1) if nx > 1 else L
        # PD 반복 횟수를 입자 수에 비례하여 조절
        n_particles = nx * ny
        max_iter = min(80000, max(20000, n_particles * 100))
        delta, conv, _, elapsed = solve_cantilever_2d(
            Method.PD, E, nu, L, H, P, density, nx=nx, ny=ny,
            damping=0.1, max_iterations=max_iter, tol=1e-4)
        err = compute_error(delta_pd_ana, delta)
        conv_mark = "" if conv else " *"
        print(f"  {nx:>4}  {nx}×{ny:<3}  {spacing:>10.4f}  {delta:>14.6e}  {err:>6.2f}%{conv_mark}")
        results["PD"].append((spacing, err))

    # --- SPG 수렴성 ---
    print(f"\n  SPG (평면변형):")
    print(f"  {'레벨':>4}  {'nx×ny':>8}  {'h':>10}  {'수치해':>14}  {'오차':>7}")

    for nx, ny in pd_levels:
        spacing = L / (nx - 1) if nx > 1 else L
        n_particles = nx * ny
        max_iter = min(150000, max(30000, n_particles * 200))
        delta, conv, _, elapsed = solve_cantilever_2d(
            Method.SPG, E, nu, L, H, P, density, nx=nx, ny=ny,
            stabilization=0.01, viscous_damping=0.01,
            max_iterations=max_iter, tol=1e-3)
        err = compute_error(delta_pd_ana, delta)
        conv_mark = "" if conv else " *"
        print(f"  {nx:>4}  {nx}×{ny:<3}  {spacing:>10.4f}  {delta:>14.6e}  {err:>6.2f}%{conv_mark}")
        results["SPG"].append((spacing, err))

    # 수렴율 계산
    print(f"\n  수렴율 (log-log 기울기):")
    convergence_rates = {}
    for name in ["FEM", "PD", "SPG"]:
        data = results[name]
        if len(data) >= 2:
            # 마지막 두 레벨로 수렴율 계산
            h1, e1 = data[-2]
            h2, e2 = data[-1]
            if e1 > 1e-10 and e2 > 1e-10 and h1 != h2:
                rate = math.log(e1 / e2) / math.log(h1 / h2)
            else:
                rate = float("nan")
        else:
            rate = float("nan")
        convergence_rates[name] = rate
        print(f"  {name:<6} rate = {rate:.2f}")

    print(f"\n  * = 미수렴 (최대 반복 도달)")

    return results, convergence_rates


# =============================================================================
#  B-1: 3D 실린더 압축
# =============================================================================

def benchmark_cylinder_compression():
    """B-1: 3D 실린더 단축 압축."""
    print_header("B-1: 3D 실린더 압축 (Cylinder Compression)")

    R = 0.25       # 반지름 [m]
    L = 1.0        # 높이 (z축) [m]
    E = 1e6        # 영 계수 [Pa]
    nu = 0.3       # 푸아송 비
    sigma = -1000.0  # 압축 응력 [Pa]
    density = 1000.0

    A_cyl = math.pi * R**2  # 원형 단면적

    # 해석해 (상하한)
    u_free, u_constrained = cylinder_compression_analytical(sigma, L, E, nu)

    print(f"\n  문제: R={R}m, L={L}m, E={E:.0e}Pa, ν={nu}, σ={sigma:.0f}Pa")
    print(f"  단면적: A = πR² = {A_cyl:.6f} m²")
    print(f"  해석해 (자유 측면):   u = {u_free:.6e} m")
    print(f"  해석해 (완전 구속):   u = {u_constrained:.6e} m")
    print()
    print(f"  {'솔버':<6} {'해석해 범위[m]':>28}  {'수치해[m]':>12}  범위  (자유 대비 오차)")
    print(f"  {'-'*6} {'-'*28}  {'-'*12}  {'-'*4}  {'-'*16}")

    results = {}

    # --- FEM: 동일 면적 정사각 단면 직육면체 ---
    side = math.sqrt(A_cyl)  # √(πR²) ≈ 0.443m
    fem_nz = 20
    fem_nxy = 10
    domain = create_domain(Method.FEM, dim=3, origin=(0, 0, 0),
                           size=(side, side, L), n_divisions=(fem_nxy, fem_nxy, fem_nz))

    bottom = domain.select(axis=2, value=0.0)
    top = domain.select(axis=2, value=L)
    domain.set_fixed(bottom)

    # 상단에 균등 압축력 (총력 = σ × A)
    total_force = sigma * A_cyl
    force_per_node = total_force / len(top)
    domain.set_force(top, [0.0, 0.0, force_per_node])

    mat = Material(E=E, nu=nu, density=density, dim=3)
    solver = Solver(domain, mat)
    t0 = time.time()
    result = solver.solve()
    elapsed_fem = time.time() - t0
    u = solver.get_displacements()
    delta_fem = np.mean(u[top, 2])

    in_range, err = print_range_row("FEM", u_free, u_constrained, delta_fem)
    results["FEM"] = {"delta": delta_fem, "in_range": in_range, "error": err,
                      "converged": result.converged, "time": elapsed_fem}

    # --- PD: 직육면체 + 원형 마스킹 ---
    D = 2.0 * R
    pd_nx = pd_ny = 11
    pd_nz = 21
    domain = create_domain(Method.PD, dim=3, origin=(0, 0, 0),
                           size=(D, D, L), n_divisions=(pd_nx, pd_ny, pd_nz))

    positions = domain.get_positions()
    cx, cy = D / 2.0, D / 2.0

    # 원형 단면 필터링
    dx = positions[:, 0] - cx
    dy = positions[:, 1] - cy
    dist_sq = dx**2 + dy**2
    in_cylinder = dist_sq <= R**2

    # 원 밖 입자 인덱스
    outside = np.where(~in_cylinder)[0]
    inside = np.where(in_cylinder)[0]

    # 간격 계산 (tol용)
    spacing_z = L / (pd_nz - 1)
    tol_z = spacing_z * 0.3

    # 원 안쪽 바닥 입자
    bottom_inside = inside[np.abs(positions[inside, 2]) < tol_z]
    # 원 안쪽 상단 입자
    top_inside = inside[np.abs(positions[inside, 2] - L) < tol_z]

    # 바깥 입자 + 바닥 입자 고정
    all_fixed = np.unique(np.concatenate([outside, bottom_inside]))
    domain.set_fixed(all_fixed)

    # 상단 내부 입자에 압축력
    force_per_p = total_force / len(top_inside)
    domain.set_force(top_inside, [0.0, 0.0, force_per_p])

    mat = Material(E=E, nu=nu, density=density, dim=3)
    solver = Solver(domain, mat, damping=0.1, max_iterations=80000, tol=1e-4)
    t0 = time.time()
    result = solver.solve()
    elapsed_pd = time.time() - t0
    u = solver.get_displacements()
    delta_pd = np.mean(u[top_inside, 2])

    in_range, err = print_range_row("PD", u_free, u_constrained, delta_pd)
    results["PD"] = {"delta": delta_pd, "in_range": in_range, "error": err,
                     "converged": result.converged, "time": elapsed_pd}

    # --- SPG: 동일 원형 마스킹 ---
    domain = create_domain(Method.SPG, dim=3, origin=(0, 0, 0),
                           size=(D, D, L), n_divisions=(pd_nx, pd_ny, pd_nz))

    positions = domain.get_positions()
    dx = positions[:, 0] - cx
    dy = positions[:, 1] - cy
    dist_sq = dx**2 + dy**2
    in_cylinder = dist_sq <= R**2

    outside = np.where(~in_cylinder)[0]
    inside = np.where(in_cylinder)[0]
    bottom_inside = inside[np.abs(positions[inside, 2]) < tol_z]
    top_inside = inside[np.abs(positions[inside, 2] - L) < tol_z]

    all_fixed = np.unique(np.concatenate([outside, bottom_inside]))
    domain.set_fixed(all_fixed)

    force_per_p = total_force / len(top_inside)
    domain.set_force(top_inside, [0.0, 0.0, force_per_p])

    mat = Material(E=E, nu=nu, density=density, dim=3)
    solver = Solver(domain, mat, stabilization=0.01, viscous_damping=0.01,
                    max_iterations=150000, tol=1e-3)
    t0 = time.time()
    result = solver.solve()
    elapsed_spg = time.time() - t0
    u = solver.get_displacements()
    delta_spg = np.mean(u[top_inside, 2])

    in_range, err = print_range_row("SPG", u_free, u_constrained, delta_spg)
    results["SPG"] = {"delta": delta_spg, "in_range": in_range, "error": err,
                      "converged": result.converged, "time": elapsed_spg}

    print()
    for name in ["FEM", "PD", "SPG"]:
        r = results[name]
        conv_str = "수렴" if r["converged"] else "미수렴"
        print(f"  {name}: {r['time']:.1f}초 ({conv_str})")

    return results


# =============================================================================
#  최종 요약
# =============================================================================

def print_final_summary(all_results):
    """최종 요약 테이블 출력."""
    print(f"\n{'#' * 70}")
    print(f"  최종 요약: 솔버별 오차 비교")
    print(f"{'#' * 70}")

    print(f"\n  {'문제':<20}  {'FEM':>10}  {'PD':>10}  {'SPG':>10}")
    print(f"  {'-'*20}  {'-'*10}  {'-'*10}  {'-'*10}")

    # A-1: 2D 외팔보
    if "A-1" in all_results:
        r = all_results["A-1"]
        fem_err = f"{r['FEM']['error']:.1f}%" if "FEM" in r else "N/A"
        pd_err = f"{r['PD']['error']:.1f}%" if "PD" in r else "N/A"
        spg_err = f"{r['SPG']['error']:.1f}%" if "SPG" in r else "N/A"
        print(f"  {'A-1: 2D 외팔보':<20}  {fem_err:>10}  {pd_err:>10}  {spg_err:>10}")

    # A-2: 3D 외팔보
    if "A-2" in all_results:
        r = all_results["A-2"]
        fem_err = f"{r['FEM']['error']:.1f}%" if "FEM" in r else "N/A"
        pd_err = f"{r['PD']['error']:.1f}%" if "PD" in r else "N/A"
        spg_err = f"{r['SPG']['error']:.1f}%" if "SPG" in r else "N/A"
        print(f"  {'A-2: 3D 외팔보':<20}  {fem_err:>10}  {pd_err:>10}  {spg_err:>10}")

    # A-3: 수렴율
    if "A-3" in all_results:
        _, rates = all_results["A-3"]
        fem_rate = f"{rates.get('FEM', float('nan')):.2f}"
        pd_rate = f"{rates.get('PD', float('nan')):.2f}"
        spg_rate = f"{rates.get('SPG', float('nan')):.2f}"
        print(f"  {'A-3: 수렴율':<20}  {fem_rate:>10}  {pd_rate:>10}  {spg_rate:>10}")

    # B-1: 실린더
    if "B-1" in all_results:
        r = all_results["B-1"]
        def fmt_cyl(name):
            if name in r:
                mark = "범위내" if r[name]["in_range"] else "범위외"
                return f"{mark}({r[name]['error']:.1f}%)"
            return "N/A"
        print(f"  {'B-1: 실린더 압축':<20}  {fmt_cyl('FEM'):>10}  {fmt_cyl('PD'):>10}  {fmt_cyl('SPG'):>10}")

    # 솔버별 평가
    print()
    for name in ["FEM", "PD", "SPG"]:
        errors = []
        for key in ["A-1", "A-2"]:
            if key in all_results and name in all_results[key]:
                errors.append(all_results[key][name]["error"])
        if errors:
            avg_err = np.mean(errors)
            grade = grade_error(avg_err)
            print(f"  {name} 평균 오차: {avg_err:.1f}% ({grade})")


# =============================================================================
#  메인 실행
# =============================================================================

def main():
    """전체 벤치마크 실행."""
    # 프레임워크 초기화 (Taichi, F64 정밀도)
    init()

    print()
    print("#" * 70)
    print("  통합 FEA 검증 벤치마크")
    print("  FEM / NOSB-PD / SPG 해석해 비교")
    print("#" * 70)

    t_total = time.time()
    all_results = {}

    # --- Part A: 외팔보 ---
    try:
        all_results["A-1"] = benchmark_cantilever_2d()
    except Exception as e:
        print(f"\n  [A-1 오류] {e}")
        import traceback
        traceback.print_exc()

    try:
        all_results["A-2"] = benchmark_cantilever_3d()
    except Exception as e:
        print(f"\n  [A-2 오류] {e}")
        import traceback
        traceback.print_exc()

    try:
        all_results["A-3"] = benchmark_cantilever_convergence_2d()
    except Exception as e:
        print(f"\n  [A-3 오류] {e}")
        import traceback
        traceback.print_exc()

    # --- Part B: 실린더 압축 ---
    try:
        all_results["B-1"] = benchmark_cylinder_compression()
    except Exception as e:
        print(f"\n  [B-1 오류] {e}")
        import traceback
        traceback.print_exc()

    # --- 최종 요약 ---
    print_final_summary(all_results)

    elapsed_total = time.time() - t_total
    print(f"\n  총 실행 시간: {elapsed_total:.1f}초")
    print()


if __name__ == "__main__":
    main()
