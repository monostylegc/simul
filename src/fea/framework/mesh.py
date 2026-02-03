"""메쉬 생성 모듈.

STL에서 FEM 메쉬 또는 PD 입자 생성.
"""

import numpy as np
import pyvista as pv
from typing import Tuple, Optional, Literal
from dataclasses import dataclass, field


@dataclass
class FEMMesh:
    """FEM 테트라헤드럴 메쉬."""
    nodes: np.ndarray           # (n_nodes, 3)
    elements: np.ndarray        # (n_elements, 4)
    surface_nodes: np.ndarray = field(default_factory=lambda: np.array([]))

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def n_elements(self) -> int:
        return len(self.elements)

    @property
    def bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        """(min, max) 좌표."""
        return self.nodes.min(axis=0), self.nodes.max(axis=0)


@dataclass
class PDParticles:
    """Peridynamics 입자."""
    positions: np.ndarray       # (n_particles, 3)
    spacing: float              # 격자 간격

    @property
    def n_particles(self) -> int:
        return len(self.positions)

    @property
    def bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        return self.positions.min(axis=0), self.positions.max(axis=0)

    @property
    def volume(self) -> float:
        """단일 입자 부피."""
        return self.spacing ** 3


class MeshGenerator:
    """STL에서 메쉬/입자 생성."""

    @staticmethod
    def load_stl(filepath: str) -> Tuple[np.ndarray, np.ndarray]:
        """STL 파일 로드.

        Returns:
            vertices: (N, 3) 정점
            faces: (M, 3) 삼각형 인덱스
        """
        from spine_sim.core.mesh import TriangleMesh
        mesh = TriangleMesh.load_stl(filepath)
        return mesh.vertices, mesh.faces

    @staticmethod
    def create_fem_mesh(
        vertices: np.ndarray,
        faces: np.ndarray,
        quality: float = 2.0
    ) -> FEMMesh:
        """STL에서 FEM 테트라헤드럴 메쉬 생성.

        Args:
            vertices: 표면 정점
            faces: 표면 삼각형
            quality: tetgen 품질 파라미터 (낮을수록 조밀)

        Returns:
            FEMMesh 객체
        """
        import tetgen

        tgen = tetgen.TetGen(vertices.astype(np.float64), faces.astype(np.int32))
        nodes, elements, _, _ = tgen.tetrahedralize(
            order=1,
            quality=True,
            minratio=quality,
        )

        # 표면 노드 찾기 (z_min, z_max 근처)
        z_min, z_max = nodes[:, 2].min(), nodes[:, 2].max()
        tol = (z_max - z_min) * 0.05
        surface = np.where(
            (nodes[:, 2] < z_min + tol) | (nodes[:, 2] > z_max - tol)
        )[0]

        return FEMMesh(
            nodes=nodes.astype(np.float32),
            elements=elements.astype(np.int32),
            surface_nodes=surface.astype(np.int32)
        )

    @staticmethod
    def create_pd_particles(
        vertices: np.ndarray,
        faces: np.ndarray,
        spacing: float = 2.0
    ) -> PDParticles:
        """STL에서 균일 격자 입자 생성.

        Args:
            vertices: 표면 정점
            faces: 표면 삼각형
            spacing: 격자 간격 [mm]

        Returns:
            PDParticles 객체
        """
        # 바운딩 박스
        mins = vertices.min(axis=0) - spacing
        maxs = vertices.max(axis=0) + spacing

        # 격자 생성
        x = np.arange(mins[0], maxs[0], spacing)
        y = np.arange(mins[1], maxs[1], spacing)
        z = np.arange(mins[2], maxs[2], spacing)

        xx, yy, zz = np.meshgrid(x, y, z, indexing='ij')
        grid_points = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])

        # PyVista로 내부 점 필터링
        pv_faces = np.hstack([np.full((len(faces), 1), 3), faces]).flatten()
        surface = pv.PolyData(vertices, pv_faces)
        cloud = pv.PolyData(grid_points)
        selection = cloud.select_enclosed_points(surface, tolerance=0.0)
        mask = selection.point_data['SelectedPoints'].astype(bool)

        return PDParticles(
            positions=grid_points[mask].astype(np.float32),
            spacing=spacing
        )

    @staticmethod
    def find_interface_nodes(
        positions: np.ndarray,
        z_min: float,
        z_max: float,
        tolerance: float = 5.0
    ) -> np.ndarray:
        """특정 z 범위의 노드/입자 인덱스 찾기."""
        mask = (positions[:, 2] >= z_min - tolerance) & \
               (positions[:, 2] <= z_max + tolerance)
        return np.where(mask)[0]
