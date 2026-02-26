"""Incremental Marching Cubes - 실시간 드릴링을 위한 최적화된 메쉬 추출.

기존 Marching Cubes의 문제점:
- 매 프레임 전체 볼륨을 재계산
- serialize=True로 GPU 병렬화 이점 없음

해결책:
- 볼륨을 청크(chunk)로 나눔
- 드릴링 영향 받는 청크만 재계산 (dirty tracking)
- 청크별 메쉬를 캐시하고 필요할 때만 업데이트
"""

import taichi as ti
import numpy as np
from typing import Tuple, List, Optional, Set
from dataclasses import dataclass, field

from .marching_cubes import MarchingCubes


@dataclass
class ChunkMesh:
    """청크별 메쉬 데이터."""
    vertices: np.ndarray
    normals: np.ndarray
    faces: np.ndarray
    is_valid: bool = True


@ti.data_oriented
class IncrementalMarchingCubes:
    """증분 Marching Cubes.

    볼륨을 청크로 나누어 변경된 부분만 재계산합니다.
    실시간 드릴링에 적합합니다.
    """

    def __init__(
        self,
        volume_size: Tuple[int, int, int],
        chunk_size: int = 16,
        max_vertices_per_chunk: int = 50000,
        max_triangles_per_chunk: int = 50000
    ):
        """증분 Marching Cubes 초기화.

        Args:
            volume_size: 볼륨 크기 (nx, ny, nz)
            chunk_size: 청크 크기 (기본 16)
            max_vertices_per_chunk: 청크당 최대 정점 수
            max_triangles_per_chunk: 청크당 최대 삼각형 수
        """
        self.volume_size = volume_size
        self.chunk_size = chunk_size

        # 청크 그리드 크기 계산
        self.n_chunks_x = (volume_size[0] + chunk_size - 1) // chunk_size
        self.n_chunks_y = (volume_size[1] + chunk_size - 1) // chunk_size
        self.n_chunks_z = (volume_size[2] + chunk_size - 1) // chunk_size

        # 청크별 Marching Cubes
        self.mc = MarchingCubes(
            max_vertices=max_vertices_per_chunk,
            max_triangles=max_triangles_per_chunk
        )

        # 청크 메쉬 캐시
        self.chunk_meshes: dict = {}  # (cx, cy, cz) -> ChunkMesh

        # Dirty 청크 추적
        self.dirty_chunks: Set[Tuple[int, int, int]] = set()

        # 전체 메쉬 캐시
        self._cached_vertices: Optional[np.ndarray] = None
        self._cached_normals: Optional[np.ndarray] = None
        self._cached_faces: Optional[np.ndarray] = None
        self._mesh_dirty = True

    def mark_dirty(self, x: int, y: int, z: int, radius: float = 0):
        """특정 위치를 dirty로 표시.

        드릴링 영역 주변의 청크들을 dirty로 마킹합니다.

        Args:
            x, y, z: 볼륨 좌표
            radius: 영향 반경 (복셀 단위)
        """
        # 영향 받는 복셀 범위
        r = int(radius) + 1
        x_min = max(0, x - r)
        x_max = min(self.volume_size[0] - 1, x + r)
        y_min = max(0, y - r)
        y_max = min(self.volume_size[1] - 1, y + r)
        z_min = max(0, z - r)
        z_max = min(self.volume_size[2] - 1, z + r)

        # 영향 받는 청크 계산
        cx_min = x_min // self.chunk_size
        cx_max = x_max // self.chunk_size
        cy_min = y_min // self.chunk_size
        cy_max = y_max // self.chunk_size
        cz_min = z_min // self.chunk_size
        cz_max = z_max // self.chunk_size

        for cx in range(cx_min, cx_max + 1):
            for cy in range(cy_min, cy_max + 1):
                for cz in range(cz_min, cz_max + 1):
                    self.dirty_chunks.add((cx, cy, cz))

        self._mesh_dirty = True

    def mark_all_dirty(self):
        """모든 청크를 dirty로 표시."""
        for cx in range(self.n_chunks_x):
            for cy in range(self.n_chunks_y):
                for cz in range(self.n_chunks_z):
                    self.dirty_chunks.add((cx, cy, cz))
        self._mesh_dirty = True

    def _extract_chunk(
        self,
        volume,
        cx: int, cy: int, cz: int,
        isovalue: float
    ) -> ChunkMesh:
        """단일 청크의 메쉬 추출.

        Args:
            volume: VoxelVolume 객체
            cx, cy, cz: 청크 인덱스
            isovalue: 등위값

        Returns:
            청크 메쉬
        """
        # 청크 볼륨 범위 계산
        x_start = cx * self.chunk_size
        y_start = cy * self.chunk_size
        z_start = cz * self.chunk_size

        x_end = min(x_start + self.chunk_size + 1, volume.nx)
        y_end = min(y_start + self.chunk_size + 1, volume.ny)
        z_end = min(z_start + self.chunk_size + 1, volume.nz)

        # 청크 크기가 너무 작으면 스킵
        if x_end - x_start < 2 or y_end - y_start < 2 or z_end - z_start < 2:
            return ChunkMesh(
                vertices=np.zeros((0, 3), dtype=np.float32),
                normals=np.zeros((0, 3), dtype=np.float32),
                faces=np.zeros((0, 3), dtype=np.int32),
                is_valid=True
            )

        # 청크 데이터 추출
        chunk_data = volume.data.to_numpy()[
            x_start:x_end,
            y_start:y_end,
            z_start:z_end
        ]

        # 임시 볼륨으로 Marching Cubes 수행
        chunk_nx, chunk_ny, chunk_nz = chunk_data.shape

        # Taichi 필드로 변환
        temp_data = ti.field(dtype=ti.f32, shape=(chunk_nx, chunk_ny, chunk_nz))
        temp_data.from_numpy(chunk_data.astype(np.float32))

        # 원점 계산
        origin_x = volume.origin[0] + x_start * volume.spacing
        origin_y = volume.origin[1] + y_start * volume.spacing
        origin_z = volume.origin[2] + z_start * volume.spacing

        # 메쉬 추출
        self.mc.extract_surface(
            temp_data,
            chunk_nx, chunk_ny, chunk_nz,
            origin_x, origin_y, origin_z,
            volume.spacing,
            isovalue
        )

        n_verts = self.mc.vertex_count[None]
        n_tris = self.mc.triangle_count[None]

        if n_verts == 0 or n_tris == 0:
            return ChunkMesh(
                vertices=np.zeros((0, 3), dtype=np.float32),
                normals=np.zeros((0, 3), dtype=np.float32),
                faces=np.zeros((0, 3), dtype=np.int32),
                is_valid=True
            )

        vertices = self.mc.vertices.to_numpy()[:n_verts].copy()
        normals = self.mc.normals.to_numpy()[:n_verts].copy()
        faces = self.mc.triangles.to_numpy()[:n_tris * 3].reshape(-1, 3).copy()

        return ChunkMesh(
            vertices=vertices,
            normals=normals,
            faces=faces,
            is_valid=True
        )

    def update(self, volume, isovalue: float = 0.5):
        """dirty 청크만 업데이트.

        Args:
            volume: VoxelVolume 객체
            isovalue: 등위값
        """
        if not self.dirty_chunks:
            return

        for chunk_key in list(self.dirty_chunks):
            cx, cy, cz = chunk_key
            if 0 <= cx < self.n_chunks_x and \
               0 <= cy < self.n_chunks_y and \
               0 <= cz < self.n_chunks_z:
                self.chunk_meshes[chunk_key] = self._extract_chunk(
                    volume, cx, cy, cz, isovalue
                )

        self.dirty_chunks.clear()
        self._mesh_dirty = True

    def get_mesh(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """전체 메쉬 반환 (모든 청크 병합).

        Returns:
            (vertices, normals, faces) numpy 배열
        """
        if not self._mesh_dirty and self._cached_vertices is not None:
            return self._cached_vertices, self._cached_normals, self._cached_faces

        all_vertices = []
        all_normals = []
        all_faces = []
        vertex_offset = 0

        for chunk_key, chunk_mesh in self.chunk_meshes.items():
            if not chunk_mesh.is_valid or len(chunk_mesh.vertices) == 0:
                continue

            all_vertices.append(chunk_mesh.vertices)
            all_normals.append(chunk_mesh.normals)
            all_faces.append(chunk_mesh.faces + vertex_offset)
            vertex_offset += len(chunk_mesh.vertices)

        if not all_vertices:
            empty = np.zeros((0, 3), dtype=np.float32)
            return empty, empty, np.zeros((0, 3), dtype=np.int32)

        self._cached_vertices = np.vstack(all_vertices).astype(np.float32)
        self._cached_normals = np.vstack(all_normals).astype(np.float32)
        self._cached_faces = np.vstack(all_faces).astype(np.int32)
        self._mesh_dirty = False

        return self._cached_vertices, self._cached_normals, self._cached_faces

    def extract(self, volume, isovalue: float = 0.5) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """전체 메쉬 추출 (기존 API 호환).

        처음 호출 시 모든 청크를 계산하고,
        이후에는 dirty 청크만 업데이트합니다.

        Args:
            volume: VoxelVolume 객체
            isovalue: 등위값

        Returns:
            (vertices, normals, faces)
        """
        # 처음이거나 볼륨 크기가 변경된 경우 전체 재계산
        if not self.chunk_meshes:
            self.mark_all_dirty()

        self.update(volume, isovalue)
        return self.get_mesh()

    def get_stats(self) -> dict:
        """통계 정보 반환."""
        total_verts = 0
        total_tris = 0
        valid_chunks = 0

        for chunk_mesh in self.chunk_meshes.values():
            if chunk_mesh.is_valid:
                total_verts += len(chunk_mesh.vertices)
                total_tris += len(chunk_mesh.faces)
                valid_chunks += 1

        return {
            "total_chunks": self.n_chunks_x * self.n_chunks_y * self.n_chunks_z,
            "cached_chunks": len(self.chunk_meshes),
            "valid_chunks": valid_chunks,
            "dirty_chunks": len(self.dirty_chunks),
            "total_vertices": total_verts,
            "total_triangles": total_tris,
        }
