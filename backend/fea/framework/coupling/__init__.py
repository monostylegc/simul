"""FEM ↔ PD/SPG 적응적 커플링 모듈.

하나의 메쉬를 FEM 영역과 PD/SPG 영역으로 분할하여
Dirichlet-Neumann 교대법으로 커플링 해석을 수행한다.

지원 모드:
- 수동(manual): 사용자가 PD/SPG 영역 요소를 사전 지정
- 자동(auto): FEM 1차 해석 후 응력/변형률 기준으로 자동 전환
"""

from .zone_splitter import split_mesh, ZoneSplit
from .interface_manager import InterfaceManager
from .criteria import SwitchingCriteria
from .coupled_solver import CoupledSolver

__all__ = [
    "split_mesh",
    "ZoneSplit",
    "InterfaceManager",
    "SwitchingCriteria",
    "CoupledSolver",
]
