"""에너지 균형 검증 테스트.

FEM 해석 결과의 에너지 보존을 검증한다.

테스트 전략:
1. 선형 탄성: W_ext = U_int (정확한 에너지 균형)
2. 초탄성: 변형 에너지 양정치 + 균형
3. 호장법 경로: 증분 에너지 단조증가
4. 에너지 비율 E(λ)/λ² ≈ 상수 (선형)
5. 엣지 케이스: 무하중, 단일 요소
"""

import numpy as np
import pytest

import taichi as ti

try:
    ti.init(arch=ti.cpu, default_fp=ti.f64)
except RuntimeError:
    pass

from ..core.element import ElementType
from ..core.mesh import FEMesh
from ..material.linear_elastic import LinearElastic
from ..solver.static_solver import StaticSolver
from ..solver.energy_balance import (
    compute_external_work,
    compute_internal_energy,
    compute_internal_energy_from_forces,
    check_energy_balance,
    check_incremental_energy,
    EnergyReport,
)


# ──────────── 유틸리티 ────────────

def _solve_cantilever_2d(E=200e9, nu=0.3, F=-1e6, L=10.0, H=1.0, nx=4, ny=1):
    """2D 캔틸레버 해석 (선형 탄성).

    Returns:
        (mesh, material)
    """
    nodes = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            nodes.append([L * i / nx, H * j / ny])
    nodes = np.array(nodes, dtype=np.float64)

    elements = []
    for j in range(ny):
        for i in range(nx):
            n0 = j * (nx + 1) + i
            elements.append([n0, n0 + 1, n0 + 1 + (nx + 1), n0 + (nx + 1)])
    elements = np.array(elements, dtype=np.int32)

    mesh = FEMesh(len(nodes), len(elements), ElementType.QUAD4)
    mesh.initialize_from_numpy(nodes, elements)
    material = LinearElastic(E, nu, dim=2, plane_stress=False)

    left = np.where(np.abs(nodes[:, 0]) < 1e-10)[0]
    mesh.set_fixed_nodes(left)

    right = np.where(np.abs(nodes[:, 0] - L) < 1e-10)[0]
    force_per_node = F / len(right)
    f_ext = np.zeros((len(nodes), 2), dtype=np.float64)
    for node in right:
        f_ext[node, 1] = force_per_node
    mesh.f_ext.from_numpy(f_ext)

    solver = StaticSolver(mesh, material)
    solver.solve(verbose=False)

    return mesh, material


def _solve_cantilever_3d(E=200e9, nu=0.3, F=-1e6, L=4.0, H=1.0, W=1.0):
    """3D 캔틸레버 해석 (HEX8)."""
    nx, ny, nz = 2, 1, 1
    nodes = []
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                nodes.append([L * i / nx, H * j / ny, W * k / nz])
    nodes = np.array(nodes, dtype=np.float64)

    elements = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                n0 = k * (ny + 1) * (nx + 1) + j * (nx + 1) + i
                n1 = n0 + 1
                n2 = n1 + (nx + 1)
                n3 = n0 + (nx + 1)
                n4 = n0 + (ny + 1) * (nx + 1)
                n5 = n4 + 1
                n6 = n5 + (nx + 1)
                n7 = n4 + (nx + 1)
                elements.append([n0, n1, n2, n3, n4, n5, n6, n7])
    elements = np.array(elements, dtype=np.int32)

    mesh = FEMesh(len(nodes), len(elements), ElementType.HEX8)
    mesh.initialize_from_numpy(nodes, elements)
    material = LinearElastic(E, nu, dim=3)

    left = np.where(np.abs(nodes[:, 0]) < 1e-10)[0]
    mesh.set_fixed_nodes(left)

    right = np.where(np.abs(nodes[:, 0] - L) < 1e-10)[0]
    force_per_node = F / len(right)
    f_ext = np.zeros((len(nodes), 3), dtype=np.float64)
    for node in right:
        f_ext[node, 1] = force_per_node
    mesh.f_ext.from_numpy(f_ext)

    solver = StaticSolver(mesh, material)
    solver.solve(verbose=False)

    return mesh, material


# ──────────── 기본 테스트 ────────────

class TestEnergyComputation:
    """에너지 계산 함수 테스트."""

    def test_external_work_positive(self):
        """하중과 변위가 같은 방향이면 외부 일 > 0."""
        mesh, mat = _solve_cantilever_2d()
        W = compute_external_work(mesh)
        # 하중 아래로, 변위도 아래로 → W = u · f > 0
        assert W > 0, f"외부 일이 음수: {W:.4e}"

    def test_internal_energy_positive(self):
        """변형 에너지 항상 ≥ 0."""
        mesh, mat = _solve_cantilever_2d()
        U = compute_internal_energy(mesh)
        assert U > 0, f"내부 에너지가 음수: {U:.4e}"

    def test_energy_from_forces(self):
        """내부력 기반 에너지 ≈ 가우스 적분 에너지."""
        mesh, mat = _solve_cantilever_2d()
        U_gauss = compute_internal_energy(mesh)
        U_force = compute_internal_energy_from_forces(mesh)

        rel_diff = abs(U_gauss - U_force) / max(abs(U_gauss), 1e-30)
        assert rel_diff < 0.01, (
            f"가우스/내부력 에너지 불일치: {rel_diff:.4e} "
            f"(U_gauss={U_gauss:.4e}, U_force={U_force:.4e})"
        )

    def test_zero_displacement_zero_energy(self):
        """변위 없으면 에너지 = 0."""
        nodes = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
        elements = np.array([[0, 1, 2, 3]], dtype=np.int32)
        mesh = FEMesh(4, 1, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)

        # 변위 = 0, 응력/변형률 계산
        mesh.compute_deformation_gradient()
        mat = LinearElastic(1e6, 0.3, dim=2)
        mat.compute_stress(mesh)
        mat.compute_nodal_forces(mesh)

        W = compute_external_work(mesh)
        U = compute_internal_energy(mesh)

        assert abs(W) < 1e-20
        assert abs(U) < 1e-20


# ──────────── 에너지 균형 ────────────

class TestEnergyBalance:
    """에너지 균형 (W_ext = U_int) 검증."""

    def test_linear_elastic_2d_balance(self):
        """2D 선형 탄성 캔틸레버: W_ext ≈ U_int."""
        mesh, mat = _solve_cantilever_2d()
        report = check_energy_balance(mesh, mat, tol=0.02)

        assert report.is_balanced, (
            f"에너지 불균형: error={report.energy_error:.4e}, "
            f"W_ext={report.external_work:.4e}, U_int={report.internal_energy:.4e}"
        )
        assert report.is_positive_definite
        assert 0.98 < report.energy_ratio < 1.02

    def test_linear_elastic_3d_balance(self):
        """3D 선형 탄성 캔틸레버: W_ext ≈ U_int."""
        mesh, mat = _solve_cantilever_3d()
        report = check_energy_balance(mesh, mat, tol=0.02)

        assert report.is_balanced, (
            f"에너지 불균형: error={report.energy_error:.4e}"
        )
        assert report.is_positive_definite

    def test_energy_scales_with_force(self):
        """하중 2배 → 에너지 4배 (선형 탄성).

        W = ½ F u = ½ F (F/k) = F²/(2k)
        """
        mesh1, _ = _solve_cantilever_2d(F=-1e6)
        W1 = compute_external_work(mesh1)

        mesh2, _ = _solve_cantilever_2d(F=-2e6)
        W2 = compute_external_work(mesh2)

        ratio = W2 / W1
        assert abs(ratio - 4.0) < 0.1, (
            f"에너지 비율 {ratio:.2f} ≠ 4.0 (하중 2배 → 에너지 4배)"
        )

    def test_energy_scales_with_stiffness(self):
        """강성 2배 → 에너지 1/2 (같은 하중).

        W = F²/(2k). k ∝ E이므로 E 2배 → W 1/2.
        """
        mesh1, _ = _solve_cantilever_2d(E=100e9)
        W1 = compute_external_work(mesh1)

        mesh2, _ = _solve_cantilever_2d(E=200e9)
        W2 = compute_external_work(mesh2)

        ratio = W1 / W2
        assert abs(ratio - 2.0) < 0.15, (
            f"에너지 비율 {ratio:.2f} ≠ 2.0 (강성 2배 → 에너지 반감)"
        )

    def test_report_format(self):
        """EnergyReport 형식 확인."""
        mesh, mat = _solve_cantilever_2d()
        report = check_energy_balance(mesh, mat)

        assert isinstance(report, EnergyReport)
        assert hasattr(report, 'external_work')
        assert hasattr(report, 'internal_energy')
        assert hasattr(report, 'energy_ratio')
        assert hasattr(report, 'energy_error')
        assert hasattr(report, 'is_balanced')
        assert hasattr(report, 'is_positive_definite')
        assert isinstance(report.details, dict)


# ──────────── 호장법 에너지 경로 ────────────

class TestIncrementalEnergy:
    """증분 에너지 검증 (호장법 경로)."""

    def test_linear_incremental_energy(self):
        """선형 문제의 호장법 에너지: 증분 양수 + 단조증가."""
        from ..solver.arclength_solver import ArcLengthSolver

        # 2D 캔틸레버
        L, H, nx, ny = 10.0, 1.0, 4, 1
        nodes = []
        for j in range(ny + 1):
            for i in range(nx + 1):
                nodes.append([L * i / nx, H * j / ny])
        nodes = np.array(nodes, dtype=np.float64)

        elements = []
        for j in range(ny):
            for i in range(nx):
                n0 = j * (nx + 1) + i
                elements.append([n0, n0 + 1, n0 + 1 + (nx + 1), n0 + (nx + 1)])
        elements = np.array(elements, dtype=np.int32)

        mesh = FEMesh(len(nodes), len(elements), ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)
        material = LinearElastic(200e9, 0.3, dim=2, plane_stress=False)

        left = np.where(np.abs(nodes[:, 0]) < 1e-10)[0]
        mesh.set_fixed_nodes(left)
        right = np.where(np.abs(nodes[:, 0] - L) < 1e-10)[0]

        nn = len(nodes)
        f_ref = np.zeros(nn * 2)
        for n in right:
            f_ref[n * 2 + 1] = -1e6 / len(right)

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.3,
            max_steps=10,
            max_load_factor=1.0,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)

        assert result["converged"]

        # 증분 에너지 검증
        inc_result = check_incremental_energy(
            result["load_factors"],
            result["displacements"],
            f_ref,
        )

        assert inc_result["valid"], "증분 에너지에 음수 존재"
        assert inc_result["all_increments_positive"]

        # 총 에너지 양수
        assert inc_result["total_work_trapezoid"] > 0
        assert inc_result["total_work_endpoint"] > 0

    def test_incremental_energy_empty(self):
        """빈 경로: 단계 없음."""
        result = check_incremental_energy(
            [0.0], [np.zeros(10)], np.ones(10),
        )
        assert result["valid"]
        assert result["n_steps"] == 0


# ──────────── 초탄성 에너지 ────────────

class TestHyperelasticEnergy:
    """초탄성 재료의 에너지 검증."""

    def test_neo_hookean_energy_positive(self):
        """Neo-Hookean 변형 에너지 ≥ 0."""
        from ..material.neo_hookean import NeoHookean

        nodes = np.array([
            [0, 0], [1, 0], [1, 1], [0, 1],
        ], dtype=np.float64)
        elements = np.array([[0, 1, 2, 3]], dtype=np.int32)

        mesh = FEMesh(4, 1, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elements)
        material = NeoHookean(1e6, 0.3, dim=2)

        # 작은 변위 적용
        u = np.array([
            [0.0, 0.0], [0.01, -0.005],
            [0.01, -0.005], [0.0, 0.0],
        ], dtype=np.float64)
        mesh.u.from_numpy(u)
        mesh.compute_deformation_gradient()
        material.compute_stress(mesh)
        material.compute_nodal_forces(mesh)

        # NeoHookean은 mesh.strain을 채우지 않으므로 내부력 기반 사용
        U = compute_internal_energy_from_forces(mesh)
        assert U > 0, f"Neo-Hookean 에너지 음수: {U:.4e}"
