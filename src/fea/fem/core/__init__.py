"""Core FEM data structures."""

from .mesh import FEMesh
from .element import ElementType, get_element_info

__all__ = ["FEMesh", "ElementType", "get_element_info"]
