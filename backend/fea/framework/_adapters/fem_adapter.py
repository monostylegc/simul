"""FEM 솔버 어댑터.

통합 Domain/Material → FEMesh + StaticSolver 변환을 담당한다.
"""

import time
import numpy as np
from typing import Optional

from .base_adapter import AdapterBase
from ..domain import Domain
from ..material import Material
from ..result import SolveResult


def _create_quad4_mesh(nx, ny, Lx, Ly, ox=0.0, oy=0.0):
    """2D QUAD4 구조 메쉬 생성."""
    dx, dy = Lx / nx, Ly / ny
    n_nodes = (nx + 1) * (ny + 1)
    n_elements = nx * ny

    nodes = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            nodes.append([ox + i * dx, oy + j * dy])
    nodes = np.array(nodes, dtype=np.float64)

    elements = []
    for ey in range(ny):
        for ex in range(nx):
            n0 = ex + ey * (nx + 1)
            n1 = n0 + 1
            n2 = n0 + (nx + 1) + 1
            n3 = n0 + (nx + 1)
            elements.append([n0, n1, n2, n3])
    elements = np.array(elements, dtype=np.int32)

    return nodes, elements, n_nodes, n_elements


def _create_hex8_mesh(nx, ny, nz, Lx, Ly, Lz, ox=0.0, oy=0.0, oz=0.0):
    """3D HEX8 구조 메쉬 생성."""
    dx, dy, dz = Lx / nx, Ly / ny, Lz / nz
    n_nodes = (nx + 1) * (ny + 1) * (nz + 1)
    n_elements = nx * ny * nz

    nodes = []
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                nodes.append([ox + i * dx, oy + j * dy, oz + k * dz])
    nodes = np.array(nodes, dtype=np.float64)

    elements = []
    for ez in range(nz):
        for ey in range(ny):
            for ex in range(nx):
                n0 = ex + ey * (nx + 1) + ez * (nx + 1) * (ny + 1)
                n1 = n0 + 1
                n2 = n0 + (nx + 1) + 1
                n3 = n0 + (nx + 1)
                n4 = n0 + (nx + 1) * (ny + 1)
                n5 = n4 + 1
                n6 = n4 + (nx + 1) + 1
                n7 = n4 + (nx + 1)
                elements.append([n0, n1, n2, n3, n4, n5, n6, n7])
    elements = np.array(elements, dtype=np.int32)

    return nodes, elements, n_nodes, n_elements


class FEMAdapter(AdapterBase):
    """FEM 솔버 어댑터.

    통합 Domain/Material을 FEMesh + StaticSolver로 변환한다.
    """

    def __init__(self, domain: Domain, material: Material, **options):
        from ...fem.core.mesh import FEMesh
        from ...fem.core.element import ElementType
        from ...fem.solver.static_solver import StaticSolver

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
            elem_type = ElementType.HEX8 if dim == 3 else ElementType.QUAD4
        elif dim == 2:
            nx, ny = n_div
            nodes, elements, n_nodes, n_elements = _create_quad4_mesh(
                nx, ny, size[0], size[1], origin[0], origin[1]
            )
            elem_type = ElementType.QUAD4
        else:
            nx, ny, nz = n_div
            nodes, elements, n_nodes, n_elements = _create_hex8_mesh(
                nx, ny, nz, size[0], size[1], size[2],
                origin[0], origin[1], origin[2]
            )
            elem_type = ElementType.HEX8

        self.mesh = FEMesh(
            n_nodes=n_nodes,
            n_elements=n_elements,
            element_type=elem_type,
        )
        self.mesh.initialize_from_numpy(nodes, elements)
        self.dim = dim
        self.n_nodes = n_nodes

        # 접촉력 버퍼 (numpy, 매 반복 시 f_ext에 합산)
        self._contact_forces = np.zeros((n_nodes, dim), dtype=np.float64)
        # 사용자 지정 외력 저장 (접촉력 초기화 시 복원용)
        self._user_f_ext = np.zeros((n_nodes, dim), dtype=np.float64)

        # 경계조건 적용 (자유도별 지원)
        if domain._fixed_indices is not None:
            self.mesh.set_fixed_nodes(
                domain._fixed_indices,
                domain._fixed_values,
                dofs=getattr(domain, '_fixed_dofs', None),
            )

        if domain._force_indices is not None:
            indices = domain._force_indices
            forces_val = domain._force_values
            if forces_val.ndim == 1:
                # 모든 노드에 동일 힘 → (n, dim) 배열로 확장
                forces_arr = np.tile(
                    forces_val.astype(np.float64), (len(indices), 1)
                )
            else:
                forces_arr = forces_val.astype(np.float64)
            self._user_f_ext[indices] = forces_arr
            self.mesh.set_nodal_forces(indices, forces_arr)

        # 재료 + 솔버
        fem_material = material._create_fem_material()
        self.solver = StaticSolver(
            self.mesh, fem_material,
            max_iterations=options.get("max_iterations", 50),
            tol=options.get("tol", 1e-8),
        )

    def solve(self, **kwargs) -> SolveResult:
        """FEM 정적 해석 실행."""
        # 접촉력이 있으면 f_ext에 합산
        total_f_ext = self._user_f_ext + self._contact_forces
        self.mesh.f_ext.from_numpy(total_f_ext)

        t0 = time.time()
        result = self.solver.solve(verbose=kwargs.get("verbose", False))
        elapsed = time.time() - t0

        return SolveResult(
            converged=result["converged"],
            iterations=result.get("iterations", 1),
            residual=result.get("residual", 0.0),
            relative_residual=result.get("relative_residual", 0.0),
            elapsed_time=elapsed,
        )

    def get_displacements(self) -> np.ndarray:
        """변위 반환 (n_nodes, dim)."""
        return self.mesh.get_displacements()

    def get_stress(self) -> np.ndarray:
        """응력 반환."""
        return self.mesh.get_stress()

    def get_damage(self) -> Optional[np.ndarray]:
        """FEM은 손상도를 지원하지 않음."""
        return None

    # === 접촉 해석용 추가 메서드 ===

    def get_current_positions(self) -> np.ndarray:
        """현재 좌표 반환 (참조좌표 + 변위)."""
        return self.mesh.X.to_numpy() + self.mesh.get_displacements()

    def get_reference_positions(self) -> np.ndarray:
        """참조 좌표 반환."""
        return self.mesh.X.to_numpy()

    def inject_contact_forces(self, indices: np.ndarray, forces: np.ndarray):
        """접촉력 주입 (f_ext에 추가)."""
        for i, idx in enumerate(indices):
            self._contact_forces[idx] += forces[i].astype(np.float64)

    def clear_contact_forces(self):
        """접촉력 초기화."""
        self._contact_forces[:] = 0.0

    def step(self, dt: float):
        """FEM 정적 솔버는 step = solve."""
        self.solve()

    def get_stable_dt(self) -> float:
        """정적 솔버이므로 큰 값 반환."""
        return 1e10
