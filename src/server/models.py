"""Pydantic 데이터 모델 — 경계조건, 재료, 해석 요청, 수술 계획."""

from typing import Literal, Optional
from pydantic import BaseModel


class BoundaryCondition(BaseModel):
    """경계조건 (고정 또는 하중)."""
    type: Literal["fixed", "force"]
    node_indices: list[int]
    values: list[list[float]]  # (n, dim) 변위 또는 힘 벡터


class RegionBC(BaseModel):
    """영역별 경계조건 — FEM 노드 또는 PD/SPG 입자에 적용."""
    type: Literal["fixed", "force"]
    node_indices: list[int]
    values: list[list[float]]


class MaterialRegion(BaseModel):
    """재료 영역 — 특정 노드 그룹에 할당되는 물성 + 솔버."""
    name: str                  # "bone", "disc", "ligament"
    method: Literal["fem", "pd", "spg"] = "fem"  # 영역별 솔버 지정
    E: float                   # Young's modulus [Pa]
    nu: float                  # Poisson ratio
    density: float = 1000.0
    node_indices: list[int]    # PD/SPG: 이 재료에 속하는 입자 인덱스
    # FEM 전용: 볼륨 메쉬 데이터
    nodes: Optional[list[list[float]]] = None      # (n_nodes, 3) HEX8 노드 좌표
    elements: Optional[list[list[int]]] = None      # (n_elements, 8) HEX8 연결정보
    # 영역별 경계조건
    boundary_conditions: Optional[list[RegionBC]] = None


class AnalysisRequest(BaseModel):
    """해석 요청 — 클라이언트에서 서버로 전송."""
    positions: list[list[float]]     # (n, 3) 입자/노드 좌표
    volumes: list[float]             # (n,) 복셀 체적
    method: Literal["fem", "pd", "spg"]
    boundary_conditions: list[BoundaryCondition]
    materials: list[MaterialRegion]
    options: dict = {}               # 솔버별 옵션 (dt, n_steps 등)


# ── 임플란트 배치 ──

class ImplantPlacement(BaseModel):
    """임플란트 배치 정보."""
    name: str
    stl_path: str
    position: list[float]               # [x, y, z]
    rotation: list[float] = [0, 0, 0]   # [rx, ry, rz] Euler radians
    scale: list[float] = [1, 1, 1]
    material: str = "titanium"           # titanium, peek, custom
    E: Optional[float] = None            # 커스텀 재료일 때 직접 지정
    nu: Optional[float] = None
    density: Optional[float] = None


# ── 수술 계획 ──

class SurgicalPlan(BaseModel):
    """수술 계획 — 임플란트 배치 + 뼈 수정 + 해석 설정."""
    implants: list[ImplantPlacement] = []
    bone_modifications: dict = {}        # 드릴 히스토리 (이름 → 변경 데이터)
    boundary_conditions: list[BoundaryCondition] = []
    materials: list[MaterialRegion] = []


# ── 세그멘테이션 요청 ──

class SegmentationRequest(BaseModel):
    """세그멘테이션 요청."""
    input_path: str
    engine: str = "totalspineseg"        # totalspineseg | totalseg | spine_unified
    device: str = "gpu"                  # gpu | cpu
    fast: bool = False                   # 빠른 모드 (저해상도)
    modality: Optional[str] = None       # CT | MRI | None(자동 감지)


# ── 메쉬 추출 요청 ──

class MeshExtractRequest(BaseModel):
    """라벨맵 → 메쉬 추출 요청."""
    labels_path: str
    selected_labels: Optional[list[int]] = None  # None이면 전체
    resolution: int = 64
    smooth: bool = True


# ── 자동 재료 요청 ──

class AutoMaterialRequest(BaseModel):
    """자동 재료 매핑 요청 — 결과는 사용자가 수동 조정 가능."""
    label_values: list[int]              # 각 노드/입자의 SpineLabel 값
    implant_materials: dict = {}         # 임플란트명 → 재료명


# ── DICOM 원클릭 파이프라인 ──

class DicomPipelineRequest(BaseModel):
    """DICOM 원클릭 파이프라인 요청 — 변환+세그멘테이션+메쉬 추출."""
    dicom_dir: str                       # DICOM 파일 디렉토리 경로
    engine: str = "auto"                 # auto | totalseg | totalspineseg | spine_unified
    device: str = "gpu"                  # gpu | cpu
    fast: bool = False                   # 빠른 모드
    modality: Optional[str] = None       # CT | MRI | None (auto면 DICOM 태그에서 감지)
    smooth: bool = True                  # 메쉬 스무딩
    resolution: int = 64                 # 메쉬 해상도
