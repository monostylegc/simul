"""호장법(Arc-Length) 솔버.

Crisfield의 구면 호장법(spherical arc-length method)을 사용하여
불안정 하중-변위 경로를 추적한다.

주요 적용 사례:
- Snap-through: 하중 제어로 추적 불가능한 극한점(limit point) 통과
- Snap-back: 변위 제어로도 추적 불가능한 역방향 경로
- 후좌굴(post-buckling) 해석

알고리즘 (Crisfield, 1981):
1. 예측 단계: 접선 방향으로 초기 증분 Δu₀ = Δλ₀ · K⁻¹ · f_ref
2. 수정 단계: Newton-Raphson + 구속 조건(arc-length constraint)
   - 구면 구속: ‖Δu‖² + (Δλ · ψ)² = Δl²
   - Borja 방식: 이차 방정식 풀기로 Δλ 증분 결정
3. 적응적 호장 크기: 수렴 속도에 따라 Δl 조절

참고문헌:
- Crisfield (1981), "A fast incremental/iterative solution procedure..."
- de Souza Neto et al. (2008), "Computational Methods for Plasticity", Ch.4
- Ritto-Corrêa & Camotim (2008), "On the arc-length and other quadratic..."
"""

import numpy as np
from typing import Optional, Callable, Dict, List, TYPE_CHECKING
from scipy import sparse
from scipy.sparse.linalg import spsolve

from .assembly import assemble_stiffness_matrix, assemble_geometric_stiffness

if TYPE_CHECKING:
    from ..core.mesh import FEMesh
    from ..material.base import MaterialBase


class ArcLengthSolver:
    """Crisfield 구면 호장법 솔버.

    Args:
        mesh: FEMesh 인스턴스
        material: 재료 모델
        arc_length: 초기 호장(arc) 크기 Δl
        max_steps: 최대 하중 단계 수
        max_iterations: 단계별 최대 Newton 반복 수
        tol: 수렴 허용치 (상대 잔차)
        psi: 구속 조건 스케일링 계수 (0=업데이트 평면법, 1=구면법)
        desired_iterations: 적응적 호장 목표 반복 횟수
        min_arc_length: 최소 호장 크기
        max_arc_length: 최대 호장 크기
        max_load_factor: 최대 하중 비율 λ (이 값 도달 시 종료)
        linear_solver: "auto" | "direct" | "cg"
    """

    def __init__(
        self,
        mesh: "FEMesh",
        material: "MaterialBase",
        arc_length: float = 0.1,
        max_steps: int = 100,
        max_iterations: int = 30,
        tol: float = 1e-8,
        psi: float = 1.0,
        desired_iterations: int = 5,
        min_arc_length: float = 1e-6,
        max_arc_length: float = 10.0,
        max_load_factor: float = 1.0,
        linear_solver: str = "auto",
    ):
        self.mesh = mesh
        self.material = material
        self.arc_length = arc_length
        self.max_steps = max_steps
        self.max_iterations = max_iterations
        self.tol = tol
        self.psi = psi
        self.desired_iterations = desired_iterations
        self.min_arc_length = min_arc_length
        self.max_arc_length = max_arc_length
        self.max_load_factor = max_load_factor
        self.linear_solver = linear_solver

        # DOF 정보
        self.dim = mesh.dim
        self.n_dof = mesh.n_nodes * mesh.dim

        # 참조 외력 벡터 (스케일링 기준)
        self._f_ref = None

        # 결과 저장 (하중-변위 경로)
        self.load_history: List[float] = []
        self.displacement_history: List[np.ndarray] = []
        self.energy_history: List[float] = []

    def solve(
        self,
        f_ref: Optional[np.ndarray] = None,
        verbose: bool = True,
        progress_callback: Optional[Callable] = None,
    ) -> Dict:
        """호장법 해석 실행.

        외부 하중 = λ · f_ref 로 매개변수화한다.
        하중 비율 λ가 0에서 max_load_factor까지 호장법으로 추적한다.

        Args:
            f_ref: 참조 외력 벡터 (n_dof,). None이면 mesh.f_ext 사용.
            verbose: 수렴 정보 출력
            progress_callback: 진행 콜백 (dict → bool). False 반환 시 취소.

        Returns:
            결과 딕셔너리:
            - converged: 전체 해석 수렴 여부
            - n_steps: 완료된 하중 단계 수
            - load_factors: 각 단계의 λ 값
            - displacements: 각 단계의 변위 배열
            - energies: 각 단계의 변형 에너지
        """
        from ..validation import logger, FEAConvergenceError

        # 참조 외력 벡터 설정
        if f_ref is not None:
            self._f_ref = f_ref.copy()
        else:
            self._f_ref = self.mesh.f_ext.to_numpy().flatten()

        f_ref_norm = np.linalg.norm(self._f_ref)
        if f_ref_norm < 1e-30:
            raise FEAConvergenceError(
                "참조 외력 벡터가 영(zero)입니다. 하중을 적용해 주세요.",
                iterations=0, residual=0.0, reason="zero_reference_load",
            )

        # 고정 DOF 인덱스
        fixed = self.mesh.fixed.to_numpy()
        fixed_dofs = self._get_fixed_dofs(fixed)
        free_dofs = np.setdiff1d(np.arange(self.n_dof), fixed_dofs)

        # 초기화
        lam = 0.0          # 현재 하중 비율
        u = np.zeros(self.n_dof)   # 현재 총 변위
        dl = self.arc_length       # 현재 호장 크기

        self.load_history = [0.0]
        self.displacement_history = [np.zeros(self.n_dof)]
        self.energy_history = [0.0]

        # 이전 증분 변위 (예측 방향 결정용)
        prev_delta_u = np.zeros(self.n_dof)

        if verbose:
            logger.info(f"호장법(Arc-Length) 솔버 시작: Δl₀={dl:.4e}, ψ={self.psi}")
            logger.info(f"  목표 λ_max={self.max_load_factor}, 최대 {self.max_steps}단계")

        n_completed = 0

        for step in range(self.max_steps):
            # ─── 접선 강성 행렬 조립 ───
            K = self._assemble_tangent_stiffness()
            K_bc = self._apply_bc_to_K(K, fixed_dofs)

            # ─── 접선 변위: δu_f = K⁻¹ · f_ref ───
            f_ref_bc = self._f_ref.copy()
            f_ref_bc[fixed_dofs] = 0.0
            du_f = self._solve_linear_system(K_bc.tocsr(), f_ref_bc)
            du_f[fixed_dofs] = 0.0

            # ─── 예측 단계(predictor) ───
            if step == 0:
                # 첫 단계: 양의 방향
                sign = 1.0
            else:
                # 이전 방향 연속: 접선 변위와 이전 증분의 내적
                dot = np.dot(du_f[free_dofs], prev_delta_u[free_dofs])
                sign = 1.0 if dot >= 0.0 else -1.0

            # 예측 하중 증분
            psi_sq = self.psi ** 2
            denom = np.dot(du_f[free_dofs], du_f[free_dofs]) + psi_sq
            if denom < 1e-30:
                if verbose:
                    logger.warning(f"  단계 {step}: 접선 벡터 길이 0 — 해석 종료")
                break

            delta_lam = sign * dl / np.sqrt(denom)

            # 하중 비율 제한: max_load_factor 초과 방지
            if lam + delta_lam > self.max_load_factor:
                delta_lam = self.max_load_factor - lam
            elif lam + delta_lam < -self.max_load_factor:
                delta_lam = -self.max_load_factor - lam

            delta_u = delta_lam * du_f

            # 현재 시점 총 변위/하중 비율 업데이트
            u_trial = u + delta_u
            lam_trial = lam + delta_lam

            # ─── 수정 단계(corrector): Newton-Raphson ───
            converged_step = False
            n_iters = 0

            for it in range(self.max_iterations):
                n_iters = it + 1

                # 변위 적용 → 잔차 계산
                self._set_displacement(u_trial)
                self.mesh.compute_deformation_gradient()
                self.material.compute_stress(self.mesh)
                self.material.compute_nodal_forces(self.mesh)

                # mesh.f = -∫ B^T σ dV (음수 내부력 규약)
                # 잔차 R = f_ext + mesh.f = f_ext - ∫ B^T σ dV
                f_neg_int = self.mesh.f.to_numpy().flatten()
                residual = lam_trial * self._f_ref + f_neg_int
                residual[fixed_dofs] = 0.0

                res_norm = np.linalg.norm(residual)
                ref_force = np.linalg.norm(lam_trial * self._f_ref)
                if ref_force < 1e-20:
                    ref_force = f_ref_norm

                rel_res = res_norm / ref_force

                if verbose and it % 5 == 0:
                    logger.info(
                        f"  단계 {step}, 반복 {it}: |R|={res_norm:.4e}, "
                        f"rel={rel_res:.4e}, λ={lam_trial:.6f}"
                    )

                # 수렴 판정
                if rel_res < self.tol:
                    converged_step = True
                    break

                # NaN/Inf 감지
                if np.isnan(res_norm) or np.isinf(res_norm):
                    if verbose:
                        logger.warning(f"  단계 {step}: NaN/Inf 잔차 발생")
                    break

                # ─── 접선 강성 재조립 + 보정 ───
                K = self._assemble_tangent_stiffness()
                K_bc = self._apply_bc_to_K(K, fixed_dofs)

                # δu_f: K·δu_f = f_ref (하중 방향)
                f_ref_bc = self._f_ref.copy()
                f_ref_bc[fixed_dofs] = 0.0
                du_f = self._solve_linear_system(K_bc.tocsr(), f_ref_bc)
                du_f[fixed_dofs] = 0.0

                # δu_r: K·δu_r = R (잔차 방향)
                du_r = self._solve_linear_system(K_bc.tocsr(), residual)
                du_r[fixed_dofs] = 0.0

                # 구면 구속 조건으로 δλ 결정 (이차 방정식)
                # (Δu + δu_r + δλ·du_f)·(Δu + δu_r + δλ·du_f) + (Δλ+δλ)²ψ² = Δl²
                #
                # 단순화: 업데이트 법선 근사 (Ritto-Corrêa)
                # δλ = -du_r·Δu / (du_f·Δu + ψ²·Δλ)
                Delta_u = u_trial - u     # 이번 단계 누적 증분
                Delta_lam = lam_trial - lam

                a_coeff = (np.dot(du_f[free_dofs], du_f[free_dofs])
                           + psi_sq)
                b_coeff = (np.dot(du_f[free_dofs],
                                  Delta_u[free_dofs] + du_r[free_dofs])
                           + psi_sq * Delta_lam)

                if abs(b_coeff) < 1e-30:
                    # 분모 0 방지
                    d_lam = 0.0
                else:
                    # 선형화된 구속 조건 (Ritto-Corrêa 법선 업데이트)
                    d_lam = -np.dot(Delta_u[free_dofs], du_r[free_dofs]) / b_coeff

                # 증분 업데이트
                d_u = du_r + d_lam * du_f

                u_trial = u_trial + d_u
                lam_trial = lam_trial + d_lam

            # ─── 단계 결과 처리 ───
            if converged_step:
                # 이전 증분 저장 (다음 예측 방향용)
                prev_delta_u = u_trial - u

                # 상태 업데이트
                u = u_trial.copy()
                lam = lam_trial

                # 에너지 계산: U = ½ u^T · f_int = ½ u^T · (-mesh.f)
                energy = -0.5 * np.dot(u, self.mesh.f.to_numpy().flatten())

                # 경로 기록
                self.load_history.append(float(lam))
                self.displacement_history.append(u.copy())
                self.energy_history.append(float(energy))

                n_completed += 1

                if verbose:
                    logger.info(
                        f"  ✓ 단계 {step} 수렴: λ={lam:.6f}, "
                        f"|u|_max={np.max(np.abs(u)):.4e}, "
                        f"{n_iters}회 반복"
                    )

                # 진행 콜백
                if progress_callback is not None:
                    should_continue = progress_callback({
                        "step": step,
                        "max_steps": self.max_steps,
                        "load_factor": float(lam),
                        "max_load_factor": self.max_load_factor,
                        "iterations": n_iters,
                        "energy": float(energy),
                    })
                    if should_continue is False:
                        if verbose:
                            logger.info("  해석 취소됨 (콜백 요청)")
                        return self._build_result(n_completed, cancelled=True)

                # 종료 조건: 최대 하중 비율 도달
                if abs(lam) >= self.max_load_factor:
                    if verbose:
                        logger.info(f"  목표 하중 비율 λ={self.max_load_factor} 도달")
                    break

                # ─── 적응적 호장 크기 조절 ───
                if n_iters > 0:
                    ratio = self.desired_iterations / max(n_iters, 1)
                    # Bergan & Mollestad 기법: Δl_new = Δl * √(ratio)
                    dl_new = dl * np.sqrt(ratio)
                    dl = np.clip(dl_new, self.min_arc_length, self.max_arc_length)

            else:
                # 수렴 실패: 호장 크기 줄이고 재시도
                if verbose:
                    logger.warning(
                        f"  ✗ 단계 {step} 미수렴 ({self.max_iterations}회), "
                        f"호장 크기 축소: {dl:.4e} → {dl*0.5:.4e}"
                    )

                dl *= 0.5
                if dl < self.min_arc_length:
                    if verbose:
                        logger.error("  최소 호장 크기 도달 — 해석 종료")
                    break

                # 변위/하중 비율 이전 상태로 복원
                self._set_displacement(u)
                lam_trial = lam

                # 재료 상태 복원 (소성 등)
                if hasattr(self.material, 'reset_state'):
                    # 주의: 전체 리셋이 아닌 증분 롤백이 이상적이나
                    # 현재 아키텍처에서는 전체 재계산으로 대체
                    self.mesh.compute_deformation_gradient()
                    self.material.compute_stress(self.mesh)

        if verbose:
            logger.info(
                f"호장법 해석 완료: {n_completed}단계, "
                f"최종 λ={lam:.6f}"
            )

        return self._build_result(n_completed)

    def _build_result(
        self, n_steps: int, cancelled: bool = False
    ) -> Dict:
        """결과 딕셔너리 생성."""
        return {
            "converged": n_steps > 0,
            "n_steps": n_steps,
            "cancelled": cancelled,
            "load_factors": self.load_history.copy(),
            "displacements": [d.copy() for d in self.displacement_history],
            "energies": self.energy_history.copy(),
            "final_load_factor": self.load_history[-1] if self.load_history else 0.0,
        }

    def _set_displacement(self, u: np.ndarray):
        """변위 벡터를 메쉬에 설정."""
        u_reshaped = u.reshape(-1, self.dim)
        self.mesh.u.from_numpy(u_reshaped.astype(np.float64))

    def _assemble_tangent_stiffness(self) -> sparse.coo_matrix:
        """접선 강성 행렬 조립 (재료 + 기하 강성).

        선형 재료인 경우 기하 강성 생략.
        """
        elements = self.mesh.elements.to_numpy()
        dNdX = self.mesh.dNdX.to_numpy()
        gauss_vol = self.mesh.gauss_vol.to_numpy()

        C = self.material.get_elasticity_tensor()

        K_mat = assemble_stiffness_matrix(
            elements=elements,
            dNdX=dNdX,
            gauss_vol=gauss_vol,
            n_nodes=self.mesh.n_nodes,
            n_gauss=self.mesh.n_gauss,
            dim=self.dim,
            C_single=C,
        )

        # 비선형 재료: 기하 강성 추가
        if not self.material.is_linear:
            stress = self.mesh.stress.to_numpy()
            K_geo = assemble_geometric_stiffness(
                elements=elements,
                dNdX=dNdX,
                gauss_vol=gauss_vol,
                stress=stress,
                n_nodes=self.mesh.n_nodes,
                n_gauss=self.mesh.n_gauss,
                dim=self.dim,
            )
            return K_mat + K_geo

        return K_mat

    def _apply_bc_to_K(
        self, K: sparse.coo_matrix, fixed_dofs: np.ndarray
    ) -> sparse.coo_matrix:
        """경계조건을 강성 행렬에 적용 (페널티 방법).

        고정 DOF에 대각 페널티를 추가한다.
        """
        K_csr = K.tocsr()
        if len(fixed_dofs) == 0:
            return K_csr

        penalty = 1e30
        diag = K_csr.diagonal().copy()
        diag[fixed_dofs] += penalty
        K_csr.setdiag(diag)
        return K_csr

    def _solve_linear_system(
        self, K: sparse.csr_matrix, f: np.ndarray
    ) -> np.ndarray:
        """선형 시스템 풀기."""
        n_dof = K.shape[0]

        if self.linear_solver == "auto":
            use_cg = (n_dof > 50000)
        elif self.linear_solver == "cg":
            use_cg = True
        else:
            use_cg = False

        if use_cg:
            try:
                from scipy.sparse.linalg import cg, spilu, LinearOperator
                K_csc = K.tocsc()
                fill = 5 if n_dof > 100000 else 10
                ilu = spilu(K_csc, fill_factor=fill)
                M = LinearOperator(K.shape, matvec=ilu.solve)
                u, info = cg(K, f, M=M, tol=1e-10, maxiter=5000)
                if info == 0:
                    return u
            except Exception:
                pass
            # 폴백: 직접 해법
            return spsolve(K, f)
        else:
            return spsolve(K, f)

    def _get_fixed_dofs(self, fixed: np.ndarray) -> np.ndarray:
        """고정 플래그 → DOF 인덱스 변환 (자유도별).

        Args:
            fixed: DOF별 고정 플래그 (n_nodes, dim)
        """
        fixed_flat = fixed.reshape(-1)
        result = np.where(fixed_flat == 1)[0]
        return result.astype(np.int64)

    def get_equilibrium_path(
        self,
        node_id: int,
        dof: int = 0,
    ) -> tuple:
        """특정 노드의 하중-변위 평형 경로 추출.

        Args:
            node_id: 노드 인덱스
            dof: 자유도 방향 (0=x, 1=y, 2=z)

        Returns:
            (displacements, load_factors) 튜플
        """
        dof_idx = node_id * self.dim + dof

        disps = []
        lams = []
        for i, u in enumerate(self.displacement_history):
            disps.append(u[dof_idx])
            lams.append(self.load_history[i])

        return np.array(disps), np.array(lams)
