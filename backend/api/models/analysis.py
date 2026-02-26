"""해석 관련 Pydantic 모델 — 경계조건, 재료 영역, 해석 요청."""

from typing import Literal, Optional
from pydantic import BaseModel


class BoundaryCondition(BaseModel):
    """경계조건 (고정 또는 하중).

    FEM 노드와 PD/SPG 입자 모두에 적용 가능.
    이전의 RegionBC와 동일 구조로 통합함.
    """
    type: Literal["fixed", "force"]
    node_indices: list[int]
    values: list[list[float]]  # (n, dim) 변위 또는 힘 벡터


class CouplingConfig(BaseModel):
    """FEM-PD/SPG 커플링 설정."""
    mode: Literal["manual", "auto"] = "manual"
    particle_method: Literal["pd", "spg"] = "pd"
    pd_element_indices: Optional[list[int]] = None    # 수동 모드: PD 영역 요소 인덱스
    von_mises_threshold: Optional[float] = None       # 자동 모드: Von Mises 임계값 [Pa]
    max_strain_threshold: Optional[float] = None      # 자동 모드: 최대 주변형률 임계값
    buffer_layers: int = 1                            # 자동 모드: 인접 요소 확장 레이어
    coupling_tol: float = 1e-4                        # 커플링 수렴 허용 오차
    max_coupling_iters: int = 20                      # 최대 커플링 반복 수


class MaterialRegion(BaseModel):
    """재료 영역 — 특정 노드 그룹에 할당되는 물성 + 솔버 + 구성 모델."""
    name: str                  # "bone", "disc", "ligament"
    method: Literal["fem", "pd", "spg", "coupled"] = "fem"  # 영역별 솔버 지정
    E: float                   # Young's modulus [Pa]
    nu: float                  # Poisson ratio
    density: float = 1000.0
    # 구성 모델 (FEM 전용, PD/SPG는 항상 linear_elastic)
    constitutive_model: Literal[
        "linear_elastic", "neo_hookean", "mooney_rivlin", "ogden"
    ] = "linear_elastic"
    # 초탄성 파라미터 (구성 모델에 따라 선택적 사용)
    C10: Optional[float] = None       # Mooney-Rivlin 제1상수 [Pa]
    C01: Optional[float] = None       # Mooney-Rivlin 제2상수 [Pa]
    D1: Optional[float] = None        # 비압축성 파라미터 [1/Pa]
    mu_ogden: Optional[float] = None  # Ogden 전단 계수 [Pa]
    alpha_ogden: Optional[float] = None  # Ogden 지수
    node_indices: list[int]    # PD/SPG: 이 재료에 속하는 입자 인덱스
    # FEM 전용: 볼륨 메쉬 데이터
    nodes: Optional[list[list[float]]] = None      # (n_nodes, 3) HEX8 노드 좌표
    elements: Optional[list[list[int]]] = None      # (n_elements, 8) HEX8 연결정보
    # 영역별 경계조건 (BoundaryCondition 재사용)
    boundary_conditions: Optional[list[BoundaryCondition]] = None
    # 커플링 설정 (method="coupled" 시 사용)
    coupling: Optional[CouplingConfig] = None


class AnalysisRequest(BaseModel):
    """해석 요청 — 클라이언트에서 서버로 전송."""
    positions: list[list[float]]     # (n, 3) 입자/노드 좌표
    volumes: list[float]             # (n,) 복셀 체적
    method: Literal["fem", "pd", "spg", "coupled"]
    boundary_conditions: list[BoundaryCondition]
    materials: list[MaterialRegion]
    options: dict = {}               # 솔버별 옵션 (dt, n_steps 등)
