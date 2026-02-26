"""횡이방성(Transversely Isotropic) 재료 모델.

소변형 횡이방성 선형 탄성:
- 등방면(isotropic plane) 내에서는 등방성
- 이방 축(fiber direction) 방향은 다른 물성

5개 독립 상수:
- E1: 이방 축 방향 영 계수 [Pa]  (뼈의 장축 방향)
- E2: 등방면 영 계수 [Pa]
- ν12: 이방 축 ↔ 등방면 푸아송 비
- ν23: 등방면 내 푸아송 비
- G12: 이방 축 ↔ 등방면 전단 계수 [Pa]

좌표계:
- 3D: 방향 1 = 이방 축, 방향 2,3 = 등방면
- 2D: 방향 1 = 이방 축, 방향 2 = 등방면 내 수직 방향

적용: 피질골 (E1≈17 GPa, E2≈11.5 GPa)

참고문헌:
- Reilly & Burstein, J Biomech (1975)
- Yoon & Katz, J Biomech (1976)
"""

import taichi as ti
import numpy as np
from typing import Optional, Tuple, TYPE_CHECKING

from .base import MaterialBase

if TYPE_CHECKING:
    from ..core.mesh import FEMesh


@ti.data_oriented
class TransverseIsotropic(MaterialBase):
    """횡이방성 선형 탄성 재료 모델.

    피질골 등 방향 의존적 재료에 사용.
    Voigt 표기 탄성 텐서를 직접 조립하여 응력을 계산한다.
    """

    def __init__(
        self,
        E1: float,
        E2: float,
        nu12: float,
        nu23: float,
        G12: float,
        fiber_direction: Optional[Tuple[float, ...]] = None,
        dim: int = 3,
    ):
        """초기화.

        Args:
            E1: 이방 축(fiber) 방향 영 계수 [Pa]
            E2: 등방면 영 계수 [Pa]
            nu12: 이방 축 ↔ 등방면 푸아송 비
            nu23: 등방면 내 푸아송 비
            G12: 이방 축 ↔ 등방면 전단 계수 [Pa]
            fiber_direction: 이방 축 방향 벡터 (기본값: x축 [1,0,0])
                             정규화됨
            dim: 공간 차원 (2 또는 3)
        """
        super().__init__(dim)

        # 입력 검증
        from ..validation import validate_transverse_isotropic
        validate_transverse_isotropic(E1, E2, nu12, nu23, G12, "TransverseIsotropic")

        self.E1 = E1
        self.E2 = E2
        self.nu12 = nu12
        self.nu23 = nu23
        self.G12 = G12

        # 유도 상수
        self.G23 = E2 / (2.0 * (1.0 + nu23))   # 등방면 내 전단 계수
        self.nu21 = nu12 * E2 / E1               # 대칭 조건: ν21/E2 = ν12/E1

        # 이방 축 방향 (정규화)
        if fiber_direction is None:
            if dim == 3:
                self._fiber_dir = np.array([1.0, 0.0, 0.0])
            else:
                self._fiber_dir = np.array([1.0, 0.0])
        else:
            fdir = np.array(fiber_direction[:dim], dtype=np.float64)
            norm = np.linalg.norm(fdir)
            if norm < 1e-12:
                raise ValueError("fiber_direction의 노름이 0에 가깝습니다")
            self._fiber_dir = fdir / norm

        # 탄성 텐서 조립
        self._C = self._build_elasticity_tensor()

        # Taichi 필드로 복사 (커널 접근용)
        if dim == 3:
            self._C_ti = ti.Matrix.field(6, 6, dtype=ti.f64, shape=())
        else:
            self._C_ti = ti.Matrix.field(3, 3, dtype=ti.f64, shape=())
        self._C_ti[None] = ti.Matrix(self._C.tolist())

        # 이방 축 회전 행렬 (재료 좌표 → 전역 좌표)
        self._T = self._build_rotation_matrix()
        if dim == 3:
            self._T_ti = ti.Matrix.field(6, 6, dtype=ti.f64, shape=())
        else:
            self._T_ti = ti.Matrix.field(3, 3, dtype=ti.f64, shape=())

        # 회전된 탄성 텐서: C_global = T^T · C_mat · T
        C_global = self._T.T @ self._C @ self._T
        self._C_global = C_global
        self._C_ti[None] = ti.Matrix(C_global.tolist())

    def _build_elasticity_tensor(self) -> np.ndarray:
        """재료 좌표계에서 Voigt 탄성 텐서 조립.

        방향 1 = 이방 축, 방향 2,3 = 등방면

        Returns:
            C: 6×6 (3D) 또는 3×3 (2D) 재료 강성 행렬
        """
        E1, E2 = self.E1, self.E2
        nu12, nu23, nu21 = self.nu12, self.nu23, self.nu21
        G12, G23 = self.G12, self.G23

        if self.dim == 3:
            # 유순도 행렬 S (6×6 Voigt, 1방향 = 이방 축)
            S = np.zeros((6, 6))
            # 수직 성분
            S[0, 0] = 1.0 / E1       # ε11/σ11
            S[1, 1] = 1.0 / E2       # ε22/σ22
            S[2, 2] = 1.0 / E2       # ε33/σ33 (등방면)
            S[0, 1] = -nu12 / E1     # ε22/σ11 = -ν12/E1
            S[1, 0] = -nu12 / E1     # ε11/σ22 = -ν21/E2 = -ν12/E1
            S[0, 2] = -nu12 / E1     # ε33/σ11
            S[2, 0] = -nu12 / E1     # ε11/σ33
            S[1, 2] = -nu23 / E2     # ε33/σ22
            S[2, 1] = -nu23 / E2     # ε22/σ33
            # 전단 성분 (Voigt: γ12, γ13, γ23)
            S[3, 3] = 1.0 / G12      # γ23 (23평면) → G23은 등방면
            S[4, 4] = 1.0 / G12      # γ13 (13평면) → G12
            S[5, 5] = 1.0 / G23      # γ12 (12평면) → G12

            # 전단 컴포넌트 Voigt 규약: [ε11, ε22, ε33, ε23, ε13, ε12]
            # 재배치: Voigt = [σ1, σ2, σ3, τ23, τ13, τ12]
            # S의 전단 부분 재확인
            # 1=fiber, 2,3=isotropic plane
            # τ23: 등방면 내 → G23
            # τ13: fiber-등방면 → G12
            # τ12: fiber-등방면 → G12
            S[3, 3] = 1.0 / G23      # τ23/γ23
            S[4, 4] = 1.0 / G12      # τ13/γ13
            S[5, 5] = 1.0 / G12      # τ12/γ12

            # 강성 텐서: C = S^{-1}
            C = np.linalg.inv(S)
            return C
        else:
            # 2D 평면변형: 3D 유순도에서 ε₃₃=0 조건으로 축소
            # S'_ij = S_ij - S_i2·S_2j / S_22 (i,j ∈ {0,1})
            # 먼저 3D 유순도 구축 (방향 1=이방축, 2=등방면, 3=등방면)
            S3d = np.zeros((6, 6))
            S3d[0, 0] = 1.0 / E1
            S3d[1, 1] = 1.0 / E2
            S3d[2, 2] = 1.0 / E2
            S3d[0, 1] = -nu12 / E1
            S3d[1, 0] = -nu12 / E1
            S3d[0, 2] = -nu12 / E1
            S3d[2, 0] = -nu12 / E1
            S3d[1, 2] = -nu23 / E2
            S3d[2, 1] = -nu23 / E2
            S3d[3, 3] = 1.0 / G23
            S3d[4, 4] = 1.0 / G12
            S3d[5, 5] = 1.0 / G12

            # 평면변형 축소: ε₃₃=0 → σ₃₃ 소거
            # 방향 3 = 인덱스 2 (Voigt 수직 성분)
            S2d = np.zeros((3, 3))
            S2d[0, 0] = S3d[0, 0] - S3d[0, 2] * S3d[2, 0] / S3d[2, 2]
            S2d[0, 1] = S3d[0, 1] - S3d[0, 2] * S3d[2, 1] / S3d[2, 2]
            S2d[1, 0] = S3d[1, 0] - S3d[1, 2] * S3d[2, 0] / S3d[2, 2]
            S2d[1, 1] = S3d[1, 1] - S3d[1, 2] * S3d[2, 1] / S3d[2, 2]
            S2d[2, 2] = S3d[5, 5]  # γ12/τ12 (면내 전단)

            C = np.linalg.inv(S2d)
            return C

    def _build_rotation_matrix(self) -> np.ndarray:
        """이방 축 회전에 대한 Voigt 변환 행렬 생성.

        재료 좌표 (1방향=x축) → 전역 좌표 (1방향=fiber_direction)
        Bond 변환 행렬 (응력 변환용).

        Returns:
            T: 6×6 (3D) 또는 3×3 (2D) 변환 행렬
        """
        if self.dim == 3:
            fdir = self._fiber_dir
            # 이방 축이 이미 x축이면 회전 불필요
            if np.allclose(fdir, [1, 0, 0]):
                return np.eye(6)

            # 회전 행렬 R (3×3): 재료 x축 → 전역 fiber방향
            e1 = fdir
            # e2: fiber에 수직인 임의 벡터
            if abs(fdir[2]) < 0.9:
                temp = np.array([0, 0, 1.0])
            else:
                temp = np.array([1, 0, 0.0])
            e2 = np.cross(fdir, temp)
            e2 /= np.linalg.norm(e2)
            e3 = np.cross(e1, e2)

            # 방향 코사인 행렬 (a_ij = cos(전역_i, 재료_j))
            a = np.array([e1, e2, e3])  # 각 행 = 전역 축이 재료 축에 대한 코사인

            # Bond 변환 행렬 for stress (Voigt: σ11,σ22,σ33,σ23,σ13,σ12)
            T = np.zeros((6, 6))
            # 수직 응력 변환
            for i in range(3):
                for j in range(3):
                    T[i, j] = a[i, j]**2
            # 전단 항
            T[0, 3] = 2*a[0, 1]*a[0, 2]; T[0, 4] = 2*a[0, 0]*a[0, 2]; T[0, 5] = 2*a[0, 0]*a[0, 1]
            T[1, 3] = 2*a[1, 1]*a[1, 2]; T[1, 4] = 2*a[1, 0]*a[1, 2]; T[1, 5] = 2*a[1, 0]*a[1, 1]
            T[2, 3] = 2*a[2, 1]*a[2, 2]; T[2, 4] = 2*a[2, 0]*a[2, 2]; T[2, 5] = 2*a[2, 0]*a[2, 1]

            T[3, 0] = a[1, 0]*a[2, 0]; T[3, 1] = a[1, 1]*a[2, 1]; T[3, 2] = a[1, 2]*a[2, 2]
            T[3, 3] = a[1, 1]*a[2, 2]+a[1, 2]*a[2, 1]
            T[3, 4] = a[1, 0]*a[2, 2]+a[1, 2]*a[2, 0]
            T[3, 5] = a[1, 0]*a[2, 1]+a[1, 1]*a[2, 0]

            T[4, 0] = a[0, 0]*a[2, 0]; T[4, 1] = a[0, 1]*a[2, 1]; T[4, 2] = a[0, 2]*a[2, 2]
            T[4, 3] = a[0, 1]*a[2, 2]+a[0, 2]*a[2, 1]
            T[4, 4] = a[0, 0]*a[2, 2]+a[0, 2]*a[2, 0]
            T[4, 5] = a[0, 0]*a[2, 1]+a[0, 1]*a[2, 0]

            T[5, 0] = a[0, 0]*a[1, 0]; T[5, 1] = a[0, 1]*a[1, 1]; T[5, 2] = a[0, 2]*a[1, 2]
            T[5, 3] = a[0, 1]*a[1, 2]+a[0, 2]*a[1, 1]
            T[5, 4] = a[0, 0]*a[1, 2]+a[0, 2]*a[1, 0]
            T[5, 5] = a[0, 0]*a[1, 1]+a[0, 1]*a[1, 0]

            return T
        else:
            # 2D 회전
            fdir = self._fiber_dir
            if np.allclose(fdir, [1, 0]):
                return np.eye(3)

            c = fdir[0]  # cos θ
            s = fdir[1]  # sin θ

            # 2D Voigt 변환 [σ11, σ22, σ12]
            T = np.array([
                [c**2,     s**2,    2*c*s],
                [s**2,     c**2,   -2*c*s],
                [-c*s,     c*s,    c**2-s**2],
            ])
            return T

    @property
    def is_linear(self) -> bool:
        """횡이방성은 선형 탄성."""
        return True

    def get_elasticity_tensor(self) -> np.ndarray:
        """전역 좌표계 탄성 텐서 반환 (Voigt 표기).

        Returns:
            C: 6×6 (3D) 또는 3×3 (2D) 전역 탄성 텐서
        """
        return self._C_global.copy()

    def compute_stress(self, mesh: "FEMesh"):
        """소변형률로부터 응력 계산.

        σ = C : ε  (Voigt 표기로 행렬-벡터 곱)
        """
        n_gauss = mesh.n_elements * mesh.n_gauss
        if self.dim == 3:
            self._compute_stress_3d_kernel(
                mesh.F, mesh.stress, mesh.strain, n_gauss,
            )
        else:
            self._compute_stress_2d_kernel(
                mesh.F, mesh.stress, mesh.strain, n_gauss,
            )

    @ti.kernel
    def _compute_stress_3d_kernel(
        self,
        F: ti.template(),
        stress: ti.template(),
        strain: ti.template(),
        n_gauss: int,
    ):
        """3D 횡이방성 응력 계산 커널."""
        C = self._C_ti[None]

        for gp in range(n_gauss):
            Fg = F[gp]
            I = ti.Matrix.identity(ti.f64, 3)
            eps = 0.5 * (Fg + Fg.transpose()) - I

            # Voigt 변형률: [ε11, ε22, ε33, γ23, γ13, γ12]
            eps_v = ti.Vector([
                eps[0, 0], eps[1, 1], eps[2, 2],
                2.0 * eps[1, 2], 2.0 * eps[0, 2], 2.0 * eps[0, 1]
            ])

            # σ = C · ε (Voigt)
            sigma_v = C @ eps_v

            # Voigt → 텐서
            sigma = ti.Matrix([
                [sigma_v[0], sigma_v[5], sigma_v[4]],
                [sigma_v[5], sigma_v[1], sigma_v[3]],
                [sigma_v[4], sigma_v[3], sigma_v[2]],
            ])

            stress[gp] = sigma
            strain[gp] = eps

    @ti.kernel
    def _compute_stress_2d_kernel(
        self,
        F: ti.template(),
        stress: ti.template(),
        strain: ti.template(),
        n_gauss: int,
    ):
        """2D 횡이방성 응력 계산 커널."""
        C = self._C_ti[None]

        for gp in range(n_gauss):
            Fg = F[gp]
            I = ti.Matrix.identity(ti.f64, 2)
            eps = 0.5 * (Fg + Fg.transpose()) - I

            # Voigt 변형률: [ε11, ε22, γ12]
            eps_v = ti.Vector([eps[0, 0], eps[1, 1], 2.0 * eps[0, 1]])

            # σ = C · ε (Voigt)
            sigma_v = C @ eps_v

            # Voigt → 텐서
            sigma = ti.Matrix([
                [sigma_v[0], sigma_v[2]],
                [sigma_v[2], sigma_v[1]],
            ])

            stress[gp] = sigma
            strain[gp] = eps

    def compute_nodal_forces(self, mesh: "FEMesh"):
        """내부 절점력 계산 (소변형 B-matrix 방식)."""
        mesh.f.fill(0)
        self._compute_forces_kernel(
            mesh.elements, mesh.dNdX, mesh.stress,
            mesh.gauss_vol, mesh.f,
            mesh.n_elements, mesh.n_gauss, mesh.nodes_per_elem,
        )

    @ti.kernel
    def _compute_forces_kernel(
        self,
        elements: ti.template(),
        dNdX: ti.template(),
        stress: ti.template(),
        gauss_vol: ti.template(),
        f: ti.template(),
        n_elements: int,
        n_gauss: int,
        nodes_per_elem: int,
    ):
        """내부력 커널: f_a = - Σ_gp σ · (dN_a/dX) · vol."""
        dim = ti.static(self.dim)
        for e in range(n_elements):
            for g in range(n_gauss):
                gp_idx = e * n_gauss + g
                sigma = stress[gp_idx]
                dN = dNdX[gp_idx]
                vol = gauss_vol[gp_idx]

                for a in range(nodes_per_elem):
                    node = elements[e][a]
                    f_a = ti.Vector.zero(ti.f64, dim)
                    for i in ti.static(range(dim)):
                        for j in ti.static(range(dim)):
                            f_a[i] -= sigma[i, j] * dN[a, j] * vol
                    ti.atomic_add(f[node], f_a)

    def __repr__(self) -> str:
        return (
            f"TransverseIsotropic(E1={self.E1:.2e}, E2={self.E2:.2e}, "
            f"ν12={self.nu12:.3f}, ν23={self.nu23:.3f}, G12={self.G12:.2e})"
        )
