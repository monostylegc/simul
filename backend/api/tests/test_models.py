"""데이터 모델 테스트."""

import pytest
from backend.api.models import (
    BoundaryCondition,
    MaterialRegion,
    AnalysisRequest,
    ImplantPlacement,
    SurgicalPlan,
    SegmentationRequest,
    MeshExtractRequest,
    AutoMaterialRequest,
)


class TestBoundaryCondition:
    def test_fixed_bc(self):
        bc = BoundaryCondition(type="fixed", node_indices=[0, 1, 2], values=[[0, 0, 0]])
        assert bc.type == "fixed"
        assert len(bc.node_indices) == 3

    def test_force_bc(self):
        bc = BoundaryCondition(type="force", node_indices=[10], values=[[0, -100, 0]])
        assert bc.type == "force"
        assert bc.values[0][1] == -100


class TestMaterialRegion:
    def test_bone(self):
        mat = MaterialRegion(name="bone", E=15e9, nu=0.3, density=1850, node_indices=[0, 1])
        assert mat.E == 15e9
        assert mat.density == 1850


class TestAnalysisRequest:
    def test_basic(self):
        req = AnalysisRequest(
            positions=[[0, 0, 0], [1, 0, 0]],
            volumes=[1.0, 1.0],
            method="fem",
            boundary_conditions=[],
            materials=[],
        )
        assert req.method == "fem"
        assert len(req.positions) == 2


class TestImplantPlacement:
    def test_default_material(self):
        impl = ImplantPlacement(
            name="screw1", stl_path="screw.stl", position=[0, 0, 0]
        )
        assert impl.material == "titanium"
        assert impl.scale == [1, 1, 1]

    def test_custom_material(self):
        impl = ImplantPlacement(
            name="cage", stl_path="cage.stl",
            position=[0, 0, 0], material="custom",
            E=5e9, nu=0.35, density=1400,
        )
        assert impl.E == 5e9


class TestSurgicalPlan:
    def test_empty_plan(self):
        plan = SurgicalPlan()
        assert plan.implants == []
        assert plan.boundary_conditions == []

    def test_with_implants(self):
        plan = SurgicalPlan(
            implants=[
                ImplantPlacement(name="s1", stl_path="s.stl", position=[0, 0, 0]),
            ],
        )
        assert len(plan.implants) == 1

    def test_json_roundtrip(self):
        plan = SurgicalPlan(
            implants=[
                ImplantPlacement(name="cage", stl_path="cage.stl", position=[1, 2, 3]),
            ],
            materials=[
                MaterialRegion(name="bone", E=15e9, nu=0.3, node_indices=[0]),
            ],
        )
        json_str = plan.model_dump_json()
        restored = SurgicalPlan.model_validate_json(json_str)
        assert restored.implants[0].name == "cage"
        assert restored.materials[0].E == 15e9


class TestSegmentationRequest:
    def test_defaults(self):
        req = SegmentationRequest(input_path="/tmp/test.nii.gz")
        assert req.engine == "totalspineseg"
        assert req.device == "gpu"
        assert req.fast is False


class TestMeshExtractRequest:
    def test_defaults(self):
        req = MeshExtractRequest(labels_path="/tmp/labels.nii.gz")
        assert req.resolution == 64
        assert req.smooth is True
        assert req.selected_labels is None

    def test_selected_labels(self):
        req = MeshExtractRequest(
            labels_path="/tmp/labels.nii.gz",
            selected_labels=[120, 121, 222],
        )
        assert len(req.selected_labels) == 3


class TestAutoMaterialRequest:
    def test_basic(self):
        req = AutoMaterialRequest(label_values=[0, 120, 222, 301])
        assert len(req.label_values) == 4
        assert req.implant_materials == {}
