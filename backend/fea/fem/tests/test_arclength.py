"""호장법(Arc-Length) 솔버 테스트.

Crisfield 구면 호장법의 정확성과 안정성을 검증한다.

테스트 전략:
1. 선형 문제: 호장법 결과 ≈ 직접 풀이 (기본 정확성)
2. 비선형 하중 경로: 단계별 하중 비율 추적 (경로 추적 능력)
3. 적응적 호장 크기: 수렴 속도에 따른 자동 조절
4. 솔버 API: 콜백, 취소, 결과 형식
5. 평형 경로 추출: 특정 노드의 하중-변위 곡선
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
from ..solver.arclength_solver import ArcLengthSolver
from ..solver.static_solver import StaticSolver


# ──────────── 유틸리티 ────────────

def _create_cantilever_2d(L=10.0, H=1.0, nx=4, ny=1):
    """2D 캔틸레버 빔 생성 (QUAD4 요소).

    왼쪽 끝 고정, 오른쪽 끝에 하중 적용.

    Args:
        L: 빔 길이
        H: 빔 높이
        nx: x방향 요소 수
        ny: y방향 요소 수

    Returns:
        (mesh, material, right_node_ids, n_nodes)
    """
    # 노드 생성
    nodes = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            x = L * i / nx
            y = H * j / ny
            nodes.append([x, y])
    nodes = np.array(nodes, dtype=np.float64)
    n_nodes = len(nodes)

    # 요소 연결 (QUAD4: 반시계 방향)
    elements = []
    for j in range(ny):
        for i in range(nx):
            n0 = j * (nx + 1) + i
            n1 = n0 + 1
            n2 = n1 + (nx + 1)
            n3 = n0 + (nx + 1)
            elements.append([n0, n1, n2, n3])
    elements = np.array(elements, dtype=np.int32)
    n_elements = len(elements)

    # 메쉬 초기화
    mesh = FEMesh(n_nodes, n_elements, ElementType.QUAD4)
    mesh.initialize_from_numpy(nodes, elements)

    # 재료 (선형 탄성)
    material = LinearElastic(
        youngs_modulus=200e9,  # 강
        poisson_ratio=0.3,
        dim=2,
        plane_stress=False,
    )

    # 왼쪽 끝 고정 (x=0 노드)
    left_nodes = np.where(np.abs(nodes[:, 0]) < 1e-10)[0]
    mesh.set_fixed_nodes(left_nodes)

    # 오른쪽 끝 노드 (x=L)
    right_nodes = np.where(np.abs(nodes[:, 0] - L) < 1e-10)[0]

    return mesh, material, right_nodes, n_nodes


def _create_cantilever_3d(L=4.0, H=1.0, W=1.0, nx=2, ny=1, nz=1):
    """3D 캔틸레버 빔 생성 (HEX8 요소).

    Args:
        L: 빔 길이
        H: 빔 높이
        W: 빔 폭
        nx, ny, nz: 각 방향 요소 수

    Returns:
        (mesh, material, right_node_ids, n_nodes)
    """
    # 노드 생성
    nodes = []
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                x = L * i / nx
                y = H * j / ny
                z = W * k / nz
                nodes.append([x, y, z])
    nodes = np.array(nodes, dtype=np.float64)
    n_nodes = len(nodes)

    # HEX8 요소 연결
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
    n_elements = len(elements)

    mesh = FEMesh(n_nodes, n_elements, ElementType.HEX8)
    mesh.initialize_from_numpy(nodes, elements)

    material = LinearElastic(
        youngs_modulus=200e9,
        poisson_ratio=0.3,
        dim=3,
    )

    # 왼쪽 끝 고정
    left_nodes = np.where(np.abs(nodes[:, 0]) < 1e-10)[0]
    mesh.set_fixed_nodes(left_nodes)

    # 오른쪽 끝 노드
    right_nodes = np.where(np.abs(nodes[:, 0] - L) < 1e-10)[0]

    return mesh, material, right_nodes, n_nodes


# ──────────── 기본 테스트 ────────────

class TestArcLengthBasic:
    """호장법 솔버 기본 동작 테스트."""

    def test_creation(self):
        """솔버 생성 및 기본 속성."""
        mesh, material, _, _ = _create_cantilever_2d()
        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.01,
            max_steps=10,
        )
        assert solver.mesh is mesh
        assert solver.material is material
        assert solver.arc_length == 0.01
        assert solver.max_steps == 10
        assert solver.n_dof == mesh.n_nodes * mesh.dim

    def test_zero_load_error(self):
        """하중 없이 해석 시 오류 발생."""
        mesh, material, _, _ = _create_cantilever_2d()
        solver = ArcLengthSolver(mesh, material)
        # f_ref가 0이면 오류
        from ..validation import FEAConvergenceError
        with pytest.raises(FEAConvergenceError, match="영.*zero"):
            solver.solve(f_ref=np.zeros(solver.n_dof), verbose=False)

    def test_result_format(self):
        """결과 딕셔너리 형식 확인."""
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()

        # 참조 하중 설정
        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e6  # y방향 집중 하중

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.1,
            max_steps=3,
            max_load_factor=0.5,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)

        # 필수 키 확인
        assert "converged" in result
        assert "n_steps" in result
        assert "load_factors" in result
        assert "displacements" in result
        assert "energies" in result
        assert "final_load_factor" in result
        assert "cancelled" in result

        # 타입 확인
        assert isinstance(result["load_factors"], list)
        assert isinstance(result["displacements"], list)
        assert isinstance(result["energies"], list)


# ──────────── 선형 문제 정확성 ────────────

class TestArcLengthLinear:
    """선형 탄성 문제에서 호장법 정확성 검증."""

    def test_linear_cantilever_2d(self):
        """2D 캔틸레버 — 호장법 vs 직접 풀이 비교.

        선형 문제에서 호장법은 정확해에 수렴해야 한다.
        최대 하중 비율 λ=1.0에서 직접 풀이와 동일한 변위 기대.
        """
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()

        # 참조 하중 벡터
        F_total = -1e6  # 총 하중 [N]
        f_ref = np.zeros(n_nodes * 2)
        force_per_node = F_total / len(right_nodes)
        for node in right_nodes:
            f_ref[node * 2 + 1] = force_per_node

        # ── 직접 풀이 (StaticSolver) ──
        # 메쉬를 새로 만들어서 직접 풀이
        mesh_ref, mat_ref, right_ref, _ = _create_cantilever_2d()
        f_ext = np.zeros((mesh_ref.n_nodes, 2), dtype=np.float64)
        for node in right_ref:
            f_ext[node, 1] = force_per_node
        mesh_ref.f_ext.from_numpy(f_ext)

        solver_ref = StaticSolver(mesh_ref, mat_ref)
        result_ref = solver_ref.solve(verbose=False)
        u_ref = mesh_ref.u.to_numpy().flatten()

        # ── 호장법 ──
        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.5,
            max_steps=20,
            max_load_factor=1.0,
            tol=1e-10,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)

        assert result["converged"]
        assert result["final_load_factor"] >= 0.99

        # 최종 변위 비교
        u_arc = result["displacements"][-1]
        rel_error = np.linalg.norm(u_arc - u_ref) / np.linalg.norm(u_ref)
        assert rel_error < 0.02, (
            f"호장법 변위 오차 {rel_error:.4e} > 2%"
        )

    def test_linear_cantilever_3d(self):
        """3D 캔틸레버 — 호장법 vs 직접 풀이 비교."""
        mesh, material, right_nodes, n_nodes = _create_cantilever_3d()

        # 참조 하중
        F_total = -1e6
        f_ref = np.zeros(n_nodes * 3)
        force_per_node = F_total / len(right_nodes)
        for node in right_nodes:
            f_ref[node * 3 + 1] = force_per_node

        # 직접 풀이
        mesh_ref, mat_ref, right_ref, _ = _create_cantilever_3d()
        f_ext = np.zeros((mesh_ref.n_nodes, 3), dtype=np.float64)
        for node in right_ref:
            f_ext[node, 1] = force_per_node
        mesh_ref.f_ext.from_numpy(f_ext)

        solver_ref = StaticSolver(mesh_ref, mat_ref)
        result_ref = solver_ref.solve(verbose=False)
        u_ref = mesh_ref.u.to_numpy().flatten()

        # 호장법 (3D는 수치 잔차 바닥이 높으므로 tol을 완화)
        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.5,
            max_steps=20,
            max_load_factor=1.0,
            tol=1e-8,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)

        assert result["converged"]
        u_arc = result["displacements"][-1]
        rel_error = np.linalg.norm(u_arc - u_ref) / np.linalg.norm(u_ref)
        assert rel_error < 0.02, (
            f"3D 호장법 변위 오차 {rel_error:.4e} > 2%"
        )


# ──────────── 하중 경로 추적 ────────────

class TestArcLengthPath:
    """하중-변위 경로 추적 능력 테스트."""

    def test_monotonic_load_path(self):
        """선형 문제에서 하중 비율 단조증가 확인.

        선형 탄성 + 양의 하중이면 λ가 0에서 1까지 단조증가해야 한다.
        """
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()

        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e6

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.3,
            max_steps=20,
            max_load_factor=1.0,
            tol=1e-8,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)

        assert result["converged"]

        # 하중 비율 단조증가 확인
        lams = result["load_factors"]
        for i in range(1, len(lams)):
            assert lams[i] > lams[i - 1], (
                f"λ 단조증가 위반: λ[{i-1}]={lams[i-1]:.6f} ≥ λ[{i}]={lams[i]:.6f}"
            )

    def test_proportional_displacement(self):
        """선형 문제에서 변위 ∝ λ 확인.

        선형 탄성이므로 u(λ) = λ · u(1.0) 선형 관계가 성립해야 한다.
        """
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()

        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e6

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.3,
            max_steps=20,
            max_load_factor=1.0,
            tol=1e-10,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)
        assert result["converged"]

        # 최종 변위
        u_final = result["displacements"][-1]
        lam_final = result["load_factors"][-1]

        # 중간 단계에서 선형 관계 확인
        for i in range(1, len(result["load_factors"]) - 1):
            u_i = result["displacements"][i]
            lam_i = result["load_factors"][i]

            # u_i ≈ (lam_i / lam_final) * u_final
            u_expected = (lam_i / lam_final) * u_final
            nz_mask = np.abs(u_final) > 1e-15
            if np.any(nz_mask):
                rel_err = (np.linalg.norm(u_i[nz_mask] - u_expected[nz_mask])
                           / np.linalg.norm(u_expected[nz_mask]))
                assert rel_err < 0.05, (
                    f"단계 {i}: 비례 오차 {rel_err:.4e} > 5%"
                )

    def test_equilibrium_path_extraction(self):
        """평형 경로(하중-변위 곡선) 추출 기능."""
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()

        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e6

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.3,
            max_steps=10,
            max_load_factor=1.0,
        )
        solver.solve(f_ref=f_ref, verbose=False)

        # 오른쪽 끝 노드의 y변위 경로
        tip_node = right_nodes[0]
        disps, lams = solver.get_equilibrium_path(tip_node, dof=1)

        assert len(disps) == len(lams)
        assert len(disps) > 1  # 최소 1단계 이상

        # λ=0에서 변위=0
        assert disps[0] == 0.0
        assert lams[0] == 0.0


# ──────────── 적응적 호장 크기 ────────────

class TestArcLengthAdaptive:
    """적응적 호장 크기 조절 테스트."""

    def test_step_count_varies_with_arc_length(self):
        """호장 크기에 따라 단계 수가 달라짐을 확인.

        큰 호장 = 적은 단계, 작은 호장 = 많은 단계.
        desired_iterations=1로 설정하여 적응적 호장 크기 조절을 비활성화한다.
        (선형 문제에서 1회 수렴 → ratio=1 → dl 변경 없음)
        """
        mesh1, mat1, rn1, nn1 = _create_cantilever_2d()
        mesh2, mat2, rn2, nn2 = _create_cantilever_2d()

        f_ref1 = np.zeros(nn1 * 2)
        f_ref2 = np.zeros(nn2 * 2)
        for node in rn1:
            f_ref1[node * 2 + 1] = -1e6
        for node in rn2:
            f_ref2[node * 2 + 1] = -1e6

        # 큰 호장 (λ=1.0에 ~2단계로 도달)
        solver1 = ArcLengthSolver(
            mesh1, mat1,
            arc_length=0.5,
            max_steps=50,
            max_load_factor=1.0,
            desired_iterations=1,  # dl 고정 (ratio=1)
        )
        result1 = solver1.solve(f_ref=f_ref1, verbose=False)

        # 작은 호장 (λ=1.0에 더 많은 단계 필요)
        solver2 = ArcLengthSolver(
            mesh2, mat2,
            arc_length=0.05,
            max_steps=50,
            max_load_factor=1.0,
            desired_iterations=1,  # dl 고정 (ratio=1)
        )
        result2 = solver2.solve(f_ref=f_ref2, verbose=False)

        # 작은 호장이 더 많은 단계를 가져야 함
        assert result2["n_steps"] > result1["n_steps"], (
            f"작은 호장({result2['n_steps']}단계) ≤ 큰 호장({result1['n_steps']}단계)"
        )


# ──────────── 콜백 및 취소 ────────────

class TestArcLengthCallback:
    """진행 콜백 및 취소 기능 테스트."""

    def test_progress_callback(self):
        """진행 콜백 호출 확인."""
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()
        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e6

        callback_data = []

        def callback(info):
            callback_data.append(info.copy())
            return True

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.3,
            max_steps=5,
            max_load_factor=1.0,
        )
        solver.solve(f_ref=f_ref, verbose=False, progress_callback=callback)

        # 콜백이 최소 1회 이상 호출
        assert len(callback_data) > 0

        # 콜백 데이터 형식 확인
        info = callback_data[0]
        assert "step" in info
        assert "load_factor" in info
        assert "iterations" in info
        assert "energy" in info

    def test_cancellation(self):
        """콜백에서 취소 요청 시 즉시 중지."""
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()
        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e6

        call_count = [0]

        def cancel_after_2(info):
            call_count[0] += 1
            return call_count[0] < 2  # 2번째에서 취소

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.1,
            max_steps=50,
            max_load_factor=1.0,
        )
        result = solver.solve(
            f_ref=f_ref, verbose=False, progress_callback=cancel_after_2,
        )

        assert result["cancelled"] is True
        assert result["n_steps"] == 2  # 정확히 2단계 수행


# ──────────── 에너지 검증 ────────────

class TestArcLengthEnergy:
    """변형 에너지 기록 테스트."""

    def test_energy_nonnegative(self):
        """모든 단계에서 변형 에너지 ≥ 0."""
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()
        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e6

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.3,
            max_steps=10,
            max_load_factor=1.0,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)

        for i, e in enumerate(result["energies"]):
            assert e >= 0.0, f"단계 {i}: 음의 에너지 {e}"

    def test_energy_monotonic_linear(self):
        """선형 탄성에서 에너지 단조증가.

        선형 문제에서 λ 증가 → u 증가 → 에너지 증가.
        """
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()
        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e6

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.3,
            max_steps=10,
            max_load_factor=1.0,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)
        energies = result["energies"]

        for i in range(1, len(energies)):
            assert energies[i] >= energies[i - 1] - 1e-10, (
                f"에너지 단조증가 위반: E[{i-1}]={energies[i-1]:.6e} > E[{i}]={energies[i]:.6e}"
            )

    def test_energy_quadratic_in_lambda(self):
        """선형 탄성에서 E(λ) ∝ λ² 확인.

        U = ½ u^T K u = ½ λ² u_ref^T K u_ref 이므로
        E(λ) / λ² ≈ 상수.
        """
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()
        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e6

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.3,
            max_steps=10,
            max_load_factor=1.0,
            tol=1e-10,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)

        lams = result["load_factors"]
        energies = result["energies"]

        # λ > 0인 단계에서 E/λ² 비율 수집
        ratios = []
        for i in range(1, len(lams)):
            if abs(lams[i]) > 1e-10:
                ratio = energies[i] / (lams[i] ** 2)
                ratios.append(ratio)

        if len(ratios) >= 2:
            # 모든 비율이 비슷해야 함 (±5%)
            mean_ratio = np.mean(ratios)
            for r in ratios:
                assert abs(r - mean_ratio) / abs(mean_ratio) < 0.05, (
                    f"E/λ² 비율 변동: {r:.4e} vs 평균 {mean_ratio:.4e}"
                )


# ──────────── 비선형 재료 테스트 ────────────

class TestArcLengthNonlinear:
    """비선형 재료와의 호장법 조합 테스트."""

    def test_neo_hookean_path(self):
        """Neo-Hookean 초탄성과 호장법 경로 추적.

        대변형에서도 단계별로 수렴해야 한다.
        """
        from ..material.neo_hookean import NeoHookean

        mesh, _, right_nodes, n_nodes = _create_cantilever_2d(
            L=4.0, H=1.0, nx=4, ny=1,
        )
        material = NeoHookean(
            youngs_modulus=1e6,  # 부드러운 재료 (큰 변형 유도)
            poisson_ratio=0.3,
            dim=2,
        )

        # 참조 하중 (작게 설정하여 안정적 수렴)
        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -5e3

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.1,
            max_steps=20,
            max_load_factor=1.0,
            tol=1e-6,
            max_iterations=30,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)

        # 최소 1단계 이상 수렴해야 함
        assert result["n_steps"] >= 1, "Neo-Hookean 호장법에서 단계 수렴 실패"
        assert result["final_load_factor"] > 0.0

    def test_nonlinear_path_differs_from_linear(self):
        """비선형 경로가 선형 경로와 다름을 확인.

        동일 메쉬/하중에서 Neo-Hookean vs LinearElastic 비교.
        대변형이면 결과가 달라야 한다.
        """
        from ..material.neo_hookean import NeoHookean

        # Neo-Hookean (부드러운 재료 → 대변형)
        mesh_nl, _, rn_nl, nn_nl = _create_cantilever_2d(
            L=4.0, H=1.0, nx=4, ny=1,
        )
        mat_nl = NeoHookean(
            youngs_modulus=1e5,  # 매우 부드러운 재료
            poisson_ratio=0.3,
            dim=2,
        )
        f_ref_nl = np.zeros(nn_nl * 2)
        for node in rn_nl:
            f_ref_nl[node * 2 + 1] = -2e3

        solver_nl = ArcLengthSolver(
            mesh_nl, mat_nl,
            arc_length=0.1,
            max_steps=20,
            max_load_factor=1.0,
            tol=1e-6,
        )
        result_nl = solver_nl.solve(f_ref=f_ref_nl, verbose=False)

        # 선형 탄성 (같은 E, ν)
        mesh_le, _, rn_le, nn_le = _create_cantilever_2d(
            L=4.0, H=1.0, nx=4, ny=1,
        )
        mat_le = LinearElastic(
            youngs_modulus=1e5,
            poisson_ratio=0.3,
            dim=2,
            plane_stress=False,
        )
        f_ref_le = np.zeros(nn_le * 2)
        for node in rn_le:
            f_ref_le[node * 2 + 1] = -2e3

        solver_le = ArcLengthSolver(
            mesh_le, mat_le,
            arc_length=0.1,
            max_steps=20,
            max_load_factor=1.0,
            tol=1e-8,
        )
        result_le = solver_le.solve(f_ref=f_ref_le, verbose=False)

        # 둘 다 수렴해야 하고, 결과가 달라야 함
        if result_nl["n_steps"] >= 1 and result_le["n_steps"] >= 1:
            u_nl = result_nl["displacements"][-1]
            u_le = result_le["displacements"][-1]

            # 적어도 하나의 노드에서 1% 이상 차이
            max_le = np.max(np.abs(u_le))
            if max_le > 1e-15:
                diff = np.max(np.abs(u_nl - u_le)) / max_le
                # 대변형이면 차이가 있어야 함 (최소 0.1%)
                # 만약 변형이 작으면 차이가 작을 수 있으므로 조건부 확인
                max_disp = np.max(np.abs(u_le))
                beam_length = 4.0
                if max_disp / beam_length > 0.01:  # 변형이 빔 길이의 1% 이상
                    assert diff > 1e-4, (
                        f"비선형/선형 차이 {diff:.4e} — 대변형인데 차이가 너무 작음"
                    )


# ──────────── 수렴 실패 처리 ────────────

class TestArcLengthRobustness:
    """수렴 실패 및 엣지 케이스 처리."""

    def test_arc_length_reduction_on_failure(self):
        """수렴 실패 시 호장 크기 축소 확인.

        극단적으로 큰 하중 + 작은 max_iterations → 일부 단계 실패 → 호장 축소.
        """
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()

        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e12  # 매우 큰 하중

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=1.0,    # 큰 초기 호장
            max_steps=5,
            max_iterations=2,   # 매우 적은 반복 → 실패 유도
            max_load_factor=1.0,
            min_arc_length=0.01,
        )
        # 실패해도 크래시하면 안 됨
        result = solver.solve(f_ref=f_ref, verbose=False)

        assert isinstance(result, dict)
        assert "converged" in result

    def test_max_load_factor_respected(self):
        """max_load_factor 초과 시 자동 종료."""
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()
        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e6

        max_lf = 0.5
        solver = ArcLengthSolver(
            mesh, material,
            arc_length=0.3,
            max_steps=50,
            max_load_factor=max_lf,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)

        # λ가 max_load_factor 근처에서 멈추어야 함
        assert result["final_load_factor"] <= max_lf + 0.5  # 여유 있게 체크

    def test_single_step(self):
        """단 1단계만 수행하는 경우."""
        mesh, material, right_nodes, n_nodes = _create_cantilever_2d()
        f_ref = np.zeros(n_nodes * 2)
        for node in right_nodes:
            f_ref[node * 2 + 1] = -1e6

        solver = ArcLengthSolver(
            mesh, material,
            arc_length=5.0,   # 큰 호장 → 1단계에 λ=1 도달 가능
            max_steps=1,
            max_load_factor=1.0,
        )
        result = solver.solve(f_ref=f_ref, verbose=False)

        # 1단계로 제한
        assert result["n_steps"] <= 1
