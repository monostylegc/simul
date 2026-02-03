"""Abstract base class for peridynamics material models."""

from abc import ABC, abstractmethod
import taichi as ti


class MaterialBase(ABC):
    """Abstract base class for peridynamics material models.

    Material models compute force from bond stretch (bond-based PD)
    or stress from deformation gradient (correspondence-based NOSB-PD).
    """

    @abstractmethod
    def get_micromodulus(self) -> float:
        """Get the micromodulus constant c for bond-based PD.

        For 2D: c = 9*E / (pi * h^3 * delta)
        For 3D: c = 18*K / (pi * delta^4)

        where E is Young's modulus, K is bulk modulus, h is thickness,
        and delta is the horizon.
        """
        pass

    @abstractmethod
    def compute_pairwise_force(
        self,
        stretch: float,
        xi_length: float,
        omega: float
    ) -> float:
        """Compute pairwise force magnitude for bond-based PD.

        Args:
            stretch: Bond stretch s = (|eta| - |xi|) / |xi|
            xi_length: Reference bond length |xi|
            omega: Influence function weight

        Returns:
            Force magnitude (scalar, along bond direction)
        """
        pass
