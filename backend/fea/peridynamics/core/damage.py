"""Critical stretch damage model for peridynamics."""

import taichi as ti
import numpy as np
from typing import TYPE_CHECKING
import math

if TYPE_CHECKING:
    from .particles import ParticleSystem
    from .bonds import BondSystem


@ti.data_oriented
class DamageModel:
    """Critical stretch damage model for bond-based peridynamics.

    A bond breaks when its stretch exceeds the critical stretch value.
    Local damage is computed as the ratio of broken bonds to initial bonds.

    The critical stretch is related to fracture energy by:
        2D: s_c = sqrt(4 * pi * G_c / (9 * E * delta))
        3D: s_c = sqrt(5 * G_c / (9 * E * delta))

    where:
        G_c: Critical energy release rate (fracture energy)
        E: Young's modulus
        delta: Peridynamics horizon
    """

    def __init__(
        self,
        critical_stretch: float = 0.01,
        dim: int = 2
    ):
        """Initialize damage model.

        Args:
            critical_stretch: Critical stretch value s_c
            dim: Spatial dimension (2 or 3)
        """
        self.critical_stretch = critical_stretch
        self.dim = dim

    @staticmethod
    def compute_critical_stretch(
        youngs_modulus: float,
        fracture_energy: float,
        horizon: float,
        dim: int = 3
    ) -> float:
        """Compute critical stretch from material properties.

        Args:
            youngs_modulus: Young's modulus E [Pa]
            fracture_energy: Fracture energy G_c [J/m^2]
            horizon: Peridynamics horizon delta [m]
            dim: Spatial dimension (2 or 3)

        Returns:
            Critical stretch value s_c
        """
        if dim == 2:
            # 2D: s_c = sqrt(4 * pi * G_c / (9 * E * delta))
            return math.sqrt(4 * math.pi * fracture_energy / (9 * youngs_modulus * horizon))
        else:
            # 3D: s_c = sqrt(5 * G_c / (9 * E * delta))
            return math.sqrt(5 * fracture_energy / (9 * youngs_modulus * horizon))

    @staticmethod
    def compute_critical_stretch_bone(
        bone_type: str = "cortical",
        horizon: float = 0.003
    ) -> float:
        """Compute critical stretch for bone material.

        Args:
            bone_type: "cortical" or "cancellous"
            horizon: Peridynamics horizon [m]

        Returns:
            Critical stretch for bone
        """
        if bone_type == "cortical":
            # Cortical bone properties
            E = 17e9  # 17 GPa
            G_c = 500.0  # J/m^2 (typical for cortical bone)
        else:
            # Cancellous bone properties
            E = 0.5e9  # 0.5 GPa
            G_c = 50.0  # J/m^2

        return DamageModel.compute_critical_stretch(E, G_c, horizon, dim=3)

    @ti.kernel
    def update_damage(
        self,
        particles: ti.template(),
        bonds: ti.template(),
        critical_stretch: ti.f64
    ):
        """Update bond damage state based on critical stretch criterion.

        Args:
            particles: ParticleSystem (for current positions)
            bonds: BondSystem (bond state to update)
            critical_stretch: Critical stretch value
        """
        for i in range(bonds.n_particles):
            for k in range(bonds.n_neighbors[i]):
                # Skip already broken bonds
                if bonds.broken[i, k] == 0:
                    stretch = bonds.get_stretch(particles.x, i, k)

                    # Break bond if stretch exceeds critical value
                    if stretch > critical_stretch:
                        bonds.broken[i, k] = 1

    @ti.kernel
    def compute_local_damage(
        self,
        particles: ti.template(),
        bonds: ti.template()
    ):
        """Compute local damage for each particle.

        Local damage phi = (broken bonds) / (initial bonds)
        where phi = 0 means intact and phi = 1 means fully damaged.

        Args:
            particles: ParticleSystem (damage field to update)
            bonds: BondSystem (for bond state)
        """
        for i in range(bonds.n_particles):
            initial = bonds.initial_bonds[i]
            if initial > 0:
                broken_count = 0
                for k in range(bonds.n_neighbors[i]):
                    if bonds.broken[i, k] == 1:
                        broken_count += 1
                particles.damage[i] = ti.cast(broken_count, ti.f64) / ti.cast(initial, ti.f64)
            else:
                particles.damage[i] = 0.0

    def step(self, particles: "ParticleSystem", bonds: "BondSystem"):
        """Perform damage update step.

        Args:
            particles: ParticleSystem
            bonds: BondSystem
        """
        self.update_damage(particles, bonds, self.critical_stretch)
        self.compute_local_damage(particles, bonds)

    def get_statistics(self, bonds: "BondSystem") -> dict:
        """Get damage statistics.

        Args:
            bonds: BondSystem

        Returns:
            Dictionary with damage statistics
        """
        intact = bonds.count_intact_bonds()
        broken = bonds.count_broken_bonds()
        total = intact + broken

        return {
            "intact_bonds": int(intact),
            "broken_bonds": int(broken),
            "total_bonds": int(total),
            "damage_ratio": broken / total if total > 0 else 0.0
        }
