"""Triangle mesh data structure with STL/OBJ loading."""

import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Tuple, List

from .transform import Transform


@dataclass
class TriangleMesh:
    """Triangle mesh for 3D models.

    Stores vertices, faces, and optional normals/colors.
    """
    vertices: np.ndarray  # (N, 3) float32
    faces: np.ndarray     # (M, 3) int32 - vertex indices
    normals: Optional[np.ndarray] = None  # (N, 3) or (M, 3)
    colors: Optional[np.ndarray] = None   # (N, 3) or (N, 4)
    name: str = "mesh"
    transform: Transform = field(default_factory=Transform)

    def __post_init__(self):
        self.vertices = np.array(self.vertices, dtype=np.float32)
        self.faces = np.array(self.faces, dtype=np.int32)
        if self.normals is None:
            self.compute_normals()

    @property
    def n_vertices(self) -> int:
        return len(self.vertices)

    @property
    def n_faces(self) -> int:
        return len(self.faces)

    def compute_normals(self):
        """Compute per-vertex normals from faces."""
        self.normals = np.zeros_like(self.vertices)

        for face in self.faces:
            v0, v1, v2 = self.vertices[face]
            normal = np.cross(v1 - v0, v2 - v0)
            norm = np.linalg.norm(normal)
            if norm > 1e-8:
                normal /= norm
            self.normals[face] += normal

        # Normalize
        norms = np.linalg.norm(self.normals, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        self.normals /= norms

    def get_transformed_vertices(self) -> np.ndarray:
        """Get vertices in world coordinates."""
        return self.transform.apply(self.vertices)

    def get_transformed_normals(self) -> np.ndarray:
        """Get normals in world coordinates."""
        if self.normals is None:
            self.compute_normals()
        return self.transform.apply_direction(self.normals)

    def get_bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get axis-aligned bounding box (min, max)."""
        verts = self.get_transformed_vertices()
        return verts.min(axis=0), verts.max(axis=0)

    def get_center(self) -> np.ndarray:
        """Get center of bounding box."""
        min_b, max_b = self.get_bounds()
        return (min_b + max_b) / 2

    @classmethod
    def load_stl(cls, filepath: str, name: Optional[str] = None) -> "TriangleMesh":
        """Load mesh from STL file.

        Supports both ASCII and binary STL.
        """
        filepath = Path(filepath)
        if name is None:
            name = filepath.stem

        with open(filepath, 'rb') as f:
            header = f.read(80)

            # Check if ASCII or binary
            f.seek(0)
            try:
                first_line = f.readline().decode('ascii').strip().lower()
                is_ascii = first_line.startswith('solid')
            except:
                is_ascii = False

            f.seek(0)

        if is_ascii:
            return cls._load_stl_ascii(filepath, name)
        else:
            return cls._load_stl_binary(filepath, name)

    @classmethod
    def _load_stl_binary(cls, filepath: Path, name: str) -> "TriangleMesh":
        """Load binary STL."""
        with open(filepath, 'rb') as f:
            f.read(80)  # header
            n_triangles = np.frombuffer(f.read(4), dtype=np.uint32)[0]

            vertices = []
            face_normals = []

            for _ in range(n_triangles):
                normal = np.frombuffer(f.read(12), dtype=np.float32)
                v0 = np.frombuffer(f.read(12), dtype=np.float32)
                v1 = np.frombuffer(f.read(12), dtype=np.float32)
                v2 = np.frombuffer(f.read(12), dtype=np.float32)
                f.read(2)  # attribute byte count

                face_normals.append(normal)
                vertices.extend([v0, v1, v2])

        vertices = np.array(vertices, dtype=np.float32)
        faces = np.arange(len(vertices), dtype=np.int32).reshape(-1, 3)

        # Merge duplicate vertices
        vertices, faces = cls._merge_vertices(vertices, faces)

        return cls(vertices=vertices, faces=faces, name=name)

    @classmethod
    def _load_stl_ascii(cls, filepath: Path, name: str) -> "TriangleMesh":
        """Load ASCII STL."""
        vertices = []

        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip().lower()
                if line.startswith('vertex'):
                    parts = line.split()
                    v = [float(parts[1]), float(parts[2]), float(parts[3])]
                    vertices.append(v)

        vertices = np.array(vertices, dtype=np.float32)
        faces = np.arange(len(vertices), dtype=np.int32).reshape(-1, 3)

        vertices, faces = cls._merge_vertices(vertices, faces)

        return cls(vertices=vertices, faces=faces, name=name)

    @classmethod
    def load_obj(cls, filepath: str, name: Optional[str] = None) -> "TriangleMesh":
        """Load mesh from OBJ file."""
        filepath = Path(filepath)
        if name is None:
            name = filepath.stem

        vertices = []
        faces = []

        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split()
                if parts[0] == 'v':
                    vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
                elif parts[0] == 'f':
                    # Handle different face formats: v, v/vt, v/vt/vn, v//vn
                    face = []
                    for p in parts[1:]:
                        idx = int(p.split('/')[0]) - 1  # OBJ is 1-indexed
                        face.append(idx)
                    # Triangulate if needed
                    for i in range(1, len(face) - 1):
                        faces.append([face[0], face[i], face[i+1]])

        return cls(
            vertices=np.array(vertices, dtype=np.float32),
            faces=np.array(faces, dtype=np.int32),
            name=name
        )

    @classmethod
    def load(cls, filepath: str, name: Optional[str] = None) -> "TriangleMesh":
        """Load mesh from file (auto-detect format)."""
        filepath = Path(filepath)
        ext = filepath.suffix.lower()

        if ext == '.stl':
            return cls.load_stl(filepath, name)
        elif ext == '.obj':
            return cls.load_obj(filepath, name)
        else:
            raise ValueError(f"Unsupported format: {ext}")

    @staticmethod
    def _merge_vertices(vertices: np.ndarray, faces: np.ndarray,
                        tolerance: float = 1e-6) -> Tuple[np.ndarray, np.ndarray]:
        """Merge duplicate vertices."""
        # Round to tolerance
        rounded = np.round(vertices / tolerance) * tolerance

        # Find unique vertices
        unique, inverse = np.unique(rounded, axis=0, return_inverse=True)

        # Remap faces
        new_faces = inverse[faces]

        return unique.astype(np.float32), new_faces.astype(np.int32)

    def to_taichi_mesh(self):
        """Convert to Taichi-compatible format for rendering.

        Returns vertices and indices as flat arrays.
        """
        verts = self.get_transformed_vertices()
        norms = self.get_transformed_normals()

        # Flatten for Taichi GGUI
        return {
            'vertices': verts,
            'normals': norms,
            'indices': self.faces.flatten()
        }

    @classmethod
    def create_box(cls, size: Tuple[float, float, float] = (1, 1, 1),
                   center: Tuple[float, float, float] = (0, 0, 0)) -> "TriangleMesh":
        """Create a box mesh."""
        sx, sy, sz = size
        cx, cy, cz = center

        vertices = np.array([
            [-sx/2, -sy/2, -sz/2], [sx/2, -sy/2, -sz/2],
            [sx/2, sy/2, -sz/2], [-sx/2, sy/2, -sz/2],
            [-sx/2, -sy/2, sz/2], [sx/2, -sy/2, sz/2],
            [sx/2, sy/2, sz/2], [-sx/2, sy/2, sz/2],
        ], dtype=np.float32) + np.array([cx, cy, cz], dtype=np.float32)

        faces = np.array([
            [0, 1, 2], [0, 2, 3],  # bottom
            [4, 6, 5], [4, 7, 6],  # top
            [0, 4, 5], [0, 5, 1],  # front
            [2, 6, 7], [2, 7, 3],  # back
            [0, 3, 7], [0, 7, 4],  # left
            [1, 5, 6], [1, 6, 2],  # right
        ], dtype=np.int32)

        return cls(vertices=vertices, faces=faces, name="box")

    @classmethod
    def create_cylinder(cls, radius: float = 0.5, height: float = 1.0,
                        segments: int = 16) -> "TriangleMesh":
        """Create a cylinder mesh."""
        vertices = []
        faces = []

        # Side vertices
        for i in range(segments):
            angle = 2 * np.pi * i / segments
            x, y = radius * np.cos(angle), radius * np.sin(angle)
            vertices.append([x, y, -height/2])
            vertices.append([x, y, height/2])

        # Side faces
        for i in range(segments):
            i0 = i * 2
            i1 = i * 2 + 1
            i2 = ((i + 1) % segments) * 2
            i3 = ((i + 1) % segments) * 2 + 1
            faces.append([i0, i2, i1])
            faces.append([i1, i2, i3])

        # Top and bottom center vertices
        bottom_center = len(vertices)
        vertices.append([0, 0, -height/2])
        top_center = len(vertices)
        vertices.append([0, 0, height/2])

        # Top and bottom faces
        for i in range(segments):
            i0 = i * 2
            i2 = ((i + 1) % segments) * 2
            faces.append([bottom_center, i0, i2])

            i1 = i * 2 + 1
            i3 = ((i + 1) % segments) * 2 + 1
            faces.append([top_center, i3, i1])

        return cls(
            vertices=np.array(vertices, dtype=np.float32),
            faces=np.array(faces, dtype=np.int32),
            name="cylinder"
        )
