"""자동 재료 매핑 테스트."""

import pytest
from src.server.services.auto_material import auto_assign_materials, SPINE_MATERIAL_DB
from src.server.models import AutoMaterialRequest


class TestSpineMaterialDB:
    def test_bone_exists(self):
        assert "bone" in SPINE_MATERIAL_DB
        assert SPINE_MATERIAL_DB["bone"]["E"] == 15e9

    def test_disc_exists(self):
        assert "disc" in SPINE_MATERIAL_DB
        assert SPINE_MATERIAL_DB["disc"]["E"] == 10e6

    def test_titanium_exists(self):
        assert "titanium" in SPINE_MATERIAL_DB
        assert SPINE_MATERIAL_DB["titanium"]["E"] == 110e9

    def test_peek_exists(self):
        assert "peek" in SPINE_MATERIAL_DB
        assert SPINE_MATERIAL_DB["peek"]["E"] == 4e9

    def test_all_materials_have_required_fields(self):
        for name, mat in SPINE_MATERIAL_DB.items():
            assert "E" in mat, f"{name}: E 누락"
            assert "nu" in mat, f"{name}: nu 누락"
            assert "density" in mat, f"{name}: density 누락"
            assert mat["E"] > 0
            assert 0 < mat["nu"] < 0.5
            assert mat["density"] > 0


class TestAutoAssignMaterials:
    def test_bone_labels(self):
        """척추골 라벨(120=L1)이 bone으로 매핑되는지 확인."""
        request = AutoMaterialRequest(label_values=[0, 120, 120, 121])
        result = auto_assign_materials(request)

        assert "materials" in result
        assert "material_db" in result

        mat_names = [m["name"] for m in result["materials"]]
        assert "bone" in mat_names

        # bone 재료의 node_indices에 0(배경)은 포함 안 됨
        bone_mat = next(m for m in result["materials"] if m["name"] == "bone")
        assert 0 not in bone_mat["node_indices"]
        assert len(bone_mat["node_indices"]) == 3  # 인덱스 1, 2, 3

    def test_disc_labels(self):
        """디스크 라벨(222=L4L5)이 disc로 매핑되는지 확인."""
        request = AutoMaterialRequest(label_values=[222, 222])
        result = auto_assign_materials(request)

        mat_names = [m["name"] for m in result["materials"]]
        assert "disc" in mat_names

    def test_mixed_labels(self):
        """혼합 라벨 처리."""
        request = AutoMaterialRequest(
            label_values=[0, 120, 222, 301, 120]
        )
        result = auto_assign_materials(request)

        mat_names = [m["name"] for m in result["materials"]]
        assert "bone" in mat_names
        assert "disc" in mat_names
        assert "soft_tissue" in mat_names

    def test_empty_labels(self):
        """배경만 있으면 빈 결과."""
        request = AutoMaterialRequest(label_values=[0, 0, 0])
        result = auto_assign_materials(request)
        assert len(result["materials"]) == 0

    def test_implant_materials(self):
        """임플란트 재료 추가."""
        request = AutoMaterialRequest(
            label_values=[120],
            implant_materials={"screw1": "titanium"},
        )
        result = auto_assign_materials(request)

        mat_names = [m["name"] for m in result["materials"]]
        assert any("screw1" in n for n in mat_names)

    def test_material_db_returned(self):
        """material_db가 반환되는지 확인."""
        request = AutoMaterialRequest(label_values=[120])
        result = auto_assign_materials(request)

        assert "bone" in result["material_db"]
        assert "titanium" in result["material_db"]

    def test_progress_callback(self):
        """진행률 콜백 호출 확인."""
        calls = []
        def cb(step, detail):
            calls.append(step)

        request = AutoMaterialRequest(label_values=[120, 222])
        auto_assign_materials(request, progress_callback=cb)
        assert "material" in calls
        assert "done" in calls
