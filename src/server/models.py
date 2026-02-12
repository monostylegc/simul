"""Pydantic 데이터 모델 — 경계조건, 재료, 해석 요청."""

from typing import Literal, Optional
from pydantic import BaseModel


class BoundaryCondition(BaseModel):
    """경계조건 (고정 또는 하중)."""
    type: Literal["fixed", "force"]
    node_indices: list[int]
    values: list[list[float]]  # (n, dim) 변위 또는 힘 벡터


class MaterialRegion(BaseModel):
    """재료 영역 — 특정 노드 그룹에 할당되는 물성."""
    name: str                  # "bone", "disc", "ligament"
    E: float                   # Young's modulus [Pa]
    nu: float                  # Poisson ratio
    density: float = 1000.0
    node_indices: list[int]    # 이 재료에 속하는 노드


class AnalysisRequest(BaseModel):
    """해석 요청 — 클라이언트에서 서버로 전송."""
    positions: list[list[float]]     # (n, 3) 입자/노드 좌표
    volumes: list[float]             # (n,) 복셀 체적
    method: Literal["fem", "pd", "spg"]
    boundary_conditions: list[BoundaryCondition]
    materials: list[MaterialRegion]
    options: dict = {}               # 솔버별 옵션 (dt, n_steps 등)
