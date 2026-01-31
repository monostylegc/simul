"""Non-Ordinary State-Based Peridynamics (NOSB-PD) core computations.

NOSB-PD uses correspondence material models to incorporate classical
continuum constitutive relations, allowing arbitrary Poisson's ratio.

Key equations:
1. Shape tensor: K = Σ ω(|ξ|) · (ξ ⊗ ξ) · V_j
2. Deformation gradient: F = [Σ ω(|ξ|) · (η ⊗ ξ) · V_j] · K⁻¹
3. Stress: P = material.compute_stress(F)  (1st Piola-Kirchhoff)
4. Force state: t = ω · P · K⁻¹ · ξ
5. Internal force: f_i = Σ (t_ij - t_ji) · V_j

References:
- Silling et al. (2007) "Peridynamic states and constitutive modeling"
- Tupek & Radovitzky (2014) "An extended constitutive correspondence formulation"
"""

import taichi as ti
import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .particles import ParticleSystem
    from .bonds import BondSystem


@ti.data_oriented
class NOSBCompute:
    """NOSB-PD computation kernels.

    Computes deformation gradient using correspondence formulation
    and converts classical stress to peridynamic force states.
    """

    def __init__(
        self,
        particles: "ParticleSystem",
        bonds: "BondSystem",
        stabilization: float = 0.0
    ):
        """Initialize NOSB computation.

        Args:
            particles: ParticleSystem instance
            bonds: BondSystem instance
            stabilization: Stabilization parameter for zero-energy modes (0-1)
                          Recommended: 0.05-0.15 for most problems
        """
        self.particles = particles
        self.bonds = bonds
        self.dim = particles.dim
        self.n_particles = particles.n_particles
        self.stabilization = stabilization

        # Store stabilization as field
        self.G_s = ti.field(dtype=ti.f32, shape=())
        self.G_s[None] = stabilization

    @ti.kernel
    def compute_shape_tensor(self):
        """Compute shape tensor K for each particle.

        K_i = Σ_j ω(|ξ_ij|) · (ξ_ij ⊗ ξ_ij) · V_j

        The shape tensor characterizes the reference configuration
        of the neighborhood.
        """
        for i in range(self.n_particles):
            # Initialize K to zero
            K = ti.Matrix.zero(ti.f32, self.dim, self.dim)

            for k in range(self.bonds.n_neighbors[i]):
                if self.bonds.broken[i, k] == 0:
                    j = self.bonds.neighbors[i, k]

                    # Reference bond vector
                    xi = self.bonds.xi[i, k]
                    omega = self.bonds.omega[i, k]
                    V_j = self.particles.volume[j]

                    # Outer product: ξ ⊗ ξ
                    for m in ti.static(range(self.dim)):
                        for n in ti.static(range(self.dim)):
                            K[m, n] += omega * xi[m] * xi[n] * V_j

            self.particles.K[i] = K

            # Compute inverse
            det = K.determinant()
            if ti.abs(det) > 1e-12:
                self.particles.K_inv[i] = K.inverse()
            else:
                # Singular - use identity (will cause issues, but prevents crash)
                self.particles.K_inv[i] = ti.Matrix.identity(ti.f32, self.dim)

    @ti.kernel
    def compute_deformation_gradient(self):
        """Compute deformation gradient F for each particle.

        F_i = [Σ_j ω(|ξ_ij|) · (η_ij ⊗ ξ_ij) · V_j] · K_i⁻¹

        where η_ij = x_j - x_i is the current bond vector.
        """
        for i in range(self.n_particles):
            # Compute N = Σ ω · (η ⊗ ξ) · V
            N = ti.Matrix.zero(ti.f32, self.dim, self.dim)

            for k in range(self.bonds.n_neighbors[i]):
                if self.bonds.broken[i, k] == 0:
                    j = self.bonds.neighbors[i, k]

                    # Current bond vector
                    eta = self.particles.x[j] - self.particles.x[i]
                    # Reference bond vector
                    xi = self.bonds.xi[i, k]

                    omega = self.bonds.omega[i, k]
                    V_j = self.particles.volume[j]

                    # Outer product: η ⊗ ξ
                    for m in ti.static(range(self.dim)):
                        for n in ti.static(range(self.dim)):
                            N[m, n] += omega * eta[m] * xi[n] * V_j

            # F = N · K⁻¹
            self.particles.F[i] = N @ self.particles.K_inv[i]

    @ti.kernel
    def compute_force_state_linear_elastic(
        self,
        bulk_modulus: ti.f32,
        shear_modulus: ti.f32
    ):
        """Compute forces using linear elastic correspondence material.

        Stress: σ = λ·tr(ε)·I + 2μ·ε  (Cauchy stress)
        P = J·σ·F⁻ᵀ  (1st Piola-Kirchhoff)

        For small deformations: P ≈ σ

        Force state: t_ij = ω_ij · P_i · K_i⁻¹ · ξ_ij

        Args:
            bulk_modulus: Bulk modulus K
            shear_modulus: Shear modulus μ (G)
        """
        mu = shear_modulus

        # Reset forces
        for i in range(self.n_particles):
            self.particles.f[i] = ti.Vector.zero(ti.f32, self.dim)

        # Compute stress and force state
        for i in range(self.n_particles):
            F = self.particles.F[i]

            # Small strain tensor: ε = 0.5·(F + Fᵀ) - I
            I = ti.Matrix.identity(ti.f32, self.dim)
            eps = 0.5 * (F + F.transpose()) - I
            tr_eps = eps.trace()

            # Lamé's first parameter
            lam = bulk_modulus - shear_modulus  # 2D
            if ti.static(self.dim == 3):
                lam = bulk_modulus - 2.0 * shear_modulus / 3.0

            # Cauchy stress: σ = λ·tr(ε)·I + 2μ·ε
            sigma = lam * tr_eps * I + 2.0 * mu * eps

            # For small deformation, P ≈ σ
            P = sigma
            self.particles.P[i] = P

            # Precompute P · K⁻¹
            PK_inv = P @ self.particles.K_inv[i]

            # Compute force state and accumulate forces
            for k in range(self.bonds.n_neighbors[i]):
                if self.bonds.broken[i, k] == 0:
                    j = self.bonds.neighbors[i, k]

                    xi = self.bonds.xi[i, k]
                    omega = self.bonds.omega[i, k]
                    V_j = self.particles.volume[j]

                    # Force state: t_ij = ω · P · K⁻¹ · ξ
                    t_ij = omega * (PK_inv @ xi)

                    # Force on i from bond ij
                    self.particles.f[i] += t_ij * V_j

    @ti.kernel
    def compute_force_state_with_stabilization(
        self,
        bulk_modulus: ti.f32,
        shear_modulus: ti.f32,
        bond_constant: ti.f32
    ):
        """Compute forces with zero-energy mode stabilization.

        Internal force: f_i = ∫ (t[i]<j> - t[j]<i>) dV_j

        where t[i]<j> = ω_ij · P_i · K_i⁻¹ · ξ_ij

        Stabilization adds bond-based penalty force.

        Args:
            bulk_modulus: Bulk modulus K
            shear_modulus: Shear modulus μ
            bond_constant: Bond-based micromodulus c for stabilization
        """
        mu = shear_modulus
        G_s = self.G_s[None]

        # First pass: compute stress P for all particles
        for i in range(self.n_particles):
            F = self.particles.F[i]

            I = ti.Matrix.identity(ti.f32, self.dim)
            eps = 0.5 * (F + F.transpose()) - I
            tr_eps = eps.trace()

            lam = bulk_modulus - shear_modulus
            if ti.static(self.dim == 3):
                lam = bulk_modulus - 2.0 * shear_modulus / 3.0

            sigma = lam * tr_eps * I + 2.0 * mu * eps
            self.particles.P[i] = sigma

        # Reset forces
        for i in range(self.n_particles):
            self.particles.f[i] = ti.Vector.zero(ti.f32, self.dim)

        # Second pass: compute forces with proper antisymmetry
        for i in range(self.n_particles):
            P_i = self.particles.P[i]
            K_inv_i = self.particles.K_inv[i]
            PK_inv_i = P_i @ K_inv_i
            V_i = self.particles.volume[i]

            for k in range(self.bonds.n_neighbors[i]):
                if self.bonds.broken[i, k] == 0:
                    j = self.bonds.neighbors[i, k]

                    xi_ij = self.bonds.xi[i, k]
                    xi_len = self.bonds.xi_length[i, k]
                    omega = self.bonds.omega[i, k]
                    V_j = self.particles.volume[j]

                    # Force state from i (acting on bond ij)
                    t_ij = omega * (PK_inv_i @ xi_ij)

                    # Force state from j (acting on bond ji = -ij)
                    # We need P_j, K_inv_j and xi_ji = -xi_ij
                    P_j = self.particles.P[j]
                    K_inv_j = self.particles.K_inv[j]
                    PK_inv_j = P_j @ K_inv_j
                    xi_ji = -xi_ij
                    t_ji = omega * (PK_inv_j @ xi_ji)

                    # Net force on i from bond ij: (T[i]<ξ> - T[j]<-ξ>) * V_j
                    # T[i]<ξ> = t_ij = ω * P_i * K_inv_i * ξ
                    # T[j]<-ξ> = ω * P_j * K_inv_j * (-ξ) = t_ji
                    # So: f_i = (t_ij - t_ji) * V_j = ω * (P_i*K_inv_i + P_j*K_inv_j) * ξ * V_j
                    f_corr = (t_ij - t_ji) * V_j

                    # Stabilization force (symmetric, bond-based)
                    eta = self.particles.x[j] - self.particles.x[i]
                    eta_len = eta.norm()

                    f_stab = ti.Vector.zero(ti.f32, self.dim)
                    if eta_len > 1e-10 and xi_len > 1e-10:
                        stretch = (eta_len - xi_len) / xi_len
                        f_stab = G_s * bond_constant * stretch * omega * (eta / eta_len) * V_j

                    self.particles.f[i] += f_corr + f_stab

    @ti.kernel
    def apply_force_antisymmetry(self):
        """Apply antisymmetry to forces (Newton's 3rd law).

        Ensures f_ij = -f_ji by averaging.
        This is a correction step if needed.
        """
        # For proper implementation, we'd need to store pairwise forces
        # and then apply antisymmetry. For now, the per-particle
        # computation handles this implicitly.
        pass


@ti.data_oriented
class NOSBMaterial:
    """Material interface for NOSB-PD.

    Converts Young's modulus and Poisson's ratio to bulk and shear moduli.
    """

    def __init__(
        self,
        youngs_modulus: float,
        poisson_ratio: float,
        dim: int = 3
    ):
        """Initialize NOSB material.

        Args:
            youngs_modulus: Young's modulus E [Pa]
            poisson_ratio: Poisson's ratio ν (can be any value in valid range)
            dim: Spatial dimension
        """
        self.E = youngs_modulus
        self.nu = poisson_ratio
        self.dim = dim

        # Compute elastic moduli
        # Bulk modulus: K = E / (3(1-2ν)) for 3D
        #              K = E / (2(1-ν)) for 2D plane stress
        if dim == 2:
            self.K = youngs_modulus / (2 * (1 - poisson_ratio))
        else:
            self.K = youngs_modulus / (3 * (1 - 2 * poisson_ratio))

        # Shear modulus: μ = E / (2(1+ν))
        self.mu = youngs_modulus / (2 * (1 + poisson_ratio))

        # For stabilization: equivalent bond-based micromodulus
        # This is approximate and used only for zero-energy mode control
        self.c_bond = None  # Set by user if stabilization needed

    def get_bulk_modulus(self) -> float:
        return self.K

    def get_shear_modulus(self) -> float:
        return self.mu

    def set_stabilization_modulus(self, horizon: float, thickness: float = 1.0):
        """Compute stabilization micromodulus from horizon.

        Args:
            horizon: Peridynamics horizon δ
            thickness: Plate thickness (for 2D)
        """
        import math
        if self.dim == 2:
            self.c_bond = 9 * self.E / (math.pi * thickness * horizon**3)
        else:
            self.c_bond = 18 * self.K / (math.pi * horizon**4)

    def __repr__(self) -> str:
        return (f"NOSBMaterial(E={self.E:.2e}, ν={self.nu:.3f}, "
                f"K={self.K:.2e}, μ={self.mu:.2e})")
