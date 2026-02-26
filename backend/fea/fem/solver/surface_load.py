"""표면 하중 계산 모듈.

요소 면에 작용하는 압력/분포 하중을 등가 절점력으로 변환한다.

지원:
- 3D: 삼각형 면 (TET4), 사각형 면 (HEX8) 압력
- 2D: 선분 변 (TRI3, QUAD4) 압력
- 균일 압력 및 노드별 가변 압력

참고: 압력은 면 외향 법선의 **반대** 방향으로 작용한다.
      양수 압력 = 압축 (면 안쪽으로).
"""

import numpy as np
from typing import List, Tuple, Optional, Union

from ..core.element import (
    ElementType,
    get_element_info,
    get_face_nodes,
    ELEMENT_FACES,
)
from ..core.mesh import FEMesh


# ============================================================================
# 표면 Gauss 적분 규칙
# ============================================================================

def _gauss_line_2pt():
    """2점 선분 적분 규칙 (ξ ∈ [-1, 1]).

    Returns:
        points: (2,) 적분점 좌표
        weights: (2,) 가중치
    """
    gp = 1.0 / np.sqrt(3.0)
    return np.array([-gp, +gp]), np.array([1.0, 1.0])


def _gauss_tri_1pt():
    """1점 삼각형 적분 규칙 (면적 좌표).

    Returns:
        points: (1, 2) 적분점 좌표 (ξ, η)
        weights: (1,) 가중치 (참조 삼각형 면적 0.5 포함)
    """
    return np.array([[1.0 / 3.0, 1.0 / 3.0]]), np.array([0.5])


def _gauss_tri_3pt():
    """3점 삼각형 적분 규칙 (면적 좌표).

    Returns:
        points: (3, 2) 적분점 좌표 (ξ, η)
        weights: (3,) 가중치
    """
    points = np.array([
        [1.0 / 6.0, 1.0 / 6.0],
        [2.0 / 3.0, 1.0 / 6.0],
        [1.0 / 6.0, 2.0 / 3.0],
    ])
    weights = np.array([1.0 / 6.0, 1.0 / 6.0, 1.0 / 6.0])
    return points, weights


def _gauss_quad_2x2():
    """2×2 사각형 적분 규칙 (ξ, η ∈ [-1, 1]).

    Returns:
        points: (4, 2) 적분점 좌표
        weights: (4,) 가중치
    """
    gp = 1.0 / np.sqrt(3.0)
    points = np.array([
        [-gp, -gp],
        [+gp, -gp],
        [+gp, +gp],
        [-gp, +gp],
    ])
    weights = np.ones(4)
    return points, weights


# ============================================================================
# 면 형상함수
# ============================================================================

def _shape_line(xi: float) -> np.ndarray:
    """2노드 선분 형상함수.

    Args:
        xi: 자연 좌표 (-1 ~ +1)

    Returns:
        형상함수 값 (2,)
    """
    return np.array([0.5 * (1 - xi), 0.5 * (1 + xi)])


def _shape_tri(xi: float, eta: float) -> np.ndarray:
    """3노드 삼각형 형상함수 (면적 좌표).

    Args:
        xi, eta: 자연 좌표 (0 ~ 1, ξ+η ≤ 1)

    Returns:
        형상함수 값 (3,)
    """
    return np.array([1 - xi - eta, xi, eta])


def _shape_quad(xi: float, eta: float) -> np.ndarray:
    """4노드 사각형 형상함수.

    Args:
        xi, eta: 자연 좌표 (-1 ~ +1)

    Returns:
        형상함수 값 (4,)
    """
    return np.array([
        0.25 * (1 - xi) * (1 - eta),
        0.25 * (1 + xi) * (1 - eta),
        0.25 * (1 + xi) * (1 + eta),
        0.25 * (1 - xi) * (1 + eta),
    ])


# ============================================================================
# 면 법선/야코비안 계산
# ============================================================================

def _compute_line_normal_and_det(
    face_coords: np.ndarray,
    xi: float,
) -> Tuple[np.ndarray, float]:
    """2D 선분의 외향 법선과 야코비안 결정자.

    선분의 접선을 90° 회전 → 외향 법선.

    Args:
        face_coords: 면 노드 좌표 (2, 2)
        xi: 자연 좌표

    Returns:
        normal: 단위 외향 법선 (2,)
        det_J: 야코비안 결정자 (= 선분 길이 / 2)
    """
    # 접선 벡터: dx/dξ
    tangent = 0.5 * (face_coords[1] - face_coords[0])
    length = np.linalg.norm(tangent)

    if length < 1e-15:
        return np.zeros(2), 0.0

    # 90° 시계방향 회전 → 외향 (반시계 노드 순서 가정)
    normal = np.array([tangent[1], -tangent[0]]) / length

    return normal, length


def _compute_tri_normal_and_det(
    face_coords: np.ndarray,
    xi: float,
    eta: float,
) -> Tuple[np.ndarray, float]:
    """3D 삼각형 면의 외향 법선과 야코비안 결정자.

    Args:
        face_coords: 면 노드 좌표 (3, 3)
        xi, eta: 자연 좌표

    Returns:
        normal: 단위 외향 법선 (3,)
        det_J: 야코비안 결정자 (면적 적분 변환)
    """
    # 접선 벡터
    # dx/dξ = x1 - x0
    # dx/dη = x2 - x0
    dxdxi = face_coords[1] - face_coords[0]
    dxdeta = face_coords[2] - face_coords[0]

    # 외적 → 법선 (크기 = 면적 변환 인자)
    cross = np.cross(dxdxi, dxdeta)
    det_J = np.linalg.norm(cross)

    if det_J < 1e-15:
        return np.zeros(3), 0.0

    normal = cross / det_J

    return normal, det_J


def _compute_quad_normal_and_det(
    face_coords: np.ndarray,
    xi: float,
    eta: float,
) -> Tuple[np.ndarray, float]:
    """3D 사각형 면의 외향 법선과 야코비안 결정자.

    Args:
        face_coords: 면 노드 좌표 (4, 3)
        xi, eta: 자연 좌표

    Returns:
        normal: 단위 외향 법선 (3,)
        det_J: 야코비안 결정자
    """
    # 형상함수 미분
    # dN/dξ = [ -(1-η), (1-η), (1+η), -(1+η) ] / 4
    # dN/dη = [ -(1-ξ), -(1+ξ), (1+ξ), (1-ξ) ] / 4
    dNdxi = np.array([
        -(1 - eta), (1 - eta), (1 + eta), -(1 + eta),
    ]) / 4.0
    dNdeta = np.array([
        -(1 - xi), -(1 + xi), (1 + xi), (1 - xi),
    ]) / 4.0

    # 접선 벡터
    dxdxi = dNdxi @ face_coords    # (3,)
    dxdeta = dNdeta @ face_coords   # (3,)

    # 외적 → 법선
    cross = np.cross(dxdxi, dxdeta)
    det_J = np.linalg.norm(cross)

    if det_J < 1e-15:
        return np.zeros(3), 0.0

    normal = cross / det_J

    return normal, det_J


# ============================================================================
# 메인 API
# ============================================================================

def compute_pressure_load(
    mesh: FEMesh,
    face_elements: np.ndarray,
    face_ids: np.ndarray,
    pressure: Union[float, np.ndarray],
) -> np.ndarray:
    """요소 면에 작용하는 압력을 등가 절점력으로 변환.

    양수 압력 = 면 안쪽 방향 (압축).

    f_i = -p · N_i · n · |J_s| · w

    Args:
        mesh: FEMesh 객체
        face_elements: 압력이 작용하는 요소 인덱스 (n_faces,)
        face_ids: 각 요소에서의 면 번호 (n_faces,)
        pressure: 균일 압력 (float) 또는 면별 압력 (n_faces,)

    Returns:
        등가 절점력 (n_nodes, dim)
    """
    face_elements = np.asarray(face_elements, dtype=np.int64)
    face_ids = np.asarray(face_ids, dtype=np.int64)

    n_faces = len(face_elements)
    if n_faces == 0:
        return np.zeros((mesh.n_nodes, mesh.dim), dtype=np.float64)

    # 압력 배열 처리
    if np.isscalar(pressure):
        p_arr = np.full(n_faces, float(pressure))
    else:
        p_arr = np.asarray(pressure, dtype=np.float64)
        assert len(p_arr) == n_faces

    # 면 노드 정의
    face_defs = get_face_nodes(mesh.element_type)
    dim = mesh.dim

    # 노드 좌표
    X = mesh.X.to_numpy()  # (n_nodes, dim)
    elements = mesh.elements.to_numpy()  # (n_elements, npe)

    # 결과 배열
    f_pressure = np.zeros((mesh.n_nodes, dim), dtype=np.float64)

    for fi in range(n_faces):
        elem_idx = face_elements[fi]
        face_id = face_ids[fi]
        p = p_arr[fi]

        # 면의 로컬 노드 인덱스
        local_nodes = face_defs[face_id]
        n_face_nodes = len(local_nodes)

        # 면의 글로벌 노드 인덱스
        elem_conn = elements[elem_idx]
        global_nodes = [elem_conn[ln] for ln in local_nodes]

        # 면 좌표
        face_coords = np.array([X[gn] for gn in global_nodes])

        if dim == 2:
            # 2D: 선분 면
            _integrate_line_pressure(
                face_coords, global_nodes, p, f_pressure
            )
        elif n_face_nodes == 3:
            # 3D 삼각형 면
            _integrate_tri_pressure(
                face_coords, global_nodes, p, f_pressure
            )
        elif n_face_nodes == 4:
            # 3D 사각형 면
            _integrate_quad_pressure(
                face_coords, global_nodes, p, f_pressure
            )

    return f_pressure


def _integrate_line_pressure(
    face_coords: np.ndarray,
    global_nodes: list,
    pressure: float,
    f_out: np.ndarray,
):
    """2D 선분 압력 적분.

    f_i = -p · N_i · n · |J| · w
    """
    points, weights = _gauss_line_2pt()

    for gp, w in zip(points, weights):
        N = _shape_line(gp)
        normal, det_J = _compute_line_normal_and_det(face_coords, gp)

        for a, gn in enumerate(global_nodes):
            # 양수 압력 = 안쪽 → 법선 반대
            f_out[gn] -= pressure * N[a] * normal * det_J * w


def _integrate_tri_pressure(
    face_coords: np.ndarray,
    global_nodes: list,
    pressure: float,
    f_out: np.ndarray,
):
    """3D 삼각형 면 압력 적분.

    1점 규칙 사용 (선형 요소에 정확).
    """
    points, weights = _gauss_tri_1pt()

    for gp, w in zip(points, weights):
        xi, eta = gp
        N = _shape_tri(xi, eta)
        normal, det_J = _compute_tri_normal_and_det(face_coords, xi, eta)

        for a, gn in enumerate(global_nodes):
            f_out[gn] -= pressure * N[a] * normal * det_J * w


def _integrate_quad_pressure(
    face_coords: np.ndarray,
    global_nodes: list,
    pressure: float,
    f_out: np.ndarray,
):
    """3D 사각형 면 압력 적분.

    2×2 규칙 사용.
    """
    points, weights = _gauss_quad_2x2()

    for gp, w in zip(points, weights):
        xi, eta = gp
        N = _shape_quad(xi, eta)
        normal, det_J = _compute_quad_normal_and_det(face_coords, xi, eta)

        for a, gn in enumerate(global_nodes):
            f_out[gn] -= pressure * N[a] * normal * det_J * w


def find_surface_faces(
    mesh: FEMesh,
    axis: int,
    value: float,
    tol: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """좌표면에 위치한 요소 면 자동 검색.

    지정된 좌표값에 모든 노드가 위치한 면을 찾는다.

    Args:
        mesh: FEMesh 객체
        axis: 좌표축 (0=x, 1=y, 2=z)
        value: 검색할 좌표값
        tol: 허용 오차 (None이면 자동 계산)

    Returns:
        face_elements: 요소 인덱스 (n_found,)
        face_ids: 면 번호 (n_found,)
    """
    if mesh.element_type not in ELEMENT_FACES:
        raise ValueError(f"면 검색 미지원 요소: {mesh.element_type}")

    face_defs = ELEMENT_FACES[mesh.element_type]
    X = mesh.X.to_numpy()
    elements = mesh.elements.to_numpy()

    # 자동 허용 오차 계산
    if tol is None:
        coords = X[:, axis]
        unique_sorted = np.unique(np.round(coords, decimals=10))
        if len(unique_sorted) > 1:
            tol = np.min(np.diff(unique_sorted)) * 0.5
        else:
            tol = 1e-6

    # 좌표면 위의 노드 찾기
    on_surface = np.abs(X[:, axis] - value) < tol

    face_elements_list = []
    face_ids_list = []

    for e in range(mesh.n_elements):
        for fi, local_nodes in enumerate(face_defs):
            # 면의 모든 노드가 좌표면 위에 있는지 확인
            global_nodes = [elements[e][ln] for ln in local_nodes]
            if all(on_surface[gn] for gn in global_nodes):
                face_elements_list.append(e)
                face_ids_list.append(fi)

    return (
        np.array(face_elements_list, dtype=np.int64),
        np.array(face_ids_list, dtype=np.int64),
    )
