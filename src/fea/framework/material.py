"""통합 재료 정의.

세 솔버(FEM, PD, SPG)에 공통으로 사용할 수 있는 재료 데이터 클래스.
각 솔버의 내부 재료 객체는 지연 생성한다.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Material:
    """통합 재료 데이터 클래스.

    Args:
        E: 영 계수 [Pa]
        nu: 푸아송 비
        density: 밀도 [kg/m³]
        dim: 공간 차원 (2 또는 3)
        plane_stress: 2D 평면응력 여부 (FEM 전용)
    """
    E: float
    nu: float
    density: float = 1000.0
    dim: int = 2
    plane_stress: bool = False

    # Lamé 매개변수 (초기화 후 자동 계산)
    lam: float = field(init=False, repr=False)
    mu: float = field(init=False, repr=False)
    K_bulk: float = field(init=False, repr=False)

    def __post_init__(self):
        """Lamé 매개변수 및 체적 탄성 계수 계산."""
        self.mu = self.E / (2.0 * (1.0 + self.nu))
        if self.dim == 2 and not self.plane_stress:
            # 평면변형 Lamé 매개변수
            self.lam = self.E * self.nu / ((1.0 + self.nu) * (1.0 - 2.0 * self.nu))
        else:
            # 3D 또는 평면응력
            self.lam = self.E * self.nu / ((1.0 + self.nu) * (1.0 - 2.0 * self.nu))
        self.K_bulk = self.E / (3.0 * (1.0 - 2.0 * self.nu))

    def _create_fem_material(self):
        """FEM LinearElastic 재료 객체 지연 생성."""
        from ..fem.material.linear_elastic import LinearElastic
        return LinearElastic(
            youngs_modulus=self.E,
            poisson_ratio=self.nu,
            dim=self.dim,
            plane_stress=self.plane_stress,
        )

    def _create_nosb_material(self):
        """NOSB-PD 재료 객체 지연 생성."""
        from ..peridynamics.core.nosb import NOSBMaterial
        return NOSBMaterial(self.E, self.nu, dim=self.dim)

    def _create_spg_material(self):
        """SPG 재료 객체 지연 생성."""
        from ..spg.material.elastic import SPGElasticMaterial
        return SPGElasticMaterial(
            self.E, self.nu, self.density, dim=self.dim
        )
