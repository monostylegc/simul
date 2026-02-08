"""SPG 커널 함수 및 형상함수 구성.

RKPM (Reproducing Kernel Particle Method) 기반 형상함수:
- Cubic B-spline 커널 함수
- 1차 일관성 (linear consistency) 보정
- 형상함수 미분 계산

참고: Chen et al. (2001), Wu et al. (2013)
"""

import taichi as ti
import numpy as np
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .particles import SPGParticleSystem


@ti.data_oriented
class SPGKernel:
    """SPG 커널 및 형상함수 계산기.

    RKPM 기반 1차 일관성 형상함수를 구성한다.
    각 입자에 대해 이웃 입자들의 형상함수 값과 미분을 계산/저장한다.

    Attributes:
        dim: 공간 차원
        support_radius: 지지 반경 h
        n_particles: 입자 수
        max_neighbors: 입자당 최대 이웃 수
    """

    def __init__(
        self,
        n_particles: int,
        max_neighbors: int = 64,
        dim: int = 3,
        support_radius: float = 1.0
    ):
        """초기화.

        Args:
            n_particles: 입자 수
            max_neighbors: 입자당 최대 이웃 수
            dim: 공간 차원
            support_radius: 커널 지지 반경 h
        """
        self.n_particles = n_particles
        self.max_neighbors = max_neighbors
        self.dim = dim
        self.support_radius = support_radius

        # 이웃 목록
        self.neighbors = ti.field(dtype=ti.i32, shape=(n_particles, max_neighbors))
        self.n_neighbors = ti.field(dtype=ti.i32, shape=n_particles)

        # 형상함수 값 Ψ_J(X_I)
        self.psi = ti.field(dtype=ti.f64, shape=(n_particles, max_neighbors))

        # 형상함수 미분 ∇Ψ_J(X_I) (dim 성분)
        self.dpsi = ti.Vector.field(dim, dtype=ti.f64, shape=(n_particles, max_neighbors))

        # 지지 반경 필드
        self.h = ti.field(dtype=ti.f64, shape=())
        self.h[None] = support_radius

        # 정규화 상수
        if dim == 2:
            self.C_d = 10.0 / (7.0 * math.pi * support_radius**2)
        else:
            self.C_d = 1.0 / (math.pi * support_radius**3)

        self.C_d_field = ti.field(dtype=ti.f64, shape=())
        self.C_d_field[None] = self.C_d

    @ti.func
    def cubic_bspline(self, r: ti.f64) -> ti.f64:
        """Cubic B-spline 커널 함수.

        W(r) = C_d * { 1 - 6r² + 6r³       (0 ≤ r ≤ 0.5)
                     { 2(1 - r)³            (0.5 < r ≤ 1)
                     { 0                    (r > 1)

        Args:
            r: 정규화된 거리 (|x - x_I| / h)

        Returns:
            커널 값
        """
        val = 0.0
        if r <= 0.5:
            val = 1.0 - 6.0 * r * r + 6.0 * r * r * r
        elif r <= 1.0:
            val = 2.0 * (1.0 - r) * (1.0 - r) * (1.0 - r)
        return self.C_d_field[None] * val

    @ti.func
    def cubic_bspline_deriv(self, r: ti.f64) -> ti.f64:
        """Cubic B-spline 커널의 r에 대한 미분.

        dW/dr = C_d * { -12r + 18r²          (0 ≤ r ≤ 0.5)
                      { -6(1 - r)²            (0.5 < r ≤ 1)
                      { 0                     (r > 1)

        Args:
            r: 정규화된 거리

        Returns:
            커널 미분 값
        """
        val = 0.0
        if r <= 0.5:
            val = -12.0 * r + 18.0 * r * r
        elif r <= 1.0:
            val = -6.0 * (1.0 - r) * (1.0 - r)
        return self.C_d_field[None] * val

    def compute_shape_functions(
        self,
        X: ti.template(),
        volume: ti.template()
    ):
        """RKPM 기반 형상함수 및 미분 계산.

        1차 일관성 보정으로 선형 다항식을 정확히 재현한다.
        Ψ_I(X) = C(X) · p(X - X_I) · W(|X - X_I|/h) · V_I

        여기서 C(X)는 보정 함수, p(x)는 기저 벡터 [1, x, y, (z)].
        계산 후 기울기 보정(gradient correction)을 적용하여
        미분 재현 조건 Σ_J ∇Ψ_J(X_I) ⊗ ξ_J = I 를 정확히 만족시킨다.

        Args:
            X: 입자 기준 좌표 필드
            volume: 입자 부피 필드
        """
        if self.dim == 2:
            self._compute_shape_functions_2d(X, volume)
            self._correct_gradients_2d(X)
        else:
            self._compute_shape_functions_3d(X, volume)
            self._correct_gradients_3d(X)

    @ti.kernel
    def _compute_shape_functions_2d(
        self,
        X: ti.template(),
        volume: ti.template()
    ):
        """2D 형상함수 계산."""
        h = self.h[None]

        for i in range(self.n_particles):
            # 모멘트 행렬 (3×3): 기저 [1, dx/h, dy/h]
            M = ti.Matrix.zero(ti.f64, 3, 3)

            n_nbr = self.n_neighbors[i]
            for k in range(n_nbr):
                j = self.neighbors[i, k]
                dx = X[j] - X[i]
                dist = dx.norm()
                r = dist / h

                w = self.cubic_bspline(r)
                w_v = w * volume[j]

                p = ti.Vector([1.0, dx[0] / h, dx[1] / h])

                for m in ti.static(range(3)):
                    for n in ti.static(range(3)):
                        M[m, n] += p[m] * p[n] * w_v

            # 역행렬
            det_M = M.determinant()
            M_inv = ti.Matrix.zero(ti.f64, 3, 3)
            if ti.abs(det_M) > 1e-30:
                M_inv = M.inverse()
            else:
                M_inv[0, 0] = 1.0
                M_inv[1, 1] = 1.0
                M_inv[2, 2] = 1.0

            # 형상함수 및 미분
            for k in range(n_nbr):
                j = self.neighbors[i, k]
                dx = X[j] - X[i]
                dist = dx.norm()
                r = dist / h

                w = self.cubic_bspline(r)
                dw_dr = self.cubic_bspline_deriv(r)

                p = ti.Vector([1.0, dx[0] / h, dx[1] / h])

                # cp = M_inv[0,:] · p
                cp = M_inv[0, 0] * p[0] + M_inv[0, 1] * p[1] + M_inv[0, 2] * p[2]

                self.psi[i, k] = cp * w * volume[j]

                # 형상함수 미분
                grad_psi = ti.Vector.zero(ti.f64, 2)
                if dist > 1e-15:
                    # ∂w/∂X_I (부호 반전)
                    grad_w = ti.Vector([
                        dw_dr * (-dx[0]) / (dist * h),
                        dw_dr * (-dx[1]) / (dist * h)
                    ])

                    # ∂(cp)/∂X_I
                    grad_cp = ti.Vector([
                        M_inv[0, 1] * (-1.0 / h),
                        M_inv[0, 2] * (-1.0 / h)
                    ])

                    # 곱의 미분
                    for d in ti.static(range(2)):
                        grad_psi[d] = (grad_cp[d] * w + cp * grad_w[d]) * volume[j]

                self.dpsi[i, k] = grad_psi

    @ti.kernel
    def _compute_shape_functions_3d(
        self,
        X: ti.template(),
        volume: ti.template()
    ):
        """3D 형상함수 계산."""
        h = self.h[None]

        for i in range(self.n_particles):
            # 모멘트 행렬 (4×4): 기저 [1, dx/h, dy/h, dz/h]
            M = ti.Matrix.zero(ti.f64, 4, 4)

            n_nbr = self.n_neighbors[i]
            for k in range(n_nbr):
                j = self.neighbors[i, k]
                dx = X[j] - X[i]
                dist = dx.norm()
                r = dist / h

                w = self.cubic_bspline(r)
                w_v = w * volume[j]

                p = ti.Vector([1.0, dx[0] / h, dx[1] / h, dx[2] / h])

                for m in ti.static(range(4)):
                    for n in ti.static(range(4)):
                        M[m, n] += p[m] * p[n] * w_v

            # 역행렬
            det_M = M.determinant()
            M_inv = ti.Matrix.zero(ti.f64, 4, 4)
            if ti.abs(det_M) > 1e-30:
                M_inv = M.inverse()
            else:
                M_inv[0, 0] = 1.0
                M_inv[1, 1] = 1.0
                M_inv[2, 2] = 1.0
                M_inv[3, 3] = 1.0

            # 형상함수 및 미분
            for k in range(n_nbr):
                j = self.neighbors[i, k]
                dx = X[j] - X[i]
                dist = dx.norm()
                r = dist / h

                w = self.cubic_bspline(r)
                dw_dr = self.cubic_bspline_deriv(r)

                p = ti.Vector([1.0, dx[0] / h, dx[1] / h, dx[2] / h])

                # cp = M_inv[0,:] · p
                cp = (M_inv[0, 0] * p[0] + M_inv[0, 1] * p[1] +
                      M_inv[0, 2] * p[2] + M_inv[0, 3] * p[3])

                self.psi[i, k] = cp * w * volume[j]

                # 형상함수 미분
                grad_psi = ti.Vector.zero(ti.f64, 3)
                if dist > 1e-15:
                    grad_w = ti.Vector([
                        dw_dr * (-dx[0]) / (dist * h),
                        dw_dr * (-dx[1]) / (dist * h),
                        dw_dr * (-dx[2]) / (dist * h)
                    ])

                    grad_cp = ti.Vector([
                        M_inv[0, 1] * (-1.0 / h),
                        M_inv[0, 2] * (-1.0 / h),
                        M_inv[0, 3] * (-1.0 / h)
                    ])

                    for d in ti.static(range(3)):
                        grad_psi[d] = (grad_cp[d] * w + cp * grad_w[d]) * volume[j]

                self.dpsi[i, k] = grad_psi

    @ti.kernel
    def _correct_gradients_2d(self, X: ti.template()):
        """2D 형상함수 기울기 보정 (미분 재현 조건 강제).

        보정 행렬 A = Σ_k ∇Ψ_k ⊗ ξ_k 를 구성하고,
        A^{-1} · ∇Ψ_k 로 대체하여 Σ ∇Ψ_k ⊗ ξ_k = I 를 강제한다.
        """
        for i in range(self.n_particles):
            # A = Σ_k dpsi[i,k] ⊗ ξ_k (이상적으로 단위 행렬)
            A = ti.Matrix.zero(ti.f64, 2, 2)
            n_nbr = self.n_neighbors[i]
            for k in range(n_nbr):
                j = self.neighbors[i, k]
                xi = X[j] - X[i]
                dpsi_k = self.dpsi[i, k]
                for m in ti.static(range(2)):
                    for n in ti.static(range(2)):
                        A[m, n] += dpsi_k[m] * xi[n]

            # A^{-1} 계산 및 기울기 보정
            det_A = A.determinant()
            if ti.abs(det_A) > 1e-30:
                A_inv = A.inverse()
                for k in range(n_nbr):
                    dpsi_k = self.dpsi[i, k]
                    corrected = A_inv @ dpsi_k
                    self.dpsi[i, k] = corrected

    @ti.kernel
    def _correct_gradients_3d(self, X: ti.template()):
        """3D 형상함수 기울기 보정 (미분 재현 조건 강제).

        보정 행렬 A = Σ_k ∇Ψ_k ⊗ ξ_k 를 구성하고,
        A^{-1} · ∇Ψ_k 로 대체하여 Σ ∇Ψ_k ⊗ ξ_k = I 를 강제한다.
        """
        for i in range(self.n_particles):
            A = ti.Matrix.zero(ti.f64, 3, 3)
            n_nbr = self.n_neighbors[i]
            for k in range(n_nbr):
                j = self.neighbors[i, k]
                xi = X[j] - X[i]
                dpsi_k = self.dpsi[i, k]
                for m in ti.static(range(3)):
                    for n in ti.static(range(3)):
                        A[m, n] += dpsi_k[m] * xi[n]

            det_A = A.determinant()
            if ti.abs(det_A) > 1e-30:
                A_inv = A.inverse()
                for k in range(n_nbr):
                    dpsi_k = self.dpsi[i, k]
                    corrected = A_inv @ dpsi_k
                    self.dpsi[i, k] = corrected

    def build_neighbor_list(
        self,
        positions: np.ndarray,
        support_radius: float
    ):
        """이웃 목록 구축 (CPU 버전).

        Args:
            positions: 입자 좌표 (n_particles, dim)
            support_radius: 지지 반경
        """
        from scipy.spatial import KDTree

        tree = KDTree(positions)
        pairs = tree.query_ball_tree(tree, support_radius)

        neighbors_np = np.zeros((self.n_particles, self.max_neighbors), dtype=np.int32)
        n_neighbors_np = np.zeros(self.n_particles, dtype=np.int32)

        for i, nbr_list in enumerate(pairs):
            # 자기 자신 제외
            nbrs = [j for j in nbr_list if j != i]
            n = min(len(nbrs), self.max_neighbors)
            n_neighbors_np[i] = n
            for k in range(n):
                neighbors_np[i, k] = nbrs[k]

        self.neighbors.from_numpy(neighbors_np)
        self.n_neighbors.from_numpy(n_neighbors_np)

    def get_shape_function_sum(self) -> np.ndarray:
        """형상함수 합 검증 (partition of unity 확인).

        Returns:
            각 입자에서의 형상함수 합 (이상적으로 1.0)
        """
        psi_np = self.psi.to_numpy()
        n_nbr = self.n_neighbors.to_numpy()
        sums = np.zeros(self.n_particles)
        for i in range(self.n_particles):
            sums[i] = np.sum(psi_np[i, :n_nbr[i]])
        return sums
