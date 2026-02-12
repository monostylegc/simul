"""Particle system for peridynamics simulation using Structure of Arrays (SoA) layout."""

import taichi as ti
import numpy as np
from typing import Optional


@ti.data_oriented
class ParticleSystem:
    """Particle system storing all particle states in SoA layout for GPU efficiency.

    Attributes:
        n_particles: Number of particles
        dim: Spatial dimension (2 or 3)
        X: Reference (initial) coordinates
        x: Current coordinates
        v: Velocity
        a: Acceleration
        f: Force accumulator
        volume: Particle volume
        density: Material density
        mass: Particle mass (volume * density)
        damage: Local damage (0 = intact, 1 = fully damaged)
    """

    def __init__(self, n_particles: int, dim: int = 2):
        """Initialize particle system.

        Args:
            n_particles: Number of particles
            dim: Spatial dimension (2 or 3)
        """
        self.n_particles = n_particles
        self.dim = dim

        # Position and velocity fields
        self.X = ti.Vector.field(dim, dtype=ti.f32, shape=n_particles)  # Reference
        self.x = ti.Vector.field(dim, dtype=ti.f32, shape=n_particles)  # Current
        self.v = ti.Vector.field(dim, dtype=ti.f32, shape=n_particles)  # Velocity
        self.a = ti.Vector.field(dim, dtype=ti.f32, shape=n_particles)  # Acceleration
        self.f = ti.Vector.field(dim, dtype=ti.f32, shape=n_particles)  # Force

        # Material properties
        self.volume = ti.field(dtype=ti.f32, shape=n_particles)
        self.density = ti.field(dtype=ti.f32, shape=n_particles)
        self.mass = ti.field(dtype=ti.f32, shape=n_particles)

        # Damage field
        self.damage = ti.field(dtype=ti.f32, shape=n_particles)

        # Per-particle 재료 상수 (다중 재료 지원)
        self.bulk_mod = ti.field(dtype=ti.f32, shape=n_particles)   # 체적 탄성률
        self.shear_mod = ti.field(dtype=ti.f32, shape=n_particles)  # 전단 탄성률

        # For NOSB-PD: shape tensor and deformation gradient
        self.K = ti.Matrix.field(dim, dim, dtype=ti.f32, shape=n_particles)  # Shape tensor
        self.K_inv = ti.Matrix.field(dim, dim, dtype=ti.f32, shape=n_particles)  # Inverse
        self.F = ti.Matrix.field(dim, dim, dtype=ti.f32, shape=n_particles)  # Deformation gradient
        self.P = ti.Matrix.field(dim, dim, dtype=ti.f32, shape=n_particles)  # 1st Piola-Kirchhoff

        # Boundary condition flags
        self.fixed = ti.field(dtype=ti.i32, shape=n_particles)  # 0=free, 1=fixed

    def initialize_from_grid(
        self,
        origin: tuple,
        spacing: float,
        n_points: tuple,
        density: float = 1000.0
    ):
        """Initialize particles on a regular grid.

        Args:
            origin: Grid origin (x, y) or (x, y, z)
            spacing: Grid spacing (particle separation)
            n_points: Number of points in each direction
            density: Material density
        """
        positions = []
        if self.dim == 2:
            for i in range(n_points[0]):
                for j in range(n_points[1]):
                    pos = (origin[0] + i * spacing, origin[1] + j * spacing)
                    positions.append(pos)
        else:
            for i in range(n_points[0]):
                for j in range(n_points[1]):
                    for k in range(n_points[2]):
                        pos = (
                            origin[0] + i * spacing,
                            origin[1] + j * spacing,
                            origin[2] + k * spacing
                        )
                        positions.append(pos)

        positions = np.array(positions, dtype=np.float32)
        n_actual = len(positions)

        if n_actual != self.n_particles:
            raise ValueError(
                f"Grid produces {n_actual} particles but system was initialized for {self.n_particles}"
            )

        # Set positions
        self.X.from_numpy(positions)
        self.x.from_numpy(positions)

        # Set material properties
        volume = spacing ** self.dim
        self._set_uniform_properties(density, volume)

    def initialize_from_arrays(
        self,
        positions: np.ndarray,
        volumes: np.ndarray,
        density: float = 1000.0
    ):
        """Initialize particles from arrays.

        Args:
            positions: Particle positions (n_particles, dim)
            volumes: Particle volumes (n_particles,)
            density: Material density
        """
        self.X.from_numpy(positions.astype(np.float32))
        self.x.from_numpy(positions.astype(np.float32))
        self.volume.from_numpy(volumes.astype(np.float32))

        densities = np.full(self.n_particles, density, dtype=np.float32)
        self.density.from_numpy(densities)

        masses = volumes * density
        self.mass.from_numpy(masses.astype(np.float32))

        # Initialize other fields
        self._init_fields()

    def _set_uniform_properties(self, density: float, volume: float):
        """Set uniform density and volume for all particles."""
        densities = np.full(self.n_particles, density, dtype=np.float32)
        volumes = np.full(self.n_particles, volume, dtype=np.float32)
        masses = volumes * density

        self.density.from_numpy(densities)
        self.volume.from_numpy(volumes)
        self.mass.from_numpy(masses)

        self._init_fields()

    @ti.kernel
    def _init_fields(self):
        """Initialize velocity, acceleration, damage to zero."""
        for i in range(self.n_particles):
            self.v[i] = ti.Vector.zero(ti.f32, self.dim)
            self.a[i] = ti.Vector.zero(ti.f32, self.dim)
            self.f[i] = ti.Vector.zero(ti.f32, self.dim)
            self.damage[i] = 0.0
            self.fixed[i] = 0

            # Initialize tensors to identity
            self.K[i] = ti.Matrix.identity(ti.f32, self.dim)
            self.K_inv[i] = ti.Matrix.identity(ti.f32, self.dim)
            self.F[i] = ti.Matrix.identity(ti.f32, self.dim)
            self.P[i] = ti.Matrix.zero(ti.f32, self.dim, self.dim)

    @ti.kernel
    def reset_forces(self):
        """Reset force accumulator to zero."""
        for i in range(self.n_particles):
            self.f[i] = ti.Vector.zero(ti.f32, self.dim)

    @ti.kernel
    def apply_body_force(self, force: ti.template()):
        """Apply uniform body force (e.g., gravity) to all particles.

        Args:
            force: Body force vector (force per unit mass)
        """
        for i in range(self.n_particles):
            if self.fixed[i] == 0:
                self.f[i] += self.mass[i] * force

    @ti.kernel
    def compute_acceleration(self):
        """Compute acceleration from forces: a = f / m."""
        for i in range(self.n_particles):
            if self.fixed[i] == 0 and self.mass[i] > 0:
                self.a[i] = self.f[i] / self.mass[i]
            else:
                self.a[i] = ti.Vector.zero(ti.f32, self.dim)

    def set_fixed_particles(self, indices: np.ndarray):
        """Set particles as fixed (Dirichlet BC).

        Args:
            indices: Array of particle indices to fix
        """
        fixed = np.zeros(self.n_particles, dtype=np.int32)
        fixed[indices] = 1
        self.fixed.from_numpy(fixed)

    def set_material_constants(self, bulk_modulus: float, shear_modulus: float):
        """단일 재료: 모든 입자에 동일 값 설정."""
        self.bulk_mod.from_numpy(np.full(self.n_particles, bulk_modulus, dtype=np.float32))
        self.shear_mod.from_numpy(np.full(self.n_particles, shear_modulus, dtype=np.float32))

    def set_material_constants_per_particle(self, bulk_arr, shear_arr):
        """다중 재료: 입자별 값 설정."""
        self.bulk_mod.from_numpy(bulk_arr.astype(np.float32))
        self.shear_mod.from_numpy(shear_arr.astype(np.float32))

    def get_positions(self) -> np.ndarray:
        """Get current particle positions as numpy array."""
        return self.x.to_numpy()

    def get_displacements(self) -> np.ndarray:
        """Get particle displacements (x - X) as numpy array."""
        return self.x.to_numpy() - self.X.to_numpy()

    def get_damage(self) -> np.ndarray:
        """Get damage field as numpy array."""
        return self.damage.to_numpy()
