"""통합 솔버.

Domain과 Material을 받아 자동으로 적절한 어댑터를 선택하고 해석을 수행한다.
"""

import numpy as np
from typing import Optional

from .domain import Domain, Method
from .material import Material
from .result import SolveResult


class Solver:
    """통합 솔버.

    Method에 따라 FEM/PD/SPG 어댑터를 자동 선택한다.

    Args:
        domain: 통합 Domain 객체
        material: 통합 Material 객체
        **options: 솔버별 추가 옵션
    """

    def __init__(self, domain: Domain, material: Material, **options):
        self.domain = domain
        self.material = material
        self._options = options

        # 어댑터 생성
        method = domain.method
        if method == Method.FEM:
            from ._adapters.fem_adapter import FEMAdapter
            self._adapter = FEMAdapter(domain, material, **options)
        elif method == Method.PD:
            from ._adapters.pd_adapter import PDAdapter
            self._adapter = PDAdapter(domain, material, **options)
        elif method == Method.SPG:
            from ._adapters.spg_adapter import SPGAdapter
            self._adapter = SPGAdapter(domain, material, **options)
        elif method == Method.COUPLED:
            from ._adapters.coupled_adapter import CoupledAdapter
            self._adapter = CoupledAdapter(domain, material, **options)
        else:
            raise ValueError(f"지원하지 않는 해석 방법: {method}")

        domain._adapter = self._adapter

    def solve(self, **kwargs) -> SolveResult:
        """해석 실행.

        Returns:
            SolveResult 객체
        """
        return self._adapter.solve(**kwargs)

    def get_displacements(self) -> np.ndarray:
        """변위 반환 (n_points, dim)."""
        return self._adapter.get_displacements()

    def get_stress(self) -> np.ndarray:
        """응력 반환."""
        return self._adapter.get_stress()

    def get_damage(self) -> Optional[np.ndarray]:
        """손상도 반환 (PD/SPG만 지원)."""
        return self._adapter.get_damage()
