"""해부학 프로파일 추상 인터페이스.

부위별 재료 물성, 접촉 규칙, 특수 구조 검출을 캡슐화하는
AnatomyProfile 추상 클래스를 정의한다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from backend.fea.framework.domain import Method
from backend.fea.framework.contact import ContactType


@dataclass
class MaterialProps:
    """재료 물성 데이터.

    Attributes:
        E: 영률 (Pa)
        nu: 포아송비
        density: 밀도 (kg/m³)
        method: 해석 방법 (FEM / PD / SPG / COUPLED)
    """
    E: float
    nu: float
    density: float = 1000.0
    method: Method = Method.FEM


class AnatomyProfile(ABC):
    """부위별 해부학 프로파일 인터페이스.

    preprocessing.assembly.assemble() 함수에서 사용하며,
    라벨 → 재료/접촉 매핑을 제공한다.

    구현 예: SpineProfile (척추), KneeProfile (무릎) 등
    """

    @abstractmethod
    def get_material(self, label: int) -> MaterialProps:
        """라벨 → 재료 물성 반환.

        Args:
            label: 세그멘테이션 라벨 값

        Returns:
            해당 라벨의 재료 물성
        """

    @abstractmethod
    def get_contact_type(
        self, label_a: int, label_b: int,
    ) -> Optional[ContactType]:
        """인접 라벨 쌍 → 접촉 유형 반환.

        Args:
            label_a: 첫 번째 라벨
            label_b: 두 번째 라벨

        Returns:
            접촉 유형 (None이면 접촉 무시)
        """

    @abstractmethod
    def get_contact_params(
        self, label_a: int, label_b: int,
    ) -> dict:
        """인접 라벨 쌍 → 접촉 파라미터 반환.

        Args:
            label_a: 첫 번째 라벨
            label_b: 두 번째 라벨

        Returns:
            접촉 파라미터 dict (penalty, friction 등)
        """
