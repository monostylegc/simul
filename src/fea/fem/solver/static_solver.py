"""Static equilibrium solver for FEM.

Solves:
- Linear problems: K·u = f (direct solve)
- Nonlinear problems: Newton-Raphson iteration

For linear materials, assembles global stiffness matrix and uses
scipy sparse solver. For nonlinear (hyperelastic) materials,
uses Newton-Raphson with line search.
"""

import taichi as ti
import numpy as np
from typing import Optional, Callable, Dict, TYPE_CHECKING
from scipy import sparse
from scipy.sparse.linalg import spsolve, cg

if TYPE_CHECKING:
    from ..core.mesh import FEMesh
    from ..material.base import MaterialBase


@ti.data_oriented
class StaticSolver:
    """Static equilibrium solver.

    Supports both linear and nonlinear analysis.
    """

    def __init__(
        self,
        mesh: "FEMesh",
        material: "MaterialBase",
        use_newton: bool = True,
        max_iterations: int = 50,
        tol: float = 1e-8
    ):
        """Initialize solver.

        Args:
            mesh: FEMesh instance
            material: Material model
            use_newton: Use Newton-Raphson for nonlinear (default: True)
            max_iterations: Maximum Newton iterations
            tol: Convergence tolerance for residual norm
        """
        self.mesh = mesh
        self.material = material
        self.use_newton = use_newton and not material.is_linear
        self.max_iterations = max_iterations
        self.tol = tol

        # DOF info
        self.n_dof = mesh.n_nodes * mesh.dim
        self.dim = mesh.dim

        # Work arrays for Newton-Raphson
        self._residual = np.zeros(self.n_dof)
        self._du = np.zeros(self.n_dof)

    def solve(
        self,
        external_force_func: Optional[Callable] = None,
        verbose: bool = True
    ) -> Dict:
        """Solve for equilibrium.

        Args:
            external_force_func: Optional function to apply external forces
            verbose: Print convergence info

        Returns:
            Dictionary with convergence info
        """
        if external_force_func is not None:
            external_force_func()

        self.mesh.apply_boundary_conditions()

        if self.material.is_linear:
            return self._solve_linear(verbose)
        elif self.use_newton:
            return self._solve_newton(verbose)
        else:
            return self._solve_nonlinear_simple(verbose)

    def _solve_linear(self, verbose: bool) -> Dict:
        """Solve linear system K·u = f."""
        if verbose:
            print("Assembling stiffness matrix...")

        # Get stiffness matrix
        K = self._assemble_stiffness_matrix()

        # Get force vector
        f_ext = self.mesh.f_ext.to_numpy().flatten()

        # Apply boundary conditions
        K, f = self._apply_bc_to_system(K, f_ext)

        if verbose:
            print(f"Solving {K.shape[0]} DOF system...")

        # Solve
        u = spsolve(K.tocsr(), f)

        # Store result
        u_reshaped = u.reshape(-1, self.dim)
        self.mesh.u.from_numpy(u_reshaped.astype(np.float32))

        # Compute stress
        self.mesh.compute_deformation_gradient()
        self.material.compute_stress(self.mesh)
        self.material.compute_nodal_forces(self.mesh)

        if verbose:
            print("Linear solve completed.")

        return {"converged": True, "iterations": 1}

    def _solve_newton(self, verbose: bool) -> Dict:
        """Solve using Newton-Raphson iteration."""
        if verbose:
            print(f"Newton-Raphson solver (tol={self.tol:.2e})")

        converged = False
        ref_residual = None

        for it in range(self.max_iterations):
            # Update deformation gradient
            self.mesh.compute_deformation_gradient()

            # Compute stress and internal forces
            self.material.compute_stress(self.mesh)
            self.material.compute_nodal_forces(self.mesh)

            # Residual: R = f_ext - f_int
            f_int = self.mesh.f.to_numpy().flatten()
            f_ext = self.mesh.f_ext.to_numpy().flatten()
            residual = f_ext - f_int

            # Apply BC to residual (zero out fixed DOFs)
            fixed = self.mesh.fixed.to_numpy()
            for i in range(self.mesh.n_nodes):
                if fixed[i] == 1:
                    for d in range(self.dim):
                        residual[i * self.dim + d] = 0.0

            res_norm = np.linalg.norm(residual)

            if ref_residual is None:
                ref_residual = res_norm if res_norm > 1e-20 else 1.0

            rel_res = res_norm / ref_residual

            if verbose:
                print(f"  Iter {it}: |R| = {res_norm:.4e}, rel = {rel_res:.4e}")

            if rel_res < self.tol:
                converged = True
                break

            # Assemble tangent stiffness
            K = self._assemble_tangent_stiffness()

            # Apply BC
            K_bc, r_bc = self._apply_bc_to_system(K, residual)

            # Solve for increment
            try:
                du = spsolve(K_bc.tocsr(), r_bc)
            except Exception as e:
                print(f"  Linear solve failed: {e}")
                break

            # Line search (simple backtracking)
            alpha = 1.0
            u_current = self.mesh.u.to_numpy().flatten()

            for ls in range(5):
                u_trial = u_current + alpha * du
                self.mesh.u.from_numpy(u_trial.reshape(-1, self.dim).astype(np.float32))

                self.mesh.compute_deformation_gradient()
                self.material.compute_stress(self.mesh)
                self.material.compute_nodal_forces(self.mesh)

                f_int_new = self.mesh.f.to_numpy().flatten()
                res_new = f_ext - f_int_new
                for i in range(self.mesh.n_nodes):
                    if fixed[i] == 1:
                        for d in range(self.dim):
                            res_new[i * self.dim + d] = 0.0

                if np.linalg.norm(res_new) < res_norm:
                    break
                alpha *= 0.5

        if converged and verbose:
            print(f"Converged in {it+1} iterations")
        elif verbose:
            print(f"Did not converge in {self.max_iterations} iterations")

        return {
            "converged": converged,
            "iterations": it + 1,
            "residual": res_norm,
            "relative_residual": rel_res
        }

    def _solve_nonlinear_simple(self, verbose: bool) -> Dict:
        """Simple fixed-point iteration for nonlinear problems."""
        if verbose:
            print("Fixed-point iteration (stress update)")

        for it in range(self.max_iterations):
            # Update deformation gradient
            self.mesh.compute_deformation_gradient()

            # Compute stress
            self.material.compute_stress(self.mesh)
            self.material.compute_nodal_forces(self.mesh)

            # Get forces
            f_int = self.mesh.f.to_numpy().flatten()
            f_ext = self.mesh.f_ext.to_numpy().flatten()
            residual = f_ext - f_int

            # Apply BC
            fixed = self.mesh.fixed.to_numpy()
            for i in range(self.mesh.n_nodes):
                if fixed[i] == 1:
                    for d in range(self.dim):
                        residual[i * self.dim + d] = 0.0

            res_norm = np.linalg.norm(residual)

            if verbose and it % 10 == 0:
                print(f"  Iter {it}: |R| = {res_norm:.4e}")

            if res_norm < self.tol:
                if verbose:
                    print(f"Converged in {it+1} iterations")
                return {"converged": True, "iterations": it + 1}

            # Use linear stiffness for update
            K = self._assemble_stiffness_matrix()
            K_bc, r_bc = self._apply_bc_to_system(K, residual)

            du = spsolve(K_bc.tocsr(), r_bc)

            # Update displacement
            u = self.mesh.u.to_numpy().flatten()
            u += 0.1 * du  # Damped update
            self.mesh.u.from_numpy(u.reshape(-1, self.dim).astype(np.float32))

        return {"converged": False, "iterations": self.max_iterations}

    def _assemble_stiffness_matrix(self) -> sparse.coo_matrix:
        """Assemble global stiffness matrix using element contributions."""
        C = self.material.get_elasticity_tensor()

        # Collect triplets
        rows = []
        cols = []
        vals = []

        elements = self.mesh.elements.to_numpy()
        dNdX = self.mesh.dNdX.to_numpy()
        gauss_vol = self.mesh.gauss_vol.to_numpy()

        n_gauss = self.mesh.n_gauss
        nodes_per_elem = self.mesh.nodes_per_elem
        dim = self.dim

        for e in range(self.mesh.n_elements):
            # Element stiffness matrix
            ke = np.zeros((nodes_per_elem * dim, nodes_per_elem * dim))

            for g in range(n_gauss):
                gp_idx = e * n_gauss + g
                dN = dNdX[gp_idx]  # (nodes_per_elem, dim)
                vol = gauss_vol[gp_idx]

                # Build B matrix
                B = self._build_B_matrix(dN)

                # ke += B^T * C * B * vol
                ke += vol * (B.T @ C @ B)

            # Assemble into global
            for a in range(nodes_per_elem):
                node_a = elements[e, a]
                for b in range(nodes_per_elem):
                    node_b = elements[e, b]
                    for i in range(dim):
                        for j in range(dim):
                            row = node_a * dim + i
                            col = node_b * dim + j
                            val = ke[a * dim + i, b * dim + j]
                            if abs(val) > 1e-20:
                                rows.append(row)
                                cols.append(col)
                                vals.append(val)

        return sparse.coo_matrix(
            (vals, (rows, cols)),
            shape=(self.n_dof, self.n_dof)
        )

    def _assemble_tangent_stiffness(self) -> sparse.coo_matrix:
        """Assemble tangent stiffness for nonlinear materials.

        For simplicity, uses the same structure as linear stiffness.
        Full geometric stiffness should be added for large deformation.
        """
        # TODO: Add geometric stiffness contribution
        return self._assemble_stiffness_matrix()

    def _build_B_matrix(self, dN: np.ndarray) -> np.ndarray:
        """Build strain-displacement matrix B.

        For 3D:
        B = [dN1/dx  0       0      dN2/dx  ...]
            [0       dN1/dy  0      0       ...]
            [0       0       dN1/dz 0       ...]
            [dN1/dy  dN1/dx  0      ...         ]
            [0       dN1/dz  dN1/dy ...         ]
            [dN1/dz  0       dN1/dx ...         ]
        """
        nodes_per_elem = dN.shape[0]
        dim = self.dim

        if dim == 3:
            B = np.zeros((6, nodes_per_elem * 3))
            for a in range(nodes_per_elem):
                # Normal strains
                B[0, a*3] = dN[a, 0]     # ε_xx
                B[1, a*3+1] = dN[a, 1]   # ε_yy
                B[2, a*3+2] = dN[a, 2]   # ε_zz
                # Shear strains
                B[3, a*3] = dN[a, 1]     # γ_xy
                B[3, a*3+1] = dN[a, 0]
                B[4, a*3+1] = dN[a, 2]   # γ_yz
                B[4, a*3+2] = dN[a, 1]
                B[5, a*3] = dN[a, 2]     # γ_xz
                B[5, a*3+2] = dN[a, 0]
        else:
            B = np.zeros((3, nodes_per_elem * 2))
            for a in range(nodes_per_elem):
                B[0, a*2] = dN[a, 0]     # ε_xx
                B[1, a*2+1] = dN[a, 1]   # ε_yy
                B[2, a*2] = dN[a, 1]     # γ_xy
                B[2, a*2+1] = dN[a, 0]

        return B

    def _apply_bc_to_system(
        self,
        K: sparse.coo_matrix,
        f: np.ndarray
    ) -> tuple:
        """Apply boundary conditions to system.

        Uses penalty method for simplicity.
        """
        K = K.tocsr()
        f = f.copy()

        fixed = self.mesh.fixed.to_numpy()
        fixed_vals = self.mesh.fixed_value.to_numpy()

        penalty = 1e30

        for i in range(self.mesh.n_nodes):
            if fixed[i] == 1:
                for d in range(self.dim):
                    dof = i * self.dim + d
                    K[dof, dof] += penalty
                    f[dof] = penalty * fixed_vals[i, d]

        return K, f

    def get_mises_stress(self) -> np.ndarray:
        """Compute and return nodal von Mises stress."""
        self.mesh.compute_mises_stress()
        return self.mesh.mises.to_numpy()

    def get_total_energy(self) -> float:
        """Get total strain energy (for hyperelastic materials)."""
        if hasattr(self.material, 'compute_total_energy'):
            return float(self.material.compute_total_energy(
                self.mesh.F,
                self.mesh.gauss_vol,
                self.mesh.n_elements * self.mesh.n_gauss
            ))
        return 0.0
