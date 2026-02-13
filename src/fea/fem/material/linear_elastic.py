"""Linear elastic material model.

Implements small strain isotropic linear elasticity:
σ = λ·tr(ε)·I + 2μ·ε

where:
- ε = 0.5·(∇u + ∇uᵀ) is small strain tensor
- λ, μ are Lamé parameters
"""

import taichi as ti
import numpy as np
from typing import TYPE_CHECKING

from .base import MaterialBase

if TYPE_CHECKING:
    from ..core.mesh import FEMesh


@ti.data_oriented
class LinearElastic(MaterialBase):
    """Isotropic linear elastic material."""

    def __init__(
        self,
        youngs_modulus: float,
        poisson_ratio: float,
        dim: int = 3,
        plane_stress: bool = False
    ):
        """Initialize linear elastic material.

        Args:
            youngs_modulus: Young's modulus E [Pa]
            poisson_ratio: Poisson's ratio ν
            dim: Spatial dimension
            plane_stress: Use plane stress assumption (2D only)
        """
        super().__init__(dim)
        self.E = youngs_modulus
        self.nu = poisson_ratio
        self.plane_stress = plane_stress

        # Compute Lamé parameters
        self.mu = youngs_modulus / (2 * (1 + poisson_ratio))

        if dim == 2 and plane_stress:
            # Plane stress: modified λ
            self.lam = youngs_modulus * poisson_ratio / (1 - poisson_ratio**2)
        else:
            # Plane strain or 3D
            self.lam = youngs_modulus * poisson_ratio / ((1 + poisson_ratio) * (1 - 2*poisson_ratio))

        # Store as Taichi fields for kernel access
        self._mu = ti.field(dtype=ti.f64, shape=())
        self._lam = ti.field(dtype=ti.f64, shape=())
        self._mu[None] = self.mu
        self._lam[None] = self.lam

    @property
    def is_linear(self) -> bool:
        return True

    def get_elasticity_tensor(self) -> np.ndarray:
        """Get elasticity tensor in Voigt notation.

        Returns:
            C matrix (6x6 for 3D, 3x3 for 2D)
        """
        E, nu = self.E, self.nu
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
        """Compute Cauchy stress from small strain."""
        self._compute_stress_kernel(
            mesh.F,
            mesh.stress,
            mesh.strain,
            mesh.n_elements * mesh.n_gauss
        )

    @ti.kernel
    def _compute_stress_kernel(
        self,
        F: ti.template(),
        stress: ti.template(),
        strain: ti.template(),
        n_gauss: int
    ):
        """Compute stress at all Gauss points."""
        lam = self._lam[None]
        mu = self._mu[None]
        dim = ti.static(self.dim)

        for gp in range(n_gauss):
            # Small strain: ε = 0.5*(F + Fᵀ) - I
            Fg = F[gp]
            I = ti.Matrix.identity(ti.f64, dim)
            eps = 0.5 * (Fg + Fg.transpose()) - I
            tr_eps = eps.trace()

            # Cauchy stress: σ = λ·tr(ε)·I + 2μ·ε
            sigma = lam * tr_eps * I + 2.0 * mu * eps

            stress[gp] = sigma
            strain[gp] = eps

    def compute_nodal_forces(self, mesh: "FEMesh"):
        """Compute internal nodal forces using B-matrix approach."""
        mesh.f.fill(0)
        self._compute_forces_kernel(
            mesh.elements,
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
        dNdX: ti.template(),
        stress: ti.template(),
        gauss_vol: ti.template(),
        f: ti.template(),
        n_elements: int,
        n_gauss: int,
        nodes_per_elem: int
    ):
        """내부 절점력 계산.

        f_a = - Σ_gp σ · (dN_a/dX) · w·det(J)
        """
        dim = ti.static(self.dim)
        for e in range(n_elements):
            for g in range(n_gauss):
                gp_idx = e * n_gauss + g
                sigma = stress[gp_idx]
                dN = dNdX[gp_idx]
                vol = gauss_vol[gp_idx]

                for a in range(nodes_per_elem):
                    node = elements[e][a]
                    f_a = ti.Vector.zero(ti.f64, dim)
                    for i in ti.static(range(dim)):
                        for j in ti.static(range(dim)):
                            f_a[i] -= sigma[i, j] * dN[a, j] * vol

                    ti.atomic_add(f[node], f_a)

    def __repr__(self) -> str:
        return f"LinearElastic(E={self.E:.2e}, ν={self.nu:.3f})"
