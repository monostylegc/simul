"""Voxel volume for bone/tissue editing."""

import taichi as ti
import numpy as np
from typing import Dict, Tuple, Optional, TYPE_CHECKING, Union
from pathlib import Path
from dataclasses import dataclass

if TYPE_CHECKING:
    from .marching_cubes import MarchingCubes
    from .volume_io import VolumeMetadata


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

    def extract_mesh(self, isovalue: float = 0.5,
                     marching_cubes: Optional["MarchingCubes"] = None
                     ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Marching Cubes로 등치면 메쉬 추출.

        복셀 데이터에서 지정된 등위값에 해당하는 표면을 삼각형 메쉬로 추출합니다.
        드릴링 결과를 시각화하는 데 사용됩니다.

        Args:
            isovalue: 등위값 (기본값 0.5). 이 값보다 큰 복셀은 내부로 간주
            marching_cubes: 재사용할 MarchingCubes 객체 (None이면 새로 생성)

        Returns:
            (vertices, normals, faces): 각각 (N, 3) numpy 배열
        """
        from .marching_cubes import MarchingCubes

        if marching_cubes is None:
            marching_cubes = MarchingCubes()

        return marching_cubes.extract(self, isovalue)

    def create_mesh_from_volume(self, isovalue: float = 0.5) -> "TriangleMesh":
        """복셀 볼륨에서 TriangleMesh 객체 생성.

        Args:
            isovalue: 등위값

        Returns:
            TriangleMesh 객체
        """
        from .mesh import TriangleMesh

        vertices, normals, faces = self.extract_mesh(isovalue)

        if len(vertices) == 0:
            # 빈 메쉬 반환
            return TriangleMesh.create_box(size=(1, 1, 1))

        mesh = TriangleMesh(vertices, faces, name="VoxelMesh")
        return mesh

    # =========================================================================
    # 파일 I/O (NRRD/NIFTI 지원)
    # =========================================================================

    @classmethod
    def load(
        cls,
        filepath: Union[str, Path],
        max_resolution: Optional[int] = 128
    ) -> "VoxelVolume":
        """NRRD/NIFTI 파일에서 VoxelVolume 로드.

        3D Slicer에서 생성한 CT 볼륨을 로드합니다.

        Args:
            filepath: NRRD/NIFTI 파일 경로
            max_resolution: 최대 해상도 (초과 시 다운샘플링, None이면 원본 유지)

        Returns:
            VoxelVolume 객체
        """
        from .volume_io import VolumeLoader

        data, metadata = VolumeLoader.load(filepath, max_resolution)

        # VoxelVolume 생성
        volume = cls(
            resolution=data.shape,
            origin=metadata.origin,
            spacing=metadata.min_spacing
        )

        # 데이터 설정 (밀도는 정규화)
        density = data.astype(np.float32)
        if density.max() > 0:
            density = density / density.max()
        volume.data.from_numpy(density)

        # 재료는 밀도 기반으로 설정 (0 = empty, 1 = bone)
        material = np.where(density > 0.5, 1, 0).astype(np.int32)
        volume.material.from_numpy(material)

        return volume

    @classmethod
    def load_labelmap(
        cls,
        filepath: Union[str, Path],
        label_mapping: Optional[Dict[int, int]] = None,
        max_resolution: Optional[int] = 128
    ) -> "VoxelVolume":
        """세그멘테이션 labelmap에서 VoxelVolume 로드.

        3D Slicer에서 생성한 세그멘테이션 labelmap을 로드합니다.

        Args:
            filepath: Labelmap 파일 경로
            label_mapping: label → material 매핑 딕셔너리
                기본값: {0: 0 (empty), 1: 1 (bone), 2: 2 (disc), 3: 3 (soft)}
            max_resolution: 최대 해상도

        Returns:
            VoxelVolume 객체
        """
        from .volume_io import VolumeLoader

        density, material, metadata = VolumeLoader.load_labelmap(
            filepath, label_mapping, max_resolution
        )

        # VoxelVolume 생성
        volume = cls(
            resolution=density.shape,
            origin=metadata.origin,
            spacing=metadata.min_spacing
        )

        # 데이터 설정
        volume.data.from_numpy(density)
        volume.material.from_numpy(material)

        return volume

    def save_nrrd(self, filepath: Union[str, Path]):
        """NRRD 형식으로 저장.

        Args:
            filepath: 저장할 파일 경로
        """
        from .volume_io import VolumeLoader

        data = self.data.to_numpy()
        # SimpleITK는 Python native float 타입을 요구함
        origin = (float(self.origin[0]), float(self.origin[1]), float(self.origin[2]))

        VolumeLoader.save_nrrd(filepath, data, origin, float(self.spacing))
