"""models 패키지 — 전체 re-export (하위 호환).

기존 `from .models import X` 임포트가 수정 없이 동작한다.
"""

from .analysis import BoundaryCondition, MaterialRegion, AnalysisRequest
from .surgical import (
    ImplantPlacement, SurgicalPlan,
    ScrewSpecModel, CageSpecModel,
    ImplantMeshRequest, GuidelineRequest,
)
from .imaging import (
    SegmentationRequest,
    MeshExtractRequest,
    AutoMaterialRequest,
    DicomPipelineRequest,
)

# 이전 RegionBC 이름도 하위 호환을 위해 BoundaryCondition으로 매핑
RegionBC = BoundaryCondition

__all__ = [
    # 해석
    "BoundaryCondition",
    "RegionBC",  # 하위 호환
    "MaterialRegion",
    "AnalysisRequest",
    # 수술
    "ImplantPlacement",
    "SurgicalPlan",
    "ScrewSpecModel",
    "CageSpecModel",
    "ImplantMeshRequest",
    "GuidelineRequest",
    # 영상
    "SegmentationRequest",
    "MeshExtractRequest",
    "AutoMaterialRequest",
    "DicomPipelineRequest",
]
