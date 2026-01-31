"""Voxel volume for bone/tissue editing."""

import taichi as ti
import numpy as np
from typing import Tuple, Optional
from dataclasses import dataclass


@ti.data_oriented
class VoxelVolume:
    """3D voxel volume for surgical editing.

    Stores density/material values that can be modified (drilling, cutting).
    """

    def __init__(
        self,
        resolution: Tuple[int, int, int],
        origin: Tuple[float, float, float] = (0, 0, 0),
        spacing: float = 1.0
    ):
        """Initialize voxel volume.

        Args:
            resolution: (nx, ny, nz) number of voxels
            origin: World position of corner (0,0,0)
            spacing: Size of each voxel
        """
        self.nx, self.ny, self.nz = resolution
        self.origin = ti.Vector(list(origin), dt=ti.f32)
        self.spacing = spacing

        # Voxel data: 0 = empty, >0 = material density
        self.data = ti.field(dtype=ti.f32, shape=resolution)

        # Material type: 0=empty, 1=bone, 2=disc, 3=soft tissue
        self.material = ti.field(dtype=ti.i32, shape=resolution)

        # For marching cubes surface extraction
        self.surface_vertices = None
        self.surface_faces = None

    @ti.kernel
    def fill_sphere(self, center_x: ti.f32, center_y: ti.f32, center_z: ti.f32,
                    radius: ti.f32, value: ti.f32, mat_type: ti.i32):
        """Fill a spherical region with a value."""
        for i, j, k in self.data:
            # World position of voxel center
            px = self.origin[0] + (i + 0.5) * self.spacing
            py = self.origin[1] + (j + 0.5) * self.spacing
            pz = self.origin[2] + (k + 0.5) * self.spacing

            dx = px - center_x
            dy = py - center_y
            dz = pz - center_z
            dist = ti.sqrt(dx*dx + dy*dy + dz*dz)

            if dist < radius:
                self.data[i, j, k] = value
                self.material[i, j, k] = mat_type

    @ti.kernel
    def fill_box(self, min_x: ti.f32, min_y: ti.f32, min_z: ti.f32,
                 max_x: ti.f32, max_y: ti.f32, max_z: ti.f32,
                 value: ti.f32, mat_type: ti.i32):
        """Fill a box region with a value."""
        for i, j, k in self.data:
            px = self.origin[0] + (i + 0.5) * self.spacing
            py = self.origin[1] + (j + 0.5) * self.spacing
            pz = self.origin[2] + (k + 0.5) * self.spacing

            if (min_x <= px <= max_x and
                min_y <= py <= max_y and
                min_z <= pz <= max_z):
                self.data[i, j, k] = value
                self.material[i, j, k] = mat_type

    @ti.kernel
    def drill(self, tip_x: ti.f32, tip_y: ti.f32, tip_z: ti.f32,
              dir_x: ti.f32, dir_y: ti.f32, dir_z: ti.f32,
              radius: ti.f32, depth: ti.f32) -> ti.i32:
        """Remove material in a cylindrical region (drill).

        Args:
            tip_x/y/z: Drill tip position
            dir_x/y/z: Drill direction (normalized)
            radius: Drill radius
            depth: Drill depth

        Returns:
            Number of voxels removed
        """
        removed = 0

        for i, j, k in self.data:
            if self.data[i, j, k] > 0:
                # Voxel center in world coords
                px = self.origin[0] + (i + 0.5) * self.spacing
                py = self.origin[1] + (j + 0.5) * self.spacing
                pz = self.origin[2] + (k + 0.5) * self.spacing

                # Vector from tip to voxel
                vx = px - tip_x
                vy = py - tip_y
                vz = pz - tip_z

                # Project onto drill axis
                proj = vx * dir_x + vy * dir_y + vz * dir_z

                # Check if within depth
                if 0 <= proj <= depth:
                    # Perpendicular distance to axis
                    perp_x = vx - proj * dir_x
                    perp_y = vy - proj * dir_y
                    perp_z = vz - proj * dir_z
                    perp_dist = ti.sqrt(perp_x*perp_x + perp_y*perp_y + perp_z*perp_z)

                    if perp_dist < radius:
                        self.data[i, j, k] = 0.0
                        self.material[i, j, k] = 0
                        removed += 1

        return removed

    @ti.kernel
    def sphere_brush(self, center_x: ti.f32, center_y: ti.f32, center_z: ti.f32,
                     radius: ti.f32, add: ti.i32, value: ti.f32, mat_type: ti.i32) -> ti.i32:
        """Add or remove material with a spherical brush.

        Args:
            center: Brush center
            radius: Brush radius
            add: 1 to add material, 0 to remove
            value: Material density to add
            mat_type: Material type

        Returns:
            Number of voxels modified
        """
        modified = 0

        for i, j, k in self.data:
            px = self.origin[0] + (i + 0.5) * self.spacing
            py = self.origin[1] + (j + 0.5) * self.spacing
            pz = self.origin[2] + (k + 0.5) * self.spacing

            dx = px - center_x
            dy = py - center_y
            dz = pz - center_z
            dist = ti.sqrt(dx*dx + dy*dy + dz*dz)

            if dist < radius:
                if add == 1:
                    if self.data[i, j, k] == 0:
                        self.data[i, j, k] = value
                        self.material[i, j, k] = mat_type
                        modified += 1
                else:
                    if self.data[i, j, k] > 0:
                        self.data[i, j, k] = 0.0
                        self.material[i, j, k] = 0
                        modified += 1

        return modified

    def world_to_voxel(self, world_pos: np.ndarray) -> np.ndarray:
        """Convert world position to voxel indices."""
        origin = np.array([self.origin[0], self.origin[1], self.origin[2]])
        return ((world_pos - origin) / self.spacing).astype(int)

    def voxel_to_world(self, voxel_idx: np.ndarray) -> np.ndarray:
        """Convert voxel indices to world position (center of voxel)."""
        origin = np.array([self.origin[0], self.origin[1], self.origin[2]])
        return origin + (voxel_idx + 0.5) * self.spacing

    def get_bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get world-space bounding box."""
        origin = np.array([self.origin[0], self.origin[1], self.origin[2]])
        size = np.array([self.nx, self.ny, self.nz]) * self.spacing
        return origin, origin + size

    def to_numpy(self) -> np.ndarray:
        """Get voxel data as numpy array."""
        return self.data.to_numpy()

    def from_numpy(self, data: np.ndarray, material: Optional[np.ndarray] = None):
        """Set voxel data from numpy array."""
        self.data.from_numpy(data.astype(np.float32))
        if material is not None:
            self.material.from_numpy(material.astype(np.int32))

    @ti.kernel
    def count_nonzero(self) -> ti.i32:
        """Count non-empty voxels."""
        count = 0
        for i, j, k in self.data:
            if self.data[i, j, k] > 0:
                count += 1
        return count
