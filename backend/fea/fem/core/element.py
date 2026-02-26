"""Finite element type definitions.

Supports 2D and 3D elements with linear and quadratic shape functions.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Tuple
import numpy as np


class ElementType(Enum):
    """Supported element types (Abaqus naming convention)."""
    # 2D triangular elements
    TRI3 = "CPS3"       # 3-node triangle, plane stress
    TRI3_PE = "CPE3"    # 3-node triangle, plane strain
    TRI6 = "CPS6"       # 6-node quadratic triangle
    TRI6_PE = "CPE6"    # 6-node quadratic triangle, plane strain

    # 2D quadrilateral elements
    QUAD4 = "CPS4"      # 4-node quad, plane stress
    QUAD4_PE = "CPE4"   # 4-node quad, plane strain
    QUAD8 = "CPS8"      # 8-node quad
    QUAD8_PE = "CPE8"   # 8-node quad, plane strain

    # 3D tetrahedral elements
    TET4 = "C3D4"       # 4-node tetrahedron
    TET10 = "C3D10"     # 10-node quadratic tetrahedron

    # 3D hexahedral elements
    HEX8 = "C3D8"       # 8-node hexahedron
    HEX20 = "C3D20"     # 20-node quadratic hexahedron


@dataclass
class ElementInfo:
    """Element type information."""
    n_nodes: int           # Nodes per element
    dim: int               # Spatial dimension
    n_gauss: int           # Number of Gauss points
    nodes_per_face: int    # Nodes per face (for surface extraction)
    is_plane_strain: bool = False
    is_quadratic: bool = False


# Element information lookup
ELEMENT_INFO = {
    ElementType.TRI3: ElementInfo(3, 2, 1, 2),
    ElementType.TRI3_PE: ElementInfo(3, 2, 1, 2, is_plane_strain=True),
    ElementType.TRI6: ElementInfo(6, 2, 3, 3, is_quadratic=True),
    ElementType.TRI6_PE: ElementInfo(6, 2, 3, 3, is_plane_strain=True, is_quadratic=True),
    ElementType.QUAD4: ElementInfo(4, 2, 4, 2),
    ElementType.QUAD4_PE: ElementInfo(4, 2, 4, 2, is_plane_strain=True),
    ElementType.QUAD8: ElementInfo(8, 2, 9, 3, is_quadratic=True),
    ElementType.QUAD8_PE: ElementInfo(8, 2, 9, 3, is_plane_strain=True, is_quadratic=True),
    ElementType.TET4: ElementInfo(4, 3, 1, 3),
    ElementType.TET10: ElementInfo(10, 3, 4, 6, is_quadratic=True),
    ElementType.HEX8: ElementInfo(8, 3, 8, 4),
    ElementType.HEX20: ElementInfo(20, 3, 27, 8, is_quadratic=True),
}


def get_element_info(elem_type: ElementType) -> ElementInfo:
    """Get element type information."""
    return ELEMENT_INFO[elem_type]


# ============================================================================
# 요소 면 정의 (표면 하중/접촉에 사용)
# ============================================================================

# 각 요소 타입별 면의 로컬 노드 인덱스
# 3D 요소: 면 = 외곽 폴리곤 (삼각형/사각형)
# 2D 요소: 면 = 변 (선분)
# 면 법선: 외향 (반시계 방향 순서 → 오른손 법칙)
ELEMENT_FACES = {
    # ─── 3D 요소 ───
    # TET4: 4 삼각형 면
    #   면 0: 노드 0,2,1 (ξ=0 면, 바닥)
    #   면 1: 노드 0,1,3 (η=0 면)
    #   면 2: 노드 1,2,3 (경사면)
    #   면 3: 노드 0,3,2 (ζ=0 면)
    ElementType.TET4: [
        [0, 2, 1],  # 면 0
        [0, 1, 3],  # 면 1
        [1, 2, 3],  # 면 2
        [0, 3, 2],  # 면 3
    ],
    # HEX8: 6 사각형 면
    #   면 0: 바닥 (z=-1): 0,3,2,1
    #   면 1: 상단 (z=+1): 4,5,6,7
    #   면 2: 전면 (y=-1): 0,1,5,4
    #   면 3: 후면 (y=+1): 2,3,7,6
    #   면 4: 좌측 (x=-1): 0,4,7,3
    #   면 5: 우측 (x=+1): 1,2,6,5
    ElementType.HEX8: [
        [0, 3, 2, 1],  # 면 0: 바닥
        [4, 5, 6, 7],  # 면 1: 상단
        [0, 1, 5, 4],  # 면 2: 전면
        [2, 3, 7, 6],  # 면 3: 후면
        [0, 4, 7, 3],  # 면 4: 좌측
        [1, 2, 6, 5],  # 면 5: 우측
    ],

    # ─── 2D 요소 (변 = "면") ───
    # TRI3: 3 변
    ElementType.TRI3: [
        [0, 1],  # 변 0: 하단
        [1, 2],  # 변 1: 경사
        [2, 0],  # 변 2: 좌측
    ],
    ElementType.TRI3_PE: [
        [0, 1],
        [1, 2],
        [2, 0],
    ],
    # QUAD4: 4 변
    ElementType.QUAD4: [
        [0, 1],  # 변 0: 하단
        [1, 2],  # 변 1: 우측
        [2, 3],  # 변 2: 상단
        [3, 0],  # 변 3: 좌측
    ],
    ElementType.QUAD4_PE: [
        [0, 1],
        [1, 2],
        [2, 3],
        [3, 0],
    ],
}


def get_face_nodes(elem_type: ElementType) -> list:
    """요소 타입별 면 노드 인덱스 목록 반환.

    Args:
        elem_type: 요소 타입

    Returns:
        면별 로컬 노드 인덱스 리스트의 리스트
    """
    if elem_type not in ELEMENT_FACES:
        raise ValueError(f"면 정의 미지원 요소: {elem_type}")
    return ELEMENT_FACES[elem_type]


def get_gauss_points_tet4() -> Tuple[np.ndarray, np.ndarray]:
    """Gauss points and weights for TET4 (1-point rule)."""
    # Natural coordinates (xi, eta, zeta)
    points = np.array([[0.25, 0.25, 0.25]])
    weights = np.array([1.0 / 6.0])  # Volume of reference tetrahedron
    return points, weights


def get_gauss_points_tet10() -> Tuple[np.ndarray, np.ndarray]:
    """Gauss points and weights for TET10 (4-point rule)."""
    a = 0.5854101966249685
    b = 0.1381966011250105
    points = np.array([
        [a, b, b],
        [b, a, b],
        [b, b, a],
        [b, b, b],
    ])
    weights = np.array([0.25, 0.25, 0.25, 0.25]) / 6.0
    return points, weights


def get_gauss_points_tri3() -> Tuple[np.ndarray, np.ndarray]:
    """Gauss points and weights for TRI3 (1-point rule)."""
    points = np.array([[1.0/3.0, 1.0/3.0]])
    weights = np.array([0.5])  # Area of reference triangle
    return points, weights


def get_shape_functions_tet4(xi: float, eta: float, zeta: float) -> np.ndarray:
    """Shape functions for 4-node tetrahedron.

    Args:
        xi, eta, zeta: Natural coordinates

    Returns:
        Shape function values (4,)
    """
    return np.array([
        1.0 - xi - eta - zeta,
        xi,
        eta,
        zeta
    ])


def get_shape_derivatives_tet4() -> np.ndarray:
    """Shape function derivatives for TET4 (constant).

    Returns:
        dN/d(xi,eta,zeta) of shape (4, 3)
    """
    return np.array([
        [-1.0, -1.0, -1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0]
    ])


def get_shape_functions_tet10(xi: float, eta: float, zeta: float) -> np.ndarray:
    """Shape functions for 10-node tetrahedron.

    Args:
        xi, eta, zeta: Natural coordinates

    Returns:
        Shape function values (10,)
    """
    L1 = 1.0 - xi - eta - zeta
    L2 = xi
    L3 = eta
    L4 = zeta

    N = np.zeros(10)
    # Corner nodes
    N[0] = L1 * (2*L1 - 1)
    N[1] = L2 * (2*L2 - 1)
    N[2] = L3 * (2*L3 - 1)
    N[3] = L4 * (2*L4 - 1)
    # Mid-edge nodes
    N[4] = 4 * L1 * L2
    N[5] = 4 * L2 * L3
    N[6] = 4 * L1 * L3
    N[7] = 4 * L1 * L4
    N[8] = 4 * L2 * L4
    N[9] = 4 * L3 * L4

    return N


def get_shape_derivatives_tet10(xi: float, eta: float, zeta: float) -> np.ndarray:
    """Shape function derivatives for TET10.

    Args:
        xi, eta, zeta: Natural coordinates

    Returns:
        dN/d(xi,eta,zeta) of shape (10, 3)
    """
    L1 = 1.0 - xi - eta - zeta
    L2 = xi
    L3 = eta
    L4 = zeta

    dN = np.zeros((10, 3))

    # dN/dxi
    dN[0, 0] = -(4*L1 - 1)
    dN[1, 0] = 4*L2 - 1
    dN[2, 0] = 0.0
    dN[3, 0] = 0.0
    dN[4, 0] = 4*(L1 - L2)
    dN[5, 0] = 4*L3
    dN[6, 0] = -4*L3
    dN[7, 0] = -4*L4
    dN[8, 0] = 4*L4
    dN[9, 0] = 0.0

    # dN/deta
    dN[0, 1] = -(4*L1 - 1)
    dN[1, 1] = 0.0
    dN[2, 1] = 4*L3 - 1
    dN[3, 1] = 0.0
    dN[4, 1] = -4*L2
    dN[5, 1] = 4*L2
    dN[6, 1] = 4*(L1 - L3)
    dN[7, 1] = -4*L4
    dN[8, 1] = 0.0
    dN[9, 1] = 4*L4

    # dN/dzeta
    dN[0, 2] = -(4*L1 - 1)
    dN[1, 2] = 0.0
    dN[2, 2] = 0.0
    dN[3, 2] = 4*L4 - 1
    dN[4, 2] = -4*L2
    dN[5, 2] = 0.0
    dN[6, 2] = -4*L3
    dN[7, 2] = 4*(L1 - L4)
    dN[8, 2] = 4*L2
    dN[9, 2] = 4*L3

    return dN


# ============================================================================
# HEX8 요소 (8노드 육면체)
# ============================================================================

# HEX8 노드 좌표 (자연 좌표계)
# 노드 배치:
#     7-------6
#    /|      /|
#   4-------5 |
#   | |     | |
#   | 3-----|-2
#   |/      |/
#   0-------1
HEX8_NODE_COORDS = np.array([
    [-1, -1, -1],  # 0
    [+1, -1, -1],  # 1
    [+1, +1, -1],  # 2
    [-1, +1, -1],  # 3
    [-1, -1, +1],  # 4
    [+1, -1, +1],  # 5
    [+1, +1, +1],  # 6
    [-1, +1, +1],  # 7
], dtype=np.float64)


def get_gauss_points_hex8() -> Tuple[np.ndarray, np.ndarray]:
    """HEX8 요소의 Gauss 적분점과 가중치 (2×2×2 = 8점).

    Returns:
        points: Gauss점 좌표 (8, 3)
        weights: 가중치 (8,)
    """
    gp = 1.0 / np.sqrt(3.0)  # ≈ 0.57735

    points = np.array([
        [-gp, -gp, -gp],
        [+gp, -gp, -gp],
        [+gp, +gp, -gp],
        [-gp, +gp, -gp],
        [-gp, -gp, +gp],
        [+gp, -gp, +gp],
        [+gp, +gp, +gp],
        [-gp, +gp, +gp],
    ])

    # 각 Gauss점의 가중치는 1.0
    weights = np.ones(8)

    return points, weights


def get_shape_functions_hex8(xi: float, eta: float, zeta: float) -> np.ndarray:
    """HEX8 요소의 형상함수.

    N_i(ξ,η,ζ) = (1/8)(1 + ξ_i·ξ)(1 + η_i·η)(1 + ζ_i·ζ)

    Args:
        xi, eta, zeta: 자연 좌표 (-1 ~ +1)

    Returns:
        형상함수 값 (8,)
    """
    N = np.zeros(8)
    for i in range(8):
        xi_i, eta_i, zeta_i = HEX8_NODE_COORDS[i]
        N[i] = 0.125 * (1 + xi_i * xi) * (1 + eta_i * eta) * (1 + zeta_i * zeta)
    return N


def get_shape_derivatives_hex8(xi: float, eta: float, zeta: float) -> np.ndarray:
    """HEX8 요소의 형상함수 미분.

    dN_i/dξ = (1/8) * ξ_i * (1 + η_i·η) * (1 + ζ_i·ζ)
    dN_i/dη = (1/8) * (1 + ξ_i·ξ) * η_i * (1 + ζ_i·ζ)
    dN_i/dζ = (1/8) * (1 + ξ_i·ξ) * (1 + η_i·η) * ζ_i

    Args:
        xi, eta, zeta: 자연 좌표 (-1 ~ +1)

    Returns:
        dN/d(xi,eta,zeta) 행렬 (8, 3)
    """
    dN = np.zeros((8, 3))
    for i in range(8):
        xi_i, eta_i, zeta_i = HEX8_NODE_COORDS[i]

        # dN/dxi
        dN[i, 0] = 0.125 * xi_i * (1 + eta_i * eta) * (1 + zeta_i * zeta)
        # dN/deta
        dN[i, 1] = 0.125 * (1 + xi_i * xi) * eta_i * (1 + zeta_i * zeta)
        # dN/dzeta
        dN[i, 2] = 0.125 * (1 + xi_i * xi) * (1 + eta_i * eta) * zeta_i

    return dN


# ============================================================================
# QUAD4 요소 (4노드 사각형)
# ============================================================================

# QUAD4 노드 좌표 (자연 좌표계)
# 노드 배치:
#   3-------2
#   |       |
#   |       |
#   0-------1
QUAD4_NODE_COORDS = np.array([
    [-1, -1],  # 0
    [+1, -1],  # 1
    [+1, +1],  # 2
    [-1, +1],  # 3
], dtype=np.float64)


def get_gauss_points_quad4() -> Tuple[np.ndarray, np.ndarray]:
    """QUAD4 요소의 Gauss 적분점과 가중치 (2×2 = 4점).

    Returns:
        points: Gauss점 좌표 (4, 2)
        weights: 가중치 (4,)
    """
    gp = 1.0 / np.sqrt(3.0)  # ≈ 0.57735

    points = np.array([
        [-gp, -gp],
        [+gp, -gp],
        [+gp, +gp],
        [-gp, +gp],
    ])

    # 각 Gauss점의 가중치는 1.0
    weights = np.ones(4)

    return points, weights


def get_shape_functions_quad4(xi: float, eta: float) -> np.ndarray:
    """QUAD4 요소의 형상함수.

    N_i(ξ,η) = (1/4)(1 + ξ_i·ξ)(1 + η_i·η)

    Args:
        xi, eta: 자연 좌표 (-1 ~ +1)

    Returns:
        형상함수 값 (4,)
    """
    N = np.zeros(4)
    for i in range(4):
        xi_i, eta_i = QUAD4_NODE_COORDS[i]
        N[i] = 0.25 * (1 + xi_i * xi) * (1 + eta_i * eta)
    return N


def get_shape_derivatives_quad4(xi: float, eta: float) -> np.ndarray:
    """QUAD4 요소의 형상함수 미분.

    dN_i/dξ = (1/4) * ξ_i * (1 + η_i·η)
    dN_i/dη = (1/4) * (1 + ξ_i·ξ) * η_i

    Args:
        xi, eta: 자연 좌표 (-1 ~ +1)

    Returns:
        dN/d(xi,eta) 행렬 (4, 2)
    """
    dN = np.zeros((4, 2))
    for i in range(4):
        xi_i, eta_i = QUAD4_NODE_COORDS[i]

        # dN/dxi
        dN[i, 0] = 0.25 * xi_i * (1 + eta_i * eta)
        # dN/deta
        dN[i, 1] = 0.25 * (1 + xi_i * xi) * eta_i

    return dN
