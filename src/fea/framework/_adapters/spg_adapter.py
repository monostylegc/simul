"""SPG 솔버 어댑터.

통합 Domain/Material → SPGParticleSystem + SPGKernel + SPGBondSystem + SPGExplicitSolver 변환.
"""

import time
import numpy as np
from typing import Optional

from .base_adapter import AdapterBase
from ..domain import Domain
from ..material import Material
from ..result import SolveResult


class SPGAdapter(AdapterBase):
    """SPG 솔버 어댑터.

    SPG 명시적 솔버를 통합 API로 래핑한다.
    """

    def __init__(self, domain: Domain, material: Material, **options):
        from ...spg.core.particles import SPGParticleSystem
        from ...spg.core.kernel import SPGKernel
        from ...spg.core.bonds import SPGBondSystem
        from ...spg.solver.explicit_solver import SPGExplicitSolver

        dim = domain.dim
        n_div = domain.n_divisions
        n_particles = int(np.prod(n_div))
        size = domain.size
        origin = domain.origin

        # 입자 간격 계산
        if dim == 2:
            spacing = size[0] / (n_div[0] - 1) if n_div[0] > 1 else size[0]
        else:
            spacing = size[0] / (n_div[0] - 1) if n_div[0] > 1 else size[0]

        # 지지 반경
        support_factor = options.get("support_factor", 2.5)
        support_radius = spacing * support_factor

        # 입자 시스템
        self.ps = SPGParticleSystem(n_particles=n_particles, dim=dim)
        self.ps.initialize_from_grid(origin, spacing, n_div, density=material.density)

        # 커널 (형상함수)
        self.kernel = SPGKernel(
            n_particles=n_particles, dim=dim,
            support_radius=support_radius,
        )
        self.kernel.build_neighbor_list(self.ps.X.to_numpy(), support_radius)
        self.kernel.compute_shape_functions(self.ps.X, self.ps.volume)

        # 본드 시스템
        self.bonds = SPGBondSystem(n_particles=n_particles, dim=dim)
        self.bonds.build_from_kernel(self.ps, self.kernel)

        # 재료
        self.spg_material = material._create_spg_material()

        # 경계조건 적용
        if domain._fixed_indices is not None:
            self.ps.set_fixed_particles(domain._fixed_indices)

        if domain._force_indices is not None:
            indices = domain._force_indices
            forces_val = domain._force_values
            if forces_val.ndim == 1:
                self.ps.set_external_force(indices, forces_val.astype(np.float64))
            else:
                # 입자별 개별 힘 설정
                f_ext = np.zeros((n_particles, dim), dtype=np.float64)
                for i, idx in enumerate(indices):
                    f_ext[idx] = forces_val[i] if i < len(forces_val) else forces_val[0]
                self.ps.f_ext.from_numpy(f_ext)

        # 사용자 외력 백업 (접촉력 초기화 시 복원용)
        self._user_f_ext = self.ps.f_ext.to_numpy().copy()

        # 솔버
        stabilization = options.get("stabilization", 0.01)
        viscous_damping = options.get("viscous_damping", 0.05)

        self.solver = SPGExplicitSolver(
            self.ps, self.kernel, self.bonds, self.spg_material,
            stabilization=stabilization,
            viscous_damping=viscous_damping,
            failure_stretch=options.get("failure_stretch"),
            failure_strain=options.get("failure_strain"),
        )
        self.dim = dim
        self.n_particles = n_particles
        self._options = options

        # 접촉력 버퍼 (numpy, 매 스텝 f_ext에 합산)
        self._contact_forces = np.zeros((n_particles, dim), dtype=np.float64)

    def solve(self, **kwargs) -> SolveResult:
        """SPG 명시적 해석 실행."""
        # 접촉력이 있으면 f_ext에 합산
        self._apply_contact_to_f_ext()

        max_iterations = kwargs.get(
            "max_iterations", self._options.get("max_iterations", 80000)
        )
        tol = kwargs.get("tol", self._options.get("tol", 1e-3))
        verbose = kwargs.get("verbose", False)

        t0 = time.time()
        result = self.solver.solve(
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
        """Cauchy 응력 반환 (n_particles, dim, dim)."""
        return self.ps.get_stress()

    def get_damage(self) -> Optional[np.ndarray]:
        """손상도 반환."""
        return self.ps.get_damage()

    # === 접촉 해석용 추가 메서드 ===

    def _apply_contact_to_f_ext(self):
        """접촉력을 f_ext에 합산."""
        total_f_ext = self._user_f_ext + self._contact_forces
        self.ps.f_ext.from_numpy(total_f_ext)

    def get_current_positions(self) -> np.ndarray:
        """현재 좌표 반환."""
        return self.ps.x.to_numpy()

    def get_reference_positions(self) -> np.ndarray:
        """참조 좌표 반환."""
        return self.ps.X.to_numpy()

    def inject_contact_forces(self, indices: np.ndarray, forces: np.ndarray):
        """접촉력 주입 (f_ext에 추가)."""
        for i, idx in enumerate(indices):
            self._contact_forces[idx] += forces[i].astype(np.float64)

    def clear_contact_forces(self):
        """접촉력 초기화."""
        self._contact_forces[:] = 0.0
        # f_ext를 사용자 원래값으로 복원
        self.ps.f_ext.from_numpy(self._user_f_ext)

    def step(self, dt: float):
        """명시적 1스텝 전진."""
        # 접촉력 적용
        self._apply_contact_to_f_ext()
        self.solver.step()

    def get_stable_dt(self) -> float:
        """안정 시간 간격 반환."""
        return float(self.solver.dt)
