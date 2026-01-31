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
