"""FEM-PD/SPG 커플링 솔버.

Dirichlet-Neumann 교대법으로 FEM 영역과 PD/SPG 영역을 커플링 해석한다.

수동 모드:
    사용자가 PD 영역 요소를 사전 지정 → 분할 → 커플링 해석

자동 모드:
    1. 전체 FEM 해석 (1차)
    2. 응력/변형률 기준으로 전환 대상 요소 판별
    3. 영역 분할
    4. 커플링 해석 (2차)

알고리즘 (Dirichlet-Neumann 교대):
    1. FEM solve (인터페이스에 PD 반력 Neumann BC 포함)
    2. FEM 인터페이스 변위 → PD 고스트 입자 Dirichlet BC
    3. PD/SPG solve
    4. PD 인터페이스 반력 → FEM Neumann BC
    5. 인터페이스 변위 변화 < tol → 수렴
"""

import numpy as np
import time
from typing import Optional

from .zone_splitter import split_mesh, ZoneSplit
from .interface_manager import InterfaceManager
from .criteria import SwitchingCriteria


class CoupledSolver:
    """FEM + PD/SPG 커플링 솔버.

    Args:
        nodes: (n_nodes, dim) 전체 메쉬 노드 좌표
        elements: (n_elements, npe) 전체 요소 연결
        material: 통합 Material 객체
        pd_element_mask: (n_elements,) bool — PD 영역 요소 마스크
        particle_method: PD 영역 솔버 ("pd" 또는 "spg")
        coupling_tol: 커플링 수렴 허용 오차
        max_coupling_iters: 최대 커플링 반복 수
        fixed_nodes: 고정 노드 인덱스 (원본 번호, None 가능)
        fixed_values: 고정 변위값 (None이면 0)
        force_nodes: 외력 노드 인덱스 (원본 번호, None 가능)
        force_values: 외력 벡터 (n_force × dim 또는 dim)
        element_volumes: (n_elements,) 요소 부피 (None이면 자동 계산)
    """

    def __init__(
        self,
        nodes: np.ndarray,
        elements: np.ndarray,
        material,
        pd_element_mask: np.ndarray,
        particle_method: str = "pd",
        coupling_tol: float = 1e-4,
        max_coupling_iters: int = 20,
        fixed_nodes: Optional[np.ndarray] = None,
        fixed_values: Optional[np.ndarray] = None,
        force_nodes: Optional[np.ndarray] = None,
        force_values: Optional[np.ndarray] = None,
        element_volumes: Optional[np.ndarray] = None,
        pd_solver_options: Optional[dict] = None,
    ):
        self.nodes = np.asarray(nodes, dtype=np.float64)
        self.elements = np.asarray(elements, dtype=np.int64)
        self.material = material
        self.particle_method = particle_method
        self.coupling_tol = coupling_tol
        self.max_coupling_iters = max_coupling_iters
        self.dim = nodes.shape[1]
        self._pd_solver_options = pd_solver_options or {}

        # 원본 경계조건 저장
        self._fixed_nodes = fixed_nodes
        self._fixed_values = fixed_values
        self._force_nodes = force_nodes
        self._force_values = force_values

        # ── 1. 영역 분할 ──
        self.split = split_mesh(
            nodes, elements, pd_element_mask, element_volumes
        )

        # ── 2. FEM 서브메쉬 + 솔버 생성 ──
        self._build_fem_solver()

        # ── 3. PD/SPG 도메인 + 솔버 생성 ──
        self._build_particle_solver()

        # ── 4. 인터페이스 매니저 ──
        self.interface = InterfaceManager(
            self.split.interface_fem,
            self.split.interface_pd,
            dim=self.dim,
        )

    def _build_fem_solver(self):
        """FEM 서브메쉬 및 솔버 생성.

        FEM 요소가 없으면 (전체 PD) fem_mesh/fem_solver = None.
        """
        n_fem_nodes = len(self.split.fem_nodes)
        n_fem_elements = len(self.split.fem_elements)

        # FEM 요소가 비어있으면 스킵
        if n_fem_elements == 0 or n_fem_nodes == 0:
            self.fem_mesh = None
            self.fem_solver = None
            return

        from ...fem.core.mesh import FEMesh
        from ...fem.core.element import ElementType
        from ...fem.solver.static_solver import StaticSolver

        # 요소 타입 결정
        npe = self.split.fem_elements.shape[1]
        if self.dim == 2:
            elem_type = ElementType.QUAD4
        else:
            elem_type = ElementType.HEX8

        self.fem_mesh = FEMesh(n_fem_nodes, n_fem_elements, elem_type)
        self.fem_mesh.initialize_from_numpy(
            self.split.fem_nodes,
            self.split.fem_elements,
        )

        # FEM 경계조건 적용 (원본→FEM 로컬 인덱스 변환)
        self._apply_fem_bc()

        # 재료 + 솔버
        fem_material = self.material._create_fem_material()
        self.fem_solver = StaticSolver(self.fem_mesh, fem_material)

    def _apply_fem_bc(self):
        """FEM 서브메쉬에 경계조건 적용 (원본→FEM 로컬 변환)."""
        g2f = self.split.global_to_fem

        # 고정 노드
        if self._fixed_nodes is not None:
            fem_fixed = []
            for g_idx in self._fixed_nodes:
                if g_idx in g2f:
                    fem_fixed.append(g2f[g_idx])
            if fem_fixed:
                fem_fixed = np.array(fem_fixed, dtype=np.int64)
                self.fem_mesh.set_fixed_nodes(fem_fixed, self._fixed_values)

        # 외력
        if self._force_nodes is not None and self._force_values is not None:
            fem_force_indices = []
            fem_force_local = []
            for i, g_idx in enumerate(self._force_nodes):
                if g_idx in g2f:
                    fem_force_indices.append(g2f[g_idx])
                    fem_force_local.append(i)
            if fem_force_indices:
                fem_force_idx = np.array(fem_force_indices, dtype=np.int64)
                fv = np.asarray(self._force_values, dtype=np.float64)
                if fv.ndim == 1:
                    forces = np.tile(fv, (len(fem_force_idx), 1))
                else:
                    forces = fv[fem_force_local]
                self.fem_mesh.set_nodal_forces(fem_force_idx, forces)

    def _build_particle_solver(self):
        """PD/SPG 도메인 및 솔버 생성.

        PD 노드가 없으면 pd_adapter = None으로 설정한다.
        인터페이스 입자와 사용자 고정 BC를 병합하여 설정한다.
        """
        # PD 영역이 비어있으면 스킵
        if len(self.split.pd_nodes) == 0:
            self.pd_domain = None
            self.pd_adapter = None
            return

        from ..domain import create_particle_domain, Method

        method_map = {"pd": Method.PD, "spg": Method.SPG}
        method = method_map.get(self.particle_method, Method.PD)

        # 도메인 생성 (PD 입자 = FEM 노드 위치)
        self.pd_domain = create_particle_domain(
            self.split.pd_nodes, method=method,
        )

        # PD 경계조건: 사용자 BC + 인터페이스 고정 BC 병합
        g2p = self.split.global_to_pd

        # 사용자 고정 노드 (원본→PD 로컬 변환)
        all_fixed = set()
        if self._fixed_nodes is not None:
            for g_idx in self._fixed_nodes:
                if g_idx in g2p:
                    all_fixed.add(g2p[g_idx])

        # 인터페이스 입자도 고정 (커플링으로 변위 제어)
        for pd_idx in self.split.interface_pd:
            all_fixed.add(int(pd_idx))

        if all_fixed:
            self.pd_domain.set_fixed(
                np.array(sorted(all_fixed), dtype=np.int64)
            )

        # 외력 (원본→PD 로컬 변환)
        if self._force_nodes is not None and self._force_values is not None:
            pd_force_indices = []
            pd_force_local = []
            for i, g_idx in enumerate(self._force_nodes):
                if g_idx in g2p:
                    pd_force_indices.append(g2p[g_idx])
                    pd_force_local.append(i)
            if pd_force_indices:
                pd_force_idx = np.array(pd_force_indices, dtype=np.int64)
                fv = np.asarray(self._force_values, dtype=np.float64)
                if fv.ndim == 1:
                    self.pd_domain.set_force(pd_force_idx, fv)
                else:
                    self.pd_domain.set_force(pd_force_idx, fv[pd_force_local])

        # 솔버 어댑터 생성 (PD 옵션 전달)
        if self.particle_method == "spg":
            from .._adapters.spg_adapter import SPGAdapter
            self.pd_adapter = SPGAdapter(
                self.pd_domain, self.material, **self._pd_solver_options
            )
        else:
            from .._adapters.pd_adapter import PDAdapter
            self.pd_adapter = PDAdapter(
                self.pd_domain, self.material, **self._pd_solver_options
            )

    def solve(self, verbose: bool = False) -> dict:
        """Dirichlet-Neumann 교대 커플링 해석.

        PD 영역이 없으면 순수 FEM 해석으로 폴백한다.

        Args:
            verbose: 상세 출력

        Returns:
            결과 딕셔너리 {converged, iterations, residual, ...}
        """
        t0 = time.time()

        # PD 영역이 비어있으면 순수 FEM 해석
        if self.pd_adapter is None and self.fem_solver is not None:
            if verbose:
                print("PD 영역 없음 → 순수 FEM 해석")
            fem_result = self.fem_solver.solve(verbose=verbose)
            elapsed = time.time() - t0
            return {
                "converged": fem_result.get("converged", False),
                "coupling_iterations": 0,
                "coupling_residual": 0.0,
                "elapsed_time": elapsed,
                "fem_converged": fem_result.get("converged", False),
                "pd_converged": True,
                "fem_only": True,
            }

        # FEM 영역이 비어있으면 순수 PD 해석
        if self.fem_solver is None and self.pd_adapter is not None:
            if verbose:
                print("FEM 영역 없음 → 순수 PD 해석")
            pd_max_iter = self._pd_solver_options.get("max_iterations", 50000)
            pd_tol = self._pd_solver_options.get("tol", 1e-4)
            pd_result = self.pd_adapter.solve(
                verbose=verbose,
                max_iterations=pd_max_iter,
                tol=pd_tol,
            )
            elapsed = time.time() - t0
            return {
                "converged": pd_result.converged if pd_result else False,
                "coupling_iterations": 0,
                "coupling_residual": 0.0,
                "elapsed_time": elapsed,
                "fem_converged": True,
                "pd_converged": pd_result.converged if pd_result else False,
                "pd_only": True,
            }

        self.interface.reset()

        if verbose:
            n_fem_e = len(self.split.fem_elements)
            n_pd_p = len(self.split.pd_nodes)
            n_intf = self.split.interface_global.shape[0]
            print(f"커플링 해석: FEM {n_fem_e}요소, "
                  f"{self.particle_method.upper()} {n_pd_p}입자, "
                  f"인터페이스 {n_intf}노드")

        converged = False
        coupling_residual = 0.0

        for c_iter in range(self.max_coupling_iters):
            # ── 1. FEM solve ──
            fem_result = self.fem_solver.solve(verbose=False)
            fem_disp = self.fem_mesh.get_displacements()

            # ── 2. 수렴 체크 ──
            conv, rel_change = self.interface.check_convergence(
                fem_disp, self.coupling_tol,
            )
            coupling_residual = rel_change

            if verbose:
                print(f"  커플링 반복 {c_iter}: "
                      f"인터페이스 변화={rel_change:.2e}, "
                      f"FEM 수렴={fem_result.get('converged', False)}")

            if conv and c_iter > 0:
                converged = True
                break

            # ── 3. FEM 변위 → PD Dirichlet BC ──
            pd_ghost_idx, pd_ghost_disp = \
                self.interface.fem_to_pd_displacements(fem_disp)

            # PD 인터페이스 입자에 변위 고정 BC 설정
            self._update_pd_interface_bc(pd_ghost_idx, pd_ghost_disp)

            # ── 4. PD/SPG solve ──
            pd_max_iter = self._pd_solver_options.get("max_iterations", 50000)
            pd_tol = self._pd_solver_options.get("tol", 1e-4)
            pd_result = self.pd_adapter.solve(
                verbose=False,
                max_iterations=pd_max_iter,
                tol=pd_tol,
            )

            # ── 5. PD 반력 → FEM Neumann BC ──
            pd_forces = self._get_pd_internal_forces()
            fem_intf_idx, fem_intf_forces = \
                self.interface.pd_to_fem_forces(pd_forces)

            # FEM 인터페이스 노드에 외력 추가
            self._update_fem_interface_forces(fem_intf_idx, fem_intf_forces)

        elapsed = time.time() - t0

        if verbose:
            status = "수렴" if converged else "미수렴"
            print(f"커플링 {status}: {c_iter + 1}회 반복, {elapsed:.2f}초")

        return {
            "converged": converged,
            "coupling_iterations": c_iter + 1,
            "coupling_residual": coupling_residual,
            "elapsed_time": elapsed,
            "fem_converged": fem_result.get("converged", False),
            "pd_converged": getattr(pd_result, "converged", False)
                if pd_result else False,
        }

    def solve_automatic(
        self,
        criteria: SwitchingCriteria,
        verbose: bool = False,
    ) -> dict:
        """자동 모드: FEM 1차 해석 → 기준 판별 → 커플링 해석.

        Args:
            criteria: 전환 판별 기준
            verbose: 상세 출력

        Returns:
            결과 딕셔너리
        """
        from ...fem.core.mesh import FEMesh
        from ...fem.core.element import ElementType
        from ...fem.solver.static_solver import StaticSolver

        t0 = time.time()

        # ── 1. 전체 FEM 해석 (1차) ──
        if verbose:
            print("자동 모드: 1차 FEM 해석 시작...")

        n_nodes = len(self.nodes)
        n_elements = len(self.elements)
        npe = self.elements.shape[1]

        if self.dim == 2:
            elem_type = ElementType.QUAD4
        else:
            elem_type = ElementType.HEX8

        full_mesh = FEMesh(n_nodes, n_elements, elem_type)
        full_mesh.initialize_from_numpy(self.nodes, self.elements)

        # 경계조건 적용
        if self._fixed_nodes is not None:
            full_mesh.set_fixed_nodes(self._fixed_nodes, self._fixed_values)
        if self._force_nodes is not None and self._force_values is not None:
            fv = np.asarray(self._force_values, dtype=np.float64)
            if fv.ndim == 1:
                forces = np.tile(fv, (len(self._force_nodes), 1))
            else:
                forces = fv
            full_mesh.set_nodal_forces(self._force_nodes, forces)

        fem_material = self.material._create_fem_material()
        full_solver = StaticSolver(full_mesh, fem_material)
        full_result = full_solver.solve(verbose=False)

        # ── 2. 응력 추출 + 전환 기준 평가 ──
        gauss_stress = full_mesh.stress.to_numpy()
        try:
            gauss_strain = full_mesh.strain.to_numpy()
        except Exception:
            gauss_strain = None

        n_gauss = full_mesh.n_gauss
        pd_mask = criteria.evaluate(
            gauss_stress, gauss_strain,
            n_elements, n_gauss,
            self.elements,
        )

        n_switched = int(pd_mask.sum())
        if verbose:
            print(f"1차 FEM 완료: {n_switched}/{n_elements} 요소 전환 대상")

        if n_switched == 0:
            # 전환 대상 없음 → 1차 FEM 결과 반환
            elapsed = time.time() - t0
            if verbose:
                print("전환 대상 없음 — FEM 결과 반환")
            return {
                "converged": full_result.get("converged", False),
                "coupling_iterations": 0,
                "coupling_residual": 0.0,
                "elapsed_time": elapsed,
                "fem_only": True,
                "switched_elements": 0,
            }

        if n_switched == n_elements:
            # 전체 전환 → 순수 PD/SPG 해석
            if verbose:
                print("전체 요소 전환 — 순수 PD/SPG 해석으로 전환")
            pd_mask[:] = True

        # ── 3. 영역 재분할 + 커플링 해석 ──
        self.split = split_mesh(self.nodes, self.elements, pd_mask)
        self._build_fem_solver()
        self._build_particle_solver()
        self.interface = InterfaceManager(
            self.split.interface_fem,
            self.split.interface_pd,
            dim=self.dim,
        )

        coupled_result = self.solve(verbose=verbose)
        coupled_result["switched_elements"] = n_switched
        coupled_result["elapsed_time"] = time.time() - t0
        coupled_result["fem_only"] = False

        return coupled_result

    def _update_pd_interface_bc(
        self,
        pd_indices: np.ndarray,
        pd_displacements: np.ndarray,
    ):
        """PD 인터페이스 입자에 변위 Dirichlet BC 갱신.

        PD 솔버의 고정 입자 위치를 FEM 변위 결과로 업데이트한다.
        ParticleSystem은 u 필드가 없으므로 x (현재 좌표)를 직접 갱신한다.
        변위 = x - X 이므로, x = X + displacement 로 설정.
        """
        adapter = self.pd_adapter

        if hasattr(adapter, 'ps'):
            # PD/SPG: Taichi 입자 시스템
            ps = adapter.ps
            X_np = ps.X.to_numpy()  # 참조 좌표
            x_np = ps.x.to_numpy()  # 현재 좌표

            for p_idx, disp in zip(pd_indices, pd_displacements):
                # 현재 좌표 = 참조 + 변위
                x_np[p_idx] = X_np[p_idx] + disp

            ps.x.from_numpy(x_np)

    def _get_pd_internal_forces(self) -> np.ndarray:
        """PD 솔버에서 내부력 배열 추출."""
        adapter = self.pd_adapter

        if hasattr(adapter, 'ps'):
            ps = adapter.ps
            if hasattr(ps, 'f_int'):
                return ps.f_int.to_numpy()
            elif hasattr(ps, 'f'):
                return ps.f.to_numpy()

        # 폴백: 0 반환
        n_pd = len(self.split.pd_nodes)
        return np.zeros((n_pd, self.dim), dtype=np.float64)

    def _update_fem_interface_forces(
        self,
        fem_indices: np.ndarray,
        fem_forces: np.ndarray,
    ):
        """FEM 인터페이스 노드에 PD 반력을 외력으로 추가."""
        # 기존 f_ext 가져오기
        f_ext = self.fem_mesh.f_ext.to_numpy()

        # 인터페이스 힘 추가 (기존 외력에 합산)
        for i, (f_idx, force) in enumerate(zip(fem_indices, fem_forces)):
            f_ext[f_idx] += force

        self.fem_mesh.f_ext.from_numpy(f_ext)

    # ── 결과 접근 ──

    def get_displacements(self) -> np.ndarray:
        """전체 노드 변위 반환 (원본 인덱스 기준).

        FEM 영역과 PD 영역의 변위를 원본 노드 순서로 합성한다.
        인터페이스 노드는 FEM 변위를 우선 사용한다.

        Returns:
            (n_nodes, dim) 변위 배열
        """
        n_nodes = len(self.nodes)
        disp = np.zeros((n_nodes, self.dim), dtype=np.float64)

        # PD 영역 변위 (먼저 배치)
        if self.pd_adapter is not None:
            pd_disp = self.pd_adapter.get_displacements()
            for i, g_idx in enumerate(self.split.pd_node_global):
                disp[g_idx] = pd_disp[i]

        # FEM 영역 변위 (인터페이스 노드는 FEM이 우선)
        if self.fem_mesh is not None:
            fem_disp = self.fem_mesh.get_displacements()
            for i, g_idx in enumerate(self.split.fem_node_global):
                disp[g_idx] = fem_disp[i]

        return disp

    def get_stress(self) -> np.ndarray:
        """전체 노드 응력 반환 (Von Mises).

        Returns:
            (n_nodes,) Von Mises 응력 (인터페이스: FEM 값 우선)
        """
        n_nodes = len(self.nodes)
        stress = np.zeros(n_nodes, dtype=np.float64)

        # PD 응력
        try:
            if self.pd_adapter is None:
                raise RuntimeError("PD 없음")
            pd_stress = self.pd_adapter.get_stress()
            if pd_stress is not None:
                if pd_stress.ndim > 1:
                    # 텐서 → 스칼라 (Frobenius norm 근사)
                    pd_scalar = np.sqrt(np.sum(pd_stress ** 2, axis=-1))
                    if pd_scalar.ndim > 1:
                        pd_scalar = np.sqrt(np.sum(pd_scalar ** 2, axis=-1))
                else:
                    pd_scalar = pd_stress
                for i, g_idx in enumerate(self.split.pd_node_global):
                    if i < len(pd_scalar):
                        stress[g_idx] = pd_scalar[i]
        except Exception:
            pass

        # FEM Mises 응력
        try:
            if self.fem_mesh is not None:
                self.fem_mesh.compute_mises_stress()
                fem_mises = self.fem_mesh.mises.to_numpy()
                for i, g_idx in enumerate(self.split.fem_node_global):
                    if i < len(fem_mises):
                        stress[g_idx] = fem_mises[i]
        except Exception:
            pass

        return stress

    def get_damage(self) -> np.ndarray:
        """전체 노드 손상도 반환 (FEM=0, PD 영역만 비영).

        Returns:
            (n_nodes,) 손상도
        """
        n_nodes = len(self.nodes)
        damage = np.zeros(n_nodes, dtype=np.float64)

        if self.pd_adapter is None:
            return damage

        pd_damage = self.pd_adapter.get_damage()
        if pd_damage is not None:
            for i, g_idx in enumerate(self.split.pd_node_global):
                if i < len(pd_damage):
                    damage[g_idx] = pd_damage[i]

        return damage
