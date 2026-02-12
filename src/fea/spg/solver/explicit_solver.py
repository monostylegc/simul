"""SPG 명시적 동적/준정적 솔버.

Velocity Verlet 시간 적분 + 운동 에너지 감쇠(준정적 해석용).
NOSB-PD 솔버와 동일한 인터페이스를 유지한다.

시간 적분 루프:
1. 위치 업데이트: x^{n+1/2} = x^n + v·Δt + 0.5·a·Δt²
2. 변형 구배 F 계산
3. 응력 σ 계산
4. 내부력 f^{int} 계산 (DNI + 안정화)
5. 본드 파괴 검사 (선택)
6. 가속도: a = (f^{ext} - f^{int}) / m
7. 속도 업데이트: v^{n+1} = v^n + 0.5·(a^n + a^{n+1})·Δt
"""

import taichi as ti
import numpy as np
from typing import Optional, Callable, TYPE_CHECKING

_sync = getattr(ti, 'sync', lambda: None)

if TYPE_CHECKING:
    from ..core.particles import SPGParticleSystem
    from ..core.kernel import SPGKernel
    from ..core.bonds import SPGBondSystem
    from ..core.spg_compute import SPGCompute
    from ..material.elastic import SPGElasticMaterial


@ti.data_oriented
class SPGExplicitSolver:
    """SPG 명시적 솔버.

    명시적 시간 적분 + 운동 감쇠로 준정적/동적 해석을 수행한다.
    """

    def __init__(
        self,
        particles: "SPGParticleSystem",
        kernel: "SPGKernel",
        bonds: "SPGBondSystem",
        material: "SPGElasticMaterial",
        stabilization: float = 0.1,
        dt: float = None,
        viscous_damping: float = 0.0,
        failure_stretch: float = None,
        failure_strain: float = None
    ):
        """초기화.

        Args:
            particles: SPG 입자 시스템
            kernel: SPG 커널/형상함수
            bonds: SPG 본드 시스템
            material: 재료 모델
            stabilization: 안정화 매개변수 η
            dt: 시간 간격 (None이면 자동 계산)
            viscous_damping: 점성 감쇠 계수
            failure_stretch: 본드 신장 파괴 기준 (None이면 파괴 비활성)
            failure_strain: 유효 소성 변형률 파괴 기준 (None이면 비활성)
        """
        from ..core.spg_compute import SPGCompute

        self.particles = particles
        self.kernel = kernel
        self.bonds = bonds
        self.material = material
        self.dim = particles.dim
        self.n_particles = particles.n_particles

        # SPG 연산 모듈
        self.spg_compute = SPGCompute(particles, kernel, bonds, stabilization)

        # 안정화 본드 상수 설정
        self.spg_compute.set_stabilization_modulus(
            material.E, kernel.support_radius,
            dim=particles.dim
        )

        # 재료 매개변수
        self.lam = ti.field(dtype=ti.f64, shape=())
        self.mu = ti.field(dtype=ti.f64, shape=())
        self.lam[None] = material.lam
        self.mu[None] = material.mu

        # Per-particle 재료 상수 초기화 (단일 재료)
        particles.set_material_constants(material.lam, material.mu)

        # 시간 간격 (형상함수 기울기 기반 spectral radius 추정)
        if dt is None:
            dt = self._estimate_stable_dt(material, particles, kernel, safety=0.5)
        self.dt = dt

        # 감쇠
        self.viscous_damping = ti.field(dtype=ti.f64, shape=())
        self.viscous_damping[None] = viscous_damping

        # 파괴 기준
        self.failure_stretch = failure_stretch
        self.failure_strain = failure_strain

        # 수렴 추적
        self.prev_ke = 0.0
        self.ke_increasing = True
        self.iteration = 0

    @staticmethod
    def _estimate_stable_dt(material, particles, kernel, safety=0.5):
        """형상함수 기울기 기반 안정 시간 간격 추정.

        강성 행렬의 spectral radius를 형상함수 기울기 크기로부터 추정한다.
        k_max ≈ (λ+2μ) * max_i(|dpsi_sum_i|² + Σ_k |dpsi[i,k]|²) * V_i
        dt_crit = 2 / sqrt(k_max / m), dt = safety * dt_crit
        """
        dpsi_np = kernel.dpsi.to_numpy()
        n_nbr_np = kernel.n_neighbors.to_numpy()
        vol_np = particles.volume.to_numpy()
        mass_np = particles.mass.to_numpy()

        modulus = material.lam + 2 * material.mu
        n = particles.n_particles
        dim = particles.dim

        lambda_max = 0.0
        for i in range(n):
            if mass_np[i] < 1e-30:
                continue

            # dpsi_sum (자기 기울기 기여)
            dpsi_sum = np.zeros(dim)
            dpsi_sq_sum = 0.0
            for k in range(n_nbr_np[i]):
                dpsi_k = dpsi_np[i, k]
                dpsi_sum += dpsi_k
                dpsi_sq_sum += np.sum(dpsi_k ** 2)

            # 자기 기여 + scatter 기여 모두 포함
            dpsi_sum_sq = np.sum(dpsi_sum ** 2)
            k_eff = modulus * vol_np[i] * (dpsi_sum_sq + dpsi_sq_sum)
            lam_i = k_eff / mass_np[i]
            lambda_max = max(lambda_max, lam_i)

        if lambda_max > 0:
            dt_crit = 2.0 / np.sqrt(lambda_max)
        else:
            dt_crit = material.estimate_stable_dt(
                kernel.support_radius / 2.0, safety=1.0
            )

        return safety * dt_crit

    @ti.kernel
    def _velocity_verlet_step1(self, dt: ti.f64):
        """위치 업데이트 (Velocity Verlet 1단계)."""
        for i in range(self.n_particles):
            if self.particles.fixed[i] == 0:
                self.particles.u[i] += (
                    self.particles.v[i] * dt +
                    0.5 * self.particles.a[i] * dt * dt
                )
                self.particles.x[i] = self.particles.X[i] + self.particles.u[i]

    @ti.kernel
    def _velocity_verlet_step2(self, dt: ti.f64) -> ti.f64:
        """속도 업데이트 + 감쇠 (Velocity Verlet 2단계).

        Returns:
            운동 에너지
        """
        ke = 0.0
        damping = 1.0 - self.viscous_damping[None]

        for i in range(self.n_particles):
            if self.particles.fixed[i] == 0 and self.particles.mass[i] > 1e-30:
                # 가속도 = (외부력 - 내부력) / 질량
                net_force = self.particles.f_ext[i] - self.particles.f_int[i]
                a_new = net_force / self.particles.mass[i]

                # 속도 업데이트
                self.particles.v[i] += 0.5 * (self.particles.a[i] + a_new) * dt
                self.particles.v[i] *= damping
                self.particles.a[i] = a_new

                # 운동 에너지
                v_sq = self.particles.v[i].dot(self.particles.v[i])
                ke += 0.5 * self.particles.mass[i] * v_sq
            else:
                self.particles.v[i] = ti.Vector.zero(ti.f64, self.dim)
                self.particles.a[i] = ti.Vector.zero(ti.f64, self.dim)
        return ke

    @ti.kernel
    def _reset_velocities(self):
        """속도 초기화 (운동 감쇠용)."""
        for i in range(self.n_particles):
            self.particles.v[i] = ti.Vector.zero(ti.f64, self.dim)

    def compute_forces(self):
        """내부력 계산 (변형 구배 → 변형률 → 응력 → 내부력 → 안정화).

        재료 상수는 particles.lam_param, particles.mu_param에서 읽는다.
        """
        self.spg_compute.compute_deformation_gradient()
        self.spg_compute.compute_strain()
        self.spg_compute.compute_internal_force_with_stabilization()

    def check_failure(self):
        """본드 파괴 검사."""
        if self.failure_stretch is not None:
            self.bonds.check_bond_failure_stretch(
                self.particles.x,
                self.kernel.neighbors,
                self.kernel.n_neighbors,
                self.failure_stretch
            )

        if self.failure_strain is not None:
            self.bonds.check_bond_failure_plastic_strain(
                self.particles.eff_plastic_strain,
                self.kernel.neighbors,
                self.kernel.n_neighbors,
                self.failure_strain
            )

        # 손상도 업데이트
        self.bonds.compute_damage(
            self.particles.damage,
            self.kernel.n_neighbors
        )

    def step(self) -> dict:
        """1 시간 스텝 수행.

        Returns:
            스텝 정보 (운동에너지, 잔차 등)
        """
        # 1. 위치 업데이트
        self._velocity_verlet_step1(self.dt)

        # 2. 내부력 계산
        self.compute_forces()

        # 3. 본드 파괴 검사
        if self.failure_stretch is not None or self.failure_strain is not None:
            self.check_failure()

        # 4. 속도 업데이트
        ke = float(self._velocity_verlet_step2(self.dt))
        _sync()

        # 5. 운동 감쇠 (준정적 해석)
        velocity_reset = False
        if ke < self.prev_ke and self.ke_increasing:
            self._reset_velocities()
            ke = 0.0
            velocity_reset = True
            self.ke_increasing = False
        elif ke > self.prev_ke:
            self.ke_increasing = True

        self.prev_ke = ke
        self.iteration += 1

        residual = float(self.spg_compute.compute_residual_norm())
        _sync()

        return {
            "kinetic_energy": ke,
            "residual": residual,
            "velocity_reset": velocity_reset
        }

    def solve(
        self,
        max_iterations: int = 100000,
        tol: float = 1e-6,
        verbose: bool = True,
        print_interval: int = 5000
    ) -> dict:
        """준정적 평형 구하기.

        Args:
            max_iterations: 최대 반복 수
            tol: 상대 잔차 허용 오차
            verbose: 진행 출력
            print_interval: 출력 간격

        Returns:
            수렴 정보
        """
        self._reset_velocities()
        self.iteration = 0
        self.prev_ke = 0.0
        self.ke_increasing = True

        # 기준 잔차
        self.compute_forces()
        _sync()
        ref_residual = float(self.spg_compute.compute_residual_norm())
        _sync()
        if ref_residual < 1e-30:
            ref_residual = 1.0

        if verbose:
            print(f"SPG 솔버: E={self.material.E:.2e}, ν={self.material.nu:.3f}")
            print(f"dt={self.dt:.2e}, 안정화 η={self.spg_compute.eta[None]:.2f}")
            print(f"기준 잔차: {ref_residual:.2e}")

        converged = False
        info = {"residual": ref_residual, "kinetic_energy": 0.0, "velocity_reset": False}

        for it in range(max_iterations):
            info = self.step()
            rel_residual = info["residual"] / ref_residual

            if verbose and it % print_interval == 0:
                disp = self.particles.get_displacements()
                max_u = np.max(np.abs(disp))
                print(f"Iter {it:6d}: res={info['residual']:.2e}, "
                      f"rel={rel_residual:.2e}, KE={info['kinetic_energy']:.2e}, "
                      f"max_u={max_u:.6f}")

            if rel_residual < tol:
                converged = True
                if verbose:
                    print(f"\n수렴 완료: {self.iteration}회 반복")
                break

        if not converged and verbose:
            print(f"\n{max_iterations}회 반복 후 미수렴")

        return {
            "converged": converged,
            "iterations": self.iteration,
            "residual": info["residual"],
            "relative_residual": info["residual"] / ref_residual
        }
