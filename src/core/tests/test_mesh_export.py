"""메쉬 내보내기 테스트."""

import pytest
import numpy as np
import tempfile
from pathlib import Path

from spine_sim.core.mesh import TriangleMesh


class TestMeshExport:
    """메쉬 내보내기 테스트 클래스."""

    def test_save_stl_binary(self):
        """바이너리 STL 저장 테스트."""
        box = TriangleMesh.create_box(size=(10, 10, 10))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.stl"
            box.save_stl(str(path), binary=True)

            assert path.exists()
            assert path.stat().st_size > 0

            # 다시 로드해서 확인
            loaded = TriangleMesh.load_stl(str(path))
            assert loaded.n_vertices == box.n_vertices
            assert loaded.n_faces == box.n_faces

    def test_save_stl_ascii(self):
        """ASCII STL 저장 테스트."""
        box = TriangleMesh.create_box(size=(10, 10, 10))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.stl"
            box.save_stl(str(path), binary=False)

            assert path.exists()

            # ASCII 파일 확인
            with open(path, 'r') as f:
                content = f.read()
                assert content.startswith("solid")
                assert "facet normal" in content
                assert "vertex" in content

    def test_save_obj(self):
        """OBJ 저장 테스트."""
        box = TriangleMesh.create_box(size=(10, 10, 10))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.obj"
            box.save_obj(str(path))

            assert path.exists()

            # OBJ 파일 확인
            with open(path, 'r') as f:
                content = f.read()
                assert "v " in content  # 정점
                assert "vn " in content  # 노멀
                assert "f " in content  # 면

    def test_save_auto_format(self):
        """자동 포맷 감지 테스트."""
        box = TriangleMesh.create_box(size=(10, 10, 10))

        with tempfile.TemporaryDirectory() as tmpdir:
            # STL
            stl_path = Path(tmpdir) / "test.stl"
            box.save(str(stl_path))
            assert stl_path.exists()

            # OBJ
            obj_path = Path(tmpdir) / "test.obj"
            box.save(str(obj_path))
            assert obj_path.exists()

    def test_save_with_transform(self):
        """변환 적용 후 저장 테스트."""
        box = TriangleMesh.create_box(size=(10, 10, 10))
        box.transform.position = np.array([100, 200, 300])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.stl"
            box.save_stl(str(path), binary=True)

            loaded = TriangleMesh.load_stl(str(path))

            # 로드된 메쉬의 바운딩 박스 확인
            min_b, max_b = loaded.get_bounds()

            # 변환이 적용되어야 함
            assert min_b[0] >= 95  # 100 - 5
            assert max_b[0] <= 105  # 100 + 5
            assert min_b[1] >= 195  # 200 - 5
            assert max_b[1] <= 205  # 200 + 5


class TestMeshMerge:
    """메쉬 병합 테스트 클래스."""

    def test_merge_two_meshes(self):
        """두 메쉬 병합 테스트."""
        box1 = TriangleMesh.create_box(size=(10, 10, 10))
        box2 = TriangleMesh.create_box(size=(10, 10, 10))
        box2.transform.position = np.array([0, 30, 0])

        merged = TriangleMesh.merge_meshes([box1, box2], name="merged")

        # 정점/면 개수 확인
        assert merged.n_vertices == box1.n_vertices + box2.n_vertices
        assert merged.n_faces == box1.n_faces + box2.n_faces

    def test_merge_with_transform(self):
        """변환 적용된 메쉬 병합 테스트."""
        box1 = TriangleMesh.create_box(size=(10, 10, 10))
        box1.transform.position = np.array([0, 0, 0])

        box2 = TriangleMesh.create_box(size=(10, 10, 10))
        box2.transform.position = np.array([0, 100, 0])

        merged = TriangleMesh.merge_meshes([box1, box2])

        # 바운딩 박스 확인 (y 범위가 넓어야 함)
        min_b, max_b = merged.get_bounds()

        assert min_b[1] < 0  # box1의 하단
        assert max_b[1] > 100  # box2의 상단

    def test_merge_empty_list(self):
        """빈 리스트 병합 테스트."""
        merged = TriangleMesh.merge_meshes([], name="empty")

        assert merged.n_vertices == 0
        assert merged.n_faces == 0

    def test_merge_and_save(self):
        """병합 후 저장 테스트."""
        box1 = TriangleMesh.create_box(size=(10, 10, 10))
        box2 = TriangleMesh.create_cylinder(radius=5, height=20)

        merged = TriangleMesh.merge_meshes([box1, box2], name="combined")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "merged.stl"
            merged.save(str(path))

            loaded = TriangleMesh.load_stl(str(path))

            assert loaded.n_vertices == merged.n_vertices
            assert loaded.n_faces == merged.n_faces
