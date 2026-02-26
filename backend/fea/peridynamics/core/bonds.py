"""Bond system for peridynamics using CSR-like storage."""

import taichi as ti
import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .particles import ParticleSystem
    from .neighbor import NeighborSearch


@ti.data_oriented
class BondSystem:
    """Bond connectivity and state for peridynamics.

    Uses CSR-like storage where each particle has a fixed maximum number of bonds.
    Bonds store the reference bond vector (xi), current state, and influence weight.

    Attributes:
        n_particles: Number of particles
        max_bonds: Maximum bonds per particle
        neighbors: (n_particles, max_bonds) neighbor indices
        n_neighbors: Number of actual neighbors per particle
        xi: Reference bond vectors (from i to j in reference configuration)
        xi_length: Reference bond lengths (precomputed)
        broken: Bond broken flag (0=intact, 1=broken)
        omega: Influence function weight
    """

    @classmethod
    def from_neighbor_counts(
        cls,
        n_particles: int,
        counts: np.ndarray,
        dim: int = 2,
        margin: int = 8
    ) -> "BondSystem":
        """이웃 수 사전 카운트로부터 적응적 할당.

        max_bonds = max(counts) + margin 으로 자동 설정하여
        메모리 낭비를 줄이면서 3D에서도 안전한 할당을 보장한다.

        Args:
            n_particles: 입자 수
            counts: 각 입자의 이웃 수 (n_particles,)
            dim: 공간 차원
            margin: 안전 여유분

        Returns:
            적응적으로 할당된 BondSystem
        """
        max_bonds = int(np.max(counts)) + margin
        return cls(n_particles, max_bonds=max_bonds, dim=dim)

    def __init__(self, n_particles: int, max_bonds: int = 64, dim: int = 2):
        """Initialize bond system.

        Args:
            n_particles: Number of particles
            max_bonds: Maximum bonds per particle
            dim: Spatial dimension
        """
        self.n_particles = n_particles
        self.max_bonds = max_bonds
        self.dim = dim

        # Connectivity (CSR-like: fixed max_bonds per particle)
        self.neighbors = ti.field(dtype=ti.i32, shape=(n_particles, max_bonds))
        self.n_neighbors = ti.field(dtype=ti.i32, shape=n_particles)

        # Reference bond vectors (f64 정밀도)
        self.xi = ti.Vector.field(dim, dtype=ti.f64, shape=(n_particles, max_bonds))
        self.xi_length = ti.field(dtype=ti.f64, shape=(n_particles, max_bonds))

        # Bond state
        self.broken = ti.field(dtype=ti.i32, shape=(n_particles, max_bonds))
        self.omega = ti.field(dtype=ti.f64, shape=(n_particles, max_bonds))

        # Total initial bonds per particle (for damage calculation)
        self.initial_bonds = ti.field(dtype=ti.i32, shape=n_particles)

    def build_from_neighbor_search(
        self,
        particles: "ParticleSystem",
        neighbor_search: "NeighborSearch",
        horizon: float
    ):
        """Build bonds from neighbor search results.

        Args:
            particles: ParticleSystem with reference positions
            neighbor_search: NeighborSearch with computed neighbor list
            horizon: Peridynamics horizon for influence function
        """
        # Copy neighbor data
        self._copy_neighbors(neighbor_search.neighbors, neighbor_search.n_neighbors)

        # Compute bond vectors and influence weights
        self._compute_bond_data(particles.X, horizon)

    @ti.kernel
    def _copy_neighbors(
        self,
        src_neighbors: ti.template(),
        src_n_neighbors: ti.template()
    ):
        """Copy neighbor data from search structure."""
        for i in range(self.n_particles):
            n = src_n_neighbors[i]
            self.n_neighbors[i] = n
            self.initial_bonds[i] = n
            for k in range(n):
                self.neighbors[i, k] = src_neighbors[i, k]
                self.broken[i, k] = 0  # All bonds initially intact

    @ti.kernel
    def _compute_bond_data(self, X: ti.template(), horizon: ti.f64):
        """Compute reference bond vectors and influence weights.

        Uses standard influence function: omega = 1 - |xi|/delta
        """
        for i in range(self.n_particles):
            for k in range(self.n_neighbors[i]):
                j = self.neighbors[i, k]
                # Reference bond vector: from i to j
                xi = X[j] - X[i]
                xi_len = xi.norm()

                self.xi[i, k] = xi
                self.xi_length[i, k] = xi_len

                # Influence function (linear decay)
                # omega = 1 - |xi|/delta, but ensure positive
                if xi_len > 0:
                    self.omega[i, k] = ti.max(0.0, 1.0 - xi_len / horizon)
                else:
                    self.omega[i, k] = 1.0

    @ti.kernel
    def reset_bonds(self):
        """Reset all bonds to intact state."""
        for i in range(self.n_particles):
            for k in range(self.n_neighbors[i]):
                self.broken[i, k] = 0

    @ti.func
    def get_current_bond_vector(self, x: ti.template(), i: ti.i32, k: ti.i32) -> ti.template():
        """Get current bond vector (eta) from current positions.

        Args:
            x: Current position field
            i: Particle index
            k: Bond index

        Returns:
            Current bond vector (from i to j)
        """
        j = self.neighbors[i, k]
        return x[j] - x[i]

    @ti.func
    def get_stretch(self, x: ti.template(), i: ti.i32, k: ti.i32) -> ti.f64:
        """Compute bond stretch s = (|eta| - |xi|) / |xi|.

        Args:
            x: Current position field
            i: Particle index
            k: Bond index

        Returns:
            Bond stretch (positive = extension, negative = compression)
        """
        eta = self.get_current_bond_vector(x, i, k)
        eta_len = eta.norm()
        xi_len = self.xi_length[i, k]

        stretch = 0.0
        if xi_len > 1e-10:
            stretch = (eta_len - xi_len) / xi_len
        return stretch

    def get_neighbor_count(self) -> np.ndarray:
        """Get neighbor count for all particles."""
        return self.n_neighbors.to_numpy()

    def get_broken_bonds(self) -> np.ndarray:
        """Get broken bond flags as numpy array."""
        return self.broken.to_numpy()

    @ti.kernel
    def count_intact_bonds(self) -> ti.i32:
        """Count total number of intact bonds."""
        count = 0
        for i in range(self.n_particles):
            for k in range(self.n_neighbors[i]):
                if self.broken[i, k] == 0:
                    count += 1
        return count

    @ti.kernel
    def count_broken_bonds(self) -> ti.i32:
        """Count total number of broken bonds."""
        count = 0
        for i in range(self.n_particles):
            for k in range(self.n_neighbors[i]):
                if self.broken[i, k] == 1:
                    count += 1
        return count
