"""솔버 어댑터 추상 기반 클래스.

모든 솔버 어댑터가 구현해야 하는 접촉 해석용 공통 인터페이스를 정의한다.
"""

from abc import ABC, abstractmethod
import numpy as np
from typing import Optional

from ..result import SolveResult


class AdapterBase(ABC):
    """모든 솔버 어댑터의 공통 인터페이스.

    기존 메서드(solve, get_displacements, get_stress, get_damage) 외에
    접촉 해석에 필요한 추가 메서드를 정의한다.
    """

    @abstractmethod
    def solve(self, **kwargs) -> SolveResult:
        """정적/준정적 해석."""

    @abstractmethod
    def get_displacements(self) -> np.ndarray:
        """현재 변위 (n_points, dim)."""

    @abstractmethod
    def get_stress(self) -> np.ndarray:
        """응력 반환."""

    @abstractmethod
    def get_damage(self) -> Optional[np.ndarray]:
        """손상도 반환 (미지원 시 None)."""

    @abstractmethod
    def get_current_positions(self) -> np.ndarray:
        """현재 좌표 (n_points, dim). 참조좌표 + 변위."""

    @abstractmethod
    def get_reference_positions(self) -> np.ndarray:
        """참조(초기) 좌표 (n_points, dim)."""

    @abstractmethod
    def inject_contact_forces(self, indices: np.ndarray, forces: np.ndarray):
        """접촉력 주입.

        Args:
            indices: 접촉 노드/입자 인덱스 (n_contact,)
            forces: 접촉력 벡터 (n_contact, dim)
        """

    @abstractmethod
    def clear_contact_forces(self):
        """접촉력 초기화 (매 접촉 반복 전)."""

    @abstractmethod
    def step(self, dt: float):
        """명시적 1스텝 전진 (접촉 해석 시 동기화용).

        Args:
            dt: 시간 간격
        """

    @abstractmethod
    def get_stable_dt(self) -> float:
        """안정 시간 간격 (명시적 해석용).

        FEM 정적 솔버는 큰 값 반환.
        """
