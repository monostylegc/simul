"""Tied(구속) 접촉 테스트.

초기 상대 위치를 유지하는 양방향 페널티 스프링 동작을 검증한다.
"""

import numpy as np
import pytest

from backend.fea.framework.contact import (
    ContactType,
    ContactDefinition,
    NodeNodeContact,
)
from backend.fea.framework.domain import Domain, Method, create_domain
from backend.fea.framework.material import Material
from backend.fea.framework.scene import Scene
from backend.fea.framework.runtime import is_initialized
from backend.fea.framework import init


# Taichi 초기화 (FEM 어댑터에서 필요)
if not is_initialized():
    init()


# ============================================================================
# 단위 테스트: NodeNodeContact.compute_tied_forces
# ============================================================================


class TestTiedForces:
    """compute_tied_forces 단위 테스트."""

    def test_no_deviation_zero_force(self):
        """이탈 없으면 접촉력 0."""
        algo = NodeNodeContact()
        pos_a = np.array([[0.0, 0.0], [1.0, 0.0]])
        pos_b = np.array([[0.0, 0.5], [1.0, 0.5]])
        pairs = np.array([[0, 0], [1, 1]], dtype=np.int64)
        ref_offsets = pos_a[pairs[:, 0]] - pos_b[pairs[:, 1]]

        forces_a, forces_b = algo.compute_tied_forces(
            pos_a, pos_b, pairs, ref_offsets, penalty=1e6,
        )

        np.testing.assert_allclose(forces_a, 0.0, atol=1e-10)
        np.testing.assert_allclose(forces_b, 0.0, atol=1e-10)

    def test_tension_restoring_force(self):
        """A가 위로 벌어지면 아래로 복원력 작용."""
        algo = NodeNodeContact()
        # 초기 상태
        pos_a_init = np.array([[0.0, 1.0]])
        pos_b_init = np.array([[0.0, 0.0]])
        pairs = np.array([[0, 0]], dtype=np.int64)
        ref_offsets = pos_a_init - pos_b_init  # [[0, 1]]

        # A가 위로 0.1 이동 (벌어짐)
        pos_a = np.array([[0.0, 1.1]])
        pos_b = pos_b_init.copy()

        penalty = 1e6
        forces_a, forces_b = algo.compute_tied_forces(
            pos_a, pos_b, pairs, ref_offsets, penalty,
        )

        # deviation = [0, 1.1] - [0, 1.0] = [0, 0.1]
        # force_a = -1e6 * [0, 0.1] = [0, -1e5] (아래로)
        np.testing.assert_allclose(forces_a[0], [0.0, -1e5], rtol=1e-10)
        # 반작용: B는 위로
        np.testing.assert_allclose(forces_b[0], [0.0, +1e5], rtol=1e-10)

    def test_compression_restoring_force(self):
        """A가 아래로 눌리면 위로 복원력 작용."""
        algo = NodeNodeContact()
        pos_a_init = np.array([[0.0, 1.0]])
        pos_b_init = np.array([[0.0, 0.0]])
        pairs = np.array([[0, 0]], dtype=np.int64)
        ref_offsets = pos_a_init - pos_b_init

        # A가 아래로 0.1 이동
        pos_a = np.array([[0.0, 0.9]])
        pos_b = pos_b_init.copy()

        forces_a, forces_b = algo.compute_tied_forces(
            pos_a, pos_b, pairs, ref_offsets, penalty=1e6,
        )

        # deviation = [0, 0.9] - [0, 1.0] = [0, -0.1]
        # force_a = -1e6 * [0, -0.1] = [0, +1e5] (위로)
        np.testing.assert_allclose(forces_a[0], [0.0, +1e5], rtol=1e-10)
        np.testing.assert_allclose(forces_b[0], [0.0, -1e5], rtol=1e-10)

    def test_lateral_deviation(self):
        """횡방향 이탈에도 복원력 작용."""
        algo = NodeNodeContact()
        pos_a_init = np.array([[0.0, 1.0]])
        pos_b_init = np.array([[0.0, 0.0]])
        pairs = np.array([[0, 0]], dtype=np.int64)
        ref_offsets = pos_a_init - pos_b_init

        # A가 오른쪽으로 0.05 이동
        pos_a = np.array([[0.05, 1.0]])
        pos_b = pos_b_init.copy()

        forces_a, forces_b = algo.compute_tied_forces(
            pos_a, pos_b, pairs, ref_offsets, penalty=1e6,
        )

        # deviation = [0.05, 0] → force_a = [-5e4, 0]
        np.testing.assert_allclose(forces_a[0], [-5e4, 0.0], rtol=1e-10)
        np.testing.assert_allclose(forces_b[0], [+5e4, 0.0], rtol=1e-10)

    def test_multiple_pairs(self):
        """다중 쌍 동시 처리."""
        algo = NodeNodeContact()
        pos_a = np.array([[0.0, 1.0], [1.0, 1.0], [2.0, 1.0]])
        pos_b = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
        pairs = np.array([[0, 0], [1, 1], [2, 2]], dtype=np.int64)
        ref_offsets = pos_a[pairs[:, 0]] - pos_b[pairs[:, 1]]

        # 이탈 없음
        forces_a, forces_b = algo.compute_tied_forces(
            pos_a, pos_b, pairs, ref_offsets, penalty=1e6,
        )
        np.testing.assert_allclose(forces_a, 0.0, atol=1e-10)
        np.testing.assert_allclose(forces_b, 0.0, atol=1e-10)

    def test_empty_pairs(self):
        """빈 쌍은 0 반환."""
        algo = NodeNodeContact()
        pos_a = np.array([[0.0, 0.0]])
        pos_b = np.array([[1.0, 1.0]])
        pairs = np.empty((0, 2), dtype=np.int64)
        ref_offsets = np.empty((0, 2))

        forces_a, forces_b = algo.compute_tied_forces(
            pos_a, pos_b, pairs, ref_offsets, penalty=1e6,
        )
        np.testing.assert_allclose(forces_a, 0.0, atol=1e-10)
        np.testing.assert_allclose(forces_b, 0.0, atol=1e-10)

    def test_3d_tied_forces(self):
        """3D 구속 접촉력 검증."""
        algo = NodeNodeContact()
        pos_a_init = np.array([[0.0, 0.0, 1.0]])
        pos_b_init = np.array([[0.0, 0.0, 0.0]])
        pairs = np.array([[0, 0]], dtype=np.int64)
        ref_offsets = pos_a_init - pos_b_init

        # A가 z방향으로 0.02 벌어짐
        pos_a = np.array([[0.0, 0.0, 1.02]])
        pos_b = pos_b_init.copy()

        forces_a, forces_b = algo.compute_tied_forces(
            pos_a, pos_b, pairs, ref_offsets, penalty=1e8,
        )

        # deviation = [0, 0, 0.02]
        # force_a = -1e8 * [0, 0, 0.02] = [0, 0, -2e6]
        np.testing.assert_allclose(forces_a[0], [0.0, 0.0, -2e6], rtol=1e-10)
        np.testing.assert_allclose(forces_b[0], [0.0, 0.0, +2e6], rtol=1e-10)


# ============================================================================
# 단위 테스트: detect_tied_pairs
# ============================================================================


class TestDetectTiedPairs:
    """detect_tied_pairs 단위 테스트."""

    def test_basic_detection(self):
        """기본 쌍 탐색."""
        algo = NodeNodeContact()
        pos_a = np.array([[0.0, 0.9], [1.0, 0.9]])
        pos_b = np.array([[0.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        surface_a = np.array([0, 1])
        surface_b = np.array([1, 2])

        pairs, offsets = algo.detect_tied_pairs(
            pos_a, pos_b, surface_a, surface_b, gap_tol=0.2,
        )

        assert len(pairs) == 2
        # 쌍 0: (0, 1) — pos_a[0]=[0,0.9] ↔ pos_b[1]=[0,1.0]
        # 쌍 1: (1, 2) — pos_a[1]=[1,0.9] ↔ pos_b[2]=[1,1.0]
        assert pairs.shape == (2, 2)
        assert offsets.shape == (2, 2)

    def test_no_pairs_outside_tolerance(self):
        """허용 거리 밖이면 쌍 없음."""
        algo = NodeNodeContact()
        pos_a = np.array([[0.0, 0.0]])
        pos_b = np.array([[10.0, 10.0]])
        surface_a = np.array([0])
        surface_b = np.array([0])

        pairs, offsets = algo.detect_tied_pairs(
            pos_a, pos_b, surface_a, surface_b, gap_tol=1.0,
        )

        assert len(pairs) == 0


# ============================================================================
# 통합 테스트: Scene + Tied Contact
# ============================================================================


class TestSceneTiedContact:
    """Scene에서 Tied 접촉 E2E 테스트."""

    def test_two_body_tied_static(self):
        """2물체 정적 해석에서 Tied 접촉으로 힘 전달 확인.

        양쪽 모두 고정 BC, 하부에 하향 힘 적용.
        낮은 penalty로 안정적 수렴.
        """
        dom_bottom = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 0.0), size=(1.0, 1.0),
            n_divisions=(2, 2),
        )
        dom_top = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 1.0), size=(1.0, 1.0),
            n_divisions=(2, 2),
        )

        mat = Material(E=1000.0, nu=0.3)

        # 경계조건: 하부 바닥 고정
        bottom = dom_bottom.select(axis=1, value=0.0)
        dom_bottom.set_fixed(bottom)

        # 하부 중간(y=0.5)에 하향 힘
        mid_bottom = dom_bottom.select(axis=1, value=0.5)
        dom_bottom.set_force(mid_bottom, [0.0, -10.0])

        # 상부: y=2 고정
        top_fixed = dom_top.select(axis=1, value=2.0)
        dom_top.set_fixed(top_fixed)

        # Scene 구성 (낮은 penalty → 안정적 staggered 수렴)
        scene = Scene()
        scene.add(dom_bottom, mat)
        scene.add(dom_top, mat)
        scene.add_contact(
            dom_bottom, dom_top,
            method=ContactType.TIED,
            penalty=500.0,  # E=1000의 절반 → 안정적 수렴
        )

        result = scene.solve(
            mode="static", verbose=False,
            max_contact_iters=50, contact_tol=1e-2,
        )

        # 하부: 하향 힘 → 변위 발생
        u_bottom = scene.get_displacements(dom_bottom)
        assert np.max(np.abs(u_bottom)) > 0, "하부 도메인에 변위 없음"

        # 상부: Tied 접촉을 통해 인터페이스에서 힘 전달 → 변형 발생
        u_top = scene.get_displacements(dom_top)
        assert np.max(np.abs(u_top)) > 0, (
            "상부 도메인에 변위 없음 — Tied 접촉이 힘을 전달하지 않음"
        )

    def test_two_body_tied_displacement_continuity(self):
        """Tied 접촉 인터페이스에서 변위 연속성 검증.

        양쪽 모두 고정 BC, 하부에 하향 힘.
        인터페이스 노드의 변위 차이가 페널티에 반비례하여 감소.
        """
        dom_bottom = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 0.0), size=(1.0, 1.0),
            n_divisions=(3, 3),
        )
        dom_top = create_domain(
            Method.FEM, dim=2,
            origin=(0.0, 1.0), size=(1.0, 1.0),
            n_divisions=(3, 3),
        )

        mat = Material(E=1000.0, nu=0.3)

        # 하부: y=0 고정
        bottom_nodes = dom_bottom.select(axis=1, value=0.0)
        dom_bottom.set_fixed(bottom_nodes)

        # 하부: 중간에 하향 힘
        mid_bottom = dom_bottom.select(axis=1, value=0.5)
        dom_bottom.set_force(mid_bottom, [0.0, -20.0])

        # 상부: y=2 고정
        top_nodes = dom_top.select(axis=1, value=2.0)
        dom_top.set_fixed(top_nodes)

        scene = Scene()
        scene.add(dom_bottom, mat)
        scene.add(dom_top, mat)
        scene.add_contact(
            dom_bottom, dom_top,
            method=ContactType.TIED,
            penalty=1e8,  # 높은 페널티 → 인터페이스에서 변위 근사 일치
        )

        result = scene.solve(mode="static", verbose=False)
        assert result["converged"]

        u_bottom = scene.get_displacements(dom_bottom)
        u_top = scene.get_displacements(dom_top)

        # 인터페이스 노드 변위 비교
        iface_bottom = dom_bottom.select(axis=1, value=1.0)
        iface_top = dom_top.select(axis=1, value=1.0)

        pos_b = dom_bottom.get_positions()
        pos_t = dom_top.get_positions()

        sorted_b = np.argsort(pos_b[iface_bottom, 0])
        sorted_t = np.argsort(pos_t[iface_top, 0])

        uy_b = u_bottom[iface_bottom[sorted_b], 1]
        uy_t = u_top[iface_top[sorted_t], 1]

        # 높은 페널티 → 인터페이스 변위 차이 작음
        diff = np.abs(uy_b - uy_t)
        assert np.max(diff) < 0.05, (
            f"인터페이스 y변위 차이 과대: max={np.max(diff):.4e}"
        )
