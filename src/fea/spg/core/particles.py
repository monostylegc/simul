"""SPG 입자 시스템 - Structure of Arrays (SoA) 레이아웃.

Peridynamics ParticleSystem과 유사하지만 SPG 고유의 필드를 포함한다:
- 형상함수 미분 (∇Ψ) 저장
- 스무딩된 변형률 필드
- 유효 소성 변형률 (파괴 기준용)
"""

import taichi as ti
import numpy as np
from typing import Optional


@ti.data_oriented
class SPGParticleSystem:
    """SPG 입자 시스템.

    Attributes:
        n_particles: 입자 수
        dim: 공간 차원 (2 또는 3)
        X: 기준 좌표 (reference)
        x: 현재 좌표 (current)
        u: 변위
        v: 속도
        a: 가속도
        f_int: 내부력
        f_ext: 외부력
        volume: 입자 부피
        volume_current: 현재 부피
        density: 밀도
        mass: 질량
        F: 변형 구배
        stress: Cauchy 응력
        strain: 스무딩된 변형률
        eff_plastic_strain: 유효 소성 변형률
        damage: 손상도 (0=완전, 1=파괴)
    """

    def __init__(self, n_particles: int, dim: int = 3):
        """초기화.

        Args:
            n_particles: 입자 수
            dim: 공간 차원
        """
        self.n_particles = n_particles
        self.dim = dim

        # 위치/속도/가속도
        self.X = ti.Vector.field(dim, dtype=ti.f64, shape=n_particles)
        self.x = ti.Vector.field(dim, dtype=ti.f64, shape=n_particles)
        self.u = ti.Vector.field(dim, dtype=ti.f64, shape=n_particles)
        self.v = ti.Vector.field(dim, dtype=ti.f64, shape=n_particles)
        self.a = ti.Vector.field(dim, dtype=ti.f64, shape=n_particles)

        # 내부/외부력
        self.f_int = ti.Vector.field(dim, dtype=ti.f64, shape=n_particles)
        self.f_ext = ti.Vector.field(dim, dtype=ti.f64, shape=n_particles)

        # 재료 특성
        self.volume = ti.field(dtype=ti.f64, shape=n_particles)
        self.volume_current = ti.field(dtype=ti.f64, shape=n_particles)
        self.density = ti.field(dtype=ti.f64, shape=n_particles)
        self.mass = ti.field(dtype=ti.f64, shape=n_particles)

        # 변형/응력 텐서
        self.F = ti.Matrix.field(dim, dim, dtype=ti.f64, shape=n_particles)
        self.stress = ti.Matrix.field(dim, dim, dtype=ti.f64, shape=n_particles)
        self.strain = ti.Matrix.field(dim, dim, dtype=ti.f64, shape=n_particles)

        # 소성/손상
        self.eff_plastic_strain = ti.field(dtype=ti.f64, shape=n_particles)
        self.damage = ti.field(dtype=ti.f64, shape=n_particles)

        # 경계조건
        self.fixed = ti.field(dtype=ti.i32, shape=n_particles)

    def initialize_from_grid(
        self,
        origin: tuple,
        spacing: float,
        n_points: tuple,
        density: float = 1000.0
    ):
        """격자로부터 입자 초기화.

        Args:
            origin: 격자 원점
            spacing: 격자 간격
            n_points: 각 방향 점 수
            density: 재료 밀도
        """
        positions = []
        if self.dim == 2:
            for i in range(n_points[0]):
                for j in range(n_points[1]):
                    positions.append((
                        origin[0] + i * spacing,
                        origin[1] + j * spacing
                    ))
        else:
            for i in range(n_points[0]):
                for j in range(n_points[1]):
                    for k in range(n_points[2]):
                        positions.append((
                            origin[0] + i * spacing,
                            origin[1] + j * spacing,
                            origin[2] + k * spacing
                        ))

        positions = np.array(positions, dtype=np.float64)
        if len(positions) != self.n_particles:
            raise ValueError(
                f"격자가 {len(positions)}개 입자를 생성하지만 "
                f"시스템은 {self.n_particles}개로 초기화됨"
            )

        volume = spacing ** self.dim
        volumes = np.full(self.n_particles, volume, dtype=np.float64)
        self._set_state(positions, volumes, density)

    def initialize_from_arrays(
        self,
        positions: np.ndarray,
        volumes: np.ndarray,
        density: float = 1000.0
    ):
        """배열로부터 입자 초기화.

        Args:
            positions: 입자 좌표 (n_particles, dim)
            volumes: 입자 부피 (n_particles,)
            density: 재료 밀도
        """
        self._set_state(positions, volumes, density)

    def _set_state(self, positions: np.ndarray, volumes: np.ndarray, density: float):
        """내부 상태 설정."""
        pos = positions.astype(np.float64)
        vol = volumes.astype(np.float64)

        self.X.from_numpy(pos)
        self.x.from_numpy(pos)
        self.volume.from_numpy(vol)
        self.volume_current.from_numpy(vol)

        densities = np.full(self.n_particles, density, dtype=np.float64)
        self.density.from_numpy(densities)

        masses = vol * density
        self.mass.from_numpy(masses)

        self._init_fields()

    @ti.kernel
    def _init_fields(self):
        """필드 초기화."""
        for i in range(self.n_particles):
            self.u[i] = ti.Vector.zero(ti.f64, self.dim)
            self.v[i] = ti.Vector.zero(ti.f64, self.dim)
            self.a[i] = ti.Vector.zero(ti.f64, self.dim)
            self.f_int[i] = ti.Vector.zero(ti.f64, self.dim)
            self.f_ext[i] = ti.Vector.zero(ti.f64, self.dim)
            self.F[i] = ti.Matrix.identity(ti.f64, self.dim)
            self.stress[i] = ti.Matrix.zero(ti.f64, self.dim, self.dim)
            self.strain[i] = ti.Matrix.zero(ti.f64, self.dim, self.dim)
            self.eff_plastic_strain[i] = 0.0
            self.damage[i] = 0.0
            self.fixed[i] = 0

    @ti.kernel
    def reset_forces(self):
        """내부/외부력 초기화."""
        for i in range(self.n_particles):
            self.f_int[i] = ti.Vector.zero(ti.f64, self.dim)

    @ti.kernel
    def update_positions(self):
        """변위로부터 현재 좌표 업데이트: x = X + u."""
        for i in range(self.n_particles):
            self.x[i] = self.X[i] + self.u[i]

    def set_fixed_particles(self, indices: np.ndarray):
        """고정 입자 설정 (Dirichlet BC).

        Args:
            indices: 고정할 입자 인덱스
        """
        fixed = np.zeros(self.n_particles, dtype=np.int32)
        fixed[indices] = 1
        self.fixed.from_numpy(fixed)

    def set_external_force(self, indices: np.ndarray, force: np.ndarray):
        """외부력 설정.

        Args:
            indices: 힘을 적용할 입자 인덱스
            force: 힘 벡터 (dim,)
        """
        f_ext = np.zeros((self.n_particles, self.dim), dtype=np.float64)
        for idx in indices:
            f_ext[idx] = force
        self.f_ext.from_numpy(f_ext)

    def get_positions(self) -> np.ndarray:
        return self.x.to_numpy()

    def get_displacements(self) -> np.ndarray:
        return self.u.to_numpy()

    def get_damage(self) -> np.ndarray:
        return self.damage.to_numpy()

    def get_stress(self) -> np.ndarray:
        return self.stress.to_numpy()
