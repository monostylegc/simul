"""Linear elastic material model for bond-based peridynamics."""

import taichi as ti
import math
from .material_base import MaterialBase


@ti.data_oriented
class LinearElasticMaterial(MaterialBase):
    """Linear elastic material for bond-based peridynamics.

    Uses the prototype microelastic brittle (PMB) model where
    the pairwise force is proportional to bond stretch.

    For 2D plane stress:
        c = 9*E / (pi * h * delta^3)

    For 3D:
        c = 18*K / (pi * delta^4)

    where c is the micromodulus, E is Young's modulus, K is bulk modulus,
    h is the thickness, and delta is the horizon.
    """

    def __init__(
        self,
        youngs_modulus: float,
        poisson_ratio: float = 0.25,
        horizon: float = 0.01,
        thickness: float = 1.0,
        dim: int = 2
    ):
        """Initialize linear elastic material.

        Args:
            youngs_modulus: Young's modulus E [Pa]
            poisson_ratio: Poisson's ratio nu (note: bond-based PD has fixed nu=1/4 for 2D, 1/3 for 3D)
            horizon: Peridynamics horizon delta [m]
            thickness: Plate thickness h [m] (for 2D)
            dim: Spatial dimension (2 or 3)
        """
        self.E = youngs_modulus
        self.nu = poisson_ratio
        self.delta = horizon
        self.thickness = thickness
        self.dim = dim

        # Compute bulk modulus
        if dim == 2:
            # Plane stress
            self.K = youngs_modulus / (2 * (1 - poisson_ratio))
        else:
            # 3D
            self.K = youngs_modulus / (3 * (1 - 2 * poisson_ratio))

        # Compute micromodulus
        self._micromodulus = self._compute_micromodulus()

    def _compute_micromodulus(self) -> float:
        """Compute the micromodulus constant c."""
        if self.dim == 2:
            # 2D plane stress: c = 9*E / (pi * h * delta^3)
            return 9 * self.E / (math.pi * self.thickness * self.delta**3)
        else:
            # 3D: c = 18*K / (pi * delta^4)
            return 18 * self.K / (math.pi * self.delta**4)

    def get_micromodulus(self) -> float:
        """Get the micromodulus constant c."""
        return self._micromodulus

    def compute_pairwise_force(
        self,
        stretch: float,
        xi_length: float,
        omega: float
    ) -> float:
        """Compute pairwise force magnitude.

        f = c * s * omega

        Args:
            stretch: Bond stretch
            xi_length: Reference bond length (not used in PMB)
            omega: Influence function weight

        Returns:
            Force magnitude
        """
        return self._micromodulus * stretch * omega


@ti.data_oriented
class LinearElasticMaterial2D:
    """Taichi-compatible 2D linear elastic material.

    This class stores material parameters as ti.field for use in kernels.
    """

    def __init__(
        self,
        youngs_modulus: float,
        horizon: float,
        thickness: float = 1.0
    ):
        """Initialize 2D linear elastic material.

        Args:
            youngs_modulus: Young's modulus E [Pa]
            horizon: Peridynamics horizon delta [m]
            thickness: Plate thickness h [m]
        """
        self.E = youngs_modulus
        self.delta = horizon
        self.thickness = thickness

        # Compute micromodulus: c = 9*E / (pi * h * delta^3)
        self.micromodulus = 9 * youngs_modulus / (math.pi * thickness * horizon**3)

        # Store as field for kernel access
        self.c = ti.field(dtype=ti.f64, shape=())
        self.c[None] = self.micromodulus

    @ti.func
    def compute_force(self, stretch: ti.f64, omega: ti.f64) -> ti.f64:
        """Compute pairwise force magnitude in kernel.

        Args:
            stretch: Bond stretch
            omega: Influence weight

        Returns:
            Force magnitude
        """
        return self.c[None] * stretch * omega
