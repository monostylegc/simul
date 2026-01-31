"""Explicit time integration solver for bond-based peridynamics."""

import taichi as ti
import numpy as np
from typing import Optional, TYPE_CHECKING
import math

if TYPE_CHECKING:
    from ..core.particles import ParticleSystem
    from ..core.bonds import BondSystem
    from ..core.damage import DamageModel
    from ..material.linear_elastic import LinearElasticMaterial2D


@ti.data_oriented
class ExplicitSolver:
    """Velocity Verlet explicit time integrator for bond-based peridynamics.

    Implements the following algorithm:
    1. x(t+dt) = x(t) + v(t)*dt + 0.5*a(t)*dt^2
    2. Compute forces f(t+dt)
    3. a(t+dt) = f(t+dt) / m
    4. v(t+dt) = v(t) + 0.5*(a(t) + a(t+dt))*dt
    5. Update damage
    """

    def __init__(
        self,
        particles: "ParticleSystem",
        bonds: "BondSystem",
        micromodulus: float,
        dt: float = 1e-6,
        damping: float = 0.0
    ):
        """Initialize explicit solver.

        Args:
            particles: ParticleSystem instance
            bonds: BondSystem instance
            micromodulus: Material micromodulus constant c
            dt: Time step size
            damping: Velocity damping coefficient (0-1)
        """
        self.particles = particles
        self.bonds = bonds
        self.dt = dt
        self.damping = damping
        self.dim = particles.dim
        self.n_particles = particles.n_particles

        # Store micromodulus as field
        self.c = ti.field(dtype=ti.f32, shape=())
        self.c[None] = micromodulus

        # Store previous acceleration for Verlet
        self.a_old = ti.Vector.field(self.dim, dtype=ti.f32, shape=self.n_particles)

        # Simulation time
        self.time = 0.0
        self.step_count = 0

    @ti.kernel
    def _position_update(self, dt: ti.f32):
        """Update positions: x(t+dt) = x(t) + v*dt + 0.5*a*dt^2."""
        for i in range(self.n_particles):
            if self.particles.fixed[i] == 0:
                self.a_old[i] = self.particles.a[i]
                self.particles.x[i] += (
                    self.particles.v[i] * dt +
                    0.5 * self.particles.a[i] * dt * dt
                )

    @ti.kernel
    def _compute_bond_forces(self):
        """Compute internal forces from bond-based peridynamics.

        For each particle i, accumulate forces from all bonded neighbors j:
        f_ij = c * s * omega * (eta / |eta|) * V_j

        where:
        - c: micromodulus
        - s: bond stretch = (|eta| - |xi|) / |xi|
        - omega: influence weight
        - eta: current bond vector
        - V_j: neighbor volume
        """
        # Reset forces
        for i in range(self.n_particles):
            self.particles.f[i] = ti.Vector.zero(ti.f32, self.dim)

        # Compute bond forces
        for i in range(self.n_particles):
            for k in range(self.bonds.n_neighbors[i]):
                # Skip broken bonds
                if self.bonds.broken[i, k] == 0:
                    j = self.bonds.neighbors[i, k]

                    # Current bond vector
                    eta = self.particles.x[j] - self.particles.x[i]
                    eta_len = eta.norm()

                    if eta_len > 1e-10:
                        # Reference bond length
                        xi_len = self.bonds.xi_length[i, k]

                        # Stretch
                        stretch = (eta_len - xi_len) / xi_len

                        # Force magnitude
                        omega = self.bonds.omega[i, k]
                        f_mag = self.c[None] * stretch * omega * self.particles.volume[j]

                        # Force vector (along bond direction)
                        f_vec = f_mag * (eta / eta_len)

                        # Accumulate force on particle i
                        self.particles.f[i] += f_vec

    @ti.kernel
    def _velocity_update(self, dt: ti.f32, damping: ti.f32):
        """Update velocities: v(t+dt) = v(t) + 0.5*(a_old + a_new)*dt."""
        for i in range(self.n_particles):
            if self.particles.fixed[i] == 0:
                # Compute new acceleration
                if self.particles.mass[i] > 0:
                    self.particles.a[i] = self.particles.f[i] / self.particles.mass[i]

                # Velocity update with optional damping
                self.particles.v[i] = (1.0 - damping) * (
                    self.particles.v[i] +
                    0.5 * (self.a_old[i] + self.particles.a[i]) * dt
                )
            else:
                self.particles.v[i] = ti.Vector.zero(ti.f32, self.dim)
                self.particles.a[i] = ti.Vector.zero(ti.f32, self.dim)

    def step(self, damage_model: Optional["DamageModel"] = None):
        """Perform one time step.

        Args:
            damage_model: Optional damage model for bond breaking
        """
        # 1. Position update
        self._position_update(self.dt)

        # 2. Compute bond forces
        self._compute_bond_forces()

        # 3. Velocity update
        self._velocity_update(self.dt, self.damping)

        # 4. Update damage if model provided
        if damage_model is not None:
            damage_model.step(self.particles, self.bonds)

        # Update time
        self.time += self.dt
        self.step_count += 1

    def run(
        self,
        n_steps: int,
        damage_model: Optional["DamageModel"] = None,
        callback: Optional[callable] = None,
        callback_interval: int = 100
    ):
        """Run simulation for multiple steps.

        Args:
            n_steps: Number of time steps
            damage_model: Optional damage model
            callback: Optional callback function called every callback_interval steps
            callback_interval: Callback frequency
        """
        for i in range(n_steps):
            self.step(damage_model)

            if callback is not None and i % callback_interval == 0:
                callback(self, i)

    @staticmethod
    def estimate_stable_dt(
        youngs_modulus: float,
        density: float,
        horizon: float,
        spacing: float,
        safety_factor: float = 0.5
    ) -> float:
        """Estimate stable time step based on CFL condition.

        dt < safety * sqrt(2 * rho / (pi * delta^2 * c))

        For bond-based PD with micromodulus c = 9*E / (pi * h * delta^3),
        this simplifies to approximately:

        dt < safety * spacing * sqrt(rho / E)

        Args:
            youngs_modulus: Young's modulus [Pa]
            density: Material density [kg/m^3]
            horizon: Peridynamics horizon [m]
            spacing: Particle spacing [m]
            safety_factor: Safety factor (0-1, typically 0.5)

        Returns:
            Estimated stable time step [s]
        """
        # Wave speed
        wave_speed = math.sqrt(youngs_modulus / density)

        # CFL condition: dt < dx / c
        dt = safety_factor * spacing / wave_speed

        return dt

    def get_kinetic_energy(self) -> float:
        """Compute total kinetic energy."""
        return self._compute_kinetic_energy()

    @ti.kernel
    def _compute_kinetic_energy(self) -> ti.f32:
        """Compute kinetic energy: 0.5 * sum(m * v^2)."""
        KE = 0.0
        for i in range(self.n_particles):
            v_sq = self.particles.v[i].dot(self.particles.v[i])
            KE += 0.5 * self.particles.mass[i] * v_sq
        return KE

    def get_strain_energy(self) -> float:
        """Compute total strain energy (approximate for bond-based PD)."""
        return self._compute_strain_energy()

    @ti.kernel
    def _compute_strain_energy(self) -> ti.f32:
        """Compute strain energy: 0.5 * c * sum(omega * s^2 * |xi| * V_i * V_j)."""
        SE = 0.0
        for i in range(self.n_particles):
            for k in range(self.bonds.n_neighbors[i]):
                if self.bonds.broken[i, k] == 0:
                    j = self.bonds.neighbors[i, k]

                    # Stretch
                    eta = self.particles.x[j] - self.particles.x[i]
                    eta_len = eta.norm()
                    xi_len = self.bonds.xi_length[i, k]

                    if xi_len > 1e-10:
                        stretch = (eta_len - xi_len) / xi_len
                        omega = self.bonds.omega[i, k]

                        # Energy contribution (factor 0.25 because we count each bond twice)
                        SE += 0.25 * self.c[None] * omega * stretch * stretch * xi_len * \
                              self.particles.volume[i] * self.particles.volume[j]
        return SE
