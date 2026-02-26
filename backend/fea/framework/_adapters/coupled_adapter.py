"""FEM+PD/SPG 커플링 솔버 어댑터.

통합 Domain/Material → CoupledSolver 변환을 담당한다.
AdapterBase를 구현하여 Scene/Solver와 호환한다.
"""

import time
import numpy as np
from typing import Optional

from .base_adapter import AdapterBase
from ..domain import Domain
from ..material import Material
from ..result import SolveResult


class CoupledAdapter(AdapterBase):
    """FEM+PD/SPG 커플링 솔버 어댑터.

    통합 Domain의 CouplingConfig에 따라 CoupledSolver를 생성하고
    AdapterBase 인터페이스를 구현한다.
    """

    def __init__(self, domain: Domain, material: Material, **options):
        from ..coupling.coupled_solver import CoupledSolver
        from ..coupling.criteria import SwitchingCriteria
        from .fem_adapter import _create_hex8_mesh, _create_quad4_mesh

        dim = domain.dim
        n_div = domain.n_divisions
        origin = domain.origin
        size = domain.size

        # ── 메쉬 생성 ──
        # 복셀 기반 커스텀 메쉬가 있으면 우선 사용 (assembly 파이프라인)
        custom_nodes = getattr(domain, '_hex_nodes', None)
        custom_elements = getattr(domain, '_hex_elements', None)

        if custom_nodes is not None and custom_elements is not None:
            nodes = custom_nodes.astype(np.float64)
            elements = custom_elements.astype(np.int32)
            n_nodes = len(nodes)
            n_elements = len(elements)
        elif dim == 2:
            nx, ny = n_div
            nodes, elements, n_nodes, n_elements = _create_quad4_mesh(
                nx, ny, size[0], size[1], origin[0], origin[1]
            )
        else:
            nx, ny, nz = n_div
            nodes, elements, n_nodes, n_elements = _create_hex8_mesh(
                nx, ny, nz, size[0], size[1], size[2],
                origin[0], origin[1], origin[2]
            )

        self.dim = dim
        self.n_nodes = n_nodes
        self.nodes = nodes

        # ── 커플링 설정 파싱 ──
        coupling_config = getattr(domain, '_coupling_config', None)
        if coupling_config is None:
            raise ValueError("커플링 설정(CouplingConfig)이 없음")

        particle_method = coupling_config.particle_method
        coupling_tol = coupling_config.coupling_tol
        max_iters = coupling_config.max_coupling_iters
        mode = coupling_config.mode

        # PD 영역 마스크 (수동 모드)
        pd_mask = np.zeros(n_elements, dtype=bool)
        if mode == "manual" and coupling_config.pd_element_indices is not None:
            valid_indices = [
                i for i in coupling_config.pd_element_indices
                if 0 <= i < n_elements
            ]
            pd_mask[valid_indices] = True

        # 경계조건
        fixed_nodes = domain._fixed_indices
        fixed_values = domain._fixed_values
        force_nodes = domain._force_indices
        force_values = domain._force_values

        # ── CoupledSolver 생성 ──
        self.coupled_solver = CoupledSolver(
            nodes=nodes,
            elements=elements,
            material=material,
            pd_element_mask=pd_mask,
            particle_method=particle_method,
            coupling_tol=coupling_tol,
            max_coupling_iters=max_iters,
            fixed_nodes=fixed_nodes,
            fixed_values=fixed_values,
            force_nodes=force_nodes,
            force_values=force_values if force_values is not None else None,
        )

        # 자동 모드 기준 저장
        self._auto_mode = (mode == "auto")
        self._criteria = None
        if self._auto_mode and coupling_config.criteria:
            self._criteria = SwitchingCriteria(
                von_mises_threshold=coupling_config.criteria.get(
                    "von_mises_threshold"
                ),
                max_strain_threshold=coupling_config.criteria.get(
                    "max_strain_threshold"
                ),
                buffer_layers=coupling_config.criteria.get(
                    "buffer_layers", 1
                ),
            )

        # 접촉력 버퍼
        self._contact_forces = np.zeros((n_nodes, dim), dtype=np.float64)

    def solve(self, **kwargs) -> SolveResult:
        """커플링 해석 실행."""
        verbose = kwargs.get("verbose", False)
        t0 = time.time()

        if self._auto_mode and self._criteria:
            result = self.coupled_solver.solve_automatic(
                self._criteria, verbose=verbose,
            )
        else:
            result = self.coupled_solver.solve(verbose=verbose)

        elapsed = time.time() - t0

        return SolveResult(
            converged=result.get("converged", False),
            iterations=result.get("coupling_iterations", 0),
            residual=result.get("coupling_residual", 0.0),
            relative_residual=result.get("coupling_residual", 0.0),
            elapsed_time=elapsed,
        )

    def get_displacements(self) -> np.ndarray:
        """변위 반환 (n_nodes, dim)."""
        return self.coupled_solver.get_displacements()

    def get_stress(self) -> np.ndarray:
        """응력 반환 (Von Mises)."""
        return self.coupled_solver.get_stress()

    def get_damage(self) -> Optional[np.ndarray]:
        """손상도 반환."""
        return self.coupled_solver.get_damage()

    # === 접촉 해석용 추가 메서드 ===

    def get_current_positions(self) -> np.ndarray:
        """현재 좌표 반환 (참조좌표 + 변위)."""
        return self.nodes + self.coupled_solver.get_displacements()

    def get_reference_positions(self) -> np.ndarray:
        """참조 좌표 반환."""
        return self.nodes.copy()

    def inject_contact_forces(self, indices: np.ndarray, forces: np.ndarray):
        """접촉력 주입."""
        for i, idx in enumerate(indices):
            self._contact_forces[idx] += forces[i].astype(np.float64)

    def clear_contact_forces(self):
        """접촉력 초기화."""
        self._contact_forces[:] = 0.0

    def step(self, dt: float):
        """커플링 솔버는 step = solve."""
        self.solve()

    def get_stable_dt(self) -> float:
        """커플링 솔버는 내부 PD dt 반환."""
        if hasattr(self.coupled_solver, 'pd_adapter'):
            return self.coupled_solver.pd_adapter.get_stable_dt()
        return 1e10
