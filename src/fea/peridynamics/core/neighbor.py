"""Grid-based neighbor search for peridynamics with O(n) complexity."""

import taichi as ti
import numpy as np
from typing import Tuple


@ti.data_oriented
class NeighborSearch:
    """Uniform grid-based neighbor search for finding particles within horizon.

    Uses a cell-linked list approach for O(n) neighbor finding.
    Each cell covers an area of size (cell_size x cell_size) where
    cell_size >= horizon to ensure all neighbors are in adjacent cells.
    """

    def __init__(
        self,
        domain_min: Tuple[float, ...],
        domain_max: Tuple[float, ...],
        horizon: float,
        max_particles: int,
        max_neighbors: int = 64,
        dim: int = 2
    ):
        """Initialize neighbor search grid.

        Args:
            domain_min: Minimum corner of domain
            domain_max: Maximum corner of domain
            horizon: Peridynamics horizon (neighborhood radius)
            max_particles: Maximum number of particles
            max_neighbors: Maximum neighbors per particle
            dim: Spatial dimension (2 or 3)
        """
        self.dim = dim
        self.horizon = horizon
        self.max_particles = max_particles
        self.max_neighbors = max_neighbors

        # Cell size should be >= horizon
        self.cell_size = horizon * 1.01  # Slightly larger to handle edge cases

        # Compute grid dimensions
        self.domain_min = ti.Vector(list(domain_min)[:dim])
        self.domain_max = ti.Vector(list(domain_max)[:dim])

        domain_size = [domain_max[i] - domain_min[i] for i in range(dim)]
        self.grid_dims = tuple(
            max(1, int(np.ceil(domain_size[i] / self.cell_size))) for i in range(dim)
        )

        if dim == 2:
            total_cells = self.grid_dims[0] * self.grid_dims[1]
        else:
            total_cells = self.grid_dims[0] * self.grid_dims[1] * self.grid_dims[2]

        self.total_cells = total_cells

        # Grid data structures
        # Cell particle count
        self.cell_count = ti.field(dtype=ti.i32, shape=total_cells)
        # Cell start index in sorted particle list
        self.cell_start = ti.field(dtype=ti.i32, shape=total_cells)
        # Particle cell assignment
        self.particle_cell = ti.field(dtype=ti.i32, shape=max_particles)
        # Sorted particle indices
        self.sorted_indices = ti.field(dtype=ti.i32, shape=max_particles)

        # Output: neighbor list (dense, fixed size per particle)
        self.neighbors = ti.field(dtype=ti.i32, shape=(max_particles, max_neighbors))
        self.n_neighbors = ti.field(dtype=ti.i32, shape=max_particles)

        # Store grid dims as fields for kernel access
        self.grid_dims_field = ti.Vector.field(dim, dtype=ti.i32, shape=())
        self.grid_dims_field[None] = ti.Vector(list(self.grid_dims)[:dim])

        self.domain_min_field = ti.Vector.field(dim, dtype=ti.f32, shape=())
        self.domain_min_field[None] = ti.Vector([float(domain_min[i]) for i in range(dim)])

    @ti.func
    def pos_to_cell(self, pos: ti.template()) -> ti.i32:
        """Convert position to cell index."""
        cell_idx = ti.cast(
            (pos - self.domain_min_field[None]) / self.cell_size,
            ti.i32
        )
        # Clamp to valid range
        for d in ti.static(range(self.dim)):
            cell_idx[d] = ti.max(0, ti.min(cell_idx[d], self.grid_dims_field[None][d] - 1))

        # Convert to linear index
        if ti.static(self.dim == 2):
            return cell_idx[0] * self.grid_dims_field[None][1] + cell_idx[1]
        else:
            return (cell_idx[0] * self.grid_dims_field[None][1] * self.grid_dims_field[None][2]
                    + cell_idx[1] * self.grid_dims_field[None][2]
                    + cell_idx[2])

    @ti.func
    def linear_to_cell(self, linear: ti.i32) -> ti.template():
        """Convert linear cell index to grid coordinates."""
        if ti.static(self.dim == 2):
            cx = linear // self.grid_dims_field[None][1]
            cy = linear % self.grid_dims_field[None][1]
            return ti.Vector([cx, cy])
        else:
            cx = linear // (self.grid_dims_field[None][1] * self.grid_dims_field[None][2])
            rem = linear % (self.grid_dims_field[None][1] * self.grid_dims_field[None][2])
            cy = rem // self.grid_dims_field[None][2]
            cz = rem % self.grid_dims_field[None][2]
            return ti.Vector([cx, cy, cz])

    @ti.kernel
    def _count_particles_per_cell(self, positions: ti.template(), n_particles: ti.i32):
        """Count particles in each cell."""
        # Reset counts
        for i in range(self.total_cells):
            self.cell_count[i] = 0

        # Count particles per cell
        for i in range(n_particles):
            cell = self.pos_to_cell(positions[i])
            self.particle_cell[i] = cell
            ti.atomic_add(self.cell_count[cell], 1)

    @ti.kernel
    def _compute_cell_starts(self):
        """Compute start index for each cell (prefix sum)."""
        # Simple serial prefix sum (could be parallelized with scan)
        running_sum = 0
        for i in range(self.total_cells):
            self.cell_start[i] = running_sum
            running_sum += self.cell_count[i]

    @ti.kernel
    def _sort_particles(self, n_particles: ti.i32):
        """Sort particles into cells."""
        # Reset counts (use as insertion pointer)
        for i in range(self.total_cells):
            self.cell_count[i] = 0

        # Insert particles
        for i in range(n_particles):
            cell = self.particle_cell[i]
            offset = ti.atomic_add(self.cell_count[cell], 1)
            self.sorted_indices[self.cell_start[cell] + offset] = i

    @ti.kernel
    def _find_neighbors(self, positions: ti.template(), n_particles: ti.i32):
        """Find neighbors within horizon for each particle."""
        horizon_sq = self.horizon * self.horizon

        for i in range(n_particles):
            pos_i = positions[i]
            cell_i = self.linear_to_cell(self.particle_cell[i])
            count = 0

            # Search neighboring cells
            if ti.static(self.dim == 2):
                for di in range(-1, 2):
                    for dj in range(-1, 2):
                        nc = cell_i + ti.Vector([di, dj])
                        # Check bounds
                        if (0 <= nc[0] < self.grid_dims_field[None][0] and
                            0 <= nc[1] < self.grid_dims_field[None][1]):
                            # Linear index of neighbor cell
                            nc_linear = nc[0] * self.grid_dims_field[None][1] + nc[1]
                            # Iterate particles in this cell
                            start = self.cell_start[nc_linear]
                            end = start + self.cell_count[nc_linear]
                            for k in range(start, end):
                                j = self.sorted_indices[k]
                                if i != j and count < self.max_neighbors:
                                    diff = positions[j] - pos_i
                                    dist_sq = diff.dot(diff)
                                    if dist_sq < horizon_sq:
                                        self.neighbors[i, count] = j
                                        count += 1
            else:
                for di in range(-1, 2):
                    for dj in range(-1, 2):
                        for dk in range(-1, 2):
                            nc = cell_i + ti.Vector([di, dj, dk])
                            if (0 <= nc[0] < self.grid_dims_field[None][0] and
                                0 <= nc[1] < self.grid_dims_field[None][1] and
                                0 <= nc[2] < self.grid_dims_field[None][2]):
                                nc_linear = (nc[0] * self.grid_dims_field[None][1] * self.grid_dims_field[None][2]
                                           + nc[1] * self.grid_dims_field[None][2] + nc[2])
                                start = self.cell_start[nc_linear]
                                end = start + self.cell_count[nc_linear]
                                for k in range(start, end):
                                    j = self.sorted_indices[k]
                                    if i != j and count < self.max_neighbors:
                                        diff = positions[j] - pos_i
                                        dist_sq = diff.dot(diff)
                                        if dist_sq < horizon_sq:
                                            self.neighbors[i, count] = j
                                            count += 1

            self.n_neighbors[i] = count

    def build(self, positions: ti.template(), n_particles: int):
        """Build neighbor list for given particle positions.

        Args:
            positions: ti.Vector.field of particle positions
            n_particles: Number of active particles
        """
        self._count_particles_per_cell(positions, n_particles)
        self._compute_cell_starts()
        self._sort_particles(n_particles)
        self._find_neighbors(positions, n_particles)

    def get_neighbors(self, particle_idx: int) -> np.ndarray:
        """Get neighbors for a specific particle (CPU query).

        Args:
            particle_idx: Particle index

        Returns:
            Array of neighbor indices
        """
        n = self.n_neighbors[particle_idx]
        neighbors = np.zeros(n, dtype=np.int32)
        for i in range(n):
            neighbors[i] = self.neighbors[particle_idx, i]
        return neighbors

    def get_all_neighbor_counts(self) -> np.ndarray:
        """Get neighbor count for all particles."""
        return self.n_neighbors.to_numpy()
