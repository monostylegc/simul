"""Finite element mesh data structure.

Uses Structure of Arrays (SoA) layout for GPU efficiency.
"""

import taichi as ti
import numpy as np
from typing import Optional, List, Tuple, TYPE_CHECKING
from dataclasses import dataclass

from .element import ElementType, get_element_info, ElementInfo

if TYPE_CHECKING:
    pass


@ti.data_oriented
class FEMesh:
    """Finite element mesh with Taichi fields.

    Stores nodal coordinates, element connectivity, and field data
    in GPU-friendly SoA layout.
    """

    def __init__(
        self,
        n_nodes: int,
        n_elements: int,
        element_type: ElementType,
        dtype: ti.types.primitive_types = ti.f64
    ):
        """Initialize mesh data structure.

        Args:
            n_nodes: Number of nodes
            n_elements: Number of elements
            element_type: Type of elements
            dtype: Data type for floating point fields
        """
        self.n_nodes = n_nodes
        self.n_elements = n_elements
        self.element_type = element_type
        self.elem_info: ElementInfo = get_element_info(element_type)
        self.dim = self.elem_info.dim
        self.nodes_per_elem = self.elem_info.n_nodes
        self.n_gauss = self.elem_info.n_gauss
        self.dtype = dtype

        # Nodal fields
        self.X = ti.Vector.field(self.dim, dtype=dtype, shape=n_nodes)  # Reference coords
        self.x = ti.Vector.field(self.dim, dtype=dtype, shape=n_nodes)  # Current coords
        self.u = ti.Vector.field(self.dim, dtype=dtype, shape=n_nodes, needs_grad=True)  # Displacement
        self.f = ti.Vector.field(self.dim, dtype=dtype, shape=n_nodes)  # Force
        self.f_ext = ti.Vector.field(self.dim, dtype=dtype, shape=n_nodes)  # External force

        # 경계조건 (자유도별 고정 플래그)
        # fixed[node, dof] = 1: 해당 DOF 고정, 0: 자유
        self.fixed = ti.field(dtype=ti.i32, shape=(n_nodes, self.dim))
        self.fixed_value = ti.Vector.field(self.dim, dtype=dtype, shape=n_nodes)

        # Element connectivity
        self.elements = ti.Vector.field(self.nodes_per_elem, dtype=ti.i32, shape=n_elements)

        # Gauss point fields
        total_gauss = n_elements * self.n_gauss
        self.F = ti.Matrix.field(self.dim, self.dim, dtype=dtype, shape=total_gauss)  # Deformation gradient
        self.stress = ti.Matrix.field(self.dim, self.dim, dtype=dtype, shape=total_gauss)  # Cauchy stress
        self.strain = ti.Matrix.field(self.dim, self.dim, dtype=dtype, shape=total_gauss)  # Small strain
        self.gauss_vol = ti.field(dtype=dtype, shape=total_gauss)  # Integration weights * det(J)

        # Shape function derivatives at Gauss points (in reference config)
        # dN/dX for each Gauss point
        self.dNdX = ti.Matrix.field(
            self.nodes_per_elem, self.dim,
            dtype=dtype,
            shape=total_gauss
        )

        # Material ID per element (for multi-material)
        self.material_id = ti.field(dtype=ti.i32, shape=n_elements)

        # Element volume (reference)
        self.elem_vol = ti.field(dtype=dtype, shape=n_elements)

        # Mises stress at nodes (for visualization)
        self.mises = ti.field(dtype=dtype, shape=n_nodes)

    def initialize_from_numpy(
        self,
        nodes: np.ndarray,
        elements: np.ndarray,
        material_ids: Optional[np.ndarray] = None
    ):
        """Initialize mesh from numpy arrays.

        Args:
            nodes: Node coordinates (n_nodes, dim)
            elements: Element connectivity (n_elements, nodes_per_elem)
            material_ids: Material IDs per element (n_elements,)
        """
        assert nodes.shape[0] == self.n_nodes
        assert nodes.shape[1] == self.dim
        assert elements.shape[0] == self.n_elements
        assert elements.shape[1] == self.nodes_per_elem

        # Copy to fields
        self.X.from_numpy(nodes.astype(np.float64))
        self.x.from_numpy(nodes.astype(np.float64))
        self.elements.from_numpy(elements.astype(np.int32))

        if material_ids is not None:
            self.material_id.from_numpy(material_ids.astype(np.int32))

        # Initialize displacements to zero
        self.u.fill(0)
        self.f.fill(0)
        self.f_ext.fill(0)
        self.fixed.fill(0)

        # Compute shape function derivatives and volumes
        self._compute_reference_quantities()

    @ti.kernel
    def _compute_reference_quantities(self):
        """Compute shape function derivatives and volumes at Gauss points."""
        for e in range(self.n_elements):
            for g in range(self.n_gauss):
                gp_idx = e * self.n_gauss + g

                # Get Gauss point in natural coordinates
                gp = self._get_gauss_point_values(g)
                xi, eta, zeta, w = gp[0], gp[1], gp[2], gp[3]

                # Compute Jacobian and its inverse
                J = self._compute_jacobian(e, xi, eta, zeta)
                det_J = J.determinant()
                J_inv = J.inverse()

                # Compute dN/dX = dN/dxi * J_inv
                dNdxi = self._get_shape_derivatives(xi, eta, zeta)
                dNdX = dNdxi @ J_inv

                # Store
                self.dNdX[gp_idx] = dNdX
                self.gauss_vol[gp_idx] = w * ti.abs(det_J)

            # Element volume (sum of Gauss volumes)
            vol = 0.0
            for g in range(self.n_gauss):
                vol += self.gauss_vol[e * self.n_gauss + g]
            self.elem_vol[e] = vol

    @ti.func
    def _get_gauss_point_values(self, g: int) -> ti.types.vector(4, ti.f64):
        """Get Gauss point coordinates and weight.

        Returns:
            Vector of (xi, eta, zeta, weight)
        """
        result = ti.Vector([0.0, 0.0, 0.0, 1.0], dt=ti.f64)

        if ti.static(self.element_type == ElementType.TET4):
            # 1-point rule for TET4
            result = ti.Vector([0.25, 0.25, 0.25, 1.0 / 6.0], dt=ti.f64)
        elif ti.static(self.element_type == ElementType.TET10):
            # 4-point rule for TET10
            a = 0.5854101966249685
            b = 0.1381966011250105
            w = 0.25 / 6.0
            if g == 0:
                result = ti.Vector([a, b, b, w], dt=ti.f64)
            elif g == 1:
                result = ti.Vector([b, a, b, w], dt=ti.f64)
            elif g == 2:
                result = ti.Vector([b, b, a, w], dt=ti.f64)
            else:
                result = ti.Vector([b, b, b, w], dt=ti.f64)
        elif ti.static(self.element_type == ElementType.TRI3 or
                       self.element_type == ElementType.TRI3_PE):
            # 1-point rule for TRI3
            result = ti.Vector([1.0/3.0, 1.0/3.0, 0.0, 0.5], dt=ti.f64)
        elif ti.static(self.element_type == ElementType.HEX8):
            # 2x2x2 Gauss rule for HEX8 (8점)
            gp = 0.5773502691896257  # 1/sqrt(3)
            # 각 점의 가중치는 1.0
            if g == 0:
                result = ti.Vector([-gp, -gp, -gp, 1.0], dt=ti.f64)
            elif g == 1:
                result = ti.Vector([+gp, -gp, -gp, 1.0], dt=ti.f64)
            elif g == 2:
                result = ti.Vector([+gp, +gp, -gp, 1.0], dt=ti.f64)
            elif g == 3:
                result = ti.Vector([-gp, +gp, -gp, 1.0], dt=ti.f64)
            elif g == 4:
                result = ti.Vector([-gp, -gp, +gp, 1.0], dt=ti.f64)
            elif g == 5:
                result = ti.Vector([+gp, -gp, +gp, 1.0], dt=ti.f64)
            elif g == 6:
                result = ti.Vector([+gp, +gp, +gp, 1.0], dt=ti.f64)
            else:
                result = ti.Vector([-gp, +gp, +gp, 1.0], dt=ti.f64)
        elif ti.static(self.element_type == ElementType.QUAD4 or
                       self.element_type == ElementType.QUAD4_PE):
            # 2x2 Gauss rule for QUAD4 (4점)
            gp = 0.5773502691896257  # 1/sqrt(3)
            if g == 0:
                result = ti.Vector([-gp, -gp, 0.0, 1.0], dt=ti.f64)
            elif g == 1:
                result = ti.Vector([+gp, -gp, 0.0, 1.0], dt=ti.f64)
            elif g == 2:
                result = ti.Vector([+gp, +gp, 0.0, 1.0], dt=ti.f64)
            else:
                result = ti.Vector([-gp, +gp, 0.0, 1.0], dt=ti.f64)

        return result

    @ti.func
    def _get_shape_derivatives(self, xi: ti.f64, eta: ti.f64, zeta: ti.f64):
        """Get shape function derivatives in natural coordinates.

        Returns:
            dN/d(xi,eta,zeta) matrix of shape (nodes_per_elem, dim)
        """
        dN = ti.Matrix.zero(self.dtype, self.nodes_per_elem, self.dim)

        if ti.static(self.element_type == ElementType.TET4):
            # Constant derivatives for linear tet
            dN[0, 0] = -1.0; dN[0, 1] = -1.0; dN[0, 2] = -1.0
            dN[1, 0] = 1.0;  dN[1, 1] = 0.0;  dN[1, 2] = 0.0
            dN[2, 0] = 0.0;  dN[2, 1] = 1.0;  dN[2, 2] = 0.0
            dN[3, 0] = 0.0;  dN[3, 1] = 0.0;  dN[3, 2] = 1.0

        elif ti.static(self.element_type == ElementType.TRI3 or
                       self.element_type == ElementType.TRI3_PE):
            # Constant derivatives for linear triangle
            dN[0, 0] = -1.0; dN[0, 1] = -1.0
            dN[1, 0] = 1.0;  dN[1, 1] = 0.0
            dN[2, 0] = 0.0;  dN[2, 1] = 1.0

        elif ti.static(self.element_type == ElementType.HEX8):
            # HEX8: 8노드 육면체
            # dN_i/dξ = (1/8) * ξ_i * (1 + η_i·η) * (1 + ζ_i·ζ)
            # dN_i/dη = (1/8) * (1 + ξ_i·ξ) * η_i * (1 + ζ_i·ζ)
            # dN_i/dζ = (1/8) * (1 + ξ_i·ξ) * (1 + η_i·η) * ζ_i
            # 노드 좌표: 0:(-1,-1,-1), 1:(+1,-1,-1), 2:(+1,+1,-1), 3:(-1,+1,-1)
            #           4:(-1,-1,+1), 5:(+1,-1,+1), 6:(+1,+1,+1), 7:(-1,+1,+1)
            xi_n = ti.Vector([-1.0, 1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0], dt=ti.f64)
            eta_n = ti.Vector([-1.0, -1.0, 1.0, 1.0, -1.0, -1.0, 1.0, 1.0], dt=ti.f64)
            zeta_n = ti.Vector([-1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0], dt=ti.f64)

            for i in ti.static(range(8)):
                xi_i = xi_n[i]
                eta_i = eta_n[i]
                zeta_i = zeta_n[i]

                dN[i, 0] = 0.125 * xi_i * (1.0 + eta_i * eta) * (1.0 + zeta_i * zeta)
                dN[i, 1] = 0.125 * (1.0 + xi_i * xi) * eta_i * (1.0 + zeta_i * zeta)
                dN[i, 2] = 0.125 * (1.0 + xi_i * xi) * (1.0 + eta_i * eta) * zeta_i

        elif ti.static(self.element_type == ElementType.QUAD4 or
                       self.element_type == ElementType.QUAD4_PE):
            # QUAD4: 4노드 사각형
            # dN_i/dξ = (1/4) * ξ_i * (1 + η_i·η)
            # dN_i/dη = (1/4) * (1 + ξ_i·ξ) * η_i
            # 노드 좌표: 0:(-1,-1), 1:(+1,-1), 2:(+1,+1), 3:(-1,+1)
            xi_n = ti.Vector([-1.0, 1.0, 1.0, -1.0], dt=ti.f64)
            eta_n = ti.Vector([-1.0, -1.0, 1.0, 1.0], dt=ti.f64)

            for i in ti.static(range(4)):
                xi_i = xi_n[i]
                eta_i = eta_n[i]

                dN[i, 0] = 0.25 * xi_i * (1.0 + eta_i * eta)
                dN[i, 1] = 0.25 * (1.0 + xi_i * xi) * eta_i

        return dN

    @ti.func
    def _compute_jacobian(self, e: int, xi: ti.f64, eta: ti.f64, zeta: ti.f64):
        """Compute Jacobian matrix J = dX/d(xi,eta,zeta)."""
        J = ti.Matrix.zero(self.dtype, self.dim, self.dim)
        dNdxi = self._get_shape_derivatives(xi, eta, zeta)

        for a in ti.static(range(self.nodes_per_elem)):
            node = self.elements[e][a]
            X_a = self.X[node]
            for i in ti.static(range(self.dim)):
                for j in ti.static(range(self.dim)):
                    J[i, j] += X_a[i] * dNdxi[a, j]

        return J

    @ti.kernel
    def compute_deformation_gradient(self):
        """Compute deformation gradient F at all Gauss points.

        F = I + du/dX = I + Σ u_a ⊗ (dN_a/dX)
        """
        for e in range(self.n_elements):
            for g in range(self.n_gauss):
                gp_idx = e * self.n_gauss + g
                dNdX = self.dNdX[gp_idx]

                # F = I + grad(u)
                F = ti.Matrix.identity(self.dtype, self.dim)
                for a in ti.static(range(self.nodes_per_elem)):
                    node = self.elements[e][a]
                    u_a = self.u[node]
                    for i in ti.static(range(self.dim)):
                        for j in ti.static(range(self.dim)):
                            F[i, j] += u_a[i] * dNdX[a, j]

                self.F[gp_idx] = F

    @ti.kernel
    def update_current_config(self):
        """Update current coordinates: x = X + u."""
        for i in range(self.n_nodes):
            self.x[i] = self.X[i] + self.u[i]

    @ti.kernel
    def apply_boundary_conditions(self):
        """Dirichlet 경계조건 적용 (자유도별)."""
        for i in range(self.n_nodes):
            for d in ti.static(range(self.dim)):
                if self.fixed[i, d] == 1:
                    self.u[i][d] = self.fixed_value[i][d]

    def set_fixed_nodes(
        self,
        node_ids: np.ndarray,
        values: Optional[np.ndarray] = None,
        dofs: Optional[list] = None,
    ):
        """고정(Dirichlet) 경계조건 설정.

        Args:
            node_ids: 고정할 노드 인덱스
            values: 고정 변위값 (n_fixed, dim). None이면 0.
            dofs: 고정할 자유도 리스트. None이면 모든 DOF 고정.
                  예: [0] → x만 고정 (롤러), [0,2] → x,z 고정
        """
        # 인덱스 범위 검증
        from ..validation import validate_bc_indices
        validate_bc_indices(node_ids, self.n_nodes, "고정 경계조건")

        fixed = np.zeros((self.n_nodes, self.dim), dtype=np.int32)
        if dofs is None:
            # 모든 DOF 고정 (하위 호환)
            fixed[node_ids, :] = 1
        else:
            for d in dofs:
                fixed[np.asarray(node_ids), d] = 1
        self.fixed.from_numpy(fixed)

        fixed_vals = np.zeros((self.n_nodes, self.dim), dtype=np.float64)
        if values is not None:
            fixed_vals[node_ids] = values
        self.fixed_value.from_numpy(fixed_vals)

    def set_fixed_dofs(
        self,
        dof_indices: np.ndarray,
        values: Optional[np.ndarray] = None,
    ):
        """자유도 인덱스로 직접 경계조건 설정.

        Args:
            dof_indices: 고정할 DOF 인덱스 (node*dim + d)
            values: 고정 변위값 (각 DOF별). None이면 0.
        """
        dof_indices = np.asarray(dof_indices, dtype=np.int64)
        fixed = np.zeros((self.n_nodes, self.dim), dtype=np.int32)
        fixed_vals = np.zeros((self.n_nodes, self.dim), dtype=np.float64)

        for i, dof in enumerate(dof_indices):
            node = int(dof // self.dim)
            d = int(dof % self.dim)
            fixed[node, d] = 1
            if values is not None:
                fixed_vals[node, d] = values[i]

        self.fixed.from_numpy(fixed)
        self.fixed_value.from_numpy(fixed_vals)

    def set_nodal_forces(self, node_ids: np.ndarray, forces: np.ndarray):
        """Set external nodal forces.

        Args:
            node_ids: Node indices
            forces: Force vectors (n_nodes, dim)
        """
        # 인덱스 범위 검증
        from ..validation import validate_bc_indices
        validate_bc_indices(node_ids, self.n_nodes, "하중 경계조건")

        f_ext = np.zeros((self.n_nodes, self.dim), dtype=np.float64)
        f_ext[node_ids] = forces
        self.f_ext.from_numpy(f_ext)

    def add_pressure_load(
        self,
        element_ids: np.ndarray,
        face_ids: np.ndarray,
        pressure: float,
    ):
        """요소 면에 압력 하중 추가.

        기존 f_ext에 압력 등가 절점력을 누적한다.

        Args:
            element_ids: 압력이 작용하는 요소 인덱스
            face_ids: 각 요소에서의 면 번호
            pressure: 균일 압력 (양수 = 압축)
        """
        from ..solver.surface_load import compute_pressure_load

        f_pressure = compute_pressure_load(
            self, element_ids, face_ids, pressure
        )

        # 기존 f_ext에 누적
        f_ext = self.f_ext.to_numpy()
        f_ext += f_pressure
        self.f_ext.from_numpy(f_ext)

    def find_surface_faces(
        self,
        axis: int,
        value: float,
        tol: Optional[float] = None,
    ):
        """좌표면에 위치한 요소 면 자동 검색.

        Args:
            axis: 좌표축 (0=x, 1=y, 2=z)
            value: 검색할 좌표값
            tol: 허용 오차

        Returns:
            (face_elements, face_ids) 튜플
        """
        from ..solver.surface_load import find_surface_faces as _find

        return _find(self, axis, value, tol)

    def get_displacements(self) -> np.ndarray:
        """Get nodal displacements as numpy array."""
        return self.u.to_numpy()

    def get_nodal_forces(self) -> np.ndarray:
        """Get internal nodal forces as numpy array."""
        return self.f.to_numpy()

    def get_stress(self) -> np.ndarray:
        """Get stress tensors at Gauss points."""
        return self.stress.to_numpy()

    @ti.kernel
    def compute_mises_stress(self):
        """Compute von Mises stress at nodes (extrapolated from Gauss points)."""
        # First reset
        for i in range(self.n_nodes):
            self.mises[i] = 0.0

        # Accumulate from elements
        count = ti.Vector.zero(ti.i32, self.n_nodes)

        for e in range(self.n_elements):
            # Average stress in element
            s_avg = ti.Matrix.zero(self.dtype, self.dim, self.dim)
            for g in range(self.n_gauss):
                s_avg += self.stress[e * self.n_gauss + g]
            s_avg /= float(self.n_gauss)

            # Von Mises
            if ti.static(self.dim == 3):
                s11, s22, s33 = s_avg[0, 0], s_avg[1, 1], s_avg[2, 2]
                s12, s23, s13 = s_avg[0, 1], s_avg[1, 2], s_avg[0, 2]
                vm = ti.sqrt(0.5 * ((s11-s22)**2 + (s22-s33)**2 + (s33-s11)**2
                                    + 6*(s12**2 + s23**2 + s13**2)))
            else:
                s11, s22, s12 = s_avg[0, 0], s_avg[1, 1], s_avg[0, 1]
                vm = ti.sqrt(s11**2 - s11*s22 + s22**2 + 3*s12**2)

            # Distribute to nodes
            for a in ti.static(range(self.nodes_per_elem)):
                node = self.elements[e][a]
                ti.atomic_add(self.mises[node], vm)

        # Average (simple nodal average)
        # Note: count should be computed separately, using elem connectivity
