"""Finite Element Method (FEM) module for spine surgery simulation.

Based on FEMcy (https://github.com/mo-hanxuan/FEMcy) with improvements for:
- Better material model interface
- Integration with peridynamics module
- Spine-specific bone material models

Key components:
- core/mesh.py: Mesh data structure with Taichi fields
- core/element.py: Element type definitions (Tet4, Tet10, Tri3, etc.)
- material/: Constitutive models (Linear elastic, Neo-Hookean, Bone)
- solver/: Static and quasi-static solvers
"""

from .core.mesh import FEMesh
from .core.element import ElementType
from .material.linear_elastic import LinearElastic
from .material.neo_hookean import NeoHookean
from .solver.static_solver import StaticSolver

__all__ = [
    "FEMesh",
    "ElementType",
    "LinearElastic",
    "NeoHookean",
    "StaticSolver",
]
