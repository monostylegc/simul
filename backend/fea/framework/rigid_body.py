"""강체(Rigid Body) 정의.

규정 운동(prescribed motion)을 수행하는 비변형 물체를 표현한다.
나사, 임플란트 등 변형이 무시되는 강체에 사용한다.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .domain import Method


@dataclass
class PrescribedMotion:
    """규정 운동 정의.

    Args:
        motion_type: 운동 유형 ("rotation" 또는 "translation")
        axis: 운동 축 방향 벡터 (자동 정규화)
        rate: 속도 (rad/s 또는 m/s)
        total: 총 변위량 (rad 또는 m)
        center: 회전 중심 좌표 (rotation만, translation 시 무시)
    """
    motion_type: str
    axis: np.ndarray
    rate: float
    total: float
    center: Optional[np.ndarray] = field(default=None, repr=False)

    def __post_init__(self):
        self.axis = np.asarray(self.axis, dtype=np.float64)
        norm = np.linalg.norm(self.axis)
        if norm > 0:
            self.axis = self.axis / norm
        if self.center is not None:
            self.center = np.asarray(self.center, dtype=np.float64)
        if self.motion_type == "rotation" and self.center is None:
            raise ValueError("회전 운동에는 center가 필요합니다")


class RigidBody:
    """강체 물체.

    삼각형 메쉬 또는 점집합으로 표현되며,
    규정 운동(prescribed motion)에 따라 좌표를 갱신한다.
    Domain을 상속하지 않고 duck typing으로 Scene과 호환한다.

    Attributes:
        method: Method.RIGID (고정)
        dim: 공간 차원
    """

    method = Method.RIGID

    def __init__(
        self,
        positions: np.ndarray,
        dim: int = 3,
        motions: Optional[List[PrescribedMotion]] = None,
    ):
        """강체 생성.

        Args:
            positions: 정점 좌표 (n_vertices, dim)
            dim: 공간 차원
            motions: 규정 운동 리스트 (순서대로 적용)
        """
        self._ref_positions = np.asarray(positions, dtype=np.float64)
        self._current_positions = self._ref_positions.copy()
        self.dim = dim
        self.motions: List[PrescribedMotion] = motions or []

        # 현재 진행 중인 motion 인덱스
        self._motion_idx = 0
        # 현재 motion에서 누적된 변위량
        self._accumulated = 0.0

        # 경계조건 저장 (Scene 호환용, 강체이므로 미사용)
        self._fixed_indices = None
        self._fixed_values = None
        self._force_indices = None
        self._force_values = None
        self._adapter = None
        self._positions = self._ref_positions

        # origin/size/n_divisions 추정 (Scene._estimate_spacing 호환)
        self._compute_bounds()

    def _compute_bounds(self):
        """메쉬 경계에서 origin, size 추정."""
        mins = self._ref_positions.min(axis=0)
        maxs = self._ref_positions.max(axis=0)
        self.origin = tuple(mins)
        self.size = tuple(maxs - mins)
        # n_divisions: 실제 격자가 아니므로 적당한 값 추정
        n = len(self._ref_positions)
        n_per_axis = max(int(round(n ** (1.0 / self.dim))), 2)
        self.n_divisions = tuple([n_per_axis] * self.dim)

    def add_motion(self, motion: PrescribedMotion):
        """규정 운동 추가."""
        self.motions.append(motion)

    def advance(self, dt: float) -> bool:
        """규정 운동을 dt만큼 전진.

        Args:
            dt: 시간 간격

        Returns:
            True면 아직 모션 진행 중, False면 모든 모션 완료
        """
        if self._motion_idx >= len(self.motions):
            return False

        motion = self.motions[self._motion_idx]
        displacement = motion.rate * dt

        # 남은 변위량 확인
        remaining = abs(motion.total) - abs(self._accumulated)
        if remaining <= 0:
            # 현재 모션 완료 → 다음 모션
            self._motion_idx += 1
            self._accumulated = 0.0
            return self._motion_idx < len(self.motions)

        # 이번 스텝에서 적용할 변위량 (남은 양을 초과하지 않음)
        sign = np.sign(motion.total) if motion.total != 0 else 1.0
        actual = min(abs(displacement), remaining) * sign

        if motion.motion_type == "rotation":
            self._apply_rotation(motion.axis, float(actual), motion.center)
        elif motion.motion_type == "translation":
            self._apply_translation(motion.axis, float(actual))
        else:
            raise ValueError(f"지원하지 않는 운동 유형: {motion.motion_type}")

        self._accumulated += actual

        # 모션 완료 체크
        if abs(abs(self._accumulated) - abs(motion.total)) < 1e-15:
            self._motion_idx += 1
            self._accumulated = 0.0

        return True

    def _apply_rotation(
        self,
        axis: np.ndarray,
        angle: float,
        center: np.ndarray,
    ):
        """Rodrigues 공식으로 회전 적용.

        Args:
            axis: 정규화된 회전축
            angle: 회전 각도 [rad]
            center: 회전 중심
        """
        # 2D: z축 회전으로 처리
        if self.dim == 2:
            cos_a = np.cos(angle)
            sin_a = np.sin(angle)
            rot = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
            centered = self._current_positions - center[:2]
            self._current_positions = (rot @ centered.T).T + center[:2]
        else:
            # 3D Rodrigues
            k = axis[:3]
            cos_a = np.cos(angle)
            sin_a = np.sin(angle)
            centered = self._current_positions - center[:3]
            # v_rot = v*cos(a) + (k×v)*sin(a) + k*(k·v)*(1-cos(a))
            cross = np.cross(k, centered)
            dot = centered @ k
            self._current_positions = (
                centered * cos_a
                + cross * sin_a
                + np.outer(dot, k) * (1 - cos_a)
                + center[:3]
            )

    def _apply_translation(self, axis: np.ndarray, distance: float):
        """병진 운동 적용.

        Args:
            axis: 정규화된 이동 방향
            distance: 이동 거리
        """
        self._current_positions += axis[:self.dim] * distance

    def get_positions(self) -> np.ndarray:
        """참조 좌표 반환 (Domain 호환)."""
        return self._ref_positions

    def get_current_positions(self) -> np.ndarray:
        """현재 좌표 반환."""
        return self._current_positions.copy()

    def select_boundary(self, tol: Optional[float] = None) -> np.ndarray:
        """전체 정점을 경계로 반환 (강체 표면 = 전체)."""
        return np.arange(len(self._ref_positions), dtype=np.int64)

    def select(
        self,
        axis: int,
        value: float,
        tol: Optional[float] = None,
    ) -> np.ndarray:
        """위치 기반 정점 선택 (Domain 호환)."""
        coords = self._ref_positions[:, axis]
        if tol is None:
            unique_sorted = np.unique(np.round(coords, decimals=10))
            if len(unique_sorted) > 1:
                tol = np.min(np.diff(unique_sorted)) * 0.5
            else:
                tol = 1e-6
        return np.where(np.abs(coords - value) < tol)[0]

    @property
    def n_points(self) -> int:
        """정점 수."""
        return len(self._ref_positions)

    def reset(self):
        """초기 상태로 리셋."""
        self._current_positions = self._ref_positions.copy()
        self._motion_idx = 0
        self._accumulated = 0.0


def create_rigid_body(
    positions: np.ndarray,
    dim: int = 3,
    motions: Optional[List[PrescribedMotion]] = None,
) -> RigidBody:
    """강체 팩토리.

    Args:
        positions: 정점 좌표 (n_vertices, dim)
        dim: 공간 차원
        motions: 규정 운동 리스트

    Returns:
        RigidBody 객체
    """
    return RigidBody(positions=positions, dim=dim, motions=motions)
