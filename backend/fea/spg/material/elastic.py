"""SPG 선형 탄성 재료 모델.

σ = λ·tr(ε)·I + 2μ·ε  (소변형 Cauchy 응력)

라메 매개변수:
  λ = Eν / ((1+ν)(1-2ν))     (3D)
  λ = Eν / ((1+ν)(1-ν))      (2D 평면변형)
  μ = E / (2(1+ν))
"""

import math


class SPGElasticMaterial:
    """SPG 선형 탄성 재료.

    Attributes:
        E: 영 계수 [Pa]
        nu: 푸아송 비
        rho: 밀도 [kg/m³]
        lam: 라메 제1 매개변수 λ
        mu: 전단 계수 μ (G)
        K: 체적 탄성 계수
    """

    def __init__(
        self,
        youngs_modulus: float,
        poisson_ratio: float,
        density: float = 1000.0,
        dim: int = 3
    ):
        """초기화.

        Args:
            youngs_modulus: 영 계수 E [Pa]
            poisson_ratio: 푸아송 비 ν
            density: 밀도 ρ [kg/m³]
            dim: 공간 차원
        """
        self.E = youngs_modulus
        self.nu = poisson_ratio
        self.rho = density
        self.dim = dim

        # 전단 계수
        self.mu = youngs_modulus / (2.0 * (1.0 + poisson_ratio))

        # 라메 제1 매개변수
        if dim == 3:
            self.lam = (youngs_modulus * poisson_ratio /
                        ((1.0 + poisson_ratio) * (1.0 - 2.0 * poisson_ratio)))
        else:
            # 2D 평면 변형
            self.lam = (youngs_modulus * poisson_ratio /
                        ((1.0 + poisson_ratio) * (1.0 - poisson_ratio)))

        # 체적 탄성 계수
        if dim == 3:
            self.K = youngs_modulus / (3.0 * (1.0 - 2.0 * poisson_ratio))
        else:
            self.K = youngs_modulus / (2.0 * (1.0 - poisson_ratio))

    def get_wave_speed(self) -> float:
        """P파 속도 계산.

        Returns:
            P파 속도 [m/s]
        """
        return math.sqrt((self.K + 4.0 * self.mu / 3.0) / self.rho)

    def estimate_stable_dt(self, spacing: float, safety: float = 0.3) -> float:
        """안정 시간 간격 추정.

        Δt = safety · Δx / c_p

        Args:
            spacing: 입자 간격
            safety: 안전 계수 (CFL 조건)

        Returns:
            안정 시간 간격
        """
        c_p = self.get_wave_speed()
        return safety * spacing / c_p

    def __repr__(self) -> str:
        return (f"SPGElasticMaterial(E={self.E:.2e}, ν={self.nu:.3f}, "
                f"ρ={self.rho:.1f}, λ={self.lam:.2e}, μ={self.mu:.2e})")
