"""Peridynamics (NOSB-PD) 솔버 어댑터.

통합 Domain/Material → ParticleSystem + BondSystem + NOSBCompute + QuasiStaticSolver 변환.
"""

import math
import time
import numpy as np
from typing import Optional

from .base_adapter import AdapterBase
from ..domain import Domain
from ..material import Material
from ..result import SolveResult


class PDAdapter(AdapterBase):
    """PD 솔버 어댑터.

    NOSB-PD 기반 준정적 솔버를 통합 API로 래핑한다.
    """

    def __init__(self, domain: Domain, material: Material, **options):
        from ...peridynamics.core.particles import ParticleSystem
        from ...peridynamics.core.neighbor import NeighborSearch
        from ...peridynamics.core.bonds import BondSystem
        from ...peridynamics.core.nosb import NOSBCompute, NOSBMaterial
        from ...peridynamics.solver.quasi_static import QuasiStaticSolver, LoadControl

        dim = domain.dim
        n_div = domain.n_divisions
        size = domain.size
        origin = domain.origin

        # ── 입자 좌표 결정 ──
        # _custom_positions 가 있으면 실제 복셀 좌표 직접 사용 (PD/SPG 파이프라인)
        # 없으면 균등 그리드 생성 (기존 방식)
        custom_pos: np.ndarray | None = getattr(domain, "_custom_positions", None)

        if custom_pos is not None:
            # 실제 복셀 중심 좌표 → n_per_axis 기반 spacing 추정
            n_particles = len(custom_pos)
            # spacing: 바운딩 박스 / 분할 수 (horizon 계산 전용)
            spacing = size[0] / (n_div[0] - 1) if n_div[0] > 1 else size[0]
            horizon_factor = options.get("horizon_factor", 3.015)
            horizon = horizon_factor * spacing
            # 입자 부피: spacing^3 균등 근사
            volumes = np.full(n_particles, spacing ** dim, dtype=np.float64)
            self.ps = ParticleSystem(n_particles, dim=dim)
            self.ps.initialize_from_arrays(custom_pos, volumes, density=material.density)
        else:
            # 균등 그리드 방식 (기존)
            n_particles = int(np.prod(n_div))
            if dim == 2:
                spacing = size[0] / (n_div[0] - 1) if n_div[0] > 1 else size[0]
            else:
                spacing = size[0] / (n_div[0] - 1) if n_div[0] > 1 else size[0]
            horizon_factor = options.get("horizon_factor", 3.015)
            horizon = horizon_factor * spacing
            self.ps = ParticleSystem(n_particles, dim=dim)
            self.ps.initialize_from_grid(origin, spacing, n_div, density=material.density)

        # 이웃 탐색
        positions = self.ps.X.to_numpy()
        domain_pad = horizon * 1.5
        mins = positions.min(axis=0) - domain_pad
        maxs = positions.max(axis=0) + domain_pad

        max_neighbors = 64 if dim == 2 else 100
        ns = NeighborSearch(
            domain_min=tuple(mins),
            domain_max=tuple(maxs),
            horizon=horizon,
            max_particles=n_particles,
            max_neighbors=max_neighbors,
            dim=dim,
        )
        ns.build(self.ps.X, n_particles)

        # 본드 시스템
        self.bonds = BondSystem(n_particles, max_bonds=max_neighbors, dim=dim)
        self.bonds.build_from_neighbor_search(self.ps, ns, horizon)

        # NOSB 재료 + 연산
        self.nosb_material = material._create_nosb_material()
        stabilization = options.get("stabilization", 0.1)
        self.nosb = NOSBCompute(self.ps, self.bonds, stabilization=stabilization)
        self.nosb.compute_shape_tensor()

        # 경계조건 적용
        if domain._fixed_indices is not None:
            self.ps.set_fixed_particles(domain._fixed_indices)

        # 외력 저장 (콜백으로 매 스텝 적용)
        self._force_indices = domain._force_indices
        self._force_values = domain._force_values
        self._loader = None

        if self._force_indices is not None:
            self._loader = LoadControl(self.ps, self._force_indices)
            forces_val = self._force_values
            if forces_val.ndim == 1:
                self._loader.set_load(tuple(forces_val))
            else:
                # 평균 힘 벡터 사용 (모두 동일하다고 가정)
                self._loader.set_load(tuple(forces_val[0]))

        # NOSB 힘 계산에 필요한 마이크로 모듈러스
        if dim == 2:
            self.c_bond = 9.0 * material.E / (math.pi * 1.0 * horizon**3)
        else:
            self.c_bond = 18.0 * material.K_bulk / (math.pi * horizon**4)

        # 준정적 솔버
        self.horizon = horizon
        self.spacing = spacing
        damping = options.get("damping", 0.1)
        micromodulus = self.c_bond

        self.solver = QuasiStaticSolver(
            self.ps, self.bonds,
            micromodulus=micromodulus,
            damping=damping,
        )
        self.dim = dim
        self.n_particles = n_particles
        self._options = options

        # 접촉력 버퍼 (numpy, 매 스텝 ps.f에 추가)
        self._contact_forces = np.zeros((n_particles, dim), dtype=np.float64)

    def _apply_forces(self):
        """외력 + 접촉력 콜백."""
        if self._loader is not None:
            self._loader.apply()
        # 접촉력 주입 (ps.f에 추가)
        if np.any(self._contact_forces != 0):
            current_f = self.ps.f.to_numpy()
            current_f += self._contact_forces
            self.ps.f.from_numpy(current_f)

    def solve(self, **kwargs) -> SolveResult:
        """NOSB-PD 준정적 해석 실행."""
        max_iterations = kwargs.get("max_iterations", self._options.get("max_iterations", 50000))
        tol = kwargs.get("tol", self._options.get("tol", 1e-4))
        verbose = kwargs.get("verbose", False)

        t0 = time.time()
        result = self.solver.solve(
            external_force_func=self._apply_forces,
            max_iterations=max_iterations,
            tol=tol,
            verbose=verbose,
        )
        elapsed = time.time() - t0

        return SolveResult(
            converged=result["converged"],
            iterations=result["iterations"],
            residual=result.get("residual", 0.0),
            relative_residual=result.get("relative_residual", 0.0),
            elapsed_time=elapsed,
        )

    def get_displacements(self) -> np.ndarray:
        """변위 반환 (n_particles, dim)."""
        return self.ps.get_displacements()

    def get_stress(self) -> np.ndarray:
        """응력은 NOSB에서 P 텐서로 근사."""
        return self.ps.P.to_numpy()

    def get_damage(self) -> Optional[np.ndarray]:
        """손상도 반환."""
        return self.ps.get_damage()

    # === 접촉 해석용 추가 메서드 ===

    def get_current_positions(self) -> np.ndarray:
        """현재 좌표 반환."""
        return self.ps.x.to_numpy()

    def get_reference_positions(self) -> np.ndarray:
        """참조 좌표 반환."""
        return self.ps.X.to_numpy()

    def inject_contact_forces(self, indices: np.ndarray, forces: np.ndarray):
        """접촉력 주입 (ps.f에 추가)."""
        for i, idx in enumerate(indices):
            self._contact_forces[idx] += forces[i].astype(np.float64)

    def clear_contact_forces(self):
        """접촉력 초기화."""
        self._contact_forces[:] = 0.0

    def step(self, dt: float):
        """명시적 1스텝 전진."""
        self.solver.step(external_force_func=self._apply_forces)

    def get_stable_dt(self) -> float:
        """안정 시간 간격 반환."""
        return float(self.solver.dt)
