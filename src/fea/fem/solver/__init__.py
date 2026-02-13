"""FEM solvers."""

from .static_solver import StaticSolver
from .dynamic_solver import DynamicSolver

__all__ = ["StaticSolver", "DynamicSolver"]
