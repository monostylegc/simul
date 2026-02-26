"""Mooney-Rivlin 초탄성 재료 모델 (2-파라미터).

변형 에너지 밀도:
ψ = C10·(I₁ - 3) + C01·(I₂ - 3) + (1/D1)·(J - 1)²

여기서:
- I₁ = tr(C) = tr(FᵀF)  — 제1불변량
- I₂ = 0.5·[I₁² - tr(C²)]  — 제2불변량
- J = det(F)  — 체적비
- C10, C01  — Mooney-Rivlin 재료 상수
- D1  — 비압축성 파라미터 (D1 = 2/K, K는 체적 탄성 계수)

Cauchy 응력:
σ = (2/J)·[(C10 + C01·I₁)·B - C01·B² + (J/D1)·(J-1)·I]

특수 케이스:
- C01 = 0 → Neo-Hookean과 동치 (C10 = μ/2)
- 연조직, 디스크, 인대 등 생체 조직에 적합

참고문헌:
- Rivlin & Saunders, "Large elastic deformations of isotropic materials" (1951)
- Bonet & Wood, "Nonlinear Continuum Mechanics for FEA"
"""

import taichi as ti
import numpy as np
from typing import TYPE_CHECKING

from .base import MaterialBase

if TYPE_CHECKING:
    from ..core.mesh import FEMesh


@ti.data_oriented
class MooneyRivlin(MaterialBase):
    """2-파라미터 Mooney-Rivlin 초탄성 재료."""

    def __init__(
        self,
        C10: float,
        C01: float,
        D1: float,
        dim: int = 3,
    ):
        """Mooney-Rivlin 재료 초기화.

        Args:
            C10: 제1 Mooney-Rivlin 상수 [Pa]
            C01: 제2 Mooney-Rivlin 상수 [Pa]
            D1: 비압축성 파라미터 (D1 = 2/K) [1/Pa]
            dim: 공간 차원
        """
        super().__init__(dim)

        # 입력 검증
        from ..validation import validate_mooney_rivlin
        validate_mooney_rivlin(C10, C01, D1)

        self.C10_val = C10
        self.C01_val = C01
        self.D1_val = D1

        # 공학적 상수 역변환 (표시용)
        self.mu = 2.0 * (C10 + C01)
        self.E = 2.0 * self.mu * (1.0 + 0.3)  # 근사: nu≈0.3 가정
        self.nu = 0.3  # 근사값

        if D1 > 0:
            K = 2.0 / D1
            self.nu = (3.0 * K - self.mu) / (6.0 * K + self.mu) if (6.0 * K + self.mu) != 0 else 0.3
            self.E = 2.0 * self.mu * (1.0 + self.nu)

        # Taichi 필드
        self._C10 = ti.field(dtype=ti.f64, shape=())
        self._C01 = ti.field(dtype=ti.f64, shape=())
        self._D1 = ti.field(dtype=ti.f64, shape=())
        self._C10[None] = C10
        self._C01[None] = C01
        self._D1[None] = D1

    @staticmethod
    def from_engineering(
        E: float,
        nu: float,
        beta: float = 0.5,
        dim: int = 3,
    ) -> "MooneyRivlin":
        """공학적 상수(E, ν)에서 Mooney-Rivlin 파라미터 자동 변환.

        Args:
            E: 영 계수 [Pa]
            nu: 푸아송 비
            beta: C10/C01 비율 (0~1). beta=1 → Neo-Hookean, beta=0.5 → 균등 분배
            dim: 공간 차원

        변환:
            μ = E / (2·(1+ν))
            C10 = (μ/2)·β
            C01 = (μ/2)·(1-β)
            K = E / (3·(1-2ν))
            D1 = 2/K
        """
        mu = E / (2.0 * (1.0 + nu))
        K = E / (3.0 * (1.0 - 2.0 * nu))
        C10 = (mu / 2.0) * beta
        C01 = (mu / 2.0) * (1.0 - beta)
        D1 = 2.0 / K if K > 0 else 0.0
        return MooneyRivlin(C10, C01, D1, dim=dim)

    @property
    def is_linear(self) -> bool:
        return False

    def get_elasticity_tensor(self) -> np.ndarray:
        """초기 접선 탄성 텐서 (F=I 기준, 선형화).

        Neo-Hookean과 동일한 구조 (μ = 2·(C10+C01)).
        """
        mu = 2.0 * (self.C10_val + self.C01_val)
        # Lamé λ 역산: D1 > 0이면 K = 2/D1, λ = K - 2μ/3
        if self.D1_val > 0:
            K = 2.0 / self.D1_val
            lam = K - 2.0 * mu / 3.0
        else:
            lam = mu  # 근사

        if self.dim == 3:
            C = np.zeros((6, 6))
            C[0, 0] = C[1, 1] = C[2, 2] = lam + 2 * mu
            C[0, 1] = C[0, 2] = C[1, 2] = lam
            C[1, 0] = C[2, 0] = C[2, 1] = lam
            C[3, 3] = C[4, 4] = C[5, 5] = mu
            return C
        else:
            C = np.zeros((3, 3))
            C[0, 0] = C[1, 1] = lam + 2 * mu
            C[0, 1] = C[1, 0] = lam
            C[2, 2] = mu
            return C

    def compute_stress(self, mesh: "FEMesh"):
        """변형 구배에서 Cauchy 응력 계산."""
        self._compute_stress_kernel(
            mesh.F,
            mesh.stress,
            mesh.n_elements * mesh.n_gauss,
        )

    @ti.kernel
    def _compute_stress_kernel(
        self,
        F: ti.template(),
        stress: ti.template(),
        n_gauss: int,
    ):
        """모든 가우스점에서 Cauchy 응력 계산.

        σ = (2/J)·[(C10 + C01·I₁)·B - C01·B² + (J/D1)·(J-1)·I]

        여기서:
        - B = F·Fᵀ  (좌 Cauchy-Green 텐서)
        - I₁ = tr(B)
        """
        C10 = self._C10[None]
        C01 = self._C01[None]
        D1 = self._D1[None]
        dim = ti.static(self.dim)

        for gp in range(n_gauss):
            Fg = F[gp]
            J = Fg.determinant()
            J_safe = ti.max(J, 1e-8)

            # 좌 Cauchy-Green: B = F·Fᵀ
            B = Fg @ Fg.transpose()
            I = ti.Matrix.identity(ti.f64, dim)
            I1 = B.trace()

            # B² = B·B
            B2 = B @ B

            # Cauchy 응력
            # σ = (2/J)·[(C10 + C01·I1)·B - C01·B² ] + (2·J/D1)·(J-1)·I  (체적 항)
            sigma = (2.0 / J_safe) * ((C10 + C01 * I1) * B - C01 * B2)

            # 체적 페널티 항 (D1 > 0일 때)
            if D1 > 1e-20:
                sigma += (2.0 * J_safe / D1) * (J_safe - 1.0) * I

            stress[gp] = sigma

    def compute_nodal_forces(self, mesh: "FEMesh"):
        """내부 절점력 계산.

        대변형: f_a = - Σ_gp P · (dN_a/dX) · det(J₀) · w
        여기서 P = J·σ·F⁻ᵀ (제1 Piola-Kirchhoff 응력)
        """
        mesh.f.fill(0)
        self._compute_forces_kernel(
            mesh.elements,
            mesh.F,
            mesh.dNdX,
            mesh.stress,
            mesh.gauss_vol,
            mesh.f,
            mesh.n_elements,
            mesh.n_gauss,
            mesh.nodes_per_elem,
        )

    @ti.kernel
    def _compute_forces_kernel(
        self,
        elements: ti.template(),
        F: ti.template(),
        dNdX: ti.template(),
        stress: ti.template(),
        gauss_vol: ti.template(),
        f: ti.template(),
        n_elements: int,
        n_gauss: int,
        nodes_per_elem: int,
    ):
        """내부력 계산 (모든 요소 타입 지원)."""
        dim = ti.static(self.dim)
        for e in range(n_elements):
            for g in range(n_gauss):
                gp_idx = e * n_gauss + g
                Fg = F[gp_idx]
                sigma = stress[gp_idx]
                dN = dNdX[gp_idx]
                vol = gauss_vol[gp_idx]

                J = Fg.determinant()
                J_safe = ti.max(J, 1e-8)

                # 제1 Piola-Kirchhoff: P = J·σ·F⁻ᵀ
                F_inv_T = Fg.inverse().transpose()
                P = J_safe * sigma @ F_inv_T

                # 모든 노드에 대해 내부력 누적
                for a in range(nodes_per_elem):
                    node = elements[e][a]
                    f_a = ti.Vector.zero(ti.f64, dim)
                    for i in ti.static(range(dim)):
                        for j in ti.static(range(dim)):
                            f_a[i] -= P[i, j] * dN[a, j] * vol

                    ti.atomic_add(f[node], f_a)

    @ti.func
    def strain_energy_density(self, F):
        """변형 에너지 밀도 계산.

        ψ = C10·(I₁ - 3) + C01·(I₂ - 3) + (1/D1)·(J - 1)²
        """
        C10 = self._C10[None]
        C01 = self._C01[None]
        D1 = self._D1[None]

        J = F.determinant()
        J_safe = ti.max(J, 1e-8)

        # 우 Cauchy-Green: C = FᵀF
        C = F.transpose() @ F
        I1 = C.trace()

        # I₂ = 0.5·(I₁² - tr(C²))
        C2 = C @ C
        I2 = 0.5 * (I1 * I1 - C2.trace())

        psi = C10 * (I1 - 3.0) + C01 * (I2 - 3.0)
        if D1 > 1e-20:
            psi += (1.0 / D1) * (J_safe - 1.0) ** 2

        return psi

    @ti.kernel
    def compute_total_energy(
        self,
        F: ti.template(),
        gauss_vol: ti.template(),
        n_gauss: int,
    ) -> ti.f64:
        """총 변형 에너지 계산."""
        energy = 0.0
        for gp in range(n_gauss):
            psi = self.strain_energy_density(F[gp])
            energy += psi * gauss_vol[gp]
        return energy

    def __repr__(self) -> str:
        return f"MooneyRivlin(C10={self.C10_val:.4e}, C01={self.C01_val:.4e}, D1={self.D1_val:.4e})"
