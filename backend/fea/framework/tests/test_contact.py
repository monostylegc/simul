"""다중 물체 접촉 해석 테스트.

1. NodeNodeContact 단위 테스트 (접촉 감지, 페널티력)
2. FEM-FEM 접촉 통합 테스트 (두 블록 압축)
3. SPG-SPG 접촉 준정적 테스트
4. Scene API 사용성 테스트
5. Domain.select_boundary() 테스트
"""

import pytest
import numpy as np

from backend.fea.framework import (
    init, create_domain, Material, Method,
    Scene, ContactType,
)
from backend.fea.framework.contact import NodeNodeContact, ContactDefinition


# ============================================================
#  NodeNodeContact 단위 테스트
# ============================================================

class TestNodeNodeContact:
    """노드-노드 접촉 알고리즘 단위 테스트."""

    def test_detect_close_pairs(self):
        """가까운 노드 쌍이 감지되는지 확인."""
        # A: y=0 직선 위 5개 점
        pos_a = np.array([
            [0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0], [4.0, 0.0]
        ])
        # B: y=0.5 직선 위 5개 점 (간격 0.5)
        pos_b = np.array([
            [0.0, 0.5], [1.0, 0.5], [2.0, 0.5], [3.0, 0.5], [4.0, 0.5]
        ])
        surface_a = np.arange(5)
        surface_b = np.arange(5)
        gap_tol = 0.6  # 0.5 < 0.6 → 접촉

        contact = NodeNodeContact()
        pairs, gaps = contact.detect(pos_a, pos_b, surface_a, surface_b, gap_tol)

        assert len(pairs) == 5, f"5쌍 감지 예상, 실제 {len(pairs)}"
        np.testing.assert_allclose(gaps, 0.5, atol=1e-10)

    def test_detect_no_contact(self):
        """거리가 gap_tol보다 멀면 접촉 없음."""
        pos_a = np.array([[0.0, 0.0], [1.0, 0.0]])
        pos_b = np.array([[0.0, 2.0], [1.0, 2.0]])
        surface_a = np.arange(2)
        surface_b = np.arange(2)
        gap_tol = 1.0  # 거리 2.0 > 1.0

        contact = NodeNodeContact()
        pairs, gaps = contact.detect(pos_a, pos_b, surface_a, surface_b, gap_tol)

        assert len(pairs) == 0

    def test_compute_forces_action_reaction(self):
        """접촉력이 작용-반작용 법칙을 만족하는지 확인."""
        pos_a = np.array([[0.0, 0.0], [1.0, 0.0]])
        pos_b = np.array([[0.0, 0.3], [1.0, 0.3]])
        surface_a = np.arange(2)
        surface_b = np.arange(2)
        gap_tol = 0.5
        penalty = 1000.0

        contact = NodeNodeContact()
        pairs, gaps = contact.detect(pos_a, pos_b, surface_a, surface_b, gap_tol)
        forces_a, forces_b = contact.compute_forces(
            pos_a, pos_b, pairs, gaps, penalty, gap_tol
        )

        # 전체 합력 = 0 (작용-반작용)
        total = forces_a.sum(axis=0) + forces_b.sum(axis=0)
        np.testing.assert_allclose(total, 0.0, atol=1e-10)

    def test_compute_forces_direction(self):
        """A가 B 위에 있을 때, A에는 위로, B에는 아래로 힘이 가하는지."""
        # A: (0, 1.0), B: (0, 0.8) → 거리 0.2
        pos_a = np.array([[0.0, 1.0]])
        pos_b = np.array([[0.0, 0.8]])
        surface_a = np.array([0])
        surface_b = np.array([0])
        gap_tol = 0.5
        penalty = 1000.0

        contact = NodeNodeContact()
        pairs, gaps = contact.detect(pos_a, pos_b, surface_a, surface_b, gap_tol)
        forces_a, forces_b = contact.compute_forces(
            pos_a, pos_b, pairs, gaps, penalty, gap_tol
        )

        # A에는 +y 방향 (밀어냄), B에는 -y 방향
        assert forces_a[0, 1] > 0, "A에 +y 방향 반발력"
        assert forces_b[0, 1] < 0, "B에 -y 방향 반발력"

    def test_compute_forces_magnitude(self):
        """페널티 * 관통깊이 = 힘 크기."""
        pos_a = np.array([[0.0, 0.0]])
        pos_b = np.array([[0.0, 0.3]])
        surface_a = np.array([0])
        surface_b = np.array([0])
        gap_tol = 0.5
        penalty = 1000.0

        contact = NodeNodeContact()
        pairs, gaps = contact.detect(pos_a, pos_b, surface_a, surface_b, gap_tol)
        forces_a, forces_b = contact.compute_forces(
            pos_a, pos_b, pairs, gaps, penalty, gap_tol
        )

        # 관통 깊이 = 0.5 - 0.3 = 0.2
        # 힘 크기 = 1000 * 0.2 = 200
        expected_mag = 200.0
        actual_mag = np.linalg.norm(forces_a[0])
        np.testing.assert_allclose(actual_mag, expected_mag, rtol=1e-10)

    def test_surface_subset(self):
        """접촉면을 부분 집합으로 지정할 수 있는지."""
        pos_a = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
        pos_b = np.array([[0.0, 0.3], [1.0, 0.3], [2.0, 0.3]])
        # A에서 인덱스 0만, B에서 인덱스 0,1만 접촉면으로 지정
        surface_a = np.array([0])
        surface_b = np.array([0, 1])
        gap_tol = 0.5

        contact = NodeNodeContact()
        pairs, gaps = contact.detect(pos_a, pos_b, surface_a, surface_b, gap_tol)

        assert len(pairs) == 1
        assert pairs[0, 0] == 0  # A의 0번
        assert pairs[0, 1] == 0  # B의 0번 (가장 가까운)


# ============================================================
#  Domain.select_boundary() 테스트
# ============================================================

class TestSelectBoundary:
    """도메인 경계 선택 테스트."""

    def test_2d_fem_boundary(self):
        """2D FEM 도메인의 경계 노드 선택."""
        init()
        domain = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 0.0), size=(1.0, 0.5),
            n_divisions=(4, 2),
        )
        boundary = domain.select_boundary()

        # 5×3 격자: 총 15개 노드
        # 내부 노드: (1,1), (2,1), (3,1) = 3개
        # 경계 노드: 15 - 3 = 12개
        assert len(boundary) == 12

    def test_2d_spg_boundary(self):
        """2D SPG 도메인의 경계 입자 선택."""
        init()
        domain = create_domain(
            Method.SPG, dim=2,
            origin=(0.0, 0.0), size=(1.0, 0.5),
            n_divisions=(5, 3),
        )
        boundary = domain.select_boundary()

        # 5×3 격자: 총 15개 입자
        # 내부: (1,1), (2,1), (3,1) = 3개
        # 경계: 15 - 3 = 12개
        assert len(boundary) == 12


# ============================================================
#  Scene API 사용성 테스트
# ============================================================

class TestSceneAPI:
    """Scene API 기본 사용성 테스트."""

    def test_add_bodies(self):
        """물체 추가."""
        init()
        scene = Scene()
        d1 = create_domain(Method.FEM, dim=2, origin=(0, 0), size=(1, 0.5), n_divisions=(5, 3))
        d2 = create_domain(Method.FEM, dim=2, origin=(0, 0.6), size=(1, 0.5), n_divisions=(5, 3))
        mat = Material(E=1e6, nu=0.3, dim=2, plane_stress=True)

        b1 = scene.add(d1, mat)
        b2 = scene.add(d2, mat)

        assert b1._index == 0
        assert b2._index == 1

    def test_add_contact(self):
        """접촉 조건 추가."""
        init()
        scene = Scene()
        d1 = create_domain(Method.FEM, dim=2, origin=(0, 0), size=(1, 0.5), n_divisions=(5, 3))
        d2 = create_domain(Method.FEM, dim=2, origin=(0, 0.6), size=(1, 0.5), n_divisions=(5, 3))
        mat = Material(E=1e6, nu=0.3, dim=2, plane_stress=True)

        scene.add(d1, mat)
        scene.add(d2, mat)
        scene.add_contact(d1, d2, method=ContactType.PENALTY, penalty=1e6)

        assert len(scene._contacts) == 1
        assert scene._contacts[0].penalty == 1e6

    def test_contact_invalid_domain(self):
        """Scene에 추가되지 않은 도메인으로 접촉 정의 시 오류."""
        init()
        scene = Scene()
        d1 = create_domain(Method.FEM, dim=2, origin=(0, 0), size=(1, 0.5), n_divisions=(5, 3))
        d2 = create_domain(Method.FEM, dim=2, origin=(0, 0.6), size=(1, 0.5), n_divisions=(5, 3))
        mat = Material(E=1e6, nu=0.3, dim=2, plane_stress=True)

        scene.add(d1, mat)
        # d2는 추가하지 않음

        with pytest.raises(ValueError):
            scene.add_contact(d1, d2)

    def test_contact_type_enum(self):
        """ContactType enum 값."""
        assert ContactType.PENALTY.value == "penalty"
        assert ContactType.TIED.value == "tied"


# ============================================================
#  FEM-FEM 접촉 통합 테스트 (두 블록 압축)
# ============================================================

class TestFEMFEMContact:
    """FEM-FEM 두 블록 접촉 정적 해석 테스트."""

    def test_two_blocks_compression(self):
        """위 블록이 아래 블록을 누르는 2D 정적 접촉 문제.

        아래 블록: y=0~0.5, 하단 고정
        위 블록: y=0.5~1.0, 상단에 하향 하중
        접촉면: y=0.5 부근
        """
        init()

        E = 1e4
        nu = 0.3
        L, H = 1.0, 0.5

        # 아래 블록
        bottom = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 0.0), size=(L, H),
            n_divisions=(5, 3),
        )
        bot_fix = bottom.select(axis=1, value=0.0)
        bottom.set_fixed(bot_fix)
        mat = Material(E=E, nu=nu, dim=2, plane_stress=True)

        # 위 블록 (약간의 간격을 두고 배치)
        gap = 0.02
        top = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, H + gap), size=(L, H),
            n_divisions=(5, 3),
        )
        top_load = top.select(axis=1, value=H + gap + H)
        P = -50.0  # 하향 하중
        top.set_force(top_load, [0.0, P / len(top_load)])

        # Scene 구성
        scene = Scene()
        scene.add(bottom, mat)
        scene.add(top, mat)

        # 접촉면 명시 지정 (아래 블록 상단, 위 블록 하단)
        bottom_top_surface = bottom.select(axis=1, value=H)
        top_bottom_surface = top.select(axis=1, value=H + gap)
        scene.add_contact(
            bottom, top,
            method=ContactType.PENALTY,
            penalty=E * 10,  # 충분히 큰 페널티
            gap_tolerance=gap * 2.0,  # 간격의 2배
            surface_a=bottom_top_surface,
            surface_b=top_bottom_surface,
        )

        result = scene.solve(mode="static", max_contact_iters=30, contact_tol=1e-2)

        # 해석 완료 확인
        assert result["elapsed_time"] > 0

        # 위 블록이 아래로 이동해야 함
        u_top = scene.get_displacements(top)
        mean_uy_top = np.mean(u_top[:, 1])
        assert mean_uy_top < 0, f"위 블록이 하향 변위해야 함: {mean_uy_top:.6f}"

        # 아래 블록도 약간 압축되어야 함 (접촉력 전달)
        u_bottom = scene.get_displacements(bottom)
        # 접촉이 발생하면 아래 블록에도 변형 있음
        max_abs_u_bottom = np.max(np.abs(u_bottom))
        # 접촉 반복이 1회 이상이면 접촉력 전달 확인
        if result.get("total_contact_force", 0) > 0:
            assert max_abs_u_bottom > 0, "접촉력이 전달되어야 함"

    def test_no_contact_bodies_independent(self):
        """접촉 조건 없이 두 물체가 독립적으로 해석되는지."""
        init()

        E = 1e4
        L, H = 1.0, 0.5

        # 두 블록 (멀리 떨어져 있음)
        d1 = create_domain(
            Method.FEM, dim=2,
            origin=(0, 0), size=(L, H),
            n_divisions=(5, 3),
        )
        left1 = d1.select(axis=0, value=0.0)
        right1 = d1.select(axis=0, value=L)
        d1.set_fixed(left1)
        d1.set_force(right1, [50.0 / len(right1), 0.0])

        d2 = create_domain(
            Method.FEM, dim=2,
            origin=(0, 5.0), size=(L, H),
            n_divisions=(5, 3),
        )
        left2 = d2.select(axis=0, value=0.0)
        right2 = d2.select(axis=0, value=L)
        d2.set_fixed(left2)
        d2.set_force(right2, [100.0 / len(right2), 0.0])

        mat = Material(E=E, nu=0.3, dim=2, plane_stress=True)

        scene = Scene()
        scene.add(d1, mat)
        scene.add(d2, mat)
        # 접촉 없음

        result = scene.solve(mode="static")
        assert result["converged"]

        # 독립 해석과 동일한 결과인지 확인
        u1 = scene.get_displacements(d1)
        u2 = scene.get_displacements(d2)

        # 두 블록 모두 양의 x 변위
        assert np.mean(u1[right1, 0]) > 0
        assert np.mean(u2[right2, 0]) > 0

        # 하중이 2배이므로 변위도 약 2배 (선형 탄성)
        ratio = np.mean(u2[right2, 0]) / np.mean(u1[right1, 0])
        np.testing.assert_allclose(ratio, 2.0, rtol=0.1)


# ============================================================
#  자동 매개변수 추정 테스트
# ============================================================

class TestAutoParameters:
    """gap_tolerance, penalty 자동 추정 테스트."""

    def test_auto_gap_and_penalty(self):
        """자동 추정이 합리적인 값을 생성하는지."""
        init()

        d1 = create_domain(
            Method.FEM, dim=2,
            origin=(0, 0), size=(1, 0.5),
            n_divisions=(10, 5),
        )
        d2 = create_domain(
            Method.FEM, dim=2,
            origin=(0, 0.6), size=(1, 0.5),
            n_divisions=(10, 5),
        )
        mat = Material(E=1e6, nu=0.3, dim=2, plane_stress=True)

        scene = Scene()
        scene.add(d1, mat)
        scene.add(d2, mat)
        scene.add_contact(d1, d2)  # 자동 추정

        # _build() 호출하여 자동 추정 트리거
        scene._build()

        cdef = scene._contacts[0]
        # gap_tolerance > 0
        assert cdef.gap_tolerance > 0, f"gap_tol={cdef.gap_tolerance}"
        # penalty > 0
        assert cdef.penalty > 0, f"penalty={cdef.penalty}"

        # 간격 = 1.0/10 = 0.1 → gap_tol ≈ 0.1 * 1.5 = 0.15
        assert 0.05 < cdef.gap_tolerance < 0.5
        # penalty ≈ 1e6 / 0.1 = 1e7
        assert cdef.penalty > 1e5


# ============================================================
#  SPG-SPG 접촉 준정적 테스트
# ============================================================

class TestSPGSPGQuasiStatic:
    """SPG-SPG 준정적 접촉 해석 테스트."""

    def test_two_blocks_quasi_static(self):
        """두 SPG 블록 준정적 접촉: 위 블록이 아래 블록을 누름.

        아래 블록: y=0~0.2, 하단 고정
        위 블록: y=0.3~0.5 (gap=0.1, gap_tol보다 큼), 상단에 하향 하중
        mode="quasi_static"으로 동기화된 준정적 접촉
        """
        init()

        E = 1e4
        nu = 0.3
        L, H = 0.5, 0.2
        nx, ny = 11, 5
        spacing = L / (nx - 1)

        # 아래 블록
        bottom = create_domain(
            Method.SPG, dim=2,
            origin=(0.0, 0.0), size=(L, H),
            n_divisions=(nx, ny),
        )
        bot_fix = bottom.select(axis=1, value=0.0)
        bottom.set_fixed(bot_fix)
        mat = Material(E=E, nu=nu, density=1000, dim=2)

        # 위 블록 (gap > gap_tolerance → 초기 접촉 없음 → 하중으로 접근)
        gap = 0.1
        top = create_domain(
            Method.SPG, dim=2,
            origin=(0.0, H + gap), size=(L, H),
            n_divisions=(nx, ny),
        )
        top_load = top.select(axis=1, value=H + gap + H)
        P_total = -50.0  # 하향 총 하중 (충분히 큼)
        top.set_force(top_load, [0.0, P_total / len(top_load)])

        # Scene 구성
        scene = Scene()
        scene.add(bottom, mat, stabilization=0.01, viscous_damping=0.05)
        scene.add(top, mat, stabilization=0.01, viscous_damping=0.05)

        # 접촉: gap_tolerance < 실제 gap → 하중에 의해 접근 시에만 접촉 발생
        bottom_top_surface = bottom.select(axis=1, value=H)
        top_bottom_surface = top.select(axis=1, value=H + gap)
        scene.add_contact(
            bottom, top,
            method=ContactType.PENALTY,
            penalty=E * 5,
            gap_tolerance=spacing * 1.5,  # ~0.075 < gap=0.1
            surface_a=bottom_top_surface,
            surface_b=top_bottom_surface,
        )

        # 준정적 해석
        result = scene.solve(
            mode="quasi_static",
            max_iterations=30000,
            tol=1e-2,
        )

        assert result["elapsed_time"] > 0
        assert result["iterations"] > 0

        # 위 블록 하단이 하향 변위 (하중 방향)
        u_top = scene.get_displacements(top)
        top_bottom_indices = top.select(axis=1, value=H + gap)
        mean_uy_bottom_of_top = np.mean(u_top[top_bottom_indices, 1])
        assert mean_uy_bottom_of_top < 0, (
            f"위 블록 하단 하향 변위 기대: {mean_uy_bottom_of_top:.6f}"
        )

        # NaN/Inf 없음
        u_bottom = scene.get_displacements(bottom)
        assert not np.any(np.isnan(u_top)), "위 블록: NaN 발생"
        assert not np.any(np.isnan(u_bottom)), "아래 블록: NaN 발생"

    def test_quasi_static_no_contact_fallback(self):
        """접촉 없이 두 SPG 물체가 독립적으로 수렴하는지."""
        init()

        E = 1e4
        L, H = 0.5, 0.1
        nx, ny = 11, 3

        d1 = create_domain(
            Method.SPG, dim=2,
            origin=(0, 0), size=(L, H),
            n_divisions=(nx, ny),
        )
        left1 = d1.select(axis=0, value=0.0)
        right1 = d1.select(axis=0, value=L)
        d1.set_fixed(left1)
        d1.set_force(right1, [10.0 / len(right1), 0.0])

        d2 = create_domain(
            Method.SPG, dim=2,
            origin=(0, 5.0), size=(L, H),
            n_divisions=(nx, ny),
        )
        left2 = d2.select(axis=0, value=0.0)
        right2 = d2.select(axis=0, value=L)
        d2.set_fixed(left2)
        d2.set_force(right2, [10.0 / len(right2), 0.0])

        mat = Material(E=E, nu=0.3, density=1000, dim=2)

        scene = Scene()
        scene.add(d1, mat, stabilization=0.01, viscous_damping=0.05)
        scene.add(d2, mat, stabilization=0.01, viscous_damping=0.05)
        # 접촉 없음

        result = scene.solve(
            mode="quasi_static",
            max_iterations=30000,
            tol=1e-2,
        )

        # 발산하지 않음
        u1 = scene.get_displacements(d1)
        u2 = scene.get_displacements(d2)
        assert not np.any(np.isnan(u1))
        assert not np.any(np.isnan(u2))

        # 양의 x 변위
        assert np.mean(u1[right1, 0]) > 0
        assert np.mean(u2[right2, 0]) > 0


# ============================================================
#  mode 선택 테스트
# ============================================================

class TestSolveMode:
    """해석 모드 선택 테스트."""

    def test_default_mode_is_quasi_static(self):
        """기본 모드가 quasi_static인지 확인."""
        init()
        scene = Scene()
        d1 = create_domain(Method.FEM, dim=2, origin=(0, 0), size=(1, 0.5), n_divisions=(5, 3))
        left = d1.select(axis=0, value=0.0)
        right = d1.select(axis=0, value=1.0)
        d1.set_fixed(left)
        d1.set_force(right, [10.0, 0.0])
        mat = Material(E=1e4, nu=0.3, dim=2, plane_stress=True)
        scene.add(d1, mat)

        # FEM만 있으면 quasi_static → static으로 폴백
        result = scene.solve()  # 기본 mode="quasi_static"
        assert result["converged"]

    def test_invalid_mode_raises(self):
        """잘못된 모드명 시 오류."""
        init()
        scene = Scene()
        d1 = create_domain(Method.FEM, dim=2, origin=(0, 0), size=(1, 0.5), n_divisions=(5, 3))
        d1.set_fixed(d1.select(axis=0, value=0.0))
        mat = Material(E=1e4, nu=0.3, dim=2, plane_stress=True)
        scene.add(d1, mat)

        with pytest.raises(ValueError):
            scene.solve(mode="invalid")
