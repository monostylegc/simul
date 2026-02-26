"""강체 어댑터.

RigidBody를 통합 AdapterBase 인터페이스로 래핑한다.
강체는 변형하지 않으므로 solve()는 즉시 반환,
step()은 규정 운동(prescribed motion)만 전진한다.
"""

import numpy as np
from typing import Optional

from .base_adapter import AdapterBase
from ..result import SolveResult
from ..rigid_body import RigidBody


class RigidBodyAdapter(AdapterBase):
    """강체 어댑터.

    AdapterBase의 모든 추상 메서드를 구현하며,
    접촉력에 의한 리액션 기록 기능을 추가한다.
    """

    def __init__(self, rigid_body: RigidBody, **options):
        self._rb = rigid_body
        self.dim = rigid_body.dim
        self._n_points = rigid_body.n_points
        self._options = options

        # 접촉력 버퍼
        self._contact_forces = np.zeros(
            (self._n_points, self.dim), dtype=np.float64
        )
        # 마지막 스텝의 리액션 힘 기록
        self._last_reaction_forces = np.zeros(
            (self._n_points, self.dim), dtype=np.float64
        )

    def solve(self, **kwargs) -> SolveResult:
        """강체는 변형 없음 → 즉시 수렴 반환."""
        return SolveResult(
            converged=True,
            iterations=0,
            residual=0.0,
            relative_residual=0.0,
            elapsed_time=0.0,
        )

    def get_displacements(self) -> np.ndarray:
        """현재 좌표 - 참조 좌표."""
        return self._rb._current_positions - self._rb._ref_positions

    def get_stress(self) -> np.ndarray:
        """강체는 응력 없음 → 0 반환."""
        return np.zeros(
            (self._n_points, self.dim, self.dim), dtype=np.float64
        )

    def get_damage(self) -> Optional[np.ndarray]:
        """강체는 손상 없음."""
        return None

    def get_current_positions(self) -> np.ndarray:
        """현재 좌표 반환."""
        return self._rb._current_positions.copy()

    def get_reference_positions(self) -> np.ndarray:
        """참조 좌표 반환."""
        return self._rb._ref_positions.copy()

    def inject_contact_forces(self, indices: np.ndarray, forces: np.ndarray):
        """접촉력 누적 (변형에는 미반영, 리액션 기록용)."""
        for i, idx in enumerate(indices):
            self._contact_forces[idx] += forces[i].astype(np.float64)

    def clear_contact_forces(self):
        """리액션 기록 후 접촉력 초기화."""
        self._last_reaction_forces = self._contact_forces.copy()
        self._contact_forces[:] = 0.0

    def step(self, dt: float):
        """규정 운동 1스텝 전진."""
        self._rb.advance(dt)

    def get_stable_dt(self) -> float:
        """강체는 dt 제한 없음."""
        return 1e10

    # === 리액션 힘 조회 ===

    def get_reaction_forces(self) -> np.ndarray:
        """마지막 스텝의 전체 리액션 힘 (n_points, dim)."""
        return self._last_reaction_forces.copy()

    def get_reaction_force_total(self) -> np.ndarray:
        """마지막 스텝 전체 리액션 힘 합산 벡터."""
        return self._last_reaction_forces.sum(axis=0)

    def get_reaction_force_magnitude(self) -> float:
        """마지막 스텝 리액션 힘 크기 (pullout force 등)."""
        return float(np.linalg.norm(self._last_reaction_forces.sum(axis=0)))
