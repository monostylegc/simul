"""Base class for FEM material models.

All material models must implement:
- compute_stress: Compute Cauchy stress from deformation gradient
- compute_tangent: Compute material tangent stiffness
"""

import abc
import taichi as ti
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.mesh import FEMesh


class MaterialBase(abc.ABC):
    """Abstract base class for material models."""

    def __init__(self, dim: int = 3):
        """Initialize material.

        Args:
            dim: Spatial dimension (2 or 3)
        """
        self.dim = dim

    @abc.abstractmethod
    def compute_stress(self, mesh: "FEMesh"):
        """Compute Cauchy stress at all Gauss points.

        Updates mesh.stress field based on mesh.F (deformation gradient).

        Args:
            mesh: FEMesh instance with computed F
        """
        pass

    @abc.abstractmethod
    def compute_nodal_forces(self, mesh: "FEMesh"):
        """Compute internal nodal forces.

        f_i = - Σ_e ∫ P : (dN_i/dX) dV

        Args:
            mesh: FEMesh instance with computed stress

        Returns internal forces in mesh.f
        """
        pass

    @abc.abstractmethod
    def get_elasticity_tensor(self):
        """Get 4th order elasticity tensor C (Voigt notation).

        Returns:
            6x6 matrix for 3D, 3x3 for 2D
        """
        pass

    @property
    def is_linear(self) -> bool:
        """Whether material is linear (stress ∝ strain)."""
        return False
