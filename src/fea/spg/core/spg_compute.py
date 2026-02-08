"""SPG 핵심 계산 커널 - 내부력, 변형 구배, 안정화.

SPG 방법의 핵심 연산:
1. 변형 구배 F = I + Σ_J (u_J - u_I) ⊗ ∇Ψ_J(X_I)
2. 재료 응력 계산 (Cauchy 응력)
3. 내부력: Galerkin DNI 공식
   f_K = -σ_K · (Σ_m ∇Ψ_m(X_K)) · V_K  (자기 기여)
        + Σ_I σ_I · ∇Ψ_K(X_I) · V_I    (이웃 기여, scatter)
4. 본드 기반 안정화 (zero-energy mode 제어)

참고: Wu et al. (2013), US Patent 20150112653A1
"""

import taichi as ti
import numpy as np
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .particles import SPGParticleSystem
    from .kernel import SPGKernel
    from .bonds import SPGBondSystem


@ti.data_oriented
class SPGCompute:
    """SPG 핵심 계산 모듈.

    직접 절점 적분(DNI)을 사용한 Galerkin 내부력 계산.
    변형 구배에 상대 변위(u_J - u_I)를 사용하여
    자기 형상함수 기울기(self-gradient) 항을 암묵적으로 처리한다.
    """

    def __init__(
        self,
        particles: "SPGParticleSystem",
        kernel: "SPGKernel",
        bonds: "SPGBondSystem",
        stabilization: float = 0.1
    ):
        """초기화.

        Args:
            particles: SPG 입자 시스템
            kernel: SPG 커널
            bonds: SPG 본드 시스템
            stabilization: 안정화 매개변수 G_s (0.05~0.5 권장)
        """
        self.particles = particles
        self.kernel = kernel
        self.bonds = bonds
        self.dim = particles.dim
        self.n_particles = particles.n_particles

        # 안정화 매개변수
        self.G_s = ti.field(dtype=ti.f64, shape=())
        self.G_s[None] = stabilization

        # 본드 안정화 상수 (재료에 맞게 설정 필요)
        self.c_bond = ti.field(dtype=ti.f64, shape=())
        self.c_bond[None] = 0.0

    def set_stabilization_modulus(self, E: float, support_radius: float,
                                  dim: int = 3, thickness: float = 1.0):
        """안정화 본드 상수 설정.

        Galerkin 내부력 대비 적절한 비율의 안정화 강성을 설정한다.
        c = E / h 스케일로 설정 (PD 마이크로 모듈러스 대신).

        Args:
            E: 영 계수
            support_radius: 지지 반경
            dim: 차원
            thickness: 두께 (2D용)
        """
        # E/h 스케일 (Galerkin 강성 대비 적절한 비율)
        c = E / support_radius
        self.c_bond[None] = c

    @ti.kernel
    def compute_deformation_gradient(self):
        """변형 구배 F 계산.

        이웃 목록이 자기 자신을 제외하므로, 상대 변위를 사용:
        F_I = I + Σ_J (u_J - u_I) ⊗ ∇Ψ_J(X_I)

        이것은 Σ_J ∇Ψ_J(X_I) = 0 (자기 포함, partition of unity 미분)
        조건에서 자기 항을 암묵적으로 포함한다:
        ∇Ψ_I(X_I) = -Σ_{J≠I} ∇Ψ_J(X_I)
        """
        for i in range(self.n_particles):
            F = ti.Matrix.identity(ti.f64, self.dim)
            u_i = self.particles.u[i]

            n_nbr = self.kernel.n_neighbors[i]
            for k in range(n_nbr):
                if self.bonds.broken[i, k] == 0:
                    j = self.kernel.neighbors[i, k]
                    # 상대 변위 (핵심 수정)
                    du = self.particles.u[j] - u_i
                    dpsi_j = self.kernel.dpsi[i, k]

                    # F += (u_J - u_I) ⊗ ∇Ψ_J(X_I)
                    for m in ti.static(range(self.dim)):
                        for n in ti.static(range(self.dim)):
                            F[m, n] += du[m] * dpsi_j[n]

            self.particles.F[i] = F

    @ti.kernel
    def compute_strain(self):
        """소변형 변형률 텐서 계산.

        ε = 0.5 · (F + F^T) - I
        """
        for i in range(self.n_particles):
            F = self.particles.F[i]
            I = ti.Matrix.identity(ti.f64, self.dim)
            self.particles.strain[i] = 0.5 * (F + F.transpose()) - I

    @ti.kernel
    def compute_stress(self, lam: ti.f64, mu: ti.f64):
        """Cauchy 응력 계산.

        σ = λ·tr(ε)·I + 2μ·ε

        Args:
            lam: 라메 제1 매개변수 λ
            mu: 전단 계수 μ
        """
        for i in range(self.n_particles):
            eps = self.particles.strain[i]
            tr_eps = eps.trace()
            I = ti.Matrix.identity(ti.f64, self.dim)
            self.particles.stress[i] = lam * tr_eps * I + 2.0 * mu * eps

    @ti.kernel
    def compute_internal_force_scatter(self):
        """Galerkin DNI 내부력 계산 (scatter 방식).

        정확한 Galerkin DNI 공식:
          f_K = Σ_I σ_I · ∇Ψ_K(X_I) · V_I

        자기 항 (I=K): ∇Ψ_K(X_K) = -Σ_{m} ∇Ψ_m(X_K)
          f_K += -σ_K · (Σ_m dpsi[K,m]) · V_K

        이웃 항 (I≠K): scatter 연산
          f_K += Σ_I σ_I · dpsi[I, k_KI] · V_I
        dpsi[I, k] = ∇Ψ_J(X_I) 이므로, I에서 이웃 J에 scatter:
          f_J += σ_I · dpsi[I, k] · V_I
        """
        # 1단계: 자기 기여 (self-contribution)
        # f_I = -σ_I · (Σ_k ∇Ψ_Jk(X_I)) · V_I
        for i in range(self.n_particles):
            dpsi_sum = ti.Vector.zero(ti.f64, self.dim)
            n_nbr = self.kernel.n_neighbors[i]
            for k in range(n_nbr):
                if self.bonds.broken[i, k] == 0:
                    dpsi_sum += self.kernel.dpsi[i, k]

            sigma_i = self.particles.stress[i]
            V_i = self.particles.volume[i]
            self.particles.f_int[i] = -(sigma_i @ dpsi_sum) * V_i

        # 2단계: 이웃 기여 (scatter)
        # 입자 I의 응력을 이웃 J에 분배:
        # f_J += σ_I · ∇Ψ_J(X_I) · V_I
        for i in range(self.n_particles):
            sigma_i = self.particles.stress[i]
            V_i = self.particles.volume[i]

            n_nbr = self.kernel.n_neighbors[i]
            for k in range(n_nbr):
                if self.bonds.broken[i, k] == 0:
                    j = self.kernel.neighbors[i, k]
                    dpsi_j_at_i = self.kernel.dpsi[i, k]
                    contrib = sigma_i @ dpsi_j_at_i * V_i

                    # scatter: atomic add
                    for d in ti.static(range(self.dim)):
                        ti.atomic_add(self.particles.f_int[j][d], contrib[d])

    @ti.kernel
    def compute_stabilization_force(self):
        """대칭 본드 기반 안정화력 (zero-energy mode 제어).

        본드 신장 기반 대칭 안정화:
        f_stab = G_s · c · s · ω · (η/|η|) · V_j

        여기서:
          s = (|η| - |ξ|) / |ξ|  (본드 신장)
          ω = 영향 함수 가중치
          η = x_j - x_i  (현재 본드 벡터)

        이 공식은 뉴턴 제3법칙을 만족하여 대칭 강성 행렬을 보장한다.
        """
        G_s = self.G_s[None]
        c = self.c_bond[None]

        if c > 0.0:
            for i in range(self.n_particles):
                n_nbr = self.kernel.n_neighbors[i]
                for k in range(n_nbr):
                    if self.bonds.broken[i, k] == 0:
                        j = self.kernel.neighbors[i, k]
                        V_j = self.particles.volume[j]

                        xi_len = self.bonds.xi_length[i, k]
                        eta = self.particles.x[j] - self.particles.x[i]
                        eta_len = eta.norm()

                        if eta_len > 1e-15 and xi_len > 1e-15:
                            stretch = (eta_len - xi_len) / xi_len
                            # 영향 함수: ω = max(0, 1 - |ξ|/h)
                            h = self.kernel.h[None]
                            omega = ti.max(0.0, 1.0 - xi_len / h)
                            # 부호 반전: f_int 규약에서 안정화력은
                            # 변형에 저항(복원)해야 하므로 음의 부호
                            f_stab = G_s * c * stretch * omega * (eta / eta_len) * V_j

                            for d in ti.static(range(self.dim)):
                                ti.atomic_sub(self.particles.f_int[i][d], f_stab[d])

    def compute_internal_force_with_stabilization(
        self,
        lam: float,
        mu: float
    ):
        """응력 계산 → 내부력(DNI) → 안정화를 순차 실행.

        Args:
            lam: 라메 제1 매개변수
            mu: 전단 계수
        """
        self.compute_stress(lam, mu)
        self.compute_internal_force_scatter()
        self.compute_stabilization_force()

    @ti.kernel
    def compute_residual_norm(self) -> ti.f64:
        """잔차력 노름 계산.

        R = f_ext - f_int (자유 입자만)
        """
        norm_sq = 0.0
        for i in range(self.n_particles):
            if self.particles.fixed[i] == 0:
                r = self.particles.f_ext[i] - self.particles.f_int[i]
                norm_sq += r.dot(r)
        return ti.sqrt(norm_sq)
