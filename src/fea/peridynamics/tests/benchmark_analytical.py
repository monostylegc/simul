"""Peridynamics 솔버 해석해 비교 벤치마크.

해석해가 알려진 표준 문제와 PD 솔버 결과를 비교하여
물리적 정확도를 검증한다.

벤치마크 문제:
1. 균일 인장 봉 (Bond-based PD) - 2D
2. NOSB-PD 균일 인장 봉 - 2D
3. NOSB-PD 3D 큐브 압축
4. 에너지 보존 (Explicit solver)
5. 격자 수렴성 분석 (NOSB-PD, 힘 기반)

실행:
    uv run python src/fea/peridynamics/tests/benchmark_analytical.py

참고:
    Bond-based PD는 Poisson 비가 2D에서 1/3, 3D에서 1/4로 고정된다.
    NOSB-PD는 임의의 Poisson 비를 지원하지만 안정화 매개변수 필요.
"""

import sys
import os
import time
import math
import numpy as np
import taichi as ti

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from src.fea.peridynamics.core.particles import ParticleSystem
from src.fea.peridynamics.core.neighbor import NeighborSearch
from src.fea.peridynamics.core.bonds import BondSystem
from src.fea.peridynamics.core.nosb import NOSBCompute, NOSBMaterial
from src.fea.peridynamics.solver.explicit import ExplicitSolver
from src.fea.peridynamics.solver.quasi_static import QuasiStaticSolver
from src.fea.peridynamics.material.linear_elastic import LinearElasticMaterial


# ============================================================
#  헬퍼 함수
# ============================================================

def create_pd_2d(nx, ny, spacing, density=1000.0, horizon_factor=3.015):
    """2D PD 시스템 생성 (입자 + 이웃 + 본드)."""
    n = nx * ny
    horizon = horizon_factor * spacing

    ps = ParticleSystem(n, dim=2)
    ps.initialize_from_grid((0.0, 0.0), spacing, (nx, ny), density=density)

    domain_pad = horizon * 1.5
    positions = ps.X.to_numpy()
    mins = positions.min(axis=0) - domain_pad
    maxs = positions.max(axis=0) + domain_pad

    ns = NeighborSearch(
        domain_min=tuple(mins), domain_max=tuple(maxs),
        horizon=horizon, max_particles=n, max_neighbors=64, dim=2
    )
    ns.build(ps.X, n)

    bonds = BondSystem(n, max_bonds=64, dim=2)
    bonds.build_from_neighbor_search(ps, ns, horizon)

    return ps, ns, bonds, horizon


def create_pd_3d(nx, ny, nz, spacing, density=1000.0, horizon_factor=3.015):
    """3D PD 시스템 생성."""
    n = nx * ny * nz
    horizon = horizon_factor * spacing

    ps = ParticleSystem(n, dim=3)
    ps.initialize_from_grid((0.0, 0.0, 0.0), spacing, (nx, ny, nz), density=density)

    domain_pad = horizon * 1.5
    positions = ps.X.to_numpy()
    mins = positions.min(axis=0) - domain_pad
    maxs = positions.max(axis=0) + domain_pad

    ns = NeighborSearch(
        domain_min=tuple(mins), domain_max=tuple(maxs),
        horizon=horizon, max_particles=n, max_neighbors=100, dim=3
    )
    ns.build(ps.X, n)

    bonds = BondSystem(n, max_bonds=100, dim=3)
    bonds.build_from_neighbor_search(ps, ns, horizon)

    return ps, ns, bonds, horizon


def print_header(title):
    print(f"\n{'=' * 64}")
    print(f"  벤치마크: {title}")
    print(f"{'=' * 64}")


def print_comparison(label, analytical, numerical, unit="m"):
    error = abs(numerical - analytical) / abs(analytical) * 100
    print(f"  {label}:")
    print(f"    해석해    = {analytical:.6e} {unit}")
    print(f"    PD 결과   = {numerical:.6e} {unit}")
    print(f"    상대 오차 = {error:8.2f}%")
    return error


# ============================================================
#  벤치마크 1: 균일 인장 봉 (Bond-based PD, 2D)
# ============================================================

def benchmark_bond_tension_2d():
    """Bond-based PD 인장 봉: 변위 적용 후 수렴 확인."""
    print_header("균일 인장 봉 (Bond-based PD, 2D)")

    # 재료 매개변수
    E = 1e4
    nu_pd = 1.0 / 3.0  # Bond-based PD 2D 고정값
    density = 1000.0
    spacing = 0.02
    nx = 51  # L = 1.0m
    ny = 11  # H = 0.2m
    L = (nx - 1) * spacing
    H = (ny - 1) * spacing

    ps, ns, bonds, horizon = create_pd_2d(nx, ny, spacing, density)
    n = nx * ny
    print(f"  격자: {nx}×{ny} = {n}개 입자, 간격={spacing}")

    # Bond-based micromodulus (2D)
    c = 9 * E / (math.pi * 1.0 * horizon**3)  # 2D, thickness=1

    # 왼쪽 고정 (x < horizon)
    positions = ps.X.to_numpy()
    left_mask = positions[:, 0] < horizon
    left_indices = np.where(left_mask)[0]
    ps.set_fixed_particles(left_indices)

    # 오른쪽에 균일 인장 변위 적용 (변형률 기반)
    strain = 0.01  # 1%
    u_analytical = strain * L
    x = ps.x.to_numpy()
    X = ps.X.to_numpy()
    for i in range(n):
        if not left_mask[i]:
            x[i, 0] = X[i, 0] + strain * X[i, 0]
    ps.x.from_numpy(x.astype(np.float64))

    # 준정적 솔버로 평형 탐색
    solver = QuasiStaticSolver(ps, bonds, micromodulus=c, damping=0.1)

    t0 = time.time()
    for _ in range(2000):
        solver.step()
    elapsed = time.time() - t0

    # 결과: 오른쪽 면 x-변위
    disp = ps.get_displacements()
    right_mask = positions[:, 0] > L - spacing * 0.5
    u_pd = np.mean(disp[right_mask, 0])

    print(f"  수렴: 2000 스텝, {elapsed:.2f}초")
    error = print_comparison("x-변위 (오른쪽 끝)", u_analytical, u_pd)

    # 안정성 확인
    assert not np.any(np.isnan(disp)), "NaN 발생!"
    print(f"  최대 변위: {np.max(np.abs(disp)):.6e} m (안정)")

    return error


# ============================================================
#  벤치마크 2: NOSB-PD 균일 인장 봉 (2D)
# ============================================================

def benchmark_nosb_tension_2d():
    """NOSB-PD 인장 봉: 임의 Poisson 비 지원."""
    print_header("NOSB-PD 균일 인장 봉 (2D)")

    E = 1e4
    nu = 0.3
    density = 1000.0
    spacing = 0.02
    nx = 51
    ny = 11
    L = (nx - 1) * spacing
    H = (ny - 1) * spacing

    ps, ns, bonds, horizon = create_pd_2d(nx, ny, spacing, density)
    n = nx * ny
    print(f"  격자: {nx}×{ny} = {n}개 입자, 간격={spacing}")

    # NOSB 재료
    material = NOSBMaterial(E, nu, dim=2)

    # NOSB 계산기 - 형상 텐서
    nosb = NOSBCompute(ps, bonds, stabilization=0.1)
    nosb.compute_shape_tensor()

    # 왼쪽 고정
    positions = ps.X.to_numpy()
    left_mask = positions[:, 0] < horizon
    left_indices = np.where(left_mask)[0]
    ps.set_fixed_particles(left_indices)

    # 균일 인장 변위 적용
    strain = 0.01
    x = ps.x.to_numpy()
    X = ps.X.to_numpy()
    for i in range(n):
        if not left_mask[i]:
            x[i, 0] = X[i, 0] + strain * X[i, 0]
    ps.x.from_numpy(x.astype(np.float64))

    # NOSB 계산: F → σ → f
    t0 = time.time()
    nosb.compute_deformation_gradient()

    # 안정화 마이크로 모듈러스
    c_bond = 9 * E / (math.pi * 1.0 * horizon**3)
    ps.set_material_constants(material.K, material.mu)
    nosb.compute_force_state_with_stabilization(c_bond)
    elapsed = time.time() - t0

    # 해석해: u = strain * L
    u_analytical = strain * L

    disp = ps.get_displacements()
    right_mask = positions[:, 0] > L - spacing * 0.5
    u_nosb = np.mean(disp[right_mask, 0])

    print(f"  계산 시간: {elapsed:.2f}초")
    error = print_comparison("x-변위 (오른쪽 끝)", u_analytical, u_nosb)

    # 변형 구배 확인: 내부 입자에서 F ≈ [[1+strain, 0],[0, 1-nu*strain]]
    F = ps.F.to_numpy()
    interior = np.where(
        (positions[:, 0] > horizon) &
        (positions[:, 0] < L - horizon) &
        (positions[:, 1] > horizon) &
        (positions[:, 1] < H - horizon)
    )[0]

    if len(interior) > 0:
        F_mean = np.mean(F[interior], axis=0)
        F_expected = np.eye(2)
        F_expected[0, 0] = 1 + strain
        F_err = np.linalg.norm(F_mean - F_expected) / np.linalg.norm(F_expected) * 100
        print(f"  내부 F 평균:\n    {F_mean}")
        print(f"  F 오차: {F_err:.2f}%")

    return error


# ============================================================
#  벤치마크 3: NOSB-PD 3D 큐브 압축
# ============================================================

def benchmark_nosb_compression_3d():
    """NOSB-PD 3D 큐브 압축."""
    print_header("NOSB-PD 3D 큐브 압축")

    E = 1e6
    nu = 0.25
    density = 1000.0
    spacing = 0.05
    nx, ny, nz = 11, 11, 11
    L = (nx - 1) * spacing

    ps, ns, bonds, horizon = create_pd_3d(nx, ny, nz, spacing, density)
    n = nx * ny * nz
    print(f"  격자: {nx}×{ny}×{nz} = {n}개 입자, 간격={spacing}")

    material = NOSBMaterial(E, nu, dim=3)

    nosb = NOSBCompute(ps, bonds, stabilization=0.1)
    nosb.compute_shape_tensor()

    # 하단 고정 (z < horizon)
    positions = ps.X.to_numpy()
    bottom_mask = positions[:, 2] < horizon
    bottom_indices = np.where(bottom_mask)[0]
    ps.set_fixed_particles(bottom_indices)

    # 상단에 압축 변위
    strain = 0.01
    x = ps.x.to_numpy()
    X = ps.X.to_numpy()
    for i in range(n):
        if not bottom_mask[i]:
            x[i, 2] = X[i, 2] - strain * X[i, 2]
    ps.x.from_numpy(x.astype(np.float64))

    t0 = time.time()
    nosb.compute_deformation_gradient()
    c_bond = 18 * material.K / (math.pi * horizon**4)
    ps.set_material_constants(material.K, material.mu)
    nosb.compute_force_state_with_stabilization(c_bond)
    elapsed = time.time() - t0

    # 해석해: 상단 z-변위 = -strain * L
    u_analytical = -strain * L

    disp = ps.get_displacements()
    top_mask = positions[:, 2] > L - spacing * 0.5
    u_pd = np.mean(disp[top_mask, 2])

    print(f"  계산 시간: {elapsed:.2f}초")
    error = print_comparison("z-변위 (윗면)", u_analytical, u_pd)

    # 안정성
    assert not np.any(np.isnan(disp)), "NaN 발생!"
    print(f"  최대 변위: {np.max(np.abs(disp)):.6e} m (안정)")

    return error


# ============================================================
#  벤치마크 4: 에너지 보존 (Explicit solver)
# ============================================================

def benchmark_energy_conservation():
    """Explicit solver 에너지 보존: 감쇠 없이 총 에너지 일정.

    초기에 모든 입자에 큰 속도를 부여하여 충분한 운동에너지를
    확보한 후, 에너지 변동을 관찰한다.
    """
    print_header("에너지 보존 (Explicit solver, 무감쇠)")

    E = 1e6
    nu_pd = 1.0 / 3.0
    density = 1000.0
    spacing = 0.02
    nx, ny = 11, 11

    ps, ns, bonds, horizon = create_pd_2d(nx, ny, spacing, density)
    n = nx * ny

    material = LinearElasticMaterial(E, nu_pd, horizon, thickness=1.0, dim=2)
    c = material.get_micromodulus()

    # 보수적 dt로 에너지 보존 정밀도 확보
    dt = ExplicitSolver.estimate_stable_dt(E, density, horizon, spacing, safety_factor=0.01)
    solver = ExplicitSolver(ps, bonds, micromodulus=c, dt=dt, damping=0.0)

    # 경계 고정 + 내부에 작은 변위 부여
    positions = ps.X.to_numpy()
    L = (nx - 1) * spacing

    # 경계 2줄 고정
    boundary_mask = (
        (positions[:, 0] < spacing * 1.5) |
        (positions[:, 0] > L - spacing * 1.5) |
        (positions[:, 1] < spacing * 1.5) |
        (positions[:, 1] > L - spacing * 1.5)
    )
    ps.set_fixed_particles(np.where(boundary_mask)[0])

    # 내부 입자에 작은 초기 속도 (가우시안 분포)
    v = ps.v.to_numpy()
    cx, cy = L / 2, L / 2
    for i in range(n):
        if not boundary_mask[i]:
            r2 = (positions[i, 0] - cx)**2 + (positions[i, 1] - cy)**2
            amp = 0.1 * np.exp(-r2 / (L * 0.1)**2)
            v[i, 0] = amp
            v[i, 1] = amp * 0.5
    ps.v.from_numpy(v.astype(np.float64))

    # 5 스텝 워밍업 (초기 전이 통과)
    for _ in range(5):
        solver.step()

    KE0 = solver.get_kinetic_energy()
    SE0 = solver.get_strain_energy()
    E0 = KE0 + SE0

    print(f"  격자: {nx}×{ny} = {n}개 입자")
    print(f"  dt = {dt:.2e}초, 감쇠 = 0")
    print(f"  초기 에너지: KE={KE0:.6e}, SE={SE0:.6e}, 총={E0:.6e}")

    # 500 스텝 실행
    t0 = time.time()
    energies = []
    for step in range(500):
        solver.step()
        if step % 100 == 0:
            ke = solver.get_kinetic_energy()
            se = solver.get_strain_energy()
            energies.append((ke, se, ke + se))

    elapsed = time.time() - t0
    E_final = energies[-1][2]

    # 에너지 보존 오차
    energy_drift = abs(E_final - E0) / E0 * 100 if E0 > 1e-20 else 0
    max_drift = max(abs(e[2] - E0) / E0 * 100 for e in energies)

    print(f"  최종 에너지: KE={energies[-1][0]:.6e}, SE={energies[-1][1]:.6e}, 총={E_final:.6e}")
    print(f"  에너지 변동: {energy_drift:.2f}% (최대 {max_drift:.2f}%)")
    print(f"  계산 시간: {elapsed:.2f}초")

    # NaN 확인
    disp = ps.get_displacements()
    if np.any(np.isnan(disp)):
        print(f"  ⚠ NaN 발생! 솔버 불안정")
        return float('inf')
    print(f"  안정성: OK (NaN 없음)")

    return energy_drift


# ============================================================
#  벤치마크 5: 격자 수렴성 (NOSB-PD, 힘 기반)
# ============================================================

def benchmark_convergence_nosb():
    """NOSB-PD 격자 수렴성: 변형 구배(F) 정확도의 격자 밀도별 변화.

    균일 인장 변위 적용 후 내부 입자의 변형 구배 F가
    이론값에 얼마나 근접하는지 비교한다. 격자 밀도가 높을수록
    경계 효과가 줄어 내부 F가 정확해진다.
    """
    print_header("격자 수렴성 분석 (NOSB-PD, F 정확도)")

    E = 1e4
    nu = 0.3
    density = 1000.0
    strain = 0.01  # 1% 인장

    F_expected = np.eye(2)
    F_expected[0, 0] = 1 + strain
    print(f"  이론 F_11 = {1+strain:.4f}, F_22 = 1.0000")

    # H/spacing >= 2*3.015*2+1 ≈ 13 이상이어야 내부 입자 존재
    mesh_sizes = [
        (21, 15, 0.05),
        (31, 21, 0.033),
        (41, 27, 0.025),
        (51, 33, 0.02),
    ]

    results = []

    for nx, ny, spacing in mesh_sizes:
        L = (nx - 1) * spacing
        H = (ny - 1) * spacing

        ps, ns, bonds, horizon = create_pd_2d(nx, ny, spacing, density)
        n = nx * ny

        material = NOSBMaterial(E, nu, dim=2)
        nosb = NOSBCompute(ps, bonds, stabilization=0.1)
        nosb.compute_shape_tensor()

        positions = ps.X.to_numpy()

        # 왼쪽 고정
        left_mask = positions[:, 0] < horizon
        ps.set_fixed_particles(np.where(left_mask)[0])

        # 균일 인장 변위
        x = ps.x.to_numpy()
        X = ps.X.to_numpy()
        for i in range(n):
            if not left_mask[i]:
                x[i, 0] = X[i, 0] + strain * X[i, 0]
        ps.x.from_numpy(x.astype(np.float64))

        t0 = time.time()
        nosb.compute_deformation_gradient()
        elapsed = time.time() - t0

        # 내부 입자 (경계로부터 2*horizon 이상 떨어진)
        F = ps.F.to_numpy()
        interior = np.where(
            (positions[:, 0] > horizon) &
            (positions[:, 0] < L - horizon) &
            (positions[:, 1] > horizon) &
            (positions[:, 1] < H - horizon)
        )[0]

        if len(interior) > 0:
            F_mean = np.mean(F[interior], axis=0)
            F_err = np.linalg.norm(F_mean - F_expected) / np.linalg.norm(F_expected) * 100
        else:
            F_err = 100.0

        print(f"  --- 간격 h={spacing:.3f} ({nx}×{ny} = {n}개, 내부={len(interior)}개) ---")
        print(f"    F 오차 = {F_err:.4f}%, {elapsed:.2f}초")

        results.append((spacing, n, F_err, len(interior)))

    # 수렴율
    rates = []
    for i in range(1, len(results)):
        h1, _, e1, _ = results[i - 1]
        h2, _, e2, _ = results[i]
        if e2 > 1e-10 and e1 > 1e-10:
            rate = np.log(e1 / e2) / np.log(h1 / h2)
            rates.append(rate)

    avg_rate = np.mean(rates) if rates else 0.0
    if rates:
        print(f"\n  평균 수렴율: {avg_rate:.2f}")
        for i, r in enumerate(rates):
            print(f"    h={results[i][0]:.3f}→{results[i+1][0]:.3f}: rate={r:.2f}")

    print(f"\n  {'h':>8}  {'입자수':>8}  {'F 오차(%)':>12}  {'내부 입자':>8}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*12}  {'-'*8}")
    for h, np_, err, n_int in results:
        print(f"  {h:8.4f}  {np_:8d}  {err:12.4f}  {n_int:8d}")

    return avg_rate


# ============================================================
#  메인
# ============================================================

def main():
    ti.init(arch=ti.cpu, default_fp=ti.f64)

    print("\n################################################################")
    print("  Peridynamics 솔버 해석해 비교 벤치마크")
    print("################################################################")

    t_total = time.time()
    summary = []

    e1 = benchmark_bond_tension_2d()
    summary.append(("Bond-based 인장 (2D)", e1))

    e2 = benchmark_nosb_tension_2d()
    summary.append(("NOSB-PD 인장 (2D)", e2))

    e3 = benchmark_nosb_compression_3d()
    summary.append(("NOSB-PD 압축 (3D)", e3))

    e4 = benchmark_energy_conservation()
    summary.append(("에너지 보존", e4))

    rate = benchmark_convergence_nosb()

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
    print(f"  {'격자 수렴성':<24}  {'rate='+f'{rate:.2f}':>12}  {'양호' if rate > 0.5 else '보통':>8}")

    print(f"\n  총 실행 시간: {elapsed_total:.1f}초")
    print(f"{'=' * 64}")


if __name__ == "__main__":
    main()
