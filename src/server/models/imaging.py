"""의료 영상 관련 Pydantic 모델 — 세그멘테이션, 메쉬 추출, DICOM 파이프라인."""

from typing import Optional
from pydantic import BaseModel


class SegmentationRequest(BaseModel):
    """세그멘테이션 요청."""
    input_path: str
    engine: str = "totalspineseg"        # totalspineseg | totalseg | spine_unified
    device: str = "gpu"                  # gpu | cpu
    fast: bool = False                   # 빠른 모드 (저해상도)
    modality: Optional[str] = None       # CT | MRI | None(자동 감지)


class MeshExtractRequest(BaseModel):
    """라벨맵 → 메쉬 추출 요청."""
    labels_path: str
    selected_labels: Optional[list[int]] = None  # None이면 전체
    resolution: int = 64
    smooth: bool = True


class AutoMaterialRequest(BaseModel):
    """자동 재료 매핑 요청 — 결과는 사용자가 수동 조정 가능."""
    label_values: list[int]              # 각 노드/입자의 SpineLabel 값
    implant_materials: dict = {}         # 임플란트명 → 재료명


class DicomPipelineRequest(BaseModel):
    """DICOM 원클릭 파이프라인 요청 — 변환+세그멘테이션+메쉬 추출."""
    dicom_dir: str                       # DICOM 파일 디렉토리 경로
    engine: str = "auto"                 # auto | totalseg | totalspineseg | spine_unified
    device: str = "gpu"                  # gpu | cpu
    fast: bool = False                   # 빠른 모드
    modality: Optional[str] = None       # CT | MRI | None (auto면 DICOM 태그에서 감지)
    smooth: bool = True                  # 메쉬 스무딩
    resolution: int = 64                 # 메쉬 해상도
