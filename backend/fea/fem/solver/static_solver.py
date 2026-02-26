"""FEM 정적 평형 솔버.

선형/비선형 정적 해석:
- 선형: K·u = f (직접 / 반복 솔버 자동 선택)
- 비선형: Newton-Raphson + 기하 강성 + 라인 서치

벡터화 조립(assembly.py)과 PCG 반복 솔버를 사용하여
대규모 메쉬(100K+ 요소)에서도 실용적 성능을 달성한다.
"""

import taichi as ti
import numpy as np
from typing import Optional, Callable, Dict, TYPE_CHECKING
from scipy import sparse
from scipy.sparse.linalg import spsolve, cg

from .assembly import assemble_stiffness_matrix, assemble_geometric_stiffness

if TYPE_CHECKING:
    from ..core.mesh import FEMesh
    from ..material.base import MaterialBase


@ti.data_oriented
class StaticSolver:
    """FEM 정적 평형 솔버.

    선형 및 비선형(Newton-Raphson) 해석 지원.
    벡터화 조립 + PCG 자동 선택으로 대규모 시스템 대응.
    """

    def __init__(
        self,
        mesh: "FEMesh",
        material: "MaterialBase" = None,
        use_newton: bool = True,
        max_iterations: int = 50,
        tol: float = 1e-8,
        materials: Optional[Dict[int, "MaterialBase"]] = None,
        linear_solver: str = "auto",
    ):
        """초기화.

        Args:
            mesh: FEMesh 인스턴스
            material: 재료 모델 (단일 재료)
            use_newton: 비선형 Newton-Raphson 사용 (기본: True)
            max_iterations: 최대 Newton 반복 수
            tol: 수렴 허용치 (잔차 노름)
            materials: {material_id: MaterialBase} 딕셔너리 (다중 재료)
            linear_solver: "auto" | "direct" | "cg"
                auto: n_dof > 50000이면 CG, 아니면 직접 해법
        """
        self.mesh = mesh
        self.materials = materials
        if materials is not None and material is None:
            # 다중 재료: 첫 번째 재료를 기본 재료로 사용
            material = next(iter(materials.values()))
        self.material = material
        self.use_newton = use_newton and not material.is_linear
        self.max_iterations = max_iterations
        self.tol = tol
        self.linear_solver = linear_solver

        # DOF 정보
        self.n_dof = mesh.n_nodes * mesh.dim
        self.dim = mesh.dim

        # Newton-Raphson 작업 배열
        self._residual = np.zeros(self.n_dof)
        self._du = np.zeros(self.n_dof)

    def solve(
        self,
        external_force_func: Optional[Callable] = None,
        verbose: bool = True,
        progress_callback: Optional[Callable] = None,
    ) -> Dict:
        """정적 평형 해석 실행.

        Args:
            external_force_func: 외력 적용 함수 (선택적)
            verbose: 수렴 정보 출력 여부
            progress_callback: 진행 콜백 함수(dict → bool). False 반환 시 취소.

        Returns:
            수렴 정보 딕셔너리
        """
        if external_force_func is not None:
            external_force_func()

        self.mesh.apply_boundary_conditions()

        if self.material.is_linear:
            return self._solve_linear(verbose)
        elif self.use_newton:
            return self._solve_newton(verbose, progress_callback=progress_callback)
        else:
            return self._solve_nonlinear_simple(verbose)

    def _solve_linear(self, verbose: bool) -> Dict:
        """선형 시스템 K·u = f 풀기."""
        if verbose:
            print("강성 행렬 조립 중 (벡터화)...")

        # 강성 행렬 조립 (벡터화)
        K = self._assemble_stiffness_matrix()

        # 외력 벡터
        f_ext = self.mesh.f_ext.to_numpy().flatten()

        # 경계조건 적용
        K, f = self._apply_bc_to_system(K, f_ext)

        if verbose:
            print(f"{K.shape[0]} DOF 시스템 풀기...")

        # 선형 시스템 풀기 (자동 솔버 선택)
        u = self._solve_linear_system(K.tocsr(), f, verbose)

        # 결과 저장
        u_reshaped = u.reshape(-1, self.dim)
        self.mesh.u.from_numpy(u_reshaped.astype(np.float64))

        # 응력 계산
        self.mesh.compute_deformation_gradient()
        self.material.compute_stress(self.mesh)
        self.material.compute_nodal_forces(self.mesh)

        if verbose:
            print("선형 풀기 완료.")

        return {"converged": True, "iterations": 1}

    def _solve_newton(self, verbose: bool, progress_callback=None) -> Dict:
        """Newton-Raphson 반복 해석.

        Args:
            verbose: 상세 출력 여부
            progress_callback: 진행 콜백 함수(dict → bool). False 반환 시 취소.
        """
        from ..validation import logger, FEAConvergenceError
        if verbose:
            logger.info(f"Newton-Raphson solver (tol={self.tol:.2e})")

        converged = False
        ref_residual = None
        prev_res_norm = float("inf")
        divergence_count = 0

        for it in range(self.max_iterations):
            # 변형 구배 업데이트
            self.mesh.compute_deformation_gradient()

            # 응력 및 내부력 계산
            self.material.compute_stress(self.mesh)
            self.material.compute_nodal_forces(self.mesh)

            # 잔차: R = f_ext + mesh.f = f_ext - ∫ B^T σ dV
            # (mesh.f = -∫ B^T σ dV, 음수 내부력 규약)
            f_neg_int = self.mesh.f.to_numpy().flatten()
            f_ext = self.mesh.f_ext.to_numpy().flatten()
            residual = f_ext + f_neg_int

            # 고정 DOF 인덱스 계산 (벡터화)
            fixed = self.mesh.fixed.to_numpy()
            fixed_dofs = self._get_fixed_dofs(fixed)

            # 고정 DOF 잔차 0으로 설정 (벡터화)
            residual[fixed_dofs] = 0.0

            res_norm = np.linalg.norm(residual)

            # NaN/Inf 발산 감지
            if np.isnan(res_norm) or np.isinf(res_norm):
                logger.error(f"Newton 반복 {it}: NaN/Inf 잔차 발생")
                raise FEAConvergenceError(
                    "Newton-Raphson에서 NaN/Inf 잔차가 발생했습니다. "
                    "하중이 너무 크거나 재료 상수가 부적절할 수 있습니다.",
                    iterations=it, residual=float("inf"),
                    reason="nan_divergence",
                )

            if ref_residual is None:
                ref_residual = res_norm if res_norm > 1e-20 else 1.0

            rel_res = res_norm / ref_residual

            if verbose:
                logger.info(f"  Iter {it}: |R| = {res_norm:.4e}, rel = {rel_res:.4e}")

            # 잔차 증가 감지 (3회 연속 10배 이상 증가 시 경고)
            if it > 0 and res_norm > prev_res_norm * 10.0:
                divergence_count += 1
                if divergence_count >= 3:
                    logger.warning(
                        f"Newton 반복 {it}: 잔차가 3회 연속 10배 이상 증가 — 발산 가능성"
                    )
            else:
                divergence_count = 0
            prev_res_norm = res_norm

            # 진행 콜백 호출
            if progress_callback is not None:
                should_continue = progress_callback({
                    "iteration": it,
                    "max_iterations": self.max_iterations,
                    "residual": float(res_norm),
                    "relative_residual": float(rel_res),
                })
                if should_continue is False:
                    return {
                        "converged": False, "iterations": it,
                        "cancelled": True, "residual": float(res_norm),
                        "relative_residual": float(rel_res),
                    }

            if rel_res < self.tol:
                converged = True
                break

            # 접선 강성 조립
            K = self._assemble_tangent_stiffness()

            # 경계 조건 적용
            K_bc, r_bc = self._apply_bc_to_system(K, residual)

            # 증분 풀기 (PCG 자동 선택)
            try:
                du = self._solve_linear_system(K_bc.tocsr(), r_bc)
            except Exception as e:
                logger.error(f"  선형 풀기 실패: {e}")
                break

            # Line search (simple backtracking)
            alpha = 1.0
            u_current = self.mesh.u.to_numpy().flatten()

            for ls in range(5):
                u_trial = u_current + alpha * du
                self.mesh.u.from_numpy(u_trial.reshape(-1, self.dim).astype(np.float64))

                self.mesh.compute_deformation_gradient()
                self.material.compute_stress(self.mesh)
                self.material.compute_nodal_forces(self.mesh)

                f_neg_int_new = self.mesh.f.to_numpy().flatten()
                res_new = f_ext + f_neg_int_new
                res_new[fixed_dofs] = 0.0

                if np.linalg.norm(res_new) < res_norm:
                    break
                alpha *= 0.5

        if converged and verbose:
            print(f"Converged in {it+1} iterations")
        elif verbose:
            print(f"Did not converge in {self.max_iterations} iterations")

        return {
            "converged": converged,
            "iterations": it + 1,
            "residual": res_norm,
            "relative_residual": rel_res
        }

    def _solve_nonlinear_simple(self, verbose: bool) -> Dict:
        """Simple fixed-point iteration for nonlinear problems."""
        if verbose:
            print("Fixed-point iteration (stress update)")

        for it in range(self.max_iterations):
            # Update deformation gradient
            self.mesh.compute_deformation_gradient()

            # Compute stress
            self.material.compute_stress(self.mesh)
            self.material.compute_nodal_forces(self.mesh)

            # 잔차: R = f_ext + mesh.f (음수 내부력 규약)
            f_neg_int = self.mesh.f.to_numpy().flatten()
            f_ext = self.mesh.f_ext.to_numpy().flatten()
            residual = f_ext + f_neg_int

            # 고정 DOF 잔차 0으로 설정 (벡터화)
            fixed = self.mesh.fixed.to_numpy()
            fixed_dofs = self._get_fixed_dofs(fixed)
            residual[fixed_dofs] = 0.0

            res_norm = np.linalg.norm(residual)

            if verbose and it % 10 == 0:
                print(f"  Iter {it}: |R| = {res_norm:.4e}")

            if res_norm < self.tol:
                if verbose:
                    print(f"Converged in {it+1} iterations")
                return {"converged": True, "iterations": it + 1}

            # 선형 강성으로 업데이트
            K = self._assemble_stiffness_matrix()
            K_bc, r_bc = self._apply_bc_to_system(K, residual)

            du = self._solve_linear_system(K_bc.tocsr(), r_bc)

            # Update displacement
            u = self.mesh.u.to_numpy().flatten()
            u += 0.1 * du  # Damped update
            self.mesh.u.from_numpy(u.reshape(-1, self.dim).astype(np.float64))

        return {"converged": False, "iterations": self.max_iterations}

    def _assemble_stiffness_matrix(self) -> sparse.coo_matrix:
        """벡터화 전역 강성 행렬 조립.

        assembly.py의 벡터화 함수를 호출하여 Python for 루프 없이
        전체 요소의 강성을 일괄 계산한다.
        다중 재료 지원: material_id별 그룹핑으로 다른 C 텐서 적용.
        """
        # Taichi 필드 → numpy 추출 (1회)
        elements = self.mesh.elements.to_numpy()
        dNdX = self.mesh.dNdX.to_numpy()
        gauss_vol = self.mesh.gauss_vol.to_numpy()

        # 다중 재료 설정
        C_single = None
        material_ids_np = None
        C_map_dict = None

        if self.materials is not None:
            material_ids_np = self.mesh.material_id.to_numpy()
            C_map_dict = {mid: mat.get_elasticity_tensor()
                          for mid, mat in self.materials.items()}
        else:
            C_single = self.material.get_elasticity_tensor()

        return assemble_stiffness_matrix(
            elements=elements,
            dNdX=dNdX,
            gauss_vol=gauss_vol,
            n_nodes=self.mesh.n_nodes,
            n_gauss=self.mesh.n_gauss,
            dim=self.dim,
            C_single=C_single,
            material_ids=material_ids_np,
            C_map=C_map_dict,
        )

    def _assemble_tangent_stiffness(self) -> sparse.coo_matrix:
        """접선 강성 행렬 조립 (재료 + 기하 강성).

        K_T = K_material + K_geometric
        비선형 해석의 Newton-Raphson 수렴에 필수.

        Taichi 필드를 1회만 추출하여 재료/기하 강성 모두에 재사용한다.
        """
        # Taichi 필드 → numpy 추출 (1회만, 재사용)
        elements = self.mesh.elements.to_numpy()
        dNdX = self.mesh.dNdX.to_numpy()
        gauss_vol = self.mesh.gauss_vol.to_numpy()

        # 재료 강성 K_mat
        C_single = None
        material_ids_np = None
        C_map_dict = None
        if self.materials is not None:
            material_ids_np = self.mesh.material_id.to_numpy()
            C_map_dict = {mid: mat.get_elasticity_tensor()
                          for mid, mat in self.materials.items()}
        else:
            C_single = self.material.get_elasticity_tensor()

        K_mat = assemble_stiffness_matrix(
            elements=elements,
            dNdX=dNdX,
            gauss_vol=gauss_vol,
            n_nodes=self.mesh.n_nodes,
            n_gauss=self.mesh.n_gauss,
            dim=self.dim,
            C_single=C_single,
            material_ids=material_ids_np,
            C_map=C_map_dict,
        )

        # 기하 강성 K_geo: 같은 dNdX/gauss_vol 재사용
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

    def _solve_linear_system(
        self,
        K_csr: sparse.csr_matrix,
        f: np.ndarray,
        verbose: bool = False,
    ) -> np.ndarray:
        """선형 시스템 풀기 (자동 솔버 선택).

        auto: n_dof > 50000이면 PCG, 아니면 직접 해법.
        CG 실패 시 직접 해법으로 자동 폴백.

        Args:
            K_csr: CSR 강성 행렬
            f: 우변 벡터
            verbose: 솔버 정보 출력

        Returns:
            해 벡터
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

    def _get_fixed_dofs(self, fixed: np.ndarray) -> np.ndarray:
        """고정 플래그 → DOF 인덱스 변환 (벡터화).

        Args:
            fixed: DOF별 고정 플래그 (n_nodes, dim)

        Returns:
            고정 DOF 인덱스 배열
        """
        # (n_nodes, dim) → (n_nodes*dim,) 으로 평탄화
        # DOF 순서: [node0_x, node0_y, node0_z, node1_x, ...]
        fixed_flat = fixed.reshape(-1)
        result = np.where(fixed_flat == 1)[0]
        return result.astype(np.int64)

    def _apply_bc_to_system(
        self,
        K: sparse.coo_matrix,
        f: np.ndarray
    ) -> tuple:
        """경계조건 적용 (페널티 방법, 자유도별).

        고정 DOF에 페널티 값을 대각에 추가하고
        우변을 penalty × prescribed_value로 설정한다.
        """
        K = K.tocsr()
        f = f.copy()

        fixed = self.mesh.fixed.to_numpy()        # (n_nodes, dim)
        fixed_vals = self.mesh.fixed_value.to_numpy()  # (n_nodes, dim)

        fixed_dofs = self._get_fixed_dofs(fixed)
        if len(fixed_dofs) == 0:
            return K, f

        penalty = 1e30

        # 대각 페널티 (벡터 인덱싱)
        diag_vals = K.diagonal().copy()
        diag_vals[fixed_dofs] += penalty
        K.setdiag(diag_vals)

        # 우변: penalty × prescribed_value
        fixed_vals_flat = fixed_vals.reshape(-1)
        f[fixed_dofs] = penalty * fixed_vals_flat[fixed_dofs]

        return K, f

    def get_mises_stress(self) -> np.ndarray:
        """Compute and return nodal von Mises stress."""
        self.mesh.compute_mises_stress()
        return self.mesh.mises.to_numpy()

    def get_total_energy(self) -> float:
        """Get total strain energy (for hyperelastic materials)."""
        if hasattr(self.material, 'compute_total_energy'):
            return float(self.material.compute_total_energy(
                self.mesh.F,
                self.mesh.gauss_vol,
                self.mesh.n_elements * self.mesh.n_gauss
            ))
        return 0.0
