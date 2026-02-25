"""통합 도메인 정의.

Method enum과 create_domain() 팩토리로 FEM/PD/SPG 도메인을 동일 API로 생성한다.
"""

import enum
import numpy as np
from typing import Tuple, Optional, List, Union


class Method(enum.Enum):
    """해석 방법 열거형."""
    FEM = "fem"
    PD = "pd"
    SPG = "spg"
    RIGID = "rigid"


class Domain:
    """통합 도메인.

    내부적으로 각 솔버의 메쉬/입자 시스템을 래핑한다.
    경계조건(고정, 힘)을 통합 API로 설정할 수 있다.

    Attributes:
        method: 해석 방법
        dim: 공간 차원
        origin: 도메인 원점
        size: 도메인 크기
        n_divisions: 각 방향 분할 수
    """

    def __init__(
        self,
        method: Method,
        dim: int,
        origin: Tuple[float, ...],
        size: Tuple[float, ...],
        n_divisions: Tuple[int, ...],
        **kwargs,
    ):
        self.method = method
        self.dim = dim
        self.origin = origin
        self.size = size
        self.n_divisions = n_divisions
        self._kwargs = kwargs

        # 경계조건 저장
        self._fixed_indices: Optional[np.ndarray] = None
        self._fixed_values: Optional[np.ndarray] = None
        self._force_indices: Optional[np.ndarray] = None
        self._force_values: Optional[np.ndarray] = None

        # 어댑터가 설정하는 내부 객체
        self._adapter = None
        self._positions: Optional[np.ndarray] = None

    def select(
        self,
        axis: int,
        value: float,
        tol: Optional[float] = None,
    ) -> np.ndarray:
        """위치 기반 노드/입자 인덱스 선택.

        Args:
            axis: 좌표축 (0=x, 1=y, 2=z)
            value: 선택할 좌표값
            tol: 허용 오차 (None이면 자동 계산)

        Returns:
            선택된 인덱스 배열
        """
        positions = self.get_positions()
        if tol is None:
            # 해당 축 최소 간격의 절반
            coords = positions[:, axis]
            unique_sorted = np.unique(np.round(coords, decimals=10))
            if len(unique_sorted) > 1:
                tol = np.min(np.diff(unique_sorted)) * 0.5
            else:
                tol = 1e-6

        return np.where(np.abs(positions[:, axis] - value) < tol)[0]

    def set_fixed(
        self,
        indices: np.ndarray,
        values: Optional[np.ndarray] = None,
    ):
        """Dirichlet 경계조건 설정 (고정).

        Args:
            indices: 고정할 노드/입자 인덱스
            values: 고정 변위값 (None이면 0)
        """
        self._fixed_indices = np.asarray(indices, dtype=np.int64)
        self._fixed_values = values

    def set_force(
        self,
        indices: np.ndarray,
        forces: Union[List[float], np.ndarray],
    ):
        """Neumann 경계조건 설정 (외부력).

        Args:
            indices: 힘을 적용할 노드/입자 인덱스
            forces: 노드/입자당 힘 벡터 [fx, fy] 또는 [fx, fy, fz]
        """
        self._force_indices = np.asarray(indices, dtype=np.int64)
        forces = np.asarray(forces, dtype=np.float64)
        if forces.ndim == 1:
            # 스칼라 벡터 → 모든 노드에 동일 적용
            self._force_values = forces
        else:
            self._force_values = forces

    def get_positions(self) -> np.ndarray:
        """참조 좌표 반환.

        _custom_positions 가 설정된 경우 이를 우선 반환한다.
        (복셀 기반 PD/SPG 파이프라인에서 실제 입자 좌표를 select() 등에서 사용)
        """
        custom = getattr(self, "_custom_positions", None)
        if custom is not None:
            return custom
        if self._positions is not None:
            return self._positions
        raise RuntimeError("도메인이 아직 초기화되지 않음")

    def select_boundary(self, tol: Optional[float] = None) -> np.ndarray:
        """도메인 외곽 노드/입자 인덱스 자동 감지.

        각 축의 min/max 좌표에 위치한 노드/입자를 경계로 판단한다.

        Args:
            tol: 허용 오차 (None이면 자동 계산)

        Returns:
            경계 인덱스 배열
        """
        positions = self.get_positions()
        boundary = set()
        for ax in range(self.dim):
            coords = positions[:, ax]
            min_val, max_val = coords.min(), coords.max()
            if tol is None:
                unique_sorted = np.unique(np.round(coords, decimals=10))
                if len(unique_sorted) > 1:
                    ax_tol = np.min(np.diff(unique_sorted)) * 0.5
                else:
                    ax_tol = 1e-6
            else:
                ax_tol = tol
            boundary.update(np.where(np.abs(coords - min_val) < ax_tol)[0])
            boundary.update(np.where(np.abs(coords - max_val) < ax_tol)[0])
        return np.array(sorted(boundary), dtype=np.int64)

    @property
    def n_points(self) -> int:
        """노드/입자 수."""
        return len(self.get_positions())


def create_domain(
    method: Method,
    dim: int,
    origin: Tuple[float, ...],
    size: Tuple[float, ...],
    n_divisions: Tuple[int, ...],
    **kwargs,
) -> Domain:
    """도메인 팩토리.

    Args:
        method: 해석 방법 (FEM, PD, SPG)
        dim: 공간 차원
        origin: 도메인 원점
        size: 도메인 크기
        n_divisions: 각 방향 분할 수
        **kwargs: 추가 매개변수
            - horizon_factor: PD/SPG horizon 배수 (기본 3.015 / 2.5)
            - support_factor: SPG 지지 반경 배수 (기본 2.5)

    Returns:
        Domain 객체 (내부 메쉬/입자는 Solver 연결 시 생성)
    """
    domain = Domain(method, dim, origin, size, n_divisions, **kwargs)

    # 노드/입자 좌표 사전 생성 (select 등에서 필요)
    if method == Method.FEM:
        domain._positions = _create_fem_positions(dim, origin, size, n_divisions)
    else:
        domain._positions = _create_particle_positions(dim, origin, size, n_divisions)

    return domain


def _create_fem_positions(
    dim: int,
    origin: Tuple[float, ...],
    size: Tuple[float, ...],
    n_divisions: Tuple[int, ...],
) -> np.ndarray:
    """FEM 노드 좌표 생성."""
    if dim == 2:
        nx, ny = n_divisions
        dx, dy = size[0] / nx, size[1] / ny
        ox, oy = origin
        nodes = []
        for j in range(ny + 1):
            for i in range(nx + 1):
                nodes.append([ox + i * dx, oy + j * dy])
        return np.array(nodes, dtype=np.float64)
    else:
        nx, ny, nz = n_divisions
        dx, dy, dz = size[0] / nx, size[1] / ny, size[2] / nz
        ox, oy, oz = origin
        nodes = []
        for k in range(nz + 1):
            for j in range(ny + 1):
                for i in range(nx + 1):
                    nodes.append([ox + i * dx, oy + j * dy, oz + k * dz])
        return np.array(nodes, dtype=np.float64)


def create_particle_domain(
    positions: np.ndarray,
    method: Method,
    **kwargs,
) -> Domain:
    """입자 좌표 배열로부터 PD/SPG 도메인을 직접 생성한다.

    복셀 기반 입자 좌표를 도메인에 등록하여 균등 그리드와의 좌표 불일치를 방지한다.
    내부적으로 create_domain → _custom_positions 설정 패턴을 캡슐화한다.

    사용 예::

        domain = create_particle_domain(voxel_positions, method=Method.PD)
        bottom = domain.select(axis=2, value=positions.min(axis=0)[2])
        domain.set_fixed(bottom)

    Args:
        positions: 입자 좌표 (n_particles, dim)
        method: 해석 방법 (Method.PD 또는 Method.SPG)
        **kwargs: 추가 옵션 (horizon_factor, support_factor 등)

    Returns:
        _custom_positions 가 설정된 Domain 객체.
        get_positions() / select() 가 실제 입자 좌표를 기준으로 동작한다.
    """
    positions = np.asarray(positions, dtype=np.float64)
    n_particles, dim = positions.shape

    # 바운딩 박스 계산
    pos_min = positions.min(axis=0)
    pos_max = positions.max(axis=0)
    domain_size = pos_max - pos_min

    # 최소 도메인 크기 보장 (단일 레이어 복셀 등 퇴화 케이스)
    for d in range(dim):
        if domain_size[d] < 1e-3:
            domain_size[d] = 1e-3

    origin = tuple(pos_min.tolist())
    size = tuple(domain_size.tolist())

    # 분할 수 추정 — 실제 입자 배치에는 사용 안 함 (horizon 계산 전용)
    n_per_axis = max(2, int(round(n_particles ** (1.0 / dim))))
    n_divisions = tuple([n_per_axis] * dim)

    domain = create_domain(
        method=method, dim=dim, origin=origin, size=size,
        n_divisions=n_divisions, **kwargs,
    )

    # 실제 복셀 좌표 등록 — 어댑터가 감지해 initialize_from_arrays 사용
    domain._custom_positions = positions.copy()

    return domain


def _create_particle_positions(
    dim: int,
    origin: Tuple[float, ...],
    size: Tuple[float, ...],
    n_divisions: Tuple[int, ...],
) -> np.ndarray:
    """PD/SPG 입자 좌표 생성 (격자 중심이 아닌 격자 노드 위치)."""
    if dim == 2:
        nx, ny = n_divisions
        spacing_x = size[0] / (nx - 1) if nx > 1 else size[0]
        spacing_y = size[1] / (ny - 1) if ny > 1 else size[1]
        ox, oy = origin
        particles = []
        for i in range(nx):
            for j in range(ny):
                particles.append([ox + i * spacing_x, oy + j * spacing_y])
        return np.array(particles, dtype=np.float64)
    else:
        nx, ny, nz = n_divisions
        spacing_x = size[0] / (nx - 1) if nx > 1 else size[0]
        spacing_y = size[1] / (ny - 1) if ny > 1 else size[1]
        spacing_z = size[2] / (nz - 1) if nz > 1 else size[2]
        ox, oy, oz = origin
        particles = []
        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    particles.append([
                        ox + i * spacing_x,
                        oy + j * spacing_y,
                        oz + k * spacing_z,
                    ])
        return np.array(particles, dtype=np.float64)
