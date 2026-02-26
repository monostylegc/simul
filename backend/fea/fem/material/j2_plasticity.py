"""J2 소성(von Mises) 재료 모델.

소변형 J2 소성 + 등방 경화:
- 항복 함수: f = √(3/2 · s:s) - σ_y(ε̄ᵖ) ≤ 0
- 유동 규칙: Δεᵖ = Δγ · n  (연합 유동)
- 등방 경화: σ_y = σ_y₀ + H · ε̄ᵖ

여기서:
- s = σ - (1/3)·tr(σ)·I  (편향 응력)
- n = s / ‖s‖  (유동 방향)
- Δγ  — 소성 승수 (return-mapping으로 결정)
- H   — 경화 계수 [Pa]
- ε̄ᵖ  — 등가 소성 변형률 (누적)

적용: 티타늄 나사/플레이트 (σ_y ≈ 880 MPa, H ≈ 1-5 GPa)

참고문헌:
- Simo & Hughes, "Computational Inelasticity" (1998), Ch. 3
- de Souza Neto et al., "Computational Methods for Plasticity" (2008)
"""

import taichi as ti
import numpy as np
from typing import Optional, TYPE_CHECKING

from .base import MaterialBase

if TYPE_CHECKING:
    from ..core.mesh import FEMesh


@ti.data_oriented
class J2Plasticity(MaterialBase):
    """J2 소성 재료 모델 (소변형, 등방 경화).

    Return-mapping 알고리즘:
    1. 탄성 시행 응력 계산
    2. 항복 함수 검사 (f > 0 → 소성)
    3. 소성 시 radial return 보정
    4. 상태 변수 업데이트 (소성 변형률, 등가 소성 변형률)
    """

    def __init__(
        self,
        youngs_modulus: float,
        poisson_ratio: float,
        yield_stress: float,
        hardening_modulus: float = 0.0,
        dim: int = 3,
    ):
        """초기화.

        Args:
            youngs_modulus: 영 계수 E [Pa]
            poisson_ratio: 푸아송 비 ν
            yield_stress: 초기 항복 응력 σ_y₀ [Pa]
            hardening_modulus: 등방 경화 계수 H [Pa] (0이면 완전 소성)
            dim: 공간 차원 (2 또는 3)
        """
        super().__init__(dim)

        # 입력 검증
        from ..validation import (
            validate_elastic_constants,
            validate_yield_stress,
            validate_hardening_modulus,
        )
        validate_elastic_constants(youngs_modulus, poisson_ratio, "J2Plasticity")
        validate_yield_stress(yield_stress, "J2Plasticity")
        validate_hardening_modulus(hardening_modulus, "J2Plasticity")

        self.E = youngs_modulus
        self.nu = poisson_ratio
        self.sigma_y0 = yield_stress
        self.H = hardening_modulus

        # Lamé 매개변수
        self.mu = youngs_modulus / (2.0 * (1.0 + poisson_ratio))
        self.lam = (
            youngs_modulus * poisson_ratio
            / ((1.0 + poisson_ratio) * (1.0 - 2.0 * poisson_ratio))
        )
        self.K_bulk = youngs_modulus / (3.0 * (1.0 - 2.0 * poisson_ratio))

        # Taichi 스칼라 필드 (커널에서 접근용)
        self._mu = ti.field(dtype=ti.f64, shape=())
        self._lam = ti.field(dtype=ti.f64, shape=())
        self._K = ti.field(dtype=ti.f64, shape=())
        self._sigma_y0 = ti.field(dtype=ti.f64, shape=())
        self._H = ti.field(dtype=ti.f64, shape=())
        self._mu[None] = self.mu
        self._lam[None] = self.lam
        self._K[None] = self.K_bulk
        self._sigma_y0[None] = yield_stress
        self._H[None] = hardening_modulus

        # 소성 상태 변수 필드 — 첫 compute_stress 호출 시 초기화
        self._ep_strain: Optional[ti.MatrixField] = None   # 소성 변형률 텐서 εᵖ (면내)
        self._epe: Optional[ti.ScalarField] = None          # 등가 소성 변형률 ε̄ᵖ
        self._ep33: Optional[ti.ScalarField] = None          # 면외 소성 변형률 εᵖ₃₃ (2D 전용)
        self._initialized = False

    def _ensure_state_initialized(self, n_gauss: int):
        """상태 변수 필드를 지연 초기화.

        가우스점 수가 결정된 후 (FEMesh 생성 후) 호출.

        Args:
            n_gauss: 전체 가우스점 수
        """
        if self._initialized:
            return
        self._ep_strain = ti.Matrix.field(
            self.dim, self.dim, dtype=ti.f64, shape=n_gauss
        )
        self._epe = ti.field(dtype=ti.f64, shape=n_gauss)
        self._ep_strain.fill(0)
        self._epe.fill(0)
        # 2D 평면변형: 면외 소성 변형률 εᵖ₃₃ 추적
        if self.dim == 2:
            self._ep33 = ti.field(dtype=ti.f64, shape=n_gauss)
            self._ep33.fill(0)
        self._initialized = True

    @property
    def is_linear(self) -> bool:
        """소성 재료는 비선형."""
        return False

    def get_elasticity_tensor(self) -> np.ndarray:
        """초기 탄성 텐서 (Voigt 표기).

        소성 발생 전/후 모두 탄성 C를 반환한다.
        Newton-Raphson 수렴은 탄성 접선으로도 가능하며 (수렴 속도만 느림),
        현재 assembly.py가 per-gauss-point C를 지원하지 않으므로
        초기 탄성 C를 사용한다.

        Returns:
            C: 6×6 (3D) 또는 3×3 (2D) 탄성 텐서
        """
        lam, mu = self.lam, self.mu

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

    # ─────────── 응력 계산 (return-mapping) ───────────

    def compute_stress(self, mesh: "FEMesh"):
        """Return-mapping 알고리즘으로 응력 업데이트.

        알고리즘 (Simo & Hughes, Box 3.1):
        1. 소변형률 ε 계산
        2. 탄성 시행 변형률: εᵉ_trial = ε - εᵖₙ
        3. 시행 응력: σ_trial = λ·tr(εᵉ)·I + 2μ·εᵉ
        4. 편향 시행 응력 및 등가 응력 계산 (3D 일관)
        5. 항복 판정 → radial return (소성 보정)

        2D 평면변형: σ₃₃ = λ·tr(εᵉ₃D) + 2μ·εᵉ₃₃ 를 고려하여
        3D 일관 von Mises를 계산한다.
        """
        n_gauss = mesh.n_elements * mesh.n_gauss
        self._ensure_state_initialized(n_gauss)

        if self.dim == 2:
            self._return_mapping_2d_kernel(
                mesh.F, mesh.stress, mesh.strain,
                self._ep_strain, self._epe, self._ep33, n_gauss,
            )
        else:
            self._return_mapping_3d_kernel(
                mesh.F, mesh.stress, mesh.strain,
                self._ep_strain, self._epe, n_gauss,
            )

    @ti.kernel
    def _return_mapping_3d_kernel(
        self,
        F: ti.template(),
        stress: ti.template(),
        strain: ti.template(),
        ep_strain: ti.template(),
        epe: ti.template(),
        n_gauss: int,
    ):
        """3D return-mapping 커널."""
        mu = self._mu[None]
        lam = self._lam[None]
        sigma_y0 = self._sigma_y0[None]
        H = self._H[None]

        for gp in range(n_gauss):
            Fg = F[gp]
            I = ti.Matrix.identity(ti.f64, 3)

            # 1. 소변형률: ε = 0.5·(F + Fᵀ) - I
            eps = 0.5 * (Fg + Fg.transpose()) - I

            # 2. 탄성 시행 변형률
            eps_e_trial = eps - ep_strain[gp]
            tr_eps_e = eps_e_trial.trace()

            # 3. 시행 응력: σ_trial = λ·tr(εᵉ)·I + 2μ·εᵉ
            sigma_trial = lam * tr_eps_e * I + 2.0 * mu * eps_e_trial

            # 4. 편향 시행 응력: s = σ - (1/3)tr(σ)·I
            tr_sigma = sigma_trial.trace()
            p = tr_sigma / 3.0
            s_trial = sigma_trial - p * I

            # von Mises: q = √(3/2)·‖s‖
            s_norm_sq = 0.0
            for i in ti.static(range(3)):
                for j in ti.static(range(3)):
                    s_norm_sq += s_trial[i, j] * s_trial[i, j]
            s_norm = ti.sqrt(ti.max(s_norm_sq, 1e-30))
            q_trial = ti.sqrt(1.5) * s_norm

            # 5. 항복 함수
            epe_n = epe[gp]
            sigma_y_current = sigma_y0 + H * epe_n
            f_trial = q_trial - sigma_y_current

            if f_trial <= 0.0:
                stress[gp] = sigma_trial
                strain[gp] = eps
            else:
                # Radial return
                dgamma = f_trial / (3.0 * mu + H)
                n_flow = s_trial / s_norm
                dep = ti.sqrt(1.5) * dgamma * n_flow
                ep_strain[gp] = ep_strain[gp] + dep
                epe[gp] = epe_n + dgamma

                factor = 1.0 - 3.0 * mu * dgamma / q_trial
                s_corrected = factor * s_trial
                sigma = p * I + s_corrected
                stress[gp] = sigma
                strain[gp] = eps

    @ti.kernel
    def _return_mapping_2d_kernel(
        self,
        F: ti.template(),
        stress: ti.template(),
        strain: ti.template(),
        ep_strain: ti.template(),
        epe: ti.template(),
        ep33: ti.template(),
        n_gauss: int,
    ):
        """2D 평면변형 return-mapping 커널.

        평면변형에서 ε₃₃=0이지만 σ₃₃ ≠ 0이므로,
        3D 일관 편향 응력과 von Mises를 계산한다.

        핵심:
        - εᵉ₃₃ = 0 - εᵖ₃₃ = -εᵖ₃₃
        - σ₃₃ = λ·tr(εᵉ₃D) + 2μ·εᵉ₃₃
        - 편향: 3D trace / 3 사용
        - ‖s‖에 s₃₃ 기여 포함
        """
        mu = self._mu[None]
        lam = self._lam[None]
        sigma_y0 = self._sigma_y0[None]
        H = self._H[None]

        for gp in range(n_gauss):
            Fg = F[gp]
            I2 = ti.Matrix.identity(ti.f64, 2)

            # 1. 소변형률 (면내 2×2)
            eps = 0.5 * (Fg + Fg.transpose()) - I2

            # 2. 탄성 시행 변형률 (면내)
            eps_e_2d = eps - ep_strain[gp]
            tr_eps_e_2d = eps_e_2d.trace()

            # 면외 탄성 변형률: εᵉ₃₃ = 0 - εᵖ₃₃
            ep33_n = ep33[gp]
            eps_e_33 = -ep33_n

            # 3D 탄성 변형률 trace
            tr_eps_e_3d = tr_eps_e_2d + eps_e_33

            # 3. 시행 응력 (면내 2×2)
            sigma_trial = lam * tr_eps_e_3d * I2 + 2.0 * mu * eps_e_2d

            # 면외 시행 응력: σ₃₃ = λ·tr(εᵉ₃D) + 2μ·εᵉ₃₃
            sigma_33 = lam * tr_eps_e_3d + 2.0 * mu * eps_e_33

            # 4. 편향 시행 응력 (3D 일관)
            tr_sigma_3d = sigma_trial.trace() + sigma_33
            p = tr_sigma_3d / 3.0

            # 면내 편향 (2×2)
            s_trial_2d = sigma_trial - p * I2
            # 면외 편향
            s_33 = sigma_33 - p

            # ‖s‖ (3D): s₁₁² + s₂₂² + s₃₃² + 2·s₁₂²
            s_norm_sq = s_33 * s_33
            for i in ti.static(range(2)):
                for j in ti.static(range(2)):
                    s_norm_sq += s_trial_2d[i, j] * s_trial_2d[i, j]
            s_norm = ti.sqrt(ti.max(s_norm_sq, 1e-30))
            q_trial = ti.sqrt(1.5) * s_norm

            # 5. 항복 함수
            epe_n = epe[gp]
            sigma_y_current = sigma_y0 + H * epe_n
            f_trial = q_trial - sigma_y_current

            if f_trial <= 0.0:
                stress[gp] = sigma_trial
                strain[gp] = eps
            else:
                # Radial return
                dgamma = f_trial / (3.0 * mu + H)

                # 유동 방향 (면내): n_2D = s_2D / ‖s‖
                n_flow_2d = s_trial_2d / s_norm
                # 유동 방향 (면외): n_33 = s_33 / ‖s‖
                n_33 = s_33 / s_norm

                # 소성 변형률 증분 (면내)
                dep_2d = ti.sqrt(1.5) * dgamma * n_flow_2d
                ep_strain[gp] = ep_strain[gp] + dep_2d

                # 면외 소성 변형률 증분
                dep_33 = ti.sqrt(1.5) * dgamma * n_33
                ep33[gp] = ep33_n + dep_33

                # 등가 소성 변형률
                epe[gp] = epe_n + dgamma

                # 보정된 응력 (면내)
                factor = 1.0 - 3.0 * mu * dgamma / q_trial
                s_corrected_2d = factor * s_trial_2d
                sigma = p * I2 + s_corrected_2d

                stress[gp] = sigma
                strain[gp] = eps

    # ─────────── 내부 절점력 ───────────

    def compute_nodal_forces(self, mesh: "FEMesh"):
        """내부 절점력 계산 (소변형 B-matrix 방식)."""
        mesh.f.fill(0)
        self._compute_forces_kernel(
            mesh.elements, mesh.dNdX, mesh.stress,
            mesh.gauss_vol, mesh.f,
            mesh.n_elements, mesh.n_gauss, mesh.nodes_per_elem,
        )

    @ti.kernel
    def _compute_forces_kernel(
        self,
        elements: ti.template(),
        dNdX: ti.template(),
        stress: ti.template(),
        gauss_vol: ti.template(),
        f: ti.template(),
        n_elements: int,
        n_gauss: int,
        nodes_per_elem: int,
    ):
        """내부력 커널: f_a = - Σ_gp σ · (dN_a/dX) · vol."""
        dim = ti.static(self.dim)
        for e in range(n_elements):
            for g in range(n_gauss):
                gp_idx = e * n_gauss + g
                sigma = stress[gp_idx]
                dN = dNdX[gp_idx]
                vol = gauss_vol[gp_idx]

                for a in range(nodes_per_elem):
                    node = elements[e][a]
                    f_a = ti.Vector.zero(ti.f64, dim)
                    for i in ti.static(range(dim)):
                        for j in ti.static(range(dim)):
                            f_a[i] -= sigma[i, j] * dN[a, j] * vol
                    ti.atomic_add(f[node], f_a)

    # ─────────── 변형 에너지 ───────────

    @ti.func
    def strain_energy_density(self, eps, ep):
        """변형 에너지 밀도 (탄성부분만).

        ψ = 0.5 · εᵉ : C : εᵉ  여기서 εᵉ = ε - εᵖ
        """
        mu = self._mu[None]
        lam = self._lam[None]
        eps_e = eps - ep
        tr_eps_e = eps_e.trace()
        eps_e_sq = 0.0
        dim = ti.static(self.dim)
        for i in ti.static(range(dim)):
            for j in ti.static(range(dim)):
                eps_e_sq += eps_e[i, j] * eps_e[i, j]
        return 0.5 * lam * tr_eps_e**2 + mu * eps_e_sq

    @ti.kernel
    def compute_total_energy(
        self,
        strain: ti.template(),
        gauss_vol: ti.template(),
        n_gauss: int,
    ) -> ti.f64:
        """총 탄성 변형 에너지 계산."""
        energy = 0.0
        for gp in range(n_gauss):
            psi = self.strain_energy_density(strain[gp], self._ep_strain[gp])
            energy += psi * gauss_vol[gp]
        return energy

    # ─────────── 결과 추출 ───────────

    def get_plastic_strain(self) -> np.ndarray:
        """등가 소성 변형률 배열 반환 (가우스점별).

        Returns:
            epe: (n_gauss,) 등가 소성 변형률
        """
        if self._epe is not None:
            return self._epe.to_numpy()
        return np.array([])

    def get_plastic_strain_tensor(self) -> np.ndarray:
        """소성 변형률 텐서 반환 (가우스점별).

        Returns:
            ep: (n_gauss, dim, dim)
        """
        if self._ep_strain is not None:
            return self._ep_strain.to_numpy()
        return np.array([])

    def get_von_mises_stress(self, mesh: "FEMesh") -> np.ndarray:
        """각 가우스점의 von Mises 등가 응력 반환 (3D 일관).

        2D 평면변형에서도 σ₃₃을 고려한 정확한 3D von Mises를 계산한다.

        Args:
            mesh: FEMesh (응력이 계산된 상태)

        Returns:
            (n_gauss,) von Mises 응력 배열 [Pa]
        """
        stress_np = mesh.stress.to_numpy()
        n_gauss = len(stress_np)

        if n_gauss == 0:
            return np.array([])

        vm = np.zeros(n_gauss)

        if self.dim == 3:
            # 3D: 표준 공식
            for gp in range(n_gauss):
                s = stress_np[gp]
                p = (s[0, 0] + s[1, 1] + s[2, 2]) / 3.0
                d = np.array([s[0, 0] - p, s[1, 1] - p, s[2, 2] - p])
                vm[gp] = np.sqrt(1.5 * (
                    d[0]**2 + d[1]**2 + d[2]**2
                    + 2 * (s[0, 1]**2 + s[0, 2]**2 + s[1, 2]**2)
                ))
        else:
            # 2D 평면변형: σ₃₃ 복원 후 3D von Mises
            strain_np = mesh.strain.to_numpy()
            ep_np = self._ep_strain.to_numpy() if self._ep_strain is not None else np.zeros_like(strain_np)
            ep33_np = self._ep33.to_numpy() if self._ep33 is not None else np.zeros(n_gauss)

            for gp in range(n_gauss):
                s = stress_np[gp]
                # 탄성 변형률 복원
                eps_e_2d = strain_np[gp] - ep_np[gp]
                eps_e_33 = -ep33_np[gp]
                tr_eps_e_3d = eps_e_2d[0, 0] + eps_e_2d[1, 1] + eps_e_33
                sigma_33 = self.lam * tr_eps_e_3d + 2.0 * self.mu * eps_e_33

                p = (s[0, 0] + s[1, 1] + sigma_33) / 3.0
                d11 = s[0, 0] - p
                d22 = s[1, 1] - p
                d33 = sigma_33 - p
                vm[gp] = np.sqrt(1.5 * (
                    d11**2 + d22**2 + d33**2 + 2 * s[0, 1]**2
                ))
        return vm

    def get_yield_status(self) -> np.ndarray:
        """각 가우스점의 항복 여부 (0=탄성, 1=항복).

        Returns:
            (n_gauss,) 0 또는 1 배열
        """
        epe = self.get_plastic_strain()
        if epe.size == 0:
            return np.array([])
        return (epe > 1e-12).astype(np.float64)

    def reset_state(self):
        """소성 상태 변수를 초기값으로 리셋."""
        if self._ep_strain is not None:
            self._ep_strain.fill(0)
        if self._epe is not None:
            self._epe.fill(0)
        if self._ep33 is not None:
            self._ep33.fill(0)

    def __repr__(self) -> str:
        return (
            f"J2Plasticity(E={self.E:.2e}, ν={self.nu:.3f}, "
            f"σ_y={self.sigma_y0:.2e}, H={self.H:.2e})"
        )
