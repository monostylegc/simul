"""Main spine surgery simulator application."""

import taichi as ti
import numpy as np
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from ..core.mesh import TriangleMesh
from ..core.volume import VoxelVolume
from ..core.collision import CollisionDetector
from ..core.transform import Transform
from ..endoscope.instrument import Endoscope


@dataclass
class SceneObject:
    """Object in the surgical scene."""
    mesh: TriangleMesh
    color: tuple = (0.8, 0.8, 0.8)
    visible: bool = True
    selectable: bool = True


@ti.data_oriented
class SpineSimulator:
    """Main application for spine surgery simulation.

    Features:
    - Load and display 3D models (STL/OBJ)
    - Position and orient vertebrae
    - Endoscope navigation with collision detection
    - Surgical drilling (voxel removal)
    """

    def __init__(self, width: int = 1280, height: int = 720):
        """Initialize simulator.

        Args:
            width, height: Window size
        """
        self.width = width
        self.height = height

        # Scene objects
        self.objects: Dict[str, SceneObject] = {}
        self.selected_object: Optional[str] = None

        # Collision detector
        self.collision = CollisionDetector(max_triangles=500000)

        # Endoscope
        self.endoscope = Endoscope()
        self.show_endoscope_view = False

        # Voxel volume for drilling
        self.volume: Optional[VoxelVolume] = None

        # Rendering data
        self.vertices = ti.Vector.field(3, dtype=ti.f32, shape=100000)
        self.normals = ti.Vector.field(3, dtype=ti.f32, shape=100000)
        self.colors = ti.Vector.field(3, dtype=ti.f32, shape=100000)
        self.indices = ti.field(dtype=ti.i32, shape=300000)
        self.n_vertices = 0
        self.n_indices = 0

        # Camera
        self.camera_distance = 200.0
        self.camera_theta = 0.0  # Horizontal angle
        self.camera_phi = 30.0   # Vertical angle
        self.camera_target = np.array([0, 0, 0], dtype=np.float32)

        # Interaction state
        self.mouse_down = False
        self.last_mouse = (0, 0)
        self.tool_mode = "navigate"  # navigate, position, drill

        # Drill settings
        self.drill_radius = 2.0
        self.drill_active = False

    def load_model(self, filepath: str, name: Optional[str] = None,
                   color: tuple = (0.9, 0.85, 0.75)) -> str:
        """Load a 3D model from file.

        Args:
            filepath: Path to STL or OBJ file
            name: Object name (uses filename if None)
            color: RGB color tuple

        Returns:
            Object name
        """
        mesh = TriangleMesh.load(filepath, name)
        if name is None:
            name = mesh.name

        self.objects[name] = SceneObject(mesh=mesh, color=color)
        self._update_render_data()

        print(f"Loaded '{name}': {mesh.n_vertices} vertices, {mesh.n_faces} faces")
        return name

    def add_sample_vertebra(self, name: str = "L4", position: tuple = (0, 0, 0)):
        """Add a sample vertebra (box placeholder)."""
        # Create a simple box as placeholder
        mesh = TriangleMesh.create_box(size=(30, 25, 20))
        mesh.name = name
        mesh.transform.position = np.array(position, dtype=np.float32)

        self.objects[name] = SceneObject(
            mesh=mesh,
            color=(0.9, 0.85, 0.75)  # Bone color
        )
        self._update_render_data()
        return name

    def set_object_position(self, name: str, position: tuple):
        """Set object position."""
        if name in self.objects:
            self.objects[name].mesh.transform.position = np.array(position, dtype=np.float32)
            self._update_render_data()

    def set_object_rotation(self, name: str, rx: float, ry: float, rz: float):
        """Set object rotation (Euler angles in degrees)."""
        if name in self.objects:
            t = Transform.from_euler(rx, ry, rz)
            self.objects[name].mesh.transform.rotation = t.rotation
            self._update_render_data()

    def _update_render_data(self):
        """Update rendering buffers from scene objects."""
        all_verts = []
        all_norms = []
        all_colors = []
        all_indices = []

        vertex_offset = 0

        for name, obj in self.objects.items():
            if not obj.visible:
                continue

            mesh = obj.mesh
            verts = mesh.get_transformed_vertices()
            norms = mesh.get_transformed_normals()

            n_v = len(verts)
            all_verts.append(verts)
            all_norms.append(norms)
            all_colors.append(np.tile(obj.color, (n_v, 1)))
            all_indices.append(mesh.faces + vertex_offset)

            vertex_offset += n_v

        if all_verts:
            verts = np.vstack(all_verts).astype(np.float32)
            norms = np.vstack(all_norms).astype(np.float32)
            colors = np.vstack(all_colors).astype(np.float32)
            indices = np.vstack(all_indices).flatten().astype(np.int32)

            self.n_vertices = min(len(verts), 100000)
            self.n_indices = min(len(indices), 300000)

            # Truncate if needed
            verts = verts[:self.n_vertices]
            norms = norms[:self.n_vertices]
            colors = colors[:self.n_vertices]
            indices = indices[:self.n_indices]

            # Pad to fixed size
            verts_padded = np.zeros((100000, 3), dtype=np.float32)
            norms_padded = np.zeros((100000, 3), dtype=np.float32)
            colors_padded = np.zeros((100000, 3), dtype=np.float32)
            indices_padded = np.zeros(300000, dtype=np.int32)

            verts_padded[:len(verts)] = verts
            norms_padded[:len(norms)] = norms
            colors_padded[:len(colors)] = colors
            indices_padded[:len(indices)] = indices

            self.vertices.from_numpy(verts_padded)
            self.normals.from_numpy(norms_padded)
            self.colors.from_numpy(colors_padded)
            self.indices.from_numpy(indices_padded)

            # Update collision detector with original faces
            faces = np.vstack(all_indices).astype(np.int32)
            if len(faces) <= self.collision.max_triangles:
                self.collision.load_mesh(verts, faces)
        else:
            self.n_vertices = 0
            self.n_indices = 0

    def _get_camera_position(self) -> np.ndarray:
        """Get camera position from spherical coordinates."""
        theta = np.radians(self.camera_theta)
        phi = np.radians(self.camera_phi)

        x = self.camera_distance * np.cos(phi) * np.sin(theta)
        y = self.camera_distance * np.sin(phi)
        z = self.camera_distance * np.cos(phi) * np.cos(theta)

        return self.camera_target + np.array([x, y, z])

    def run(self):
        """Run the simulator with GUI."""
        window = ti.ui.Window("Spine Surgery Simulator", (self.width, self.height), vsync=True)
        canvas = window.get_canvas()
        scene = window.get_scene()
        camera = ti.ui.Camera()

        # GUI state
        gui = window.get_gui()

        while window.running:
            # Handle input
            self._handle_input(window)

            # Update camera
            cam_pos = self._get_camera_position()
            camera.position(*cam_pos)
            camera.lookat(*self.camera_target)
            camera.up(0, 1, 0)
            camera.fov(60)

            scene.set_camera(camera)
            scene.ambient_light((0.3, 0.3, 0.3))
            scene.point_light(pos=tuple(cam_pos + np.array([50, 100, 50])), color=(1, 1, 1))

            # Draw meshes
            if self.n_vertices > 0:
                scene.mesh(
                    self.vertices,
                    indices=self.indices,
                    normals=self.normals,
                    per_vertex_color=self.colors,
                    two_sided=True
                )

            # Draw endoscope
            if self.tool_mode in ["navigate", "drill"]:
                endo_verts, endo_faces = self.endoscope.get_mesh_geometry()
                # Would need separate buffer for endoscope rendering

            canvas.scene(scene)

            # GUI Panel
            with gui.sub_window("Controls", 0.01, 0.01, 0.25, 0.4) as w:
                w.text("Spine Surgery Simulator")
                w.text("")

                # Tool mode
                w.text("Tool Mode:")
                if w.button("Navigate"):
                    self.tool_mode = "navigate"
                if w.button("Position Object"):
                    self.tool_mode = "position"
                if w.button("Drill"):
                    self.tool_mode = "drill"

                w.text(f"Current: {self.tool_mode}")
                w.text("")

                # Endoscope controls
                w.text("Endoscope:")
                if w.button("Toggle View"):
                    self.show_endoscope_view = not self.show_endoscope_view

                w.text(f"Position: {self.endoscope.tip_position}")
                w.text(f"Colliding: {self.endoscope.is_colliding}")

                # Drill settings
                if self.tool_mode == "drill":
                    w.text("")
                    w.text("Drill Settings:")
                    self.drill_radius = w.slider_float("Radius", self.drill_radius, 0.5, 5.0)

            # Object list
            with gui.sub_window("Objects", 0.01, 0.45, 0.25, 0.35) as w:
                w.text("Scene Objects:")
                for name, obj in self.objects.items():
                    selected = name == self.selected_object
                    prefix = "> " if selected else "  "
                    if w.button(f"{prefix}{name}"):
                        self.selected_object = name

                w.text("")
                if w.button("Add Sample Vertebra"):
                    n = len([o for o in self.objects if o.startswith("L")])
                    self.add_sample_vertebra(f"L{n+1}", position=(0, -30 * n, 0))

            # Instructions
            with gui.sub_window("Help", 0.01, 0.82, 0.25, 0.17) as w:
                w.text("Controls:")
                w.text("Mouse drag: Rotate view")
                w.text("Scroll: Zoom")
                w.text("WASD: Move endoscope")
                w.text("Q/E: Rotate endoscope")

            window.show()

    def _handle_input(self, window):
        """Handle keyboard and mouse input."""
        # Mouse rotation
        mouse = window.get_cursor_pos()

        if window.is_pressed(ti.ui.LMB):
            if self.mouse_down:
                dx = (mouse[0] - self.last_mouse[0]) * 200
                dy = (mouse[1] - self.last_mouse[1]) * 200
                self.camera_theta -= dx
                self.camera_phi = np.clip(self.camera_phi + dy, -89, 89)
            self.mouse_down = True
        else:
            self.mouse_down = False

        self.last_mouse = mouse

        # Keyboard
        move_speed = 2.0
        rotate_speed = 2.0

        if window.is_pressed('w'):
            self.endoscope.move_forward(move_speed)
        if window.is_pressed('s'):
            self.endoscope.move_forward(-move_speed)
        if window.is_pressed('a'):
            self.endoscope.rotate_yaw(-rotate_speed)
        if window.is_pressed('d'):
            self.endoscope.rotate_yaw(rotate_speed)
        if window.is_pressed('q'):
            self.endoscope.rotate_pitch(-rotate_speed)
        if window.is_pressed('e'):
            self.endoscope.rotate_pitch(rotate_speed)

        # Check endoscope collision
        self.endoscope.check_collision(self.collision)

        # Zoom with scroll (if supported)
        # Taichi GGUI doesn't have direct scroll support, use +/- keys
        if window.is_pressed('=') or window.is_pressed('+'):
            self.camera_distance = max(10, self.camera_distance - 5)
        if window.is_pressed('-'):
            self.camera_distance = min(500, self.camera_distance + 5)


def main():
    """Run the spine surgery simulator."""
    ti.init(arch=ti.gpu)

    sim = SpineSimulator(width=1400, height=900)

    # Add sample vertebrae
    sim.add_sample_vertebra("L5", position=(0, 0, 0))
    sim.add_sample_vertebra("L4", position=(0, 30, 0))
    sim.add_sample_vertebra("L3", position=(0, 60, 0))

    # Position endoscope
    sim.endoscope.set_position(np.array([50, 30, 50]))
    sim.endoscope.set_direction(np.array([-1, 0, -1]))

    sim.run()


if __name__ == "__main__":
    main()
