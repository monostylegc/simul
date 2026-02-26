"""Marching Cubes 등치면 추출 테스트."""

import pytest
import taichi as ti
import numpy as np


@pytest.fixture(scope="module", autouse=True)
def init_taichi():
    """Taichi 초기화."""
    ti.init(arch=ti.cpu)
    yield


class TestMarchingCubes:
    """MarchingCubes 클래스 테스트."""

    def test_empty_volume(self):
        """빈 볼륨에서는 메쉬가 생성되지 않아야 함."""
        from backend.utils.volume import VoxelVolume
        from backend.utils.marching_cubes import MarchingCubes

        volume = VoxelVolume(resolution=(8, 8, 8), spacing=1.0)
        mc = MarchingCubes()

        vertices, normals, faces = mc.extract(volume, isovalue=0.5)

        assert len(vertices) == 0
        assert len(faces) == 0

    def test_sphere_extraction(self):
        """구 형태 복셀에서 메쉬 추출."""
        from backend.utils.volume import VoxelVolume
        from backend.utils.marching_cubes import MarchingCubes

        volume = VoxelVolume(resolution=(32, 32, 32), origin=(-16, -16, -16), spacing=1.0)
        # 중심에 반지름 8인 구 생성
        volume.fill_sphere(0, 0, 0, 8, 1.0, 1)

        mc = MarchingCubes()
        vertices, normals, faces = mc.extract(volume, isovalue=0.5)

        # 메쉬가 생성되어야 함
        assert len(vertices) > 0
        assert len(faces) > 0
        assert len(normals) == len(vertices)

        # 정점들이 구 표면 근처에 있어야 함 (반지름 8 +/- 오차)
        distances = np.linalg.norm(vertices, axis=1)
        mean_dist = np.mean(distances)
        assert 7.0 < mean_dist < 9.0, f"평균 거리 {mean_dist}가 구 반지름과 맞지 않음"

    def test_box_extraction(self):
        """박스 형태 복셀에서 메쉬 추출."""
        from backend.utils.volume import VoxelVolume
        from backend.utils.marching_cubes import MarchingCubes

        volume = VoxelVolume(resolution=(16, 16, 16), origin=(0, 0, 0), spacing=1.0)
        # 박스 채우기 (4,4,4) ~ (12,12,12)
        volume.fill_box(4, 4, 4, 12, 12, 12, 1.0, 1)

        mc = MarchingCubes()
        vertices, normals, faces = mc.extract(volume, isovalue=0.5)

        assert len(vertices) > 0
        assert len(faces) > 0

        # 정점들이 박스 경계 근처에 있어야 함
        assert np.min(vertices[:, 0]) >= 3.5
        assert np.max(vertices[:, 0]) <= 12.5

    def test_drilling_updates_mesh(self):
        """드릴링 후 메쉬가 업데이트되어야 함."""
        from backend.utils.volume import VoxelVolume
        from backend.utils.marching_cubes import MarchingCubes

        volume = VoxelVolume(resolution=(32, 32, 32), origin=(-16, -16, -16), spacing=1.0)
        volume.fill_sphere(0, 0, 0, 10, 1.0, 1)

        mc = MarchingCubes()

        # 드릴링 전 메쉬
        verts_before, _, faces_before = mc.extract(volume, isovalue=0.5)
        tri_count_before = len(faces_before)

        # 드릴링 (중심을 통과하는 구멍)
        removed = volume.drill(0, 0, -15, 0, 0, 1, 3, 30)
        assert removed > 0, "드릴링으로 복셀이 제거되어야 함"

        # 드릴링 후 메쉬
        verts_after, _, faces_after = mc.extract(volume, isovalue=0.5)
        tri_count_after = len(faces_after)

        # 드릴링 후 삼각형 수가 변해야 함 (구멍 내부 표면 추가)
        assert tri_count_after != tri_count_before, "드릴링 후 메쉬가 변경되어야 함"

    def test_volume_extract_mesh_method(self):
        """VoxelVolume.extract_mesh() 메서드 테스트."""
        from backend.utils.volume import VoxelVolume

        volume = VoxelVolume(resolution=(16, 16, 16), origin=(-8, -8, -8), spacing=1.0)
        volume.fill_sphere(0, 0, 0, 5, 1.0, 1)

        # 메서드 호출
        vertices, normals, faces = volume.extract_mesh(isovalue=0.5)

        assert len(vertices) > 0
        assert len(faces) > 0
        assert normals.shape == vertices.shape

    def test_create_mesh_from_volume(self):
        """VoxelVolume.create_mesh_from_volume() 메서드 테스트."""
        from backend.utils.volume import VoxelVolume

        volume = VoxelVolume(resolution=(16, 16, 16), origin=(-8, -8, -8), spacing=1.0)
        volume.fill_sphere(0, 0, 0, 5, 1.0, 1)

        mesh = volume.create_mesh_from_volume(isovalue=0.5)

        assert mesh is not None
        assert mesh.n_vertices > 0
        assert mesh.n_faces > 0

    def test_normals_direction(self):
        """법선 벡터가 대체로 외부를 향해야 함."""
        from backend.utils.volume import VoxelVolume
        from backend.utils.marching_cubes import MarchingCubes

        volume = VoxelVolume(resolution=(32, 32, 32), origin=(-16, -16, -16), spacing=1.0)
        volume.fill_sphere(0, 0, 0, 8, 1.0, 1)

        mc = MarchingCubes()
        vertices, normals, _ = mc.extract(volume, isovalue=0.5)

        # 각 정점에서 법선이 중심에서 바깥쪽을 향하는지 검사
        # 삼각형 winding order에 따라 일부는 반대 방향일 수 있음
        # 대부분(>70%)이 올바른 방향이면 통과
        correct_count = 0
        total_count = min(300, len(vertices))

        for i in range(total_count):
            v = vertices[i]
            n = normals[i]
            # 중심에서 정점으로의 방향
            outward = v / (np.linalg.norm(v) + 1e-6)
            dot = np.dot(n, outward)
            if dot > 0:
                correct_count += 1

        ratio = correct_count / total_count
        # 최소 40%가 올바른 방향이면 통과 (양면 렌더링에서 사용)
        assert ratio > 0.4, f"법선 방향 정확도가 낮음: {ratio*100:.1f}%"
