"""Basic tests for FEM module."""

import pytest
import numpy as np
import taichi as ti

# Initialize Taichi once for all tests
ti.init(arch=ti.cpu, default_fp=ti.f32)


def test_element_types():
    """Test element type definitions."""
    from src.fea.fem.core.element import (
        ElementType, get_element_info, get_shape_derivatives_tet4
    )

    # TET4 element
    info = get_element_info(ElementType.TET4)
    assert info.n_nodes == 4
    assert info.dim == 3
    assert info.n_gauss == 1

    # Shape function derivatives should be constant
    dN = get_shape_derivatives_tet4()
    assert dN.shape == (4, 3)
    # Sum of shape function derivatives = 0
    assert np.allclose(dN.sum(axis=0), [0, 0, 0])


def test_mesh_creation():
    """Test mesh data structure creation."""
    from src.fea.fem.core.mesh import FEMesh
    from src.fea.fem.core.element import ElementType

    # Simple tetrahedron
    nodes = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0]
    ], dtype=np.float32)

    elements = np.array([[0, 1, 2, 3]], dtype=np.int32)

    mesh = FEMesh(
        n_nodes=4,
        n_elements=1,
        element_type=ElementType.TET4
    )
    mesh.initialize_from_numpy(nodes, elements)

    # Check dimensions
    assert mesh.n_nodes == 4
    assert mesh.n_elements == 1
    assert mesh.dim == 3

    # Volume of unit tetrahedron = 1/6
    vol = mesh.elem_vol.to_numpy()[0]
    assert np.isclose(vol, 1.0/6.0, rtol=0.1), f"Volume = {vol}, expected 1/6"


def test_linear_elastic_material():
    """Test linear elastic material properties."""
    from src.fea.fem.material.linear_elastic import LinearElastic

    E = 1e6
    nu = 0.3

    mat = LinearElastic(E, nu, dim=3)

    # Check Lamé parameters
    expected_mu = E / (2 * (1 + nu))
    expected_lam = E * nu / ((1 + nu) * (1 - 2*nu))

    assert np.isclose(mat.mu, expected_mu)
    assert np.isclose(mat.lam, expected_lam)

    # Check elasticity tensor symmetry
    C = mat.get_elasticity_tensor()
    assert np.allclose(C, C.T)


def test_neo_hookean_material():
    """Test Neo-Hookean material."""
    from src.fea.fem.material.neo_hookean import NeoHookean

    E = 1e6
    nu = 0.3

    mat = NeoHookean(E, nu, dim=3)

    # Check it's marked as nonlinear
    assert not mat.is_linear

    # Initial elasticity tensor should match linear elastic
    from src.fea.fem.material.linear_elastic import LinearElastic
    lin_mat = LinearElastic(E, nu, dim=3)

    C_neo = mat.get_elasticity_tensor()
    C_lin = lin_mat.get_elasticity_tensor()

    assert np.allclose(C_neo, C_lin)


def test_solver_linear_tet():
    """Test linear solver on simple tension problem."""
    from src.fea.fem.core.mesh import FEMesh
    from src.fea.fem.core.element import ElementType
    from src.fea.fem.material.linear_elastic import LinearElastic
    from src.fea.fem.solver.static_solver import StaticSolver

    # 2-element mesh (two tetrahedra sharing a face)
    nodes = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.5, 1.0, 0.0],
        [0.5, 0.5, 1.0],
        [0.5, 0.5, -1.0],
    ], dtype=np.float32)

    elements = np.array([
        [0, 1, 2, 3],
        [0, 1, 2, 4],
    ], dtype=np.int32)

    mesh = FEMesh(n_nodes=5, n_elements=2, element_type=ElementType.TET4)
    mesh.initialize_from_numpy(nodes, elements)

    # Fix bottom face nodes (0, 1, 2) - need 3 non-collinear points in 3D
    mesh.set_fixed_nodes(np.array([0, 1, 2]))

    # Apply force on top node (3)
    mesh.set_nodal_forces(np.array([3]), np.array([[0.0, 0.0, 100.0]]))

    # Create material and solver
    material = LinearElastic(youngs_modulus=1e6, poisson_ratio=0.3, dim=3)
    solver = StaticSolver(mesh, material)

    # Solve
    result = solver.solve(verbose=False)

    assert result["converged"]

    # Check displacement direction (should move in +z)
    u = mesh.get_displacements()
    assert u[3, 2] > 0, "Node 3 should move in +z direction"


def test_2d_triangle():
    """Test 2D triangular element."""
    from src.fea.fem.core.mesh import FEMesh
    from src.fea.fem.core.element import ElementType
    from src.fea.fem.material.linear_elastic import LinearElastic

    # Simple triangle
    nodes = np.array([
        [0.0, 0.0],
        [1.0, 0.0],
        [0.5, 1.0],
    ], dtype=np.float32)

    elements = np.array([[0, 1, 2]], dtype=np.int32)

    mesh = FEMesh(n_nodes=3, n_elements=1, element_type=ElementType.TRI3)
    mesh.initialize_from_numpy(nodes, elements)

    # Check area (should be 0.5)
    vol = mesh.elem_vol.to_numpy()[0]
    assert np.isclose(vol, 0.5, rtol=0.1), f"Area = {vol}, expected 0.5"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
