"""강체(RigidBody) + 강체-변형체 접촉 테스트.

단위 테스트:
- 강체 생성, 규정 운동(회전/병진), 모션 순서 적용, 완료 판정
- 어댑터 인터페이스 호환성, 리액션 기록

통합 테스트:
- 2D 강체 블록이 SPG 블록을 압축
- 강체 + 마찰 접촉
"""

import pytest
import numpy as np

from backend.fea.framework import (
    init, create_domain, Material, Method, Scene, ContactType,
    RigidBody, PrescribedMotion, create_rigid_body,
)
from backend.fea.framework._adapters.rigid_adapter import RigidBodyAdapter


# ============================================================
#  RigidBody 단위 테스트
# ============================================================

class TestRigidBodyCreation:
    """강체 생성 테스트."""

    def test_create_from_positions_2d(self):
        """2D 점집합으로 강체 생성."""
        pos = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        rb = RigidBody(positions=pos, dim=2)

        assert rb.n_points == 4
        assert rb.dim == 2
        assert rb.method == Method.RIGID
        np.testing.assert_array_equal(rb.get_positions(), pos)

    def test_create_from_positions_3d(self):
        """3D 점집합으로 강체 생성."""
        pos = np.array([
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
        ])
        rb = RigidBody(positions=pos, dim=3)

        assert rb.n_points == 4
        assert rb.dim == 3

    def test_create_rigid_body_factory(self):
        """팩토리 함수 테스트."""
        pos = np.array([[0.0, 0.0], [1.0, 0.0]])
        rb = create_rigid_body(pos, dim=2)
        assert isinstance(rb, RigidBody)
        assert rb.n_points == 2

    def test_origin_size_estimation(self):
        """메쉬 bounds에서 origin, size 추정."""
        pos = np.array([[1.0, 2.0], [3.0, 5.0], [2.0, 3.0]])
        rb = RigidBody(positions=pos, dim=2)

        np.testing.assert_allclose(rb.origin, (1.0, 2.0))
        np.testing.assert_allclose(rb.size, (2.0, 3.0))

    def test_select_boundary_returns_all(self):
        """강체는 전체 정점이 경계."""
        pos = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        rb = RigidBody(positions=pos, dim=2)
        boundary = rb.select_boundary()
        assert len(boundary) == 4

    def test_select_by_axis(self):
        """축 기반 정점 선택."""
        pos = np.array([
            [0.0, 0.0], [1.0, 0.0], [2.0, 0.0],
            [0.0, 1.0], [1.0, 1.0], [2.0, 1.0],
        ])
        rb = RigidBody(positions=pos, dim=2)
        left = rb.select(axis=0, value=0.0)
        assert len(left) == 2  # (0,0), (0,1)


class TestPrescribedMotion:
    """규정 운동 테스트."""

    def test_rotation_requires_center(self):
        """회전 운동에 center 없으면 오류."""
        with pytest.raises(ValueError):
            PrescribedMotion(
                motion_type="rotation",
                axis=np.array([0.0, 0.0, 1.0]),
                rate=1.0,
                total=np.pi / 2,
            )

    def test_axis_normalization(self):
        """축 벡터가 자동 정규화."""
        m = PrescribedMotion(
            motion_type="translation",
            axis=np.array([3.0, 4.0, 0.0]),
            rate=1.0,
            total=1.0,
        )
        np.testing.assert_allclose(np.linalg.norm(m.axis), 1.0)


class TestPrescribedTranslation:
    """병진 운동 테스트."""

    def test_translate_2d(self):
        """2D 10mm 이동 후 좌표 검증."""
        pos = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
        motion = PrescribedMotion(
            motion_type="translation",
            axis=np.array([1.0, 0.0]),
            rate=0.5,   # 0.5 m/s
            total=10.0,  # 10 m
        )
        rb = RigidBody(positions=pos, dim=2, motions=[motion])

        # 20 스텝 × dt=1.0 → 변위 = 0.5 × 20 = 10.0
        for _ in range(20):
            rb.advance(1.0)

        expected = pos + np.array([10.0, 0.0])
        np.testing.assert_allclose(rb.get_current_positions(), expected, atol=1e-10)

    def test_translate_3d(self):
        """3D 병진 운동."""
        pos = np.array([[0, 0, 0], [1, 0, 0]], dtype=float)
        motion = PrescribedMotion(
            motion_type="translation",
            axis=np.array([0.0, 0.0, 1.0]),
            rate=2.0,
            total=5.0,
        )
        rb = RigidBody(positions=pos, dim=3, motions=[motion])

        # 5 스텝 × dt=0.5 → 변위 = 2.0 × 2.5 = 5.0
        for _ in range(5):
            rb.advance(0.5)

        np.testing.assert_allclose(
            rb.get_current_positions()[:, 2], [5.0, 5.0], atol=1e-10
        )


class TestPrescribedRotation:
    """회전 운동 테스트."""

    def test_rotate_90deg_2d(self):
        """2D 90도 회전 후 좌표 검증."""
        # 원점 중심 반지름 1.0인 점
        pos = np.array([[1.0, 0.0]])
        motion = PrescribedMotion(
            motion_type="rotation",
            axis=np.array([0.0, 0.0, 1.0]),
            center=np.array([0.0, 0.0]),
            rate=np.pi / 2,
            total=np.pi / 2,
        )
        rb = RigidBody(positions=pos, dim=2, motions=[motion])
        rb.advance(1.0)

        expected = np.array([[0.0, 1.0]])
        np.testing.assert_allclose(rb.get_current_positions(), expected, atol=1e-10)

    def test_rotate_90deg_3d(self):
        """3D z축 90도 회전."""
        pos = np.array([[1.0, 0.0, 0.0]])
        motion = PrescribedMotion(
            motion_type="rotation",
            axis=np.array([0.0, 0.0, 1.0]),
            center=np.array([0.0, 0.0, 0.0]),
            rate=np.pi / 2,
            total=np.pi / 2,
        )
        rb = RigidBody(positions=pos, dim=3, motions=[motion])
        rb.advance(1.0)

        expected = np.array([[0.0, 1.0, 0.0]])
        np.testing.assert_allclose(rb.get_current_positions(), expected, atol=1e-10)


class TestSequentialMotions:
    """순서 모션 적용 테스트."""

    def test_translation_then_translation(self):
        """병진 → 병진 순서 적용."""
        pos = np.array([[0.0, 0.0]])
        m1 = PrescribedMotion(
            motion_type="translation",
            axis=np.array([1.0, 0.0]),
            rate=1.0, total=2.0,
        )
        m2 = PrescribedMotion(
            motion_type="translation",
            axis=np.array([0.0, 1.0]),
            rate=1.0, total=3.0,
        )
        rb = RigidBody(positions=pos, dim=2, motions=[m1, m2])

        # 첫 모션: 2스텝
        for _ in range(2):
            assert rb.advance(1.0)

        # 두 번째 모션: 3스텝
        for _ in range(3):
            rb.advance(1.0)

        np.testing.assert_allclose(
            rb.get_current_positions(), [[2.0, 3.0]], atol=1e-10
        )

    def test_motion_completion_returns_false(self):
        """모든 모션 완료 시 False 반환."""
        pos = np.array([[0.0, 0.0]])
        m = PrescribedMotion(
            motion_type="translation",
            axis=np.array([1.0, 0.0]),
            rate=1.0, total=1.0,
        )
        rb = RigidBody(positions=pos, dim=2, motions=[m])

        rb.advance(1.0)  # 완료
        result = rb.advance(1.0)  # 모션 없음
        assert result is False

    def test_reset(self):
        """초기 상태로 리셋."""
        pos = np.array([[0.0, 0.0]])
        m = PrescribedMotion(
            motion_type="translation",
            axis=np.array([1.0, 0.0]),
            rate=1.0, total=1.0,
        )
        rb = RigidBody(positions=pos, dim=2, motions=[m])
        rb.advance(1.0)
        rb.reset()

        np.testing.assert_allclose(rb.get_current_positions(), pos)
        assert rb._motion_idx == 0


# ============================================================
#  RigidBodyAdapter 단위 테스트
# ============================================================

class TestRigidBodyAdapter:
    """어댑터 인터페이스 테스트."""

    def _make_adapter(self):
        pos = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        rb = RigidBody(positions=pos, dim=2)
        return RigidBodyAdapter(rb)

    def test_solve_returns_converged(self):
        """solve() 즉시 수렴."""
        adapter = self._make_adapter()
        result = adapter.solve()
        assert result.converged

    def test_get_displacements_zero(self):
        """초기 상태에서 변위 0."""
        adapter = self._make_adapter()
        u = adapter.get_displacements()
        np.testing.assert_array_equal(u, 0.0)

    def test_get_stress_zero(self):
        """강체 응력 0."""
        adapter = self._make_adapter()
        s = adapter.get_stress()
        assert s.shape == (4, 2, 2)
        np.testing.assert_array_equal(s, 0.0)

    def test_get_damage_none(self):
        """강체 손상 없음."""
        adapter = self._make_adapter()
        assert adapter.get_damage() is None

    def test_get_stable_dt_large(self):
        """강체 dt 제한 없음."""
        adapter = self._make_adapter()
        assert adapter.get_stable_dt() == 1e10

    def test_inject_and_clear_reaction(self):
        """접촉력 주입 → clear → 리액션 기록."""
        adapter = self._make_adapter()
        forces = np.array([[10.0, 5.0], [-10.0, -5.0]])
        indices = np.array([0, 2])
        adapter.inject_contact_forces(indices, forces)
        adapter.clear_contact_forces()

        reaction = adapter.get_reaction_forces()
        np.testing.assert_allclose(reaction[0], [10.0, 5.0])
        np.testing.assert_allclose(reaction[2], [-10.0, -5.0])

        mag = adapter.get_reaction_force_magnitude()
        # 합산: (10-10, 5-5) = (0, 0) → 크기 0
        np.testing.assert_allclose(mag, 0.0, atol=1e-10)

    def test_step_advances_motion(self):
        """step()이 규정 운동 전진."""
        pos = np.array([[0, 0], [1, 0]], dtype=float)
        m = PrescribedMotion(
            motion_type="translation",
            axis=np.array([0.0, 1.0]),
            rate=1.0, total=2.0,
        )
        rb = RigidBody(positions=pos, dim=2, motions=[m])
        adapter = RigidBodyAdapter(rb)

        adapter.step(1.0)
        u = adapter.get_displacements()
        np.testing.assert_allclose(u[:, 1], 1.0, atol=1e-10)


# ============================================================
#  강체-SPG 접촉 통합 테스트
# ============================================================

class TestRigidSPGContact:
    """강체가 SPG 블록을 압축하는 통합 테스트."""

    def test_rigid_pushes_spg_block(self):
        """2D 강체 블록이 SPG 블록 위에서 내려와 압축.

        SPG 블록: y=0~0.2, 하단 고정
        강체: y=0.3~0.5, 하향 병진 운동 (gap=0.1)
        """
        init()

        E = 1e4
        nu = 0.3
        L, H = 0.5, 0.2
        nx, ny = 11, 5

        # SPG 블록 (변형체)
        spg = create_domain(
            Method.SPG, dim=2,
            origin=(0.0, 0.0), size=(L, H),
            n_divisions=(nx, ny),
        )
        bot_fix = spg.select(axis=1, value=0.0)
        spg.set_fixed(bot_fix)
        mat = Material(E=E, nu=nu, density=1000, dim=2)

        # 강체 블록 (SPG 블록 위에 배치)
        gap = 0.1
        rigid_spacing = L / (nx - 1)
        rigid_pts = []
        for i in range(nx):
            for j in range(3):
                rigid_pts.append([
                    i * rigid_spacing,
                    H + gap + j * rigid_spacing,
                ])
        rigid_pts = np.array(rigid_pts)

        motion = PrescribedMotion(
            motion_type="translation",
            axis=np.array([0.0, -1.0]),
            rate=0.01,
            total=0.15,  # gap 0.1 + 0.05 관통
        )
        rb = create_rigid_body(rigid_pts, dim=2, motions=[motion])

        # Scene 구성
        scene = Scene()
        scene.add(spg, mat, stabilization=0.01, viscous_damping=0.05)
        scene.add(rb)  # 강체: material=None

        # 접촉
        spg_top = spg.select(axis=1, value=H)
        rb_bottom = rb.select(axis=1, value=H + gap)
        spacing = L / (nx - 1)
        scene.add_contact(
            spg, rb,
            method=ContactType.PENALTY,
            penalty=E * 5,
            gap_tolerance=spacing * 1.5,
            surface_a=spg_top,
            surface_b=rb_bottom,
        )

        # 준정적 해석
        result = scene.solve(
            mode="quasi_static",
            max_iterations=20000,
            tol=1e-2,
        )

        assert result["elapsed_time"] > 0

        # SPG 블록이 압축 변형
        u_spg = scene.get_displacements(spg)
        assert not np.any(np.isnan(u_spg)), "NaN 발생"

        # 강체가 하향 이동했으므로 접촉이 발생해야 함
        u_rigid = scene.get_displacements(rb)
        mean_uy_rigid = np.mean(u_rigid[:, 1])
        assert mean_uy_rigid < 0, f"강체 하향 이동: {mean_uy_rigid:.6f}"

    def test_scene_add_rigid_no_material(self):
        """Scene에 강체를 material=None으로 추가."""
        init()
        pos = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        rb = create_rigid_body(pos, dim=2)

        scene = Scene()
        body = scene.add(rb)

        assert body.material is None
        assert body.domain.method == Method.RIGID
