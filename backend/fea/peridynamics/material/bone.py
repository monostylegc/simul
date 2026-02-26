"""Bone material models for peridynamics.

Provides material properties for cortical and cancellous bone tissue
used in spine surgery simulation.
"""

import taichi as ti
import math
from .material_base import MaterialBase


@ti.data_oriented
class BoneMaterial(MaterialBase):
    """Bone material for peridynamics simulation.

    Supports both cortical (compact) and cancellous (spongy) bone types
    with typical mechanical properties from literature.

    Reference values:
    - Cortical bone: E = 15-20 GPa, nu = 0.3, rho = 1800-2000 kg/m^3
    - Cancellous bone: E = 0.1-2 GPa, nu = 0.2-0.3, rho = 100-1000 kg/m^3
    """

    # Typical bone properties (SI units)
    CORTICAL = {
        "E": 17e9,      # Young's modulus [Pa]
        "nu": 0.3,      # Poisson's ratio
        "rho": 1900,    # Density [kg/m^3]
        "G_c": 500,     # Fracture energy [J/m^2]
    }

    CANCELLOUS = {
        "E": 0.5e9,     # Young's modulus [Pa]
        "nu": 0.25,     # Poisson's ratio
        "rho": 500,     # Density [kg/m^3]
        "G_c": 50,      # Fracture energy [J/m^2]
    }

    def __init__(
        self,
        bone_type: str = "cortical",
        horizon: float = 0.003,
        thickness: float = 1.0,
        dim: int = 3,
        custom_props: dict = None
    ):
        """Initialize bone material.

        Args:
            bone_type: "cortical" or "cancellous"
            horizon: Peridynamics horizon [m]
            thickness: Plate thickness for 2D [m]
            dim: Spatial dimension (2 or 3)
            custom_props: Override default properties (E, nu, rho, G_c)
        """
        self.bone_type = bone_type
        self.delta = horizon
        self.thickness = thickness
        self.dim = dim

        # Get default properties
        if bone_type == "cortical":
            props = self.CORTICAL.copy()
        elif bone_type == "cancellous":
            props = self.CANCELLOUS.copy()
        else:
            raise ValueError(f"Unknown bone type: {bone_type}")

        # Apply custom overrides
        if custom_props:
            props.update(custom_props)

        self.E = props["E"]
        self.nu = props["nu"]
        self.rho = props["rho"]
        self.G_c = props["G_c"]

        # Compute bulk modulus
        if dim == 2:
            self.K = self.E / (2 * (1 - self.nu))
        else:
            self.K = self.E / (3 * (1 - 2 * self.nu))

        # Compute micromodulus
        self._micromodulus = self._compute_micromodulus()

        # Compute critical stretch
        self._critical_stretch = self._compute_critical_stretch()

    def _compute_micromodulus(self) -> float:
        """Compute the micromodulus constant c."""
        if self.dim == 2:
            return 9 * self.E / (math.pi * self.thickness * self.delta**3)
        else:
            return 18 * self.K / (math.pi * self.delta**4)

    def _compute_critical_stretch(self) -> float:
        """Compute critical stretch from fracture energy."""
        if self.dim == 2:
            return math.sqrt(4 * math.pi * self.G_c / (9 * self.E * self.delta))
        else:
            return math.sqrt(5 * self.G_c / (9 * self.E * self.delta))

    def get_micromodulus(self) -> float:
        """Get the micromodulus constant c."""
        return self._micromodulus

    def get_critical_stretch(self) -> float:
        """Get the critical stretch value."""
        return self._critical_stretch

    def get_density(self) -> float:
        """Get material density."""
        return self.rho

    def compute_pairwise_force(
        self,
        stretch: float,
        xi_length: float,
        omega: float
    ) -> float:
        """Compute pairwise force magnitude.

        Args:
            stretch: Bond stretch
            xi_length: Reference bond length (not used)
            omega: Influence function weight

        Returns:
            Force magnitude
        """
        return self._micromodulus * stretch * omega

    def estimate_stable_dt(self, spacing: float, safety_factor: float = 0.5) -> float:
        """Estimate stable time step.

        Args:
            spacing: Particle spacing [m]
            safety_factor: Safety factor (0-1)

        Returns:
            Stable time step [s]
        """
        wave_speed = math.sqrt(self.E / self.rho)
        return safety_factor * spacing / wave_speed

    def __repr__(self) -> str:
        return (
            f"BoneMaterial(type={self.bone_type}, E={self.E/1e9:.1f}GPa, "
            f"rho={self.rho}kg/m^3, s_c={self._critical_stretch:.4f})"
        )


# Convenience functions for common bone types
def cortical_bone(horizon: float = 0.003, dim: int = 3, **kwargs) -> BoneMaterial:
    """Create cortical bone material.

    Args:
        horizon: Peridynamics horizon [m]
        dim: Spatial dimension
        **kwargs: Override default properties

    Returns:
        BoneMaterial instance
    """
    return BoneMaterial("cortical", horizon, dim=dim, custom_props=kwargs or None)


def cancellous_bone(horizon: float = 0.003, dim: int = 3, **kwargs) -> BoneMaterial:
    """Create cancellous bone material.

    Args:
        horizon: Peridynamics horizon [m]
        dim: Spatial dimension
        **kwargs: Override default properties

    Returns:
        BoneMaterial instance
    """
    return BoneMaterial("cancellous", horizon, dim=dim, custom_props=kwargs or None)


def vertebral_body(horizon: float = 0.003, cortical_thickness: float = 0.001) -> dict:
    """Get material configuration for vertebral body.

    The vertebral body consists of:
    - Outer cortical shell (1-2mm thick)
    - Inner cancellous core

    Args:
        horizon: Peridynamics horizon [m]
        cortical_thickness: Thickness of cortical shell [m]

    Returns:
        Dictionary with cortical and cancellous materials
    """
    return {
        "cortical": cortical_bone(horizon, dim=3),
        "cancellous": cancellous_bone(horizon, dim=3),
        "cortical_thickness": cortical_thickness
    }
