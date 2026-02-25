"""수술 계획 관련 Pydantic 모델 — 임플란트 배치, 수술 계획, 가이드라인."""

from typing import Optional, Literal
from pydantic import BaseModel

from .analysis import BoundaryCondition, MaterialRegion


# ── 임플란트 메쉬 생성 요청 ──

class ScrewSpecModel(BaseModel):
    """Pedicle Screw 규격 (API 요청용)."""
    diameter: float = 6.0       # 직경 (mm)
    length: float = 45.0        # 길이 (mm)
    head_diameter: float = 10.0 # 헤드 직경 (mm)
    head_height: float = 5.0    # 헤드 높이 (mm)
    thread_pitch: float = 2.5   # 나사산 피치 (mm)
    thread_depth: float = 0.5   # 나사산 깊이 (mm)


class CageSpecModel(BaseModel):
    """Interbody Cage 규격 (API 요청용)."""
    width: float = 26.0   # 폭 (mm)
    depth: float = 10.0   # 깊이 (mm)
    height: float = 12.0  # 높이 (mm)
    angle: float = 6.0    # 전만각 (도)


class ImplantMeshRequest(BaseModel):
    """임플란트 3D 메쉬 생성 요청.

    implant_type에 따라 스크류/케이지/로드 메쉬를 생성한다.
    size 문자열 지정 시 표준 규격 사용 (예: "M6x45", "L"),
    미지정 시 screw_spec/cage_spec 필드를 사용한다.
    """
    implant_type: Literal["screw", "cage", "rod"] = "screw"
    screw_spec: Optional[ScrewSpecModel] = None
    cage_spec: Optional[CageSpecModel] = None
    rod_length: float = 100.0   # 로드 길이 (mm)
    rod_diameter: float = 5.5   # 로드 직경 (mm)
    size: str = ""              # 표준 규격 문자열 (예: "M6x45", "L")


# ── 가이드라인 메쉬 생성 요청 ──

class GuidelineRequest(BaseModel):
    """Pedicle Screw 수술 가이드라인 메쉬 생성 요청.

    척추 중심 위치를 기준으로 양측 삽입 경로/안전영역/깊이마커를 생성한다.
    """
    vertebra_position: list[float]      # 척추 중심 [x, y, z] (mm)
    vertebra_name: str = "L4"           # 척추 이름 (라벨 표시용)
    pedicle_offset: float = 15.0        # 척추경 좌우 오프셋 (mm)
    medial_angle: float = 10.0          # 내측각 (도)
    caudal_angle: float = 0.0           # 두측각 (도)
    depth: float = 45.0                 # 삽입 깊이 (mm)
    show_trajectory: bool = True        # 삽입 경로 표시
    show_safe_zone: bool = True         # 안전 영역 표시
    show_depth_marker: bool = True      # 깊이 마커 표시


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


class SurgicalPlan(BaseModel):
    """수술 계획 — 임플란트 배치 + 뼈 수정 + 해석 설정."""
    implants: list[ImplantPlacement] = []
    bone_modifications: dict = {}        # 드릴 히스토리 (이름 → 변경 데이터)
    boundary_conditions: list[BoundaryCondition] = []
    materials: list[MaterialRegion] = []
