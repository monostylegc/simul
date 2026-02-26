"""FEM 동적 솔버 (Newmark-beta / Central Difference).

시간 영역 동적 해석:
- Newmark-beta (implicit, γ=0.5, β=0.25): 무조건 안정
- Central Difference (explicit): 조건부 안정, 충격 문제용

질량 행렬: 집중 질량 (row-sum lumping)
감쇠: Rayleigh 감쇠 (C = α·M + β·K)
"""

import numpy as np
from typing import Optional, Dict, TYPE_CHECKING
from scipy import sparse
from scipy.sparse.linalg import spsolve, cg

if TYPE_CHECKING:
    from ..core.mesh import FEMesh
    from ..material.base import MaterialBase


class DynamicSolver:
    """FEM 동적 솔버.

    Newmark-beta 또는 Central Difference 시간 적분을 지원한다.
    """

    def __init__(
        self,
        mesh: "FEMesh",
        material: "MaterialBase",
        density: float = 1000.0,
        method: str = "newmark",
        dt: float = None,
        rayleigh_alpha: float = 0.0,
        rayleigh_beta: float = 0.0,
        linear_solver: str = "auto",
    ):
        """초기화.

        Args:
            mesh: FEMesh 인스턴스
            material: 재료 모델
            density: 재료 밀도 [kg/m³]
            method: "newmark" (implicit) 또는 "central_diff" (explicit)
            dt: 시간 간격 (None이면 자동 추정)
            rayleigh_alpha: Rayleigh 감쇠 α (질량 비례)
            rayleigh_beta: Rayleigh 감쇠 β (강성 비례)
            linear_solver: "auto" | "direct" | "cg"
        """
        self.mesh = mesh
        self.material = material
        self.density = density
        self.method = method
        self.dim = mesh.dim
        self.n_dof = mesh.n_nodes * mesh.dim
        self.linear_solver = linear_solver

        self.rayleigh_alpha = rayleigh_alpha
        self.rayleigh_beta = rayleigh_beta

        # 집중 질량 행렬 (대각, 벡터화)
        self.M_diag = self._compute_lumped_mass(density)

        # 강성 행렬 (벡터화 조립)
        from .static_solver import StaticSolver
        self._static_helper = StaticSolver(
            mesh, material, linear_solver=linear_solver
        )
        self.K = self._static_helper._assemble_stiffness_matrix().tocsr()

        # Rayleigh 감쇠 행렬: C = α·M + β·K
        M_sparse = sparse.diags(self.M_diag)
        self.C = rayleigh_alpha * M_sparse + rayleigh_beta * self.K

        # 시간 간격
        if dt is None:
            dt = self._estimate_stable_dt()
        self.dt = dt

        # 상태 변수
        self.u = np.zeros(self.n_dof)      # 변위
        self.v = np.zeros(self.n_dof)      # 속도
        self.a = np.zeros(self.n_dof)      # 가속도
        self.time = 0.0
        self.step_count = 0

        # Newmark 매개변수
        self.gamma = 0.5
        self.beta = 0.25

    def _compute_lumped_mass(self, density: float) -> np.ndarray:
        """집중 질량 행렬 계산 (row-sum lumping, 벡터화).

        Returns:
            대각 질량 벡터 (n_dof,)
        """
        elem_vol = self.mesh.elem_vol.to_numpy()
        elements = self.mesh.elements.to_numpy()
        n_nodes = self.mesh.n_nodes
        nodes_per_elem = self.mesh.nodes_per_elem
        dim = self.dim

        # 노드별 질량 = 밀도 × (연결 요소 부피 합 / 요소당 노드 수)
        # 벡터화: np.add.at으로 Python 루프 제거
        mass_per_node = density * elem_vol / nodes_per_elem  # (n_elements,)
        # 각 노드에 기여하는 질량 scatter
        node_mass = np.zeros(n_nodes)
        mass_per_node_rep = np.repeat(mass_per_node, nodes_per_elem)
        node_indices = elements.flatten()
        np.add.at(node_mass, node_indices, mass_per_node_rep)

        # DOF별 질량 (각 방향 동일) — 벡터화
        M_diag = np.repeat(node_mass, dim)

        return M_diag

    def _estimate_stable_dt(self) -> float:
        """안정 시간 간격 추정 (Central Difference 기준).

        dt_crit = 2 / ω_max, 여기서 ω_max = √(k_max / m_min)
        """
        # 요소 크기 추정
        elem_vol = self.mesh.elem_vol.to_numpy()
        avg_vol = np.mean(elem_vol)
        if self.dim == 3:
            h = np.power(avg_vol, 1.0 / 3.0)
        else:
            h = np.sqrt(avg_vol)

        # 파동 속도
        E = self.material.E
        nu = self.material.nu
        if self.dim == 3:
            c = np.sqrt(E * (1 - nu) / (self.density * (1 + nu) * (1 - 2 * nu)))
        else:
            c = np.sqrt(E / (self.density * (1 - nu**2)))

        dt = 0.8 * h / c  # safety factor 0.8
        return dt

    def set_initial_velocity(self, v0: np.ndarray):
        """초기 속도 설정.

        Args:
            v0: 초기 속도 벡터 (n_dof,) 또는 (n_nodes, dim)
        """
        if v0.ndim == 2:
            v0 = v0.flatten()
        self.v = v0.copy()

    def step(self, f_ext: Optional[np.ndarray] = None) -> Dict:
        """1 시간 스텝 전진.

        Args:
            f_ext: 외력 벡터 (n_dof,), None이면 mesh.f_ext 사용

        Returns:
            스텝 정보
        """
        if f_ext is None:
            f_ext = self.mesh.f_ext.to_numpy().flatten()

        if self.method == "newmark":
            return self._step_newmark(f_ext)
        else:
            return self._step_central_diff(f_ext)

    def _step_newmark(self, f_ext: np.ndarray) -> Dict:
        """Newmark-beta implicit 시간 적분.

        무조건 안정 (γ=0.5, β=0.25).
        """
        dt = self.dt
        gamma = self.gamma
        beta = self.beta

        # 예측값
        u_pred = self.u + dt * self.v + (0.5 - beta) * dt**2 * self.a
        v_pred = self.v + (1.0 - gamma) * dt * self.a

        # 유효 강성: K_eff = K + γ/(β·dt)·C + 1/(β·dt²)·M
        M_sparse = sparse.diags(self.M_diag)
        K_eff = self.K + (gamma / (beta * dt)) * self.C + (1.0 / (beta * dt**2)) * M_sparse

        # 유효 하중: f_eff = f_ext - K·u_pred - C·v_pred
        f_eff = f_ext - self.K @ u_pred - self.C @ v_pred

        # 경계조건 적용
        K_eff_bc, f_eff_bc = self._apply_bc(K_eff.tocsr(), f_eff)

        # 가속도 증분 풀기 (PCG 자동 선택)
        da = self._solve_linear_system(K_eff_bc, f_eff_bc)

        # 상태 업데이트
        self.a = da
        self.u = u_pred + beta * dt**2 * da
        self.v = v_pred + gamma * dt * da

        # 경계조건 강제
        self._enforce_bc()

        # 메쉬 업데이트
        self.mesh.u.from_numpy(self.u.reshape(-1, self.dim).astype(np.float64))

        self.time += dt
        self.step_count += 1

        ke = 0.5 * np.sum(self.M_diag * self.v**2)
        return {"kinetic_energy": ke, "time": self.time}

    def _step_central_diff(self, f_ext: np.ndarray) -> Dict:
        """Central Difference explicit 시간 적분.

        조건부 안정: dt < dt_crit.
        """
        dt = self.dt

        # 내부력 계산
        self.mesh.u.from_numpy(self.u.reshape(-1, self.dim).astype(np.float64))
        self.mesh.compute_deformation_gradient()
        self.material.compute_stress(self.mesh)
        self.material.compute_nodal_forces(self.mesh)
        f_int = self.mesh.f.to_numpy().flatten()

        # 감쇠력: f_damp = C · v
        f_damp = self.C @ self.v

        # 가속도: M·a = f_ext - f_int - f_damp
        self.a = (f_ext - f_int - f_damp) / (self.M_diag + 1e-30)

        # Central difference 업데이트
        # v(t+dt/2) = v(t-dt/2) + a(t)·dt
        self.v += self.a * dt

        # 경계조건: 고정 DOF의 속도/가속도 = 0
        self._enforce_bc()

        # u(t+dt) = u(t) + v(t+dt/2)·dt
        self.u += self.v * dt

        # 메쉬 업데이트
        self.mesh.u.from_numpy(self.u.reshape(-1, self.dim).astype(np.float64))

        self.time += dt
        self.step_count += 1

        ke = 0.5 * np.sum(self.M_diag * self.v**2)
        return {"kinetic_energy": ke, "time": self.time}

    def _solve_linear_system(
        self,
        K_csr: sparse.csr_matrix,
        f: np.ndarray,
        verbose: bool = False,
    ) -> np.ndarray:
        """선형 시스템 풀기 (자동 솔버 선택).

        auto: n_dof > 50000이면 PCG, 아니면 직접 해법.
        CG 실패 시 직접 해법으로 자동 폴백.
        """
        n_dof = K_csr.shape[0]

        # 솔버 선택
        if self.linear_solver == "auto":
            use_cg = (n_dof > 50000)
        elif self.linear_solver == "cg":
            use_cg = True
        else:
            use_cg = False

        if use_cg:
            try:
                from scipy.sparse.linalg import spilu, LinearOperator
                K_csc = K_csr.tocsc()

                # fill_factor 적응적 설정: 대규모에서는 낮추어 메모리 절약
                if n_dof > 200000:
                    fill_factor = 3
                elif n_dof > 100000:
                    fill_factor = 5
                else:
                    fill_factor = 10

                ilu = spilu(K_csc, fill_factor=fill_factor)
                M_precond = LinearOperator(K_csr.shape, matvec=ilu.solve)

                u, info = cg(K_csr, f, M=M_precond, tol=1e-10, maxiter=5000)
                if info == 0:
                    if verbose:
                        print(f"  CG 수렴 ({n_dof} DOF, fill={fill_factor})")
                    return u
                else:
                    if verbose:
                        print(f"  CG 미수렴 (info={info}), 직접 해법으로 폴백")
                    return spsolve(K_csr, f)
            except MemoryError:
                # ILU 메모리 부족 → 직접 해법으로 폴백
                if verbose:
                    print(f"  ILU 메모리 부족, 직접 해법으로 폴백")
                return spsolve(K_csr, f)
            except Exception:
                # 기타 실패 → 직접 해법
                return spsolve(K_csr, f)
        else:
            return spsolve(K_csr, f)

    def _apply_bc(self, K: sparse.csr_matrix, f: np.ndarray):
        """경계조건 적용 (페널티 방법, 자유도별)."""
        K = K.copy()
        f = f.copy()
        fixed = self.mesh.fixed.to_numpy()  # (n_nodes, dim)
        penalty = 1e30

        # 자유도별 고정 DOF 인덱스
        fixed_dofs = np.where(fixed.reshape(-1) == 1)[0]
        if len(fixed_dofs) > 0:
            # 대각 페널티 벡터화
            diag_vals = K.diagonal().copy()
            diag_vals[fixed_dofs] += penalty
            K.setdiag(diag_vals)

            # 우변: 고정 변위 = 0
            f[fixed_dofs] = 0.0

        return K, f

    def _enforce_bc(self):
        """경계조건 강제: 고정 DOF의 속도/가속도를 0으로 (자유도별)."""
        fixed = self.mesh.fixed.to_numpy()  # (n_nodes, dim)
        fixed_dofs = np.where(fixed.reshape(-1) == 1)[0]
        if len(fixed_dofs) > 0:
            self.v[fixed_dofs] = 0.0
            self.a[fixed_dofs] = 0.0
            self.u[fixed_dofs] = 0.0

    def solve(
        self,
        n_steps: int,
        f_ext: Optional[np.ndarray] = None,
        verbose: bool = True,
        print_interval: int = 100,
    ) -> Dict:
        """다중 스텝 실행.

        Args:
            n_steps: 스텝 수
            f_ext: 외력 벡터 (매 스텝 동일)
            verbose: 진행 출력
            print_interval: 출력 간격

        Returns:
            최종 정보
        """
        if verbose:
            print(f"FEM 동적 솔버: {self.method}, dt={self.dt:.2e}, "
                  f"n_steps={n_steps}")

        info = {}
        for i in range(n_steps):
            info = self.step(f_ext)

            if verbose and (i + 1) % print_interval == 0:
                max_u = np.max(np.abs(self.u))
                print(f"Step {i+1:6d}: t={info['time']:.4e}, "
                      f"KE={info['kinetic_energy']:.4e}, max_u={max_u:.4e}")

        return info

    def get_displacements(self) -> np.ndarray:
        """변위 반환 (n_nodes, dim)."""
        return self.u.reshape(-1, self.dim)

    def get_velocities(self) -> np.ndarray:
        """속도 반환 (n_nodes, dim)."""
        return self.v.reshape(-1, self.dim)

    def get_kinetic_energy(self) -> float:
        """운동 에너지 반환."""
        return 0.5 * np.sum(self.M_diag * self.v**2)

    def get_natural_frequencies(self, n_modes: int = 5) -> np.ndarray:
        """고유진동수 계산.

        일반화 고유값 문제: K·φ = ω²·M·φ

        Args:
            n_modes: 계산할 모드 수

        Returns:
            고유진동수 [Hz] 배열
        """
        from scipy.sparse.linalg import eigsh

        # 경계조건 적용된 자유 DOF만 추출 (자유도별)
        fixed = self.mesh.fixed.to_numpy()  # (n_nodes, dim)
        fixed_flat = fixed.reshape(-1)
        free_dofs = np.where(fixed_flat == 0)[0]

        if len(free_dofs) < n_modes:
            n_modes = len(free_dofs)

        # 자유 DOF만 추출
        K_free = self.K[np.ix_(free_dofs, free_dofs)]
        M_free = sparse.diags(self.M_diag[free_dofs])

        # 일반화 고유값 풀기 (가장 작은 고유값부터)
        eigenvalues, _ = eigsh(K_free, k=n_modes, M=M_free, sigma=0, which='LM')

        # ω² → f [Hz]
        omega = np.sqrt(np.abs(eigenvalues))
        freq = omega / (2 * np.pi)

        return np.sort(freq)
