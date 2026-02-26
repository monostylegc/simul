"""SPG 본드 시스템 - 입자 연결 및 파괴 관리.

SPG에서 본드는 형상함수의 영향 영역 내 입자 연결을 나타낸다.
본드 파괴 시 해당 이웃을 형상함수 계산에서 제외하여
자연스러운 균열 전파와 파편화를 구현한다.
"""

import taichi as ti
import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .particles import SPGParticleSystem
    from .kernel import SPGKernel


@ti.data_oriented
class SPGBondSystem:
    """SPG 본드 시스템.

    Attributes:
        n_particles: 입자 수
        max_bonds: 입자당 최대 본드 수
        broken: 본드 파괴 플래그 (0=건전, 1=파괴)
        xi: 기준 본드 벡터
        xi_length: 기준 본드 길이
        initial_bonds: 초기 본드 수 (손상 계산용)
    """

    @classmethod
    def from_neighbor_counts(
        cls,
        n_particles: int,
        counts: np.ndarray,
        dim: int = 3,
        margin: int = 8
    ) -> "SPGBondSystem":
        """이웃 수 사전 카운트로부터 적응적 할당.

        max_bonds = max(counts) + margin 으로 자동 설정하여
        메모리 낭비를 줄이면서 3D에서도 안전한 할당을 보장한다.

        Args:
            n_particles: 입자 수
            counts: 각 입자의 이웃 수 (n_particles,)
            dim: 공간 차원
            margin: 안전 여유분

        Returns:
            적응적으로 할당된 SPGBondSystem
        """
        max_bonds = int(np.max(counts)) + margin
        return cls(n_particles, max_bonds=max_bonds, dim=dim)

    def __init__(self, n_particles: int, max_bonds: int = 64, dim: int = 3):
        """초기화.

        Args:
            n_particles: 입자 수
            max_bonds: 입자당 최대 본드 수
            dim: 공간 차원
        """
        self.n_particles = n_particles
        self.max_bonds = max_bonds
        self.dim = dim

        # 본드 상태
        self.broken = ti.field(dtype=ti.i32, shape=(n_particles, max_bonds))

        # 기준 본드 벡터
        self.xi = ti.Vector.field(dim, dtype=ti.f64, shape=(n_particles, max_bonds))
        self.xi_length = ti.field(dtype=ti.f64, shape=(n_particles, max_bonds))

        # 초기 본드 수 (손상 지수 계산용)
        self.initial_bonds = ti.field(dtype=ti.i32, shape=n_particles)

    def build_from_kernel(self, particles: "SPGParticleSystem", kernel: "SPGKernel"):
        """커널의 이웃 목록으로부터 본드 구축.

        Args:
            particles: SPG 입자 시스템
            kernel: SPG 커널 (이웃 목록 포함)
        """
        self._compute_bond_data(particles.X, kernel.neighbors, kernel.n_neighbors)

    @ti.kernel
    def _compute_bond_data(
        self,
        X: ti.template(),
        neighbors: ti.template(),
        n_neighbors: ti.template()
    ):
        """기준 본드 벡터 및 길이 계산."""
        for i in range(self.n_particles):
            n = n_neighbors[i]
            self.initial_bonds[i] = n
            for k in range(n):
                j = neighbors[i, k]
                xi = X[j] - X[i]
                self.xi[i, k] = xi
                self.xi_length[i, k] = xi.norm()
                self.broken[i, k] = 0

    @ti.kernel
    def check_bond_failure_stretch(
        self,
        x: ti.template(),
        neighbors: ti.template(),
        n_neighbors: ti.template(),
        critical_stretch: ti.f64
    ) -> ti.i32:
        """본드 신장 기반 파괴 검사.

        s = (|η| - |ξ|) / |ξ| > s_crit 이면 파괴.

        Args:
            x: 현재 좌표 필드
            neighbors: 이웃 인덱스
            n_neighbors: 이웃 수
            critical_stretch: 임계 신장

        Returns:
            새로 파괴된 본드 수
        """
        new_broken = 0
        for i in range(self.n_particles):
            for k in range(n_neighbors[i]):
                if self.broken[i, k] == 0:
                    j = neighbors[i, k]
                    eta = x[j] - x[i]
                    eta_len = eta.norm()
                    xi_len = self.xi_length[i, k]

                    if xi_len > 1e-15:
                        stretch = (eta_len - xi_len) / xi_len
                        if stretch > critical_stretch:
                            self.broken[i, k] = 1
                            new_broken += 1
        return new_broken

    @ti.kernel
    def check_bond_failure_plastic_strain(
        self,
        eff_plastic_strain: ti.template(),
        neighbors: ti.template(),
        n_neighbors: ti.template(),
        critical_strain: ti.f64
    ) -> ti.i32:
        """유효 소성 변형률 기반 파괴 검사.

        ε_p^eff = 0.5 * (ε_p(I) + ε_p(J)) > ε_p^crit 이면 파괴.

        Args:
            eff_plastic_strain: 유효 소성 변형률 필드
            neighbors: 이웃 인덱스
            n_neighbors: 이웃 수
            critical_strain: 임계 소성 변형률

        Returns:
            새로 파괴된 본드 수
        """
        new_broken = 0
        for i in range(self.n_particles):
            for k in range(n_neighbors[i]):
                if self.broken[i, k] == 0:
                    j = neighbors[i, k]
                    avg_strain = 0.5 * (
                        eff_plastic_strain[i] + eff_plastic_strain[j]
                    )
                    if avg_strain > critical_strain:
                        self.broken[i, k] = 1
                        new_broken += 1
        return new_broken

    @ti.kernel
    def compute_damage(
        self,
        damage: ti.template(),
        n_neighbors: ti.template()
    ):
        """본드 파괴 비율로 손상도 계산.

        damage = (파괴 본드 수) / (초기 본드 수)

        Args:
            damage: 손상도 필드 (출력)
            n_neighbors: 이웃 수
        """
        for i in range(self.n_particles):
            if self.initial_bonds[i] > 0:
                broken_count = 0
                for k in range(n_neighbors[i]):
                    if self.broken[i, k] == 1:
                        broken_count += 1
                damage[i] = ti.cast(broken_count, ti.f64) / ti.cast(
                    self.initial_bonds[i], ti.f64
                )
            else:
                damage[i] = 0.0

    @ti.kernel
    def count_intact_bonds(self, n_neighbors: ti.template()) -> ti.i32:
        """건전 본드 수 집계."""
        count = 0
        for i in range(self.n_particles):
            for k in range(n_neighbors[i]):
                if self.broken[i, k] == 0:
                    count += 1
        return count
