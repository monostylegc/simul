"""3D transformation utilities."""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Transform:
    """3D rigid body transformation.

    Represents position and rotation of an object in 3D space.
    """
    position: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    rotation: np.ndarray = field(default_factory=lambda: np.eye(3, dtype=np.float32))
    scale: float = 1.0

    def __post_init__(self):
        self.position = np.array(self.position, dtype=np.float32)
        self.rotation = np.array(self.rotation, dtype=np.float32)

    def get_matrix(self) -> np.ndarray:
        """Get 4x4 transformation matrix."""
        mat = np.eye(4, dtype=np.float32)
        mat[:3, :3] = self.rotation * self.scale
        mat[:3, 3] = self.position
        return mat

    def apply(self, points: np.ndarray) -> np.ndarray:
        """Apply transformation to points.

        Args:
            points: (N, 3) array of points

        Returns:
            Transformed points (N, 3)
        """
        return (points @ self.rotation.T) * self.scale + self.position

    def apply_direction(self, directions: np.ndarray) -> np.ndarray:
        """Apply rotation to direction vectors (no translation)."""
        return directions @ self.rotation.T

    @staticmethod
    def from_euler(rx: float, ry: float, rz: float, degrees: bool = True) -> "Transform":
        """Create transform from Euler angles (XYZ order)."""
        if degrees:
            rx, ry, rz = np.radians([rx, ry, rz])

        cx, sx = np.cos(rx), np.sin(rx)
        cy, sy = np.cos(ry), np.sin(ry)
        cz, sz = np.cos(rz), np.sin(rz)

        Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
        Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])

        t = Transform()
        t.rotation = (Rz @ Ry @ Rx).astype(np.float32)
        return t

    def translate(self, delta: np.ndarray) -> "Transform":
        """Return new transform with added translation."""
        new = Transform(self.position.copy(), self.rotation.copy(), self.scale)
        new.position += np.array(delta, dtype=np.float32)
        return new

    def rotate_local(self, axis: np.ndarray, angle: float, degrees: bool = True) -> "Transform":
        """Rotate around local axis."""
        if degrees:
            angle = np.radians(angle)

        axis = np.array(axis, dtype=np.float32)
        axis = axis / (np.linalg.norm(axis) + 1e-8)

        c, s = np.cos(angle), np.sin(angle)
        K = np.array([
            [0, -axis[2], axis[1]],
            [axis[2], 0, -axis[0]],
            [-axis[1], axis[0], 0]
        ])
        R = np.eye(3) + s * K + (1 - c) * (K @ K)

        new = Transform(self.position.copy(), self.rotation.copy(), self.scale)
        new.rotation = (R @ self.rotation).astype(np.float32)
        return new
