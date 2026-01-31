"""Quasi-static solver using kinetic damping method.

Based on peridynamics literature for quasi-static simulations.
Uses kinetic energy peak detection to reset velocities.
"""

import taichi as ti
import numpy as np
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.particles import ParticleSystem
    from ..core.bonds import BondSystem
    from ..core.damage import DamageModel


@ti.data_oriented
class QuasiStaticSolver:
    """Quasi-static solver using kinetic damping.

    Algorithm:
    1. Compute forces
    2. Update velocities with explicit scheme
    3. Update positions
    4. Monitor kinetic energy - when KE peaks, reset velocities to zero
    5. Repeat until force residual < tolerance
    """

    def __init__(
        self,
        particles: "ParticleSystem",
        bonds: "BondSystem",
        micromodulus: float,
        dt: float = None
    ):
        """Initialize quasi-static solver.

        Args:
            particles: ParticleSystem instance
            bonds: BondSystem instance
            micromodulus: Material micromodulus constant c
            dt: Time step (auto-computed if None)
        """
        self.particles = particles
        self.bonds = bonds
        self.dim = particles.dim
        self.n_particles = particles.n_particles

        # Store micromodulus
        self.c = ti.field(dtype=ti.f32, shape=())
        self.c[None] = micromodulus

        # Compute stable time step if not provided
        if dt is None:
            dt = self._estimate_stable_dt()
        self.dt = dt

        # For kinetic damping
        self.prev_ke = 0.0
        self.ke_increasing = True

        # Iteration counter
        self.iteration = 0

    def _estimate_stable_dt(self) -> float:
        """Estimate stable time step based on CFL condition."""
        # Get average volume and mass
        vol = self.particles.volume.to_numpy()
        mass = self.particles.mass.to_numpy()

        avg_vol = np.mean(vol)
        avg_mass = np.mean(mass)

        # Estimate spacing from volume
        if self.dim == 2:
            spacing = np.sqrt(avg_vol)
        else:
            spacing = np.power(avg_vol, 1.0/3.0)

        # Approximate wave speed from micromodulus
        # c ~ 9E / (pi * h * delta^3) for 2D
        # Wave speed ~ sqrt(E/rho) ~ sqrt(c * delta^3 * pi * h / (9 * rho))
        # Simplified: dt ~ safety * sqrt(m / (c * V))
        c = float(self.c[None])
        dt = 0.1 * np.sqrt(avg_mass / (c * avg_vol + 1e-20))

        # Limit to reasonable range
        dt = max(1e-12, min(dt, 1e-4))

        return dt

    @ti.kernel
    def _compute_bond_forces(self):
        """Compute internal forces from bonds."""
        # Reset forces
        for i in range(self.n_particles):
            self.particles.f[i] = ti.Vector.zero(ti.f32, self.dim)

        # Compute bond forces
        for i in range(self.n_particles):
            for k in range(self.bonds.n_neighbors[i]):
                if self.bonds.broken[i, k] == 0:
                    j = self.bonds.neighbors[i, k]

                    eta = self.particles.x[j] - self.particles.x[i]
                    eta_len = eta.norm()

                    if eta_len > 1e-10:
                        xi_len = self.bonds.xi_length[i, k]
                        stretch = (eta_len - xi_len) / xi_len

                        omega = self.bonds.omega[i, k]
                        f_mag = self.c[None] * stretch * omega * self.particles.volume[j]

                        f_vec = f_mag * (eta / eta_len)
                        self.particles.f[i] += f_vec

    @ti.kernel
    def _velocity_verlet_step1(self, dt: ti.f32):
        """Velocity Verlet step 1: update positions."""
        for i in range(self.n_particles):
            if self.particles.fixed[i] == 0:
                # x(t+dt) = x(t) + v(t)*dt + 0.5*a(t)*dt^2
                self.particles.x[i] += self.particles.v[i] * dt + \
                    0.5 * self.particles.a[i] * dt * dt

    @ti.kernel
    def _velocity_verlet_step2(self, dt: ti.f32) -> ti.f32:
        """Velocity Verlet step 2: update velocities. Returns kinetic energy."""
        ke = 0.0
        for i in range(self.n_particles):
            if self.particles.fixed[i] == 0 and self.particles.mass[i] > 1e-20:
                # a(t+dt) = f(t+dt) / m
                a_new = self.particles.f[i] / self.particles.mass[i]

                # v(t+dt) = v(t) + 0.5*(a(t) + a(t+dt))*dt
                self.particles.v[i] += 0.5 * (self.particles.a[i] + a_new) * dt

                # Store new acceleration
                self.particles.a[i] = a_new

                # Kinetic energy
                v_sq = self.particles.v[i].dot(self.particles.v[i])
                ke += 0.5 * self.particles.mass[i] * v_sq
            else:
                self.particles.v[i] = ti.Vector.zero(ti.f32, self.dim)
                self.particles.a[i] = ti.Vector.zero(ti.f32, self.dim)

        return ke

    @ti.kernel
    def _reset_velocities(self):
        """Reset all velocities to zero."""
        for i in range(self.n_particles):
            self.particles.v[i] = ti.Vector.zero(ti.f32, self.dim)

    @ti.kernel
    def _compute_residual_norm(self) -> ti.f32:
        """Compute L2 norm of residual forces on free particles."""
        norm_sq = 0.0
        for i in range(self.n_particles):
            if self.particles.fixed[i] == 0:
                f_sq = self.particles.f[i].dot(self.particles.f[i])
                norm_sq += f_sq
        return ti.sqrt(norm_sq)

    @ti.kernel
    def _compute_load_norm(self, load_mask: ti.template()) -> ti.f32:
        """Compute norm of applied loads."""
        norm_sq = 0.0
        for i in range(self.n_particles):
            if load_mask[i] == 1:
                f_sq = self.particles.f[i].dot(self.particles.f[i])
                norm_sq += f_sq
        return ti.sqrt(norm_sq)

    def step(self, external_force_func: Optional[Callable] = None) -> dict:
        """Perform one iteration with kinetic damping.

        Args:
            external_force_func: Optional function to apply external forces

        Returns:
            Dictionary with iteration info
        """
        # Position update (Verlet step 1)
        self._velocity_verlet_step1(self.dt)

        # Compute forces
        self._compute_bond_forces()

        # Apply external forces
        if external_force_func is not None:
            external_force_func()

        # Velocity update (Verlet step 2)
        ke = float(self._velocity_verlet_step2(self.dt))

        # Kinetic damping: reset velocities when KE peaks
        velocity_reset = False
        if ke < self.prev_ke and self.ke_increasing:
            # KE peaked - reset velocities
            self._reset_velocities()
            ke = 0.0
            velocity_reset = True
            self.ke_increasing = False
        elif ke > self.prev_ke:
            self.ke_increasing = True

        self.prev_ke = ke
        self.iteration += 1

        return {
            "kinetic_energy": ke,
            "residual": float(self._compute_residual_norm()),
            "velocity_reset": velocity_reset
        }

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
            external_force_func: Function to apply external forces
            max_iterations: Maximum iterations
            tol: Convergence tolerance (relative residual)
            verbose: Print progress
            print_interval: Print interval

        Returns:
            Convergence info dictionary
        """
        # Reset state
        self._reset_velocities()
        self.iteration = 0
        self.prev_ke = 0.0
        self.ke_increasing = True

        # Get reference residual from external load
        self._compute_bond_forces()
        if external_force_func:
            external_force_func()
        ref_residual = float(self._compute_residual_norm())

        if ref_residual < 1e-20:
            ref_residual = 1.0

        if verbose:
            print(f"dt = {self.dt:.2e}, reference residual = {ref_residual:.2e}")

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
                      f"max_u={max_u:.2e}m, resets={reset_count}")

            if rel_residual < tol:
                converged = True
                if verbose:
                    print(f"\nConverged in {self.iteration} iterations ({reset_count} velocity resets)")
                break

        if not converged and verbose:
            print(f"\nDid not converge in {max_iterations} iterations")

        return {
            "converged": converged,
            "iterations": self.iteration,
            "residual": info["residual"],
            "relative_residual": rel_residual,
            "velocity_resets": reset_count
        }


@ti.data_oriented
class LoadControl:
    """Helper class for applying external loads."""

    def __init__(self, particles: "ParticleSystem", loaded_indices: np.ndarray):
        """Initialize load control.

        Args:
            particles: ParticleSystem
            loaded_indices: Indices of particles to load
        """
        self.particles = particles
        self.n_loaded = len(loaded_indices)
        self.dim = particles.dim

        # Store load mask
        self.load_mask = ti.field(dtype=ti.i32, shape=particles.n_particles)
        mask = np.zeros(particles.n_particles, dtype=np.int32)
        mask[loaded_indices] = 1
        self.load_mask.from_numpy(mask)

        # Current load vector per particle
        self.load = ti.Vector.field(particles.dim, dtype=ti.f32, shape=())

    def set_load(self, force_per_particle: tuple):
        """Set the load vector per particle."""
        load_list = list(force_per_particle)[:self.dim]
        self.load[None] = load_list

    @ti.kernel
    def apply(self):
        """Apply loads to particles (add to force field)."""
        for i in range(self.particles.n_particles):
            if self.load_mask[i] == 1:
                self.particles.f[i] += self.load[None]


# Alias for compatibility
ADRSolver = QuasiStaticSolver
