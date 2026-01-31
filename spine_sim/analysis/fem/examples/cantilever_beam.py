"""Cantilever beam example with FEM.

Simple 3D cantilever beam under tip load.
Demonstrates linear elastic analysis with TET4 elements.
"""

import taichi as ti
import numpy as np


def create_beam_mesh(length: float, width: float, height: float,
                     nx: int, ny: int, nz: int):
    """Create a regular mesh of tetrahedra for a beam.

    Args:
        length: Beam length (x-direction)
        width: Beam width (y-direction)
        height: Beam height (z-direction)
        nx, ny, nz: Number of divisions in each direction

    Returns:
        nodes: (n_nodes, 3) array
        elements: (n_elements, 4) array (TET4)
    """
    # Create nodes
    x = np.linspace(0, length, nx + 1)
    y = np.linspace(0, width, ny + 1)
    z = np.linspace(0, height, nz + 1)

    nodes = []
    node_idx = {}

    for i, xi in enumerate(x):
        for j, yj in enumerate(y):
            for k, zk in enumerate(z):
                node_idx[(i, j, k)] = len(nodes)
                nodes.append([xi, yj, zk])

    nodes = np.array(nodes, dtype=np.float32)

    # Create tetrahedra (5 tets per hex cell)
    elements = []

    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                # 8 corners of hex cell
                n000 = node_idx[(i, j, k)]
                n100 = node_idx[(i+1, j, k)]
                n010 = node_idx[(i, j+1, k)]
                n110 = node_idx[(i+1, j+1, k)]
                n001 = node_idx[(i, j, k+1)]
                n101 = node_idx[(i+1, j, k+1)]
                n011 = node_idx[(i, j+1, k+1)]
                n111 = node_idx[(i+1, j+1, k+1)]

                # 5 tetrahedra per hex (consistent diagonal)
                elements.append([n000, n100, n110, n111])
                elements.append([n000, n110, n010, n111])
                elements.append([n000, n010, n011, n111])
                elements.append([n000, n011, n001, n111])
                elements.append([n000, n001, n101, n111])

    elements = np.array(elements, dtype=np.int32)

    return nodes, elements


def main():
    """Run cantilever beam analysis."""
    # Initialize Taichi
    ti.init(arch=ti.gpu, default_fp=ti.f32)

    from spine_sim.analysis.fem.core.mesh import FEMesh
    from spine_sim.analysis.fem.core.element import ElementType
    from spine_sim.analysis.fem.material.linear_elastic import LinearElastic
    from spine_sim.analysis.fem.solver.static_solver import StaticSolver

    # Beam parameters
    L = 10.0  # length
    W = 1.0   # width
    H = 1.0   # height

    # Material
    E = 2.1e11  # Steel Young's modulus [Pa]
    nu = 0.3    # Poisson's ratio

    # Create mesh (finer mesh for better accuracy)
    print("Creating mesh...")
    nx, ny, nz = 20, 4, 4
    nodes, elements = create_beam_mesh(L, W, H, nx, ny, nz)

    n_nodes = len(nodes)
    n_elements = len(elements)
    print(f"Mesh: {n_nodes} nodes, {n_elements} elements")

    # Create FEM mesh
    mesh = FEMesh(n_nodes=n_nodes, n_elements=n_elements, element_type=ElementType.TET4)
    mesh.initialize_from_numpy(nodes, elements)

    # Fixed boundary: x = 0 face
    fixed_nodes = np.where(nodes[:, 0] < 1e-6)[0]
    print(f"Fixed nodes: {len(fixed_nodes)}")
    mesh.set_fixed_nodes(fixed_nodes)

    # Load: tip force at x = L
    tip_nodes = np.where(nodes[:, 0] > L - 1e-6)[0]
    tip_force = -1e6  # [N] downward force
    force_per_node = tip_force / len(tip_nodes)
    forces = np.zeros((len(tip_nodes), 3), dtype=np.float32)
    forces[:, 2] = force_per_node  # z-direction
    mesh.set_nodal_forces(tip_nodes, forces)
    print(f"Tip nodes: {len(tip_nodes)}, force per node: {force_per_node:.2f} N")

    # Create material and solver
    material = LinearElastic(youngs_modulus=E, poisson_ratio=nu, dim=3)
    solver = StaticSolver(mesh, material)

    # Solve
    print("\nSolving...")
    result = solver.solve(verbose=True)

    # Results
    u = mesh.get_displacements()

    print("\n=== Results ===")
    print(f"Converged: {result['converged']}")
    print(f"Max displacement: {np.max(np.abs(u)):.6e} m")

    # Tip deflection
    tip_disp = u[tip_nodes, 2]
    mean_tip_disp = np.mean(tip_disp)
    print(f"Mean tip deflection (z): {mean_tip_disp:.6e} m")

    # Analytical solution for cantilever beam tip deflection
    # δ = PL³/(3EI) where I = bh³/12
    I = W * H**3 / 12
    P = tip_force
    delta_analytical = P * L**3 / (3 * E * I)
    print(f"Analytical tip deflection: {delta_analytical:.6e} m")
    print(f"Error: {abs(mean_tip_disp - delta_analytical)/abs(delta_analytical)*100:.1f}%")

    return result


if __name__ == "__main__":
    main()
