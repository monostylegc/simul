"""NOSB-PD solver with quasi-static capability.

Implements Non-Ordinary State-Based Peridynamics with:
- Correspondence material model (arbitrary Poisson's ratio)
- Zero-energy mode stabilization
- Kinetic damping for quasi-static analysis
"""

import taichi as ti
import numpy as np
from typing import Optional, Callable, TYPE_CHECKING

# Import ti.sync for GPU synchronization
_sync = getattr(ti, 'sync', lambda: None)

if TYPE_CHECKING:
    from ..core.particles import ParticleSystem
    from ..core.bonds import BondSystem
    from ..core.nosb import NOSBCompute, NOSBMaterial


@ti.data_oriented
class NOSBSolver:
    """NOSB-PD solver for quasi-static and dynamic problems.

    Uses correspondence material formulation with optional stabilization.
    """

    def __init__(
        self,
        particles: "ParticleSystem",
        bonds: "BondSystem",
        material: "NOSBMaterial",
        horizon: float,
        stabilization: float = 0.1,
        dt: float = None,
        viscous_damping: float = 0.0
    ):
        """Initialize NOSB solver.

        Args:
            particles: ParticleSystem instance
            bonds: BondSystem instance
            material: NOSBMaterial with E, ν
            horizon: Peridynamics horizon
            stabilization: Zero-energy mode stabilization (0-1, recommend 0.05-0.15)
            dt: Time step (auto-computed if None)
            viscous_damping: Viscous damping coefficient (0-1, recommend 0.1-0.5 for quasi-static)
        """
        from ..core.nosb import NOSBCompute

        self.particles = particles
        self.bonds = bonds
        self.material = material
        self.dim = particles.dim
        self.n_particles = particles.n_particles
        self.horizon = horizon

        # NOSB computation module
        self.nosb = NOSBCompute(particles, bonds, stabilization)

        # Material parameters as fields
        self.K = ti.field(dtype=ti.f64, shape=())
        self.mu = ti.field(dtype=ti.f64, shape=())
        self.c_bond = ti.field(dtype=ti.f64, shape=())

        self.K[None] = material.get_bulk_modulus()
        self.mu[None] = material.get_shear_modulus()

        # Per-particle 재료 상수 초기화 (단일 재료)
        particles.set_material_constants(self.K[None], self.mu[None])

        # Set stabilization modulus
        material.set_stabilization_modulus(horizon)
        self.c_bond[None] = material.c_bond if material.c_bond else 0.0

        # Compute shape tensor (once, unless bonds break)
        self.nosb.compute_shape_tensor()

        # Time step
        if dt is None:
            dt = self._estimate_stable_dt()
        self.dt = dt

        # Viscous damping coefficient
        self.viscous_damping = ti.field(dtype=ti.f64, shape=())
        self.viscous_damping[None] = viscous_damping

        # For kinetic damping
        self.prev_ke = 0.0
        self.ke_increasing = True
        self.iteration = 0

    def _estimate_stable_dt(self) -> float:
        """안정 시간 간격 추정 (스펙트럴 반경 방법).

        SPG 솔버와 동일한 방법론: K_inv 기반 유효 강성으로부터
        spectral radius를 추정한다.
        k_eff = (λ+2μ) · V_i · (|dpsi_sum|² + Σ|dpsi_k|²)
        dt_crit = 2 / √(k_eff_max / m), safety factor 0.5
        """
        K_inv_np = self.particles.K_inv.to_numpy()
        xi_np = self.bonds.xi.to_numpy()
        omega_np = self.bonds.omega.to_numpy()
        n_nbr_np = self.bonds.n_neighbors.to_numpy()
        vol_np = self.particles.volume.to_numpy()
        mass_np = self.particles.mass.to_numpy()
        broken_np = self.bonds.broken.to_numpy()

        K_val = float(self.K[None])
        mu_val = float(self.mu[None])
        if self.dim == 3:
            lam = K_val - 2.0 * mu_val / 3.0
        else:
            lam = K_val - mu_val
        modulus = lam + 2.0 * mu_val

        n = self.n_particles
        dim = self.dim

        lambda_max = 0.0
        for i in range(n):
            if mass_np[i] < 1e-30:
                continue

            # 유효 형상함수 기울기 추정: ω · K_inv · ξ
            K_inv_i = K_inv_np[i]
            dpsi_sum = np.zeros(dim)
            dpsi_sq_sum = 0.0

            for k in range(n_nbr_np[i]):
                if broken_np[i, k] == 0:
                    xi_k = xi_np[i, k, :dim]
                    w_k = omega_np[i, k]
                    # 형상함수 기울기 근사: dpsi_k ≈ ω · K_inv · ξ · V_j
                    dpsi_k = w_k * K_inv_i @ xi_k
                    dpsi_sum += dpsi_k
                    dpsi_sq_sum += np.sum(dpsi_k ** 2)

            dpsi_sum_sq = np.sum(dpsi_sum ** 2)
            k_eff = modulus * vol_np[i] * (dpsi_sum_sq + dpsi_sq_sum)
            lam_i = k_eff / mass_np[i]
            lambda_max = max(lambda_max, lam_i)

        if lambda_max > 0:
            dt_crit = 2.0 / np.sqrt(lambda_max)
            return 0.5 * dt_crit
        else:
            # 폴백: 보수적 CFL
            rho = np.mean(self.particles.density.to_numpy())
            avg_vol = np.mean(vol_np)
            c_wave = np.sqrt((K_val + 4 * mu_val / 3) / (rho + 1e-20))
            spacing = np.power(avg_vol, 1.0 / self.dim) if self.dim == 3 else np.sqrt(avg_vol)
            return 0.1 * spacing / (c_wave + 1e-20)

    @ti.kernel
    def _velocity_verlet_step1(self, dt: ti.f64):
        """Position update."""
        for i in range(self.n_particles):
            if self.particles.fixed[i] == 0:
                self.particles.x[i] += self.particles.v[i] * dt + \
                    0.5 * self.particles.a[i] * dt * dt

    @ti.kernel
    def _velocity_verlet_step2(self, dt: ti.f64) -> ti.f64:
        """Velocity update with viscous damping. Returns kinetic energy."""
        ke = 0.0
        damping = 1.0 - self.viscous_damping[None]  # Damping factor per step
        for i in range(self.n_particles):
            if self.particles.fixed[i] == 0 and self.particles.mass[i] > 1e-20:
                a_new = self.particles.f[i] / self.particles.mass[i]
                self.particles.v[i] += 0.5 * (self.particles.a[i] + a_new) * dt
                # Apply viscous damping
                self.particles.v[i] *= damping
                self.particles.a[i] = a_new

                v_sq = self.particles.v[i].dot(self.particles.v[i])
                ke += 0.5 * self.particles.mass[i] * v_sq
            else:
                self.particles.v[i] = ti.Vector.zero(ti.f64, self.dim)
                self.particles.a[i] = ti.Vector.zero(ti.f64, self.dim)
        return ke

    @ti.kernel
    def _reset_velocities(self):
        """Reset velocities to zero."""
        for i in range(self.n_particles):
            self.particles.v[i] = ti.Vector.zero(ti.f64, self.dim)

    @ti.kernel
    def _compute_residual_norm(self) -> ti.f64:
        """Compute residual force norm."""
        norm_sq = 0.0
        for i in range(self.n_particles):
            if self.particles.fixed[i] == 0:
                f_sq = self.particles.f[i].dot(self.particles.f[i])
                norm_sq += f_sq
        return ti.sqrt(norm_sq)

    def compute_forces(self, external_force_func: Optional[Callable] = None):
        """Compute all forces.

        Args:
            external_force_func: Optional external force function
        """
        # Compute deformation gradient
        self.nosb.compute_deformation_gradient()

        # Compute internal forces with stabilization (per-particle 재료 사용)
        self.nosb.compute_force_state_with_stabilization(
            self.c_bond[None]
        )

        # Apply external forces
        if external_force_func is not None:
            external_force_func()

    def step(self, external_force_func: Optional[Callable] = None) -> dict:
        """Perform one time step with kinetic damping.

        Args:
            external_force_func: Optional external force function

        Returns:
            Iteration info dictionary
        """
        # Position update
        self._velocity_verlet_step1(self.dt)

        # Compute forces
        self.compute_forces(external_force_func)

        # Velocity update
        ke = float(self._velocity_verlet_step2(self.dt))
        _sync()  # GPU synchronization

        # Kinetic damping
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

        residual = float(self._compute_residual_norm())
        _sync()  # GPU synchronization
        return {
            "kinetic_energy": ke,
            "residual": residual,
            "velocity_reset": velocity_reset
        }

    def update_shape_tensor(self):
        """Recompute shape tensor after bond breaking."""
        self.nosb.compute_shape_tensor()

    def solve(
        self,
        external_force_func: Optional[Callable] = None,
        max_iterations: int = 100000,
        tol: float = 1e-6,
        verbose: bool = True,
        print_interval: int = 5000
    ) -> dict:
        """Solve for quasi-static equilibrium.

        Args:
            external_force_func: External force function
            max_iterations: Maximum iterations
            tol: Relative residual tolerance
            verbose: Print progress
            print_interval: Print interval

        Returns:
            Convergence info
        """
        self._reset_velocities()
        self.iteration = 0
        self.prev_ke = 0.0
        self.ke_increasing = True

        # Reference residual
        self.compute_forces(external_force_func)
        _sync()  # GPU synchronization
        ref_residual = float(self._compute_residual_norm())
        _sync()  # GPU synchronization
        if ref_residual < 1e-20:
            ref_residual = 1.0

        if verbose:
            print(f"NOSB-PD Solver: E={self.material.E:.2e}, ν={self.material.nu:.3f}")
            print(f"dt={self.dt:.2e}, stabilization={self.nosb.G_s[None]:.2f}")
            print(f"Reference residual: {ref_residual:.2e}")

        converged = False
        reset_count = 0

        for it in range(max_iterations):
            info = self.step(external_force_func)

            if info["velocity_reset"]:
                reset_count += 1

            rel_residual = info["residual"] / ref_residual

            if verbose and it % print_interval == 0:
                disp = self.particles.get_displacements()
                max_u = np.max(np.abs(disp))
                print(f"Iter {it:6d}: res={info['residual']:.2e}, "
                      f"rel={rel_residual:.2e}, KE={info['kinetic_energy']:.2e}, "
                      f"max_u={max_u:.4f}, resets={reset_count}")

            if rel_residual < tol:
                converged = True
                if verbose:
                    print(f"\nConverged in {self.iteration} iterations")
                break

        if not converged and verbose:
            print(f"\nDid not converge in {max_iterations} iterations")

        return {
            "converged": converged,
            "iterations": self.iteration,
            "residual": info["residual"],
            "relative_residual": rel_residual
        }
