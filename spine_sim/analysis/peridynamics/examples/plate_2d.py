"""2D plate tension example for bond-based peridynamics validation.

This example creates a rectangular plate under uniaxial tension and
compares the displacement field with analytical solution.

Usage:
    uv run python -m spine_sim.analysis.peridynamics.examples.plate_2d
"""

import taichi as ti
import numpy as np
import math

# Initialize Taichi
ti.init(arch=ti.gpu, default_fp=ti.f32)


def create_plate_simulation():
    """Create and run a 2D plate tension simulation."""
    from ..core.particles import ParticleSystem
    from ..core.bonds import BondSystem
    from ..core.neighbor import NeighborSearch
    from ..core.damage import DamageModel
    from ..material.linear_elastic import LinearElasticMaterial
    from ..solver.explicit import ExplicitSolver

    # Plate dimensions
    L = 0.1  # Length [m]
    W = 0.05  # Width [m]
    thickness = 0.001  # Thickness [m]

    # Discretization
    spacing = 0.002  # Particle spacing [m]
    horizon = 3.015 * spacing  # Horizon (typically 3 * spacing)

    # Grid points
    nx = int(L / spacing) + 1
    ny = int(W / spacing) + 1
    n_particles = nx * ny

    print(f"Plate: {L}m x {W}m")
    print(f"Particles: {nx} x {ny} = {n_particles}")
    print(f"Spacing: {spacing}m, Horizon: {horizon}m")

    # Material properties (aluminum-like)
    E = 70e9  # Young's modulus [Pa]
    nu = 0.25  # Poisson's ratio (fixed for 2D bond-based PD)
    rho = 2700  # Density [kg/m^3]
    G_c = 1000  # Fracture energy [J/m^2]

    # Compute critical stretch
    s_c = DamageModel.compute_critical_stretch(E, G_c, horizon, dim=2)
    print(f"Critical stretch: {s_c:.6f}")

    # Create material
    material = LinearElasticMaterial(E, nu, horizon, thickness, dim=2)
    c = material.get_micromodulus()
    print(f"Micromodulus: {c:.2e} N/m^6")

    # Estimate stable time step
    dt = ExplicitSolver.estimate_stable_dt(E, rho, horizon, spacing, safety_factor=0.5)
    print(f"Time step: {dt:.2e} s")

    # Create particle system
    particles = ParticleSystem(n_particles, dim=2)
    particles.initialize_from_grid(
        origin=(0.0, 0.0),
        spacing=spacing,
        n_points=(nx, ny),
        density=rho
    )

    # Create neighbor search
    neighbor_search = NeighborSearch(
        domain_min=(-horizon, -horizon),
        domain_max=(L + horizon, W + horizon),
        horizon=horizon,
        max_particles=n_particles,
        max_neighbors=64,
        dim=2
    )

    # Build neighbor list
    neighbor_search.build(particles.X, n_particles)

    # Create bond system
    bonds = BondSystem(n_particles, max_bonds=64, dim=2)
    bonds.build_from_neighbor_search(particles, neighbor_search, horizon)

    # Print neighbor statistics
    n_neighbors = neighbor_search.get_all_neighbor_counts()
    print(f"Neighbors per particle: min={n_neighbors.min()}, max={n_neighbors.max()}, avg={n_neighbors.mean():.1f}")

    # Set boundary conditions
    # Fix left edge (x = 0)
    positions = particles.X.to_numpy()
    left_indices = np.where(positions[:, 0] < spacing * 0.5)[0]
    right_indices = np.where(positions[:, 0] > L - spacing * 0.5)[0]

    particles.set_fixed_particles(left_indices)
    print(f"Fixed particles (left edge): {len(left_indices)}")
    print(f"Loaded particles (right edge): {len(right_indices)}")

    # Create damage model
    damage_model = DamageModel(critical_stretch=s_c, dim=2)

    # Create solver
    solver = ExplicitSolver(
        particles, bonds,
        micromodulus=c,
        dt=dt,
        damping=0.001  # Small damping for quasi-static
    )

    # Applied stress
    applied_stress = 10e6  # 10 MPa

    # Force per right-edge particle
    # Total force = stress * area = stress * W * h
    total_force = applied_stress * W * thickness
    force_per_particle = total_force / len(right_indices)

    print(f"Applied stress: {applied_stress/1e6:.1f} MPa")
    print(f"Force per particle: {force_per_particle:.2f} N")

    # Apply forces to right edge
    @ti.kernel
    def apply_traction(
        particles: ti.template(),
        right_mask: ti.template(),
        force_x: ti.f32
    ):
        for i in range(particles.n_particles):
            if right_mask[i] == 1:
                particles.f[i][0] += force_x

    # Create right edge mask
    right_mask = ti.field(dtype=ti.i32, shape=n_particles)
    mask_np = np.zeros(n_particles, dtype=np.int32)
    mask_np[right_indices] = 1
    right_mask.from_numpy(mask_np)

    # Visualization setup
    window = ti.ui.Window("2D Plate Tension", (800, 600))
    canvas = window.get_canvas()

    # Particle colors
    colors = ti.Vector.field(3, dtype=ti.f32, shape=n_particles)

    @ti.kernel
    def update_colors(particles: ti.template(), scale: ti.f32):
        for i in range(particles.n_particles):
            # Color by x-displacement (blue = 0, red = max)
            u_x = particles.x[i][0] - particles.X[i][0]
            t = ti.min(1.0, ti.max(0.0, u_x / scale))
            # Blue to red colormap
            colors[i][0] = t  # R
            colors[i][1] = 0.0  # G
            colors[i][2] = 1.0 - t  # B

    # Normalized positions for rendering
    render_pos = ti.Vector.field(2, dtype=ti.f32, shape=n_particles)

    @ti.kernel
    def update_render_pos(particles: ti.template(), offset_x: ti.f32, offset_y: ti.f32, scale: ti.f32):
        for i in range(particles.n_particles):
            render_pos[i][0] = offset_x + particles.x[i][0] * scale
            render_pos[i][1] = offset_y + particles.x[i][1] * scale

    # Analytical solution for uniaxial tension
    # u_x = sigma * x / E
    expected_max_disp = applied_stress * L / E
    print(f"Expected max displacement (analytical): {expected_max_disp*1000:.4f} mm")

    # Simulation parameters
    max_steps = 50000
    output_interval = 1000

    print("\nRunning simulation...")
    print("Press ESC to quit")

    # Run simulation
    step = 0
    while window.running and step < max_steps:
        # Apply traction force
        solver.particles.reset_forces()
        apply_traction(particles, right_mask, force_per_particle)

        # Take solver step (without damage for this example)
        solver._position_update(solver.dt)
        solver._compute_bond_forces()

        # Add traction to forces
        apply_traction(particles, right_mask, force_per_particle)

        solver._velocity_update(solver.dt, solver.damping)

        # Output progress
        if step % output_interval == 0:
            disp = particles.get_displacements()
            max_disp = np.max(disp[:, 0])
            KE = solver.get_kinetic_energy()
            print(f"Step {step}: max u_x = {max_disp*1000:.4f} mm, KE = {KE:.6e} J")

        # Render
        if step % 10 == 0:
            # Scale for visualization
            render_scale = 4.0 / L  # Fit plate in view
            disp_scale = expected_max_disp * 2  # Color scale

            update_colors(particles, disp_scale)
            update_render_pos(particles, 0.1, 0.25, render_scale)

            canvas.set_background_color((0.1, 0.1, 0.1))
            canvas.circles(render_pos, radius=0.005, per_vertex_color=colors)
            window.show()

        step += 1
        solver.step_count += 1
        solver.time += solver.dt

    # Final results
    print("\n" + "="*50)
    print("FINAL RESULTS")
    print("="*50)

    disp = particles.get_displacements()
    max_disp_x = np.max(disp[:, 0])
    max_disp_y = np.max(np.abs(disp[:, 1]))

    print(f"Max x-displacement: {max_disp_x*1000:.4f} mm")
    print(f"Max y-displacement: {max_disp_y*1000:.4f} mm")
    print(f"Expected (analytical): {expected_max_disp*1000:.4f} mm")
    print(f"Error: {abs(max_disp_x - expected_max_disp)/expected_max_disp * 100:.2f}%")

    # Poisson's ratio effect
    # For bond-based PD, effective nu = 1/3 (plane stress) or 1/4
    # Lateral strain should be: epsilon_y = -nu * epsilon_x
    epsilon_x = max_disp_x / L
    epsilon_y = -max_disp_y / W
    effective_nu = -epsilon_y / epsilon_x if epsilon_x > 0 else 0
    print(f"Effective Poisson's ratio: {effective_nu:.3f} (expected ~0.25-0.33)")

    return particles, bonds, solver


def main():
    """Run the 2D plate example."""
    print("="*50)
    print("2D PLATE TENSION - BOND-BASED PERIDYNAMICS")
    print("="*50)

    create_plate_simulation()


if __name__ == "__main__":
    main()
