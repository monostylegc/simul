"""메쉬 추출 파이프라인 테스트."""

import pytest
import numpy as np
import tempfile
from pathlib import Path
from src.server.models import MeshExtractRequest


class TestMeshExtractPipeline:
    @pytest.fixture
    def sample_labelmap(self, tmp_path):
        """테스트용 간단한 라벨맵 (NPZ)."""
        # 10x10x10 격자, 중앙에 bone(120), 아래에 disc(222)
        labels = np.zeros((10, 10, 10), dtype=np.int32)
        labels[3:7, 3:7, 5:10] = 120   # bone (상단)
        labels[3:7, 3:7, 0:5] = 222    # disc (하단)

        path = tmp_path / "labels_test.npz"
        np.savez_compressed(str(path), labels=labels)
        return str(path)

    def test_extract_from_npz(self, sample_labelmap):
        """NPZ 라벨맵에서 메쉬 추출."""
        from src.server.services.mesh_extract import extract_meshes

        request = MeshExtractRequest(
            labels_path=sample_labelmap,
            smooth=False,
        )
        result = extract_meshes(request)

        assert "meshes" in result
        # bone과 disc 2개 메쉬가 추출되어야 함
        assert len(result["meshes"]) >= 1

        # 각 메쉬에 필수 필드 확인 (base64 인코딩)
        import base64
        for m in result["meshes"]:
            assert "label" in m
            assert "name" in m
            assert "vertices_b64" in m, "vertices_b64 필드 필수"
            assert "faces_b64" in m, "faces_b64 필드 필수"
            assert "material_type" in m
            assert "color" in m
            assert m["n_vertices"] > 0
            assert m["n_faces"] > 0
            # base64 디코딩 검증
            verts_bytes = base64.b64decode(m["vertices_b64"])
            assert len(verts_bytes) == m["n_vertices"] * 3 * 4
            faces_bytes = base64.b64decode(m["faces_b64"])
            assert len(faces_bytes) == m["n_faces"] * 3 * 4

    def test_selected_labels(self, sample_labelmap):
        """특정 라벨만 추출."""
        from src.server.services.mesh_extract import extract_meshes

        request = MeshExtractRequest(
            labels_path=sample_labelmap,
            selected_labels=[120],  # bone만
            smooth=False,
        )
        result = extract_meshes(request)

        labels_in_result = [m["label"] for m in result["meshes"]]
        assert 120 in labels_in_result
        assert 222 not in labels_in_result

    def test_nonexistent_file(self):
        """존재하지 않는 파일."""
        from src.server.services.mesh_extract import extract_meshes

        request = MeshExtractRequest(labels_path="/tmp/nonexistent.npz")
        with pytest.raises(FileNotFoundError):
            extract_meshes(request)

    def test_progress_callback(self, sample_labelmap):
        """진행률 콜백 호출 확인."""
        from src.server.services.mesh_extract import extract_meshes

        calls = []
        def cb(step, detail):
            calls.append(step)

        request = MeshExtractRequest(labels_path=sample_labelmap, smooth=False)
        extract_meshes(request, progress_callback=cb)

        assert "mesh_extract" in calls
        assert "done" in calls

    def test_material_colors(self):
        """재료 색상 매핑."""
        from src.server.services.mesh_extract import _material_color

        assert _material_color("bone") == "#e6d5c3"
        assert _material_color("disc") == "#6ba3d6"
        assert _material_color("soft_tissue") == "#f0a0b0"
        assert _material_color("unknown") == "#888888"


class TestLoadLabels:
    def test_load_npz(self, tmp_path):
        """NPZ 형식 로드."""
        from src.server.services.mesh_extract import _load_labels

        labels = np.zeros((5, 5, 5), dtype=np.int32)
        labels[2, 2, 2] = 120
        path = tmp_path / "test.npz"
        np.savez_compressed(str(path), labels=labels)

        data, metadata = _load_labels(path)
        assert data.shape == (5, 5, 5)
        assert data[2, 2, 2] == 120

    def test_unsupported_format(self, tmp_path):
        """지원하지 않는 형식."""
        from src.server.services.mesh_extract import _load_labels

        path = tmp_path / "test.xyz"
        path.write_text("dummy")
        with pytest.raises(ValueError, match="지원하지 않는"):
            _load_labels(path)
