"""Collision detection for surgical instruments."""

import taichi as ti
import numpy as np
from typing import Tuple, Optional, List
from dataclasses import dataclass


@dataclass
class RayHit:
    """Ray intersection result."""
    hit: bool
    distance: float
    position: np.ndarray
    normal: np.ndarray
    face_idx: int = -1
    mesh_name: str = ""


@ti.data_oriented
class CollisionDetector:
    """Collision detection for meshes and volumes."""

    def __init__(self, max_triangles: int = 100000):
        """Initialize collision detector.

        Args:
            max_triangles: Maximum number of triangles to handle
        """
        self.max_triangles = max_triangles

        # Triangle data for ray casting
        self.tri_v0 = ti.Vector.field(3, dtype=ti.f32, shape=max_triangles)
        self.tri_v1 = ti.Vector.field(3, dtype=ti.f32, shape=max_triangles)
        self.tri_v2 = ti.Vector.field(3, dtype=ti.f32, shape=max_triangles)
        self.tri_normal = ti.Vector.field(3, dtype=ti.f32, shape=max_triangles)
        self.n_triangles = ti.field(dtype=ti.i32, shape=())

        # Ray casting result
        self.hit_result = ti.field(dtype=ti.i32, shape=())
        self.hit_distance = ti.field(dtype=ti.f32, shape=())
        self.hit_position = ti.Vector.field(3, dtype=ti.f32, shape=())
        self.hit_normal = ti.Vector.field(3, dtype=ti.f32, shape=())
        self.hit_face = ti.field(dtype=ti.i32, shape=())

    def load_mesh(self, vertices: np.ndarray, faces: np.ndarray):
        """Load mesh triangles for collision detection.

        Args:
            vertices: (N, 3) vertex positions
            faces: (M, 3) triangle indices
        """
        n_tris = len(faces)
        if n_tris > self.max_triangles:
            raise ValueError(f"Too many triangles: {n_tris} > {self.max_triangles}")

        self.n_triangles[None] = n_tris

        v0 = vertices[faces[:, 0]]
        v1 = vertices[faces[:, 1]]
        v2 = vertices[faces[:, 2]]

        # Compute normals
        e1 = v1 - v0
        e2 = v2 - v0
        normals = np.cross(e1, e2)
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        normals = normals / norms

        # Pad to max_triangles size
        v0_padded = np.zeros((self.max_triangles, 3), dtype=np.float32)
        v1_padded = np.zeros((self.max_triangles, 3), dtype=np.float32)
        v2_padded = np.zeros((self.max_triangles, 3), dtype=np.float32)
        normals_padded = np.zeros((self.max_triangles, 3), dtype=np.float32)

        v0_padded[:n_tris] = v0.astype(np.float32)
        v1_padded[:n_tris] = v1.astype(np.float32)
        v2_padded[:n_tris] = v2.astype(np.float32)
        normals_padded[:n_tris] = normals.astype(np.float32)

        self.tri_v0.from_numpy(v0_padded)
        self.tri_v1.from_numpy(v1_padded)
        self.tri_v2.from_numpy(v2_padded)
        self.tri_normal.from_numpy(normals_padded)

    @ti.kernel
    def _ray_cast_kernel(self, ox: ti.f32, oy: ti.f32, oz: ti.f32,
                         dx: ti.f32, dy: ti.f32, dz: ti.f32,
                         max_dist: ti.f32):
        """GPU ray casting against all triangles."""
        origin = ti.Vector([ox, oy, oz])
        direction = ti.Vector([dx, dy, dz])

        self.hit_result[None] = 0
        self.hit_distance[None] = max_dist
        self.hit_face[None] = -1

        for i in range(self.n_triangles[None]):
            v0 = self.tri_v0[i]
            v1 = self.tri_v1[i]
            v2 = self.tri_v2[i]

            # Möller–Trumbore intersection
            e1 = v1 - v0
            e2 = v2 - v0
            h = direction.cross(e2)
            a = e1.dot(h)

            if ti.abs(a) > 1e-8:
                f = 1.0 / a
                s = origin - v0
                u = f * s.dot(h)

                if 0.0 <= u <= 1.0:
                    q = s.cross(e1)
                    v = f * direction.dot(q)

                    if v >= 0.0 and u + v <= 1.0:
                        t = f * e2.dot(q)

                        if t > 1e-6 and t < self.hit_distance[None]:
                            self.hit_result[None] = 1
                            self.hit_distance[None] = t
                            self.hit_face[None] = i
                            self.hit_position[None] = origin + t * direction
                            self.hit_normal[None] = self.tri_normal[i]

    def ray_cast(self, origin: np.ndarray, direction: np.ndarray,
                 max_distance: float = 1000.0) -> RayHit:
        """Cast a ray and find the closest intersection.

        Args:
            origin: Ray origin (3,)
            direction: Ray direction (3,), should be normalized
            max_distance: Maximum ray distance

        Returns:
            RayHit with intersection info
        """
        direction = direction / (np.linalg.norm(direction) + 1e-8)

        self._ray_cast_kernel(
            float(origin[0]), float(origin[1]), float(origin[2]),
            float(direction[0]), float(direction[1]), float(direction[2]),
            float(max_distance)
        )

        ti.sync()

        hit = bool(self.hit_result[None])
        if hit:
            return RayHit(
                hit=True,
                distance=float(self.hit_distance[None]),
                position=self.hit_position.to_numpy(),
                normal=self.hit_normal.to_numpy(),
                face_idx=int(self.hit_face[None])
            )
        else:
            return RayHit(
                hit=False,
                distance=max_distance,
                position=origin + direction * max_distance,
                normal=np.zeros(3)
            )

    def check_cylinder_collision(self, tip: np.ndarray, direction: np.ndarray,
                                 radius: float, length: float,
                                 n_samples: int = 8) -> List[RayHit]:
        """Check collision for a cylindrical object (e.g., endoscope).

        Samples rays around the cylinder surface.

        Args:
            tip: Cylinder tip position
            direction: Cylinder axis direction
            radius: Cylinder radius
            length: Cylinder length
            n_samples: Number of rays around circumference

        Returns:
            List of hits
        """
        direction = direction / (np.linalg.norm(direction) + 1e-8)

        # Create orthonormal basis
        if abs(direction[0]) < 0.9:
            up = np.array([1, 0, 0])
        else:
            up = np.array([0, 1, 0])

        right = np.cross(direction, up)
        right = right / np.linalg.norm(right)
        up = np.cross(right, direction)

        hits = []

        # Sample around cylinder
        for i in range(n_samples):
            angle = 2 * np.pi * i / n_samples
            offset = radius * (np.cos(angle) * right + np.sin(angle) * up)

            # Cast ray from offset position
            ray_origin = tip + offset
            hit = self.ray_cast(ray_origin, direction, length)
            if hit.hit:
                hits.append(hit)

        # Also check center ray
        center_hit = self.ray_cast(tip, direction, length)
        if center_hit.hit:
            hits.append(center_hit)

        return hits


def check_sphere_triangle(sphere_center: np.ndarray, sphere_radius: float,
                          v0: np.ndarray, v1: np.ndarray, v2: np.ndarray) -> bool:
    """Check if sphere intersects triangle."""
    # Find closest point on triangle to sphere center
    edge0 = v1 - v0
    edge1 = v2 - v0
    v0_to_center = sphere_center - v0

    # Compute dot products
    d00 = np.dot(edge0, edge0)
    d01 = np.dot(edge0, edge1)
    d11 = np.dot(edge1, edge1)
    d20 = np.dot(v0_to_center, edge0)
    d21 = np.dot(v0_to_center, edge1)

    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-10:
        return False

    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w

    # Clamp to triangle
    u = max(0, min(1, u))
    v = max(0, min(1, v))
    w = max(0, min(1, w))

    # Renormalize
    total = u + v + w
    if total > 0:
        u, v, w = u/total, v/total, w/total

    closest = u * v0 + v * v1 + w * v2

    # Check distance
    dist = np.linalg.norm(sphere_center - closest)
    return dist < sphere_radius
