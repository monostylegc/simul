"""Neo-Hookean hyperelastic material model.

Strain energy density:
ψ = μ/2 * (I₁ - 3) - μ·ln(J) + λ/2 * ln²(J)

where:
- I₁ = tr(C) = tr(FᵀF) is first invariant
- J = det(F) is volume ratio
- μ, λ are Lamé parameters

Cauchy stress:
σ = J⁻¹ · (μ·(B - I) + λ·ln(J)·I)

where B = F·Fᵀ is left Cauchy-Green tensor.

Reference:
- Bonet & Wood, "Nonlinear Continuum Mechanics for Finite Element Analysis"
"""

import taichi as ti
import numpy as np
from typing import TYPE_CHECKING

from .base import MaterialBase

if TYPE_CHECKING:
    from ..core.mesh import FEMesh


@ti.data_oriented
class NeoHookean(MaterialBase):
    """Compressible Neo-Hookean hyperelastic material."""

    def __init__(
        self,
        youngs_modulus: float,
        poisson_ratio: float,
        dim: int = 3
    ):
        """Initialize Neo-Hookean material.

        Args:
            youngs_modulus: Young's modulus E [Pa]
            poisson_ratio: Poisson's ratio ν
            dim: Spatial dimension
        """
        super().__init__(dim)
        self.E = youngs_modulus
        self.nu = poisson_ratio

        # Compute Lamé parameters
        self.mu = youngs_modulus / (2 * (1 + poisson_ratio))
        self.lam = youngs_modulus * poisson_ratio / ((1 + poisson_ratio) * (1 - 2*poisson_ratio))

        # Store as Taichi fields
        self._mu = ti.field(dtype=ti.f64, shape=())
        self._lam = ti.field(dtype=ti.f64, shape=())
        self._mu[None] = self.mu
        self._lam[None] = self.lam

    @property
    def is_linear(self) -> bool:
        return False

    def get_elasticity_tensor(self) -> np.ndarray:
        """Get linearized elasticity tensor (at F=I).

        For nonlinear materials, this is the initial tangent.
        """
        lam, mu = self.lam, self.mu

        if self.dim == 3:
            C = np.zeros((6, 6))
            C[0, 0] = C[1, 1] = C[2, 2] = lam + 2*mu
            C[0, 1] = C[0, 2] = C[1, 2] = lam
            C[1, 0] = C[2, 0] = C[2, 1] = lam
            C[3, 3] = C[4, 4] = C[5, 5] = mu
            return C
        else:
            C = np.zeros((3, 3))
            C[0, 0] = C[1, 1] = lam + 2*mu
            C[0, 1] = C[1, 0] = lam
            C[2, 2] = mu
            return C

    def compute_stress(self, mesh: "FEMesh"):
        """Compute Cauchy stress from deformation gradient."""
        self._compute_stress_kernel(
            mesh.F,
            mesh.stress,
            mesh.n_elements * mesh.n_gauss
        )

    @ti.kernel
    def _compute_stress_kernel(
        self,
        F: ti.template(),
        stress: ti.template(),
        n_gauss: int
    ):
        """Compute Cauchy stress at all Gauss points.

        σ = J⁻¹ · (μ·(B - I) + λ·ln(J)·I)
        """
        mu = self._mu[None]
        lam = self._lam[None]
        dim = ti.static(self.dim)

        for gp in range(n_gauss):
            Fg = F[gp]
            J = Fg.determinant()

            # Avoid numerical issues with very small J
            J_safe = ti.max(J, 1e-8)
            ln_J = ti.log(J_safe)

            # Left Cauchy-Green: B = F · Fᵀ
            B = Fg @ Fg.transpose()
            I = ti.Matrix.identity(ti.f64, dim)

            # Cauchy stress: σ = (1/J) * (μ*(B - I) + λ*ln(J)*I)
            sigma = (1.0 / J_safe) * (mu * (B - I) + lam * ln_J * I)

            stress[gp] = sigma

    def compute_nodal_forces(self, mesh: "FEMesh"):
        """Compute internal nodal forces.

        For large deformation:
        f_a = - Σ_gp P · (dN_a/dX) · det(J₀) · w

        where P = J·σ·F⁻ᵀ is first Piola-Kirchhoff stress
        """
        mesh.f.fill(0)
        self._compute_forces_kernel(
            mesh.elements,
            mesh.F,
            mesh.dNdX,
            mesh.stress,
            mesh.gauss_vol,
            mesh.f,
            mesh.n_elements,
            mesh.n_gauss,
            mesh.nodes_per_elem
        )

    @ti.kernel
    def _compute_forces_kernel(
        self,
        elements: ti.template(),
        F: ti.template(),
        dNdX: ti.template(),
        stress: ti.template(),
        gauss_vol: ti.template(),
        f: ti.template(),
        n_elements: int,
        n_gauss: int,
        nodes_per_elem: int
    ):
        """내부력 계산 (일반화: 모든 요소 타입 지원)."""
        dim = ti.static(self.dim)
        for e in range(n_elements):
            for g in range(n_gauss):
                gp_idx = e * n_gauss + g
                Fg = F[gp_idx]
                sigma = stress[gp_idx]
                dN = dNdX[gp_idx]
                vol = gauss_vol[gp_idx]

                J = Fg.determinant()
                J_safe = ti.max(J, 1e-8)

                # First Piola-Kirchhoff: P = J * σ * F⁻ᵀ
                F_inv_T = Fg.inverse().transpose()
                P = J_safe * sigma @ F_inv_T

                # 모든 노드에 대해 내부력 누적
                for a in range(nodes_per_elem):
                    node = elements[e][a]
                    f_a = ti.Vector.zero(ti.f64, dim)
                    for i in ti.static(range(dim)):
                        for j in ti.static(range(dim)):
                            f_a[i] -= P[i, j] * dN[a, j] * vol

                    ti.atomic_add(f[node], f_a)

    @ti.func
    def strain_energy_density(self, F):
        """Compute strain energy density.

        ψ = μ/2 * (I₁ - 3) - μ·ln(J) + λ/2 * ln²(J)
        """
        mu = self._mu[None]
        lam = self._lam[None]

        J = F.determinant()
        J_safe = ti.max(J, 1e-8)
        ln_J = ti.log(J_safe)

        # I₁ = tr(C) = tr(FᵀF)
        C = F.transpose() @ F
        I1 = C.trace()

        return 0.5 * mu * (I1 - 3.0) - mu * ln_J + 0.5 * lam * ln_J**2

    @ti.kernel
    def compute_total_energy(
        self,
        F: ti.template(),
        gauss_vol: ti.template(),
        n_gauss: int
    ) -> ti.f64:
        """Compute total strain energy."""
        energy = 0.0
        for gp in range(n_gauss):
            psi = self.strain_energy_density(F[gp])
            energy += psi * gauss_vol[gp]
        return energy

    def __repr__(self) -> str:
        return f"NeoHookean(E={self.E:.2e}, ν={self.nu:.3f})"
