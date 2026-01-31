"""Endoscope instrument with collision detection."""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, TYPE_CHECKING

from .camera import EndoscopeCamera
from ..core.transform import Transform

if TYPE_CHECKING:
    from ..core.collision import CollisionDetector, RayHit


@dataclass
class Endoscope:
    """Surgical endoscope with camera and collision.

    Represents a physical endoscope that can be positioned and
    oriented in the surgical field.
    """
    # Physical properties
    diameter: float = 7.0  # mm
    length: float = 150.0  # mm
    working_channel_diameter: float = 3.0  # mm

    # Position and orientation
    tip_position: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    direction: np.ndarray = field(default_factory=lambda: np.array([0, 0, 1], dtype=np.float32))

    # Camera
    camera: EndoscopeCamera = field(default_factory=EndoscopeCamera)

    # State
    is_colliding: bool = False
    collision_depth: float = 0.0

    def __post_init__(self):
        self.tip_position = np.array(self.tip_position, dtype=np.float32)
        self.direction = np.array(self.direction, dtype=np.float32)
        self.direction = self.direction / (np.linalg.norm(self.direction) + 1e-8)
        self._update_camera()

    def _update_camera(self):
        """Update camera to match endoscope position."""
        self.camera.position = self.tip_position.copy()
        self.camera.direction = self.direction.copy()

    @property
    def radius(self) -> float:
        """Get endoscope radius."""
        return self.diameter / 2

    @property
    def base_position(self) -> np.ndarray:
        """Get position of endoscope base (opposite of tip)."""
        return self.tip_position - self.direction * self.length

    def set_position(self, position: np.ndarray):
        """Set tip position."""
        self.tip_position = np.array(position, dtype=np.float32)
        self._update_camera()

    def set_direction(self, direction: np.ndarray):
        """Set viewing direction."""
        self.direction = np.array(direction, dtype=np.float32)
        self.direction = self.direction / (np.linalg.norm(self.direction) + 1e-8)
        self._update_camera()

    def move_forward(self, distance: float):
        """Move endoscope along its axis."""
        self.tip_position = self.tip_position + self.direction * distance
        self._update_camera()

    def rotate_yaw(self, angle_degrees: float):
        """Rotate around vertical axis."""
        self.camera.rotate_yaw(angle_degrees)
        self.direction = self.camera.direction.copy()

    def rotate_pitch(self, angle_degrees: float):
        """Rotate up/down."""
        self.camera.rotate_pitch(angle_degrees)
        self.direction = self.camera.direction.copy()

    def check_collision(self, detector: "CollisionDetector") -> List["RayHit"]:
        """Check collision with scene geometry.

        Args:
            detector: CollisionDetector with loaded meshes

        Returns:
            List of collision hits
        """
        hits = detector.check_cylinder_collision(
            tip=self.tip_position,
            direction=self.direction,
            radius=self.radius,
            length=self.length,
            n_samples=8
        )

        if hits:
            self.is_colliding = True
            # Find minimum penetration
            min_dist = min(h.distance for h in hits)
            self.collision_depth = max(0, self.length - min_dist)
        else:
            self.is_colliding = False
            self.collision_depth = 0.0

        return hits

    def get_mesh_geometry(self) -> tuple:
        """Get cylinder mesh for visualization.

        Returns:
            (vertices, faces) for rendering
        """
        from ..core.mesh import TriangleMesh

        # Create cylinder
        cyl = TriangleMesh.create_cylinder(
            radius=self.radius,
            height=self.length,
            segments=16
        )

        # Orient along direction
        # Default cylinder is along Z axis
        z_axis = np.array([0, 0, 1])
        if np.abs(np.dot(z_axis, self.direction)) < 0.999:
            rotation_axis = np.cross(z_axis, self.direction)
            rotation_axis = rotation_axis / np.linalg.norm(rotation_axis)
            angle = np.arccos(np.dot(z_axis, self.direction))

            c, s = np.cos(angle), np.sin(angle)
            K = np.array([
                [0, -rotation_axis[2], rotation_axis[1]],
                [rotation_axis[2], 0, -rotation_axis[0]],
                [-rotation_axis[1], rotation_axis[0], 0]
            ])
            R = np.eye(3) + s * K + (1 - c) * (K @ K)

            cyl.vertices = cyl.vertices @ R.T

        # Translate so tip is at tip_position
        # Cylinder center is at origin, so shift by half length
        cyl.vertices = cyl.vertices + self.tip_position + self.direction * self.length / 2

        return cyl.vertices, cyl.faces

    def get_camera_params(self) -> dict:
        """Get camera parameters for Taichi GGUI."""
        return self.camera.to_taichi_camera()
