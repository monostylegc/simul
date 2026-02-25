"""통합 재료 정의.

세 솔버(FEM, PD, SPG)에 공통으로 사용할 수 있는 재료 데이터 클래스.
각 솔버의 내부 재료 객체는 지연 생성한다.

구성 모델:
- linear_elastic: 소변형 선형 탄성 (기본값)
- neo_hookean: 대변형 압축성 Neo-Hookean (FEM 전용)
- mooney_rivlin: 2-파라미터 Mooney-Rivlin 초탄성 (FEM 전용)
- ogden: 1-항 Ogden 초탄성 (FEM 전용)
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
        constitutive_model: 구성 모델 ("linear_elastic", "neo_hookean", "mooney_rivlin", "ogden")
        C10: Mooney-Rivlin 제1상수 [Pa]
        C01: Mooney-Rivlin 제2상수 [Pa]
        D1: 비압축성 파라미터 (MR/Ogden 공통) [1/Pa]
        mu_ogden: Ogden 전단 계수 [Pa]
        alpha_ogden: Ogden 지수
    """
    E: float
    nu: float
    density: float = 1000.0
    dim: int = 2
    plane_stress: bool = False

    # 구성 모델 선택
    constitutive_model: str = "linear_elastic"

    # 초탄성 파라미터 (선택적)
    C10: Optional[float] = None       # Mooney-Rivlin
    C01: Optional[float] = None       # Mooney-Rivlin
    D1: Optional[float] = None        # 비압축성 (MR, Ogden 공통)
    mu_ogden: Optional[float] = None  # Ogden
    alpha_ogden: Optional[float] = None  # Ogden

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
        """구성 모델에 따라 FEM 재료 객체 분기 생성."""
        if self.constitutive_model == "neo_hookean":
            from ..fem.material.neo_hookean import NeoHookean
            return NeoHookean(
                youngs_modulus=self.E,
                poisson_ratio=self.nu,
                dim=self.dim,
            )
        elif self.constitutive_model == "mooney_rivlin":
            from ..fem.material.mooney_rivlin import MooneyRivlin
            if self.C10 is not None and self.C01 is not None:
                return MooneyRivlin(
                    self.C10, self.C01, self.D1 or 0.0, dim=self.dim,
                )
            # E/ν에서 자동 변환
            return MooneyRivlin.from_engineering(self.E, self.nu, dim=self.dim)
        elif self.constitutive_model == "ogden":
            from ..fem.material.ogden import Ogden
            if self.mu_ogden is not None and self.alpha_ogden is not None:
                return Ogden(
                    self.mu_ogden, self.alpha_ogden, self.D1 or 0.0, dim=self.dim,
                )
            # E/ν에서 자동 변환
            return Ogden.from_engineering(self.E, self.nu, dim=self.dim)
        else:
            # 기본값: linear_elastic
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
