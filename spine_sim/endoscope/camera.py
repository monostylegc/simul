"""Endoscope camera for surgical view rendering."""

import taichi as ti
import numpy as np
from typing import Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class EndoscopeCamera:
    """Endoscope camera with configurable FOV and rendering.

    Provides a surgical view from the endoscope tip.
    """
    position: np.ndarray = field(default_factory=lambda: np.array([0, 0, 0], dtype=np.float32))
    direction: np.ndarray = field(default_factory=lambda: np.array([0, 0, 1], dtype=np.float32))
    up: np.ndarray = field(default_factory=lambda: np.array([0, 1, 0], dtype=np.float32))

    fov: float = 70.0  # Field of view in degrees
    near: float = 0.1  # Near clipping plane
    far: float = 100.0  # Far clipping plane

    # Image resolution
    width: int = 512
    height: int = 512

    def __post_init__(self):
        self.position = np.array(self.position, dtype=np.float32)
        self.direction = np.array(self.direction, dtype=np.float32)
        self.up = np.array(self.up, dtype=np.float32)
        self._normalize_vectors()

    def _normalize_vectors(self):
        """Normalize direction and up vectors."""
        self.direction = self.direction / (np.linalg.norm(self.direction) + 1e-8)

        # Make up perpendicular to direction
        right = np.cross(self.direction, self.up)
        right = right / (np.linalg.norm(right) + 1e-8)
        self.up = np.cross(right, self.direction)
        self.up = self.up / (np.linalg.norm(self.up) + 1e-8)

    def look_at(self, target: np.ndarray):
        """Point camera at target position."""
        self.direction = np.array(target, dtype=np.float32) - self.position
        self.direction = self.direction / (np.linalg.norm(self.direction) + 1e-8)
        self._normalize_vectors()

    def move_forward(self, distance: float):
        """Move camera along viewing direction."""
        self.position = self.position + self.direction * distance

    def rotate_yaw(self, angle_degrees: float):
        """Rotate camera left/right around up axis."""
        angle = np.radians(angle_degrees)
        c, s = np.cos(angle), np.sin(angle)

        # Rotation around up vector
        up = self.up
        K = np.array([
            [0, -up[2], up[1]],
            [up[2], 0, -up[0]],
            [-up[1], up[0], 0]
        ])
        R = np.eye(3) + s * K + (1 - c) * (K @ K)

        self.direction = R @ self.direction
        self._normalize_vectors()

    def rotate_pitch(self, angle_degrees: float):
        """Rotate camera up/down around right axis."""
        angle = np.radians(angle_degrees)
        c, s = np.cos(angle), np.sin(angle)

        right = np.cross(self.direction, self.up)
        right = right / (np.linalg.norm(right) + 1e-8)

        K = np.array([
            [0, -right[2], right[1]],
            [right[2], 0, -right[0]],
            [-right[1], right[0], 0]
        ])
        R = np.eye(3) + s * K + (1 - c) * (K @ K)

        self.direction = R @ self.direction
        self.up = R @ self.up
        self._normalize_vectors()

    def get_view_matrix(self) -> np.ndarray:
        """Get 4x4 view matrix."""
        right = np.cross(self.direction, self.up)
        right = right / (np.linalg.norm(right) + 1e-8)

        view = np.eye(4, dtype=np.float32)
        view[0, :3] = right
        view[1, :3] = self.up
        view[2, :3] = -self.direction
        view[:3, 3] = -view[:3, :3] @ self.position

        return view

    def get_projection_matrix(self, aspect: Optional[float] = None) -> np.ndarray:
        """Get 4x4 perspective projection matrix."""
        if aspect is None:
            aspect = self.width / self.height

        fov_rad = np.radians(self.fov)
        f = 1.0 / np.tan(fov_rad / 2)

        proj = np.zeros((4, 4), dtype=np.float32)
        proj[0, 0] = f / aspect
        proj[1, 1] = f
        proj[2, 2] = (self.far + self.near) / (self.near - self.far)
        proj[2, 3] = (2 * self.far * self.near) / (self.near - self.far)
        proj[3, 2] = -1

        return proj

    def get_ray(self, pixel_x: int, pixel_y: int) -> Tuple[np.ndarray, np.ndarray]:
        """Get ray from camera through pixel.

        Args:
            pixel_x, pixel_y: Pixel coordinates

        Returns:
            (origin, direction) tuple
        """
        # Normalized device coordinates
        ndc_x = (2.0 * pixel_x / self.width - 1.0)
        ndc_y = (1.0 - 2.0 * pixel_y / self.height)

        # Camera space direction
        aspect = self.width / self.height
        fov_rad = np.radians(self.fov)
        tan_half_fov = np.tan(fov_rad / 2)

        right = np.cross(self.direction, self.up)
        right = right / (np.linalg.norm(right) + 1e-8)

        ray_dir = (
            self.direction +
            ndc_x * tan_half_fov * aspect * right +
            ndc_y * tan_half_fov * self.up
        )
        ray_dir = ray_dir / (np.linalg.norm(ray_dir) + 1e-8)

        return self.position.copy(), ray_dir

    def get_frustum_corners(self, distance: float = 10.0) -> np.ndarray:
        """Get 4 corners of view frustum at given distance.

        Returns:
            (4, 3) array of corner positions
        """
        aspect = self.width / self.height
        fov_rad = np.radians(self.fov)
        half_height = distance * np.tan(fov_rad / 2)
        half_width = half_height * aspect

        right = np.cross(self.direction, self.up)
        right = right / (np.linalg.norm(right) + 1e-8)

        center = self.position + self.direction * distance

        corners = np.array([
            center - half_width * right - half_height * self.up,
            center + half_width * right - half_height * self.up,
            center + half_width * right + half_height * self.up,
            center - half_width * right + half_height * self.up,
        ], dtype=np.float32)

        return corners

    def to_taichi_camera(self):
        """Convert to parameters suitable for Taichi GGUI camera."""
        return {
            'position': tuple(self.position),
            'lookat': tuple(self.position + self.direction),
            'up': tuple(self.up),
            'fov': self.fov
        }
