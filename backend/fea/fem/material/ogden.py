"""Ogden 초탄성 재료 모델 (1-항).

변형 에너지 밀도 (1-term):
ψ = (μ/α)·(λ₁^α + λ₂^α + λ₃^α - 3) + (1/D1)·(J - 1)²

여기서:
- λ₁, λ₂, λ₃  — 주연신비 (F의 특이값)
- μ  — 전단 계수 [Pa]
- α  — Ogden 지수 (무차원)
- D1  — 비압축성 파라미터 (D1 = 2/K) [1/Pa]

특수 케이스:
- α = 2  → Neo-Hookean과 동치
- α < 2  → 연질 조직 (디스크, 인대)에 적합한 S자 응력-변형 곡선
- α > 2  → 경질 고분자에 적합

Cauchy 주응력 (비압축 부분):
σᵢ = (μ/J)·λᵢ^α - p   (i = 1, 2, 3)

참고문헌:
- Ogden, "Large deformation isotropic elasticity" (1972)
- Holzapfel, "Nonlinear Solid Mechanics"
"""

import taichi as ti
import numpy as np
from typing import TYPE_CHECKING

from .base import MaterialBase

if TYPE_CHECKING:
    from ..core.mesh import FEMesh


@ti.data_oriented
class Ogden(MaterialBase):
    """1-항 Ogden 초탄성 재료."""

    def __init__(
        self,
        mu: float,
        alpha: float,
        D1: float,
        dim: int = 3,
    ):
        """Ogden 재료 초기화.

        Args:
            mu: 전단 계수 [Pa]
            alpha: Ogden 지수. alpha=2 → Neo-Hookean
            D1: 비압축성 파라미터 (D1 = 2/K) [1/Pa]
            dim: 공간 차원
        """
        super().__init__(dim)

        # 입력 검증
        from ..validation import validate_ogden
        validate_ogden(mu, alpha, D1)

        self.mu_val = mu
        self.alpha_val = alpha
        self.D1_val = D1

        # 공학적 상수 역변환 (표시용)
        self.mu = mu
        self.nu = 0.3  # 근사 기본값
        if D1 > 0:
            K = 2.0 / D1
            self.nu = (3.0 * K - 2.0 * mu) / (6.0 * K + 2.0 * mu) if (6.0 * K + 2.0 * mu) != 0 else 0.3
        self.E = 2.0 * mu * (1.0 + self.nu)

        # Taichi 필드
        self._mu = ti.field(dtype=ti.f64, shape=())
        self._alpha = ti.field(dtype=ti.f64, shape=())
        self._D1 = ti.field(dtype=ti.f64, shape=())
        self._mu[None] = mu
        self._alpha[None] = alpha
        self._D1[None] = D1

    @staticmethod
    def from_engineering(
        E: float,
        nu: float,
        alpha: float = 2.0,
        dim: int = 3,
    ) -> "Ogden":
        """공학적 상수(E, ν)에서 Ogden 파라미터 변환.

        Args:
            E: 영 계수 [Pa]
            nu: 푸아송 비
            alpha: Ogden 지수 (기본 2.0 → Neo-Hookean 동치)
            dim: 공간 차원

        변환:
            μ = E / (2·(1+ν))
            K = E / (3·(1-2ν))
            D1 = 2/K
        """
        mu = E / (2.0 * (1.0 + nu))
        K = E / (3.0 * (1.0 - 2.0 * nu))
        D1 = 2.0 / K if K > 0 else 0.0
        return Ogden(mu, alpha, D1, dim=dim)

    @property
    def is_linear(self) -> bool:
        return False

    def get_elasticity_tensor(self) -> np.ndarray:
        """초기 접선 탄성 텐서 (F=I 기준, 선형화).

        α=2 기준 Neo-Hookean과 동일.
        """
        mu = self.mu_val
        if self.D1_val > 0:
            K = 2.0 / self.D1_val
            lam = K - 2.0 * mu / 3.0
        else:
            lam = mu

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
        """변형 구배에서 Cauchy 응력 계산.

        주연신비 기반 Ogden 응력을 Cauchy 텐서로 변환.
        """
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

        방법: B = F·Fᵀ의 고유값 분해 → 주연신비 λᵢ → 주응력 → Cauchy 텐서
        σ = Σᵢ σᵢ · (nᵢ ⊗ nᵢ)
        """
        mu = self._mu[None]
        alpha = self._alpha[None]
        D1 = self._D1[None]
        dim = ti.static(self.dim)

        for gp in range(n_gauss):
            Fg = F[gp]
            J = Fg.determinant()
            J_safe = ti.max(J, 1e-8)

            # 좌 Cauchy-Green: B = F·Fᵀ
            B = Fg @ Fg.transpose()

            if ti.static(dim == 3):
                # 3D: B의 고유값 분해로 주연신비² 추출
                # 특성방정식: λ³ - I1·λ² + I2·λ - I3 = 0
                I1 = B[0, 0] + B[1, 1] + B[2, 2]
                I2 = (B[0, 0] * B[1, 1] + B[1, 1] * B[2, 2] + B[0, 0] * B[2, 2]
                       - B[0, 1] ** 2 - B[1, 2] ** 2 - B[0, 2] ** 2)
                I3 = B.determinant()

                # Cardano 해법으로 주연신비² (λi²) 계산
                p = I2 - I1 * I1 / 3.0
                q = 2.0 * I1 * I1 * I1 / 27.0 - I1 * I2 / 3.0 + I3
                disc = q * q / 4.0 + p * p * p / 27.0

                # 실수 세 근 (disc ≤ 0)
                lam2_1 = 1.0
                lam2_2 = 1.0
                lam2_3 = 1.0

                if disc < 0.0:
                    r = ti.sqrt(ti.max(-p / 3.0, 0.0))
                    cos_theta = -q / (2.0 * r * r * r + 1e-30)
                    cos_theta = ti.min(ti.max(cos_theta, -1.0), 1.0)
                    theta = ti.acos(cos_theta) / 3.0
                    shift = I1 / 3.0

                    lam2_1 = shift + 2.0 * r * ti.cos(theta)
                    lam2_2 = shift + 2.0 * r * ti.cos(theta - 2.0 * 3.14159265358979 / 3.0)
                    lam2_3 = shift + 2.0 * r * ti.cos(theta + 2.0 * 3.14159265358979 / 3.0)
                else:
                    # 거의 등방적 변형: B ≈ λ²·I
                    avg = I1 / 3.0
                    lam2_1 = avg
                    lam2_2 = avg
                    lam2_3 = avg

                # 주연신비 (양수 보장)
                l1 = ti.sqrt(ti.max(lam2_1, 1e-16))
                l2 = ti.sqrt(ti.max(lam2_2, 1e-16))
                l3 = ti.sqrt(ti.max(lam2_3, 1e-16))

                # 등방(isochoric) 부분: λ̄ᵢ = J^(-1/3)·λᵢ
                J_m13 = ti.pow(J_safe, -1.0 / 3.0)
                lb1 = J_m13 * l1
                lb2 = J_m13 * l2
                lb3 = J_m13 * l3

                # Ogden 주응력 (편향 부분)
                # τᵢ = μ·λ̄ᵢ^α (Kirchhoff 주응력)
                t1 = mu * ti.pow(lb1, alpha)
                t2 = mu * ti.pow(lb2, alpha)
                t3 = mu * ti.pow(lb3, alpha)
                t_avg = (t1 + t2 + t3) / 3.0

                # 편향 Cauchy 주응력: σᵢ_dev = (tᵢ - t_avg) / J
                s1 = (t1 - t_avg) / J_safe
                s2 = (t2 - t_avg) / J_safe
                s3 = (t3 - t_avg) / J_safe

                # 체적 응력
                p_vol = 0.0
                if D1 > 1e-20:
                    p_vol = (2.0 / D1) * (J_safe - 1.0)

                # Cauchy 텐서 재조립: σ = Σ (σᵢ + p)·(nᵢ⊗nᵢ)
                # B의 고유벡터 근사 — isotropic 응력 공식 사용
                # σ = (2/J)·(β0·I + β1·B + β2·B²) 형태로 근사
                # 여기서는 등방 응력 공식 직접 사용:
                # σ = (s1 + p_vol)·(B - lam2_2·I)(B - lam2_3·I)/(...) + 순환
                # → 간소화: Ogden 응력을 B 기반으로 직접 계산

                # B 기반 Cauchy 응력 재조립 (Ogden isotropic representation)
                I_mat = ti.Matrix.identity(ti.f64, 3)

                # Rivlin-Ericksen 표현: σ = β0·I + β1·B + β₋₁·B⁻¹
                B_inv = B.inverse()

                # β 계수 결정 (3개 주응력 → 3개 β)
                # σᵢ = β0 + β1·λᵢ² + β₋₁/λᵢ²
                # [1,λ₁²,1/λ₁²] [β0]   [s1+p_vol]
                # [1,λ₂²,1/λ₂²] [β1] = [s2+p_vol]
                # [1,λ₃²,1/λ₃²] [β₋1]  [s3+p_vol]
                A = ti.Matrix([
                    [1.0, lam2_1, 1.0 / ti.max(lam2_1, 1e-16)],
                    [1.0, lam2_2, 1.0 / ti.max(lam2_2, 1e-16)],
                    [1.0, lam2_3, 1.0 / ti.max(lam2_3, 1e-16)],
                ], dt=ti.f64)

                rhs = ti.Vector([s1 + p_vol, s2 + p_vol, s3 + p_vol], dt=ti.f64)

                det_A = A.determinant()
                if ti.abs(det_A) > 1e-20:
                    beta = A.inverse() @ rhs
                    sigma = beta[0] * I_mat + beta[1] * B + beta[2] * B_inv
                else:
                    # 등방 변형: σ = (s1 + p_vol)·I
                    sigma = (s1 + p_vol) * I_mat

                stress[gp] = sigma

            else:
                # 2D 간소화: B의 2x2 고유값 분해
                I1_2d = B[0, 0] + B[1, 1]
                I2_2d = B.determinant()

                disc_2d = I1_2d * I1_2d - 4.0 * I2_2d
                disc_2d = ti.max(disc_2d, 0.0)
                sqrt_disc = ti.sqrt(disc_2d)

                lam2_1 = (I1_2d + sqrt_disc) / 2.0
                lam2_2 = (I1_2d - sqrt_disc) / 2.0

                l1 = ti.sqrt(ti.max(lam2_1, 1e-16))
                l2 = ti.sqrt(ti.max(lam2_2, 1e-16))

                J_m12 = ti.pow(J_safe, -0.5)
                lb1 = J_m12 * l1
                lb2 = J_m12 * l2

                t1 = mu * ti.pow(lb1, alpha)
                t2 = mu * ti.pow(lb2, alpha)
                t_avg = (t1 + t2) / 2.0

                s1 = (t1 - t_avg) / J_safe
                s2 = (t2 - t_avg) / J_safe

                p_vol = 0.0
                if D1 > 1e-20:
                    p_vol = (2.0 / D1) * (J_safe - 1.0)

                I_mat = ti.Matrix.identity(ti.f64, 2)
                B_inv = B.inverse()

                A = ti.Matrix([
                    [1.0, lam2_1],
                    [1.0, lam2_2],
                ], dt=ti.f64)
                rhs = ti.Vector([s1 + p_vol, s2 + p_vol], dt=ti.f64)

                det_A = A.determinant()
                if ti.abs(det_A) > 1e-20:
                    beta = A.inverse() @ rhs
                    sigma = beta[0] * I_mat + beta[1] * B
                else:
                    sigma = (s1 + p_vol) * I_mat

                stress[gp] = sigma

    def compute_nodal_forces(self, mesh: "FEMesh"):
        """내부 절점력 계산.

        대변형: f_a = - Σ_gp P · (dN_a/dX) · det(J₀) · w
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

        ψ = (μ/α)·(λ₁^α + λ₂^α + λ₃^α - 3) + (1/D1)·(J-1)²
        """
        mu = self._mu[None]
        alpha = self._alpha[None]
        D1 = self._D1[None]

        J = F.determinant()
        J_safe = ti.max(J, 1e-8)

        # 좌 Cauchy-Green
        B = F @ F.transpose()
        I1 = B.trace()

        # 간소화된 에너지: isochoric 주연신비 기반
        # ψ_dev ≈ (μ/α)·(I1_bar^(α/2) ... ) — 근사 사용
        # 정확한 계산은 SVD 필요하므로, I1 기반 근사 사용:
        J_m23 = ti.pow(J_safe, -2.0 / 3.0)
        I1_bar = J_m23 * I1

        # alpha=2일 때 정확히 Neo-Hookean:
        # ψ = (μ/2)·(I1_bar - 3)
        psi = (mu / alpha) * (ti.pow(I1_bar / 3.0, alpha / 2.0) * 3.0 - 3.0)

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
        return f"Ogden(μ={self.mu_val:.4e}, α={self.alpha_val:.2f}, D1={self.D1_val:.4e})"
