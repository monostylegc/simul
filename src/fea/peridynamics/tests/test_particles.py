"""Unit tests for ParticleSystem."""

import pytest
import numpy as np
import taichi as ti


@pytest.fixture(scope="module", autouse=True)
def init_taichi():
    """Initialize Taichi once per module."""
    ti.init(arch=ti.cpu, default_fp=ti.f32)


class TestParticleSystem:
    """Tests for ParticleSystem class."""

    def test_initialization(self):
        """Test basic initialization."""
        from spine_sim.analysis.peridynamics.core.particles import ParticleSystem

        n = 100
        ps = ParticleSystem(n, dim=2)

        assert ps.n_particles == n
        assert ps.dim == 2

    def test_grid_initialization(self):
        """Test initialization from grid."""
        from spine_sim.analysis.peridynamics.core.particles import ParticleSystem

        nx, ny = 5, 4
        n = nx * ny
        spacing = 0.1
        origin = (0.0, 0.0)

        ps = ParticleSystem(n, dim=2)
        ps.initialize_from_grid(origin, spacing, (nx, ny), density=1000.0)

        positions = ps.get_positions()
        assert positions.shape == (n, 2)

        # Check corner particles
        assert np.allclose(positions[0], [0.0, 0.0], atol=1e-6)
        assert np.allclose(positions[-1], [(nx-1)*spacing, (ny-1)*spacing], atol=1e-6)

    def test_fixed_particles(self):
        """Test setting fixed particles."""
        from spine_sim.analysis.peridynamics.core.particles import ParticleSystem

        n = 20
        ps = ParticleSystem(n, dim=2)
        ps.initialize_from_grid((0, 0), 0.1, (5, 4), density=1000.0)

        # Fix first 5 particles
        fixed_indices = np.array([0, 1, 2, 3, 4])
        ps.set_fixed_particles(fixed_indices)

        fixed = ps.fixed.to_numpy()
        assert np.sum(fixed) == 5
        assert np.all(fixed[:5] == 1)
        assert np.all(fixed[5:] == 0)

    def test_displacement(self):
        """Test displacement computation."""
        from spine_sim.analysis.peridynamics.core.particles import ParticleSystem

        n = 4
        ps = ParticleSystem(n, dim=2)
        ps.initialize_from_grid((0, 0), 1.0, (2, 2), density=1000.0)

        # Move particles
        x = ps.x.to_numpy()
        x[:, 0] += 0.1  # Uniform x displacement
        ps.x.from_numpy(x)

        disp = ps.get_displacements()
        assert np.allclose(disp[:, 0], 0.1, atol=1e-6)
        assert np.allclose(disp[:, 1], 0.0, atol=1e-6)


class TestNeighborSearch:
    """Tests for NeighborSearch class."""

    def test_basic_neighbor_search(self):
        """Test basic neighbor finding."""
        from spine_sim.analysis.peridynamics.core.particles import ParticleSystem
        from spine_sim.analysis.peridynamics.core.neighbor import NeighborSearch

        # Create 3x3 grid
        n = 9
        spacing = 1.0
        # horizon = 1.5 includes diagonals (sqrt(2) ~ 1.414 < 1.5)
        # horizon = 1.1 excludes diagonals
        horizon = 1.5  # Includes diagonal neighbors

        ps = ParticleSystem(n, dim=2)
        ps.initialize_from_grid((0, 0), spacing, (3, 3), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-1, -1),
            domain_max=(3, 3),
            horizon=horizon,
            max_particles=n,
            max_neighbors=10,
            dim=2
        )

        ns.build(ps.X, n)

        # Center particle (index 4) should have 8 neighbors (all surrounding)
        # because sqrt(2) ~ 1.414 < 1.5
        counts = ns.get_all_neighbor_counts()
        assert counts[4] == 8  # Center has 8 neighbors (4 direct + 4 diagonal)

        # Corner particles should have 3 neighbors (2 direct + 1 diagonal)
        assert counts[0] == 3
        assert counts[2] == 3
        assert counts[6] == 3
        assert counts[8] == 3

    def test_horizon_cutoff(self):
        """Test that horizon is respected."""
        from spine_sim.analysis.peridynamics.core.particles import ParticleSystem
        from spine_sim.analysis.peridynamics.core.neighbor import NeighborSearch

        n = 4
        spacing = 1.0
        horizon = 1.1  # Just enough for direct neighbors

        ps = ParticleSystem(n, dim=2)
        ps.initialize_from_grid((0, 0), spacing, (2, 2), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-1, -1),
            domain_max=(2, 2),
            horizon=horizon,
            max_particles=n,
            max_neighbors=10,
            dim=2
        )

        ns.build(ps.X, n)

        # Diagonal distance is sqrt(2) > 1.1, so no diagonal neighbors
        counts = ns.get_all_neighbor_counts()
        assert np.all(counts == 2)  # Each corner has 2 neighbors


class TestBondSystem:
    """Tests for BondSystem class."""

    def test_bond_creation(self):
        """Test bond creation from neighbor search."""
        from spine_sim.analysis.peridynamics.core.particles import ParticleSystem
        from spine_sim.analysis.peridynamics.core.neighbor import NeighborSearch
        from spine_sim.analysis.peridynamics.core.bonds import BondSystem

        n = 9
        spacing = 1.0
        horizon = 1.5

        ps = ParticleSystem(n, dim=2)
        ps.initialize_from_grid((0, 0), spacing, (3, 3), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-1, -1), domain_max=(3, 3),
            horizon=horizon, max_particles=n, dim=2
        )
        ns.build(ps.X, n)

        bonds = BondSystem(n, max_bonds=10, dim=2)
        bonds.build_from_neighbor_search(ps, ns, horizon)

        # Check bond counts match neighbor counts
        bond_counts = bonds.get_neighbor_count()
        neighbor_counts = ns.get_all_neighbor_counts()
        assert np.array_equal(bond_counts, neighbor_counts)

        # All bonds should be initially intact
        broken = bonds.get_broken_bonds()
        assert np.sum(broken) == 0


class TestDamageModel:
    """Tests for DamageModel class."""

    def test_critical_stretch_computation(self):
        """Test critical stretch formula."""
        from spine_sim.analysis.peridynamics.core.damage import DamageModel

        E = 70e9  # 70 GPa
        G_c = 1000  # J/m^2
        delta = 0.003  # 3 mm

        # 3D formula
        s_c_3d = DamageModel.compute_critical_stretch(E, G_c, delta, dim=3)
        expected_3d = np.sqrt(5 * G_c / (9 * E * delta))
        assert np.isclose(s_c_3d, expected_3d, rtol=1e-6)

        # 2D formula
        s_c_2d = DamageModel.compute_critical_stretch(E, G_c, delta, dim=2)
        expected_2d = np.sqrt(4 * np.pi * G_c / (9 * E * delta))
        assert np.isclose(s_c_2d, expected_2d, rtol=1e-6)

    def test_bone_critical_stretch(self):
        """Test bone material critical stretch."""
        from spine_sim.analysis.peridynamics.core.damage import DamageModel

        horizon = 0.003

        s_c_cortical = DamageModel.compute_critical_stretch_bone("cortical", horizon)
        s_c_cancellous = DamageModel.compute_critical_stretch_bone("cancellous", horizon)

        # Cortical should be smaller (more brittle)
        assert s_c_cortical < s_c_cancellous
        # Both should be reasonable values (0.001 - 0.1)
        assert 0.001 < s_c_cortical < 0.1
        assert 0.001 < s_c_cancellous < 0.1


class TestExplicitSolver:
    """Tests for ExplicitSolver class."""

    def test_stable_dt_estimation(self):
        """Test stable time step estimation."""
        from spine_sim.analysis.peridynamics.solver.explicit import ExplicitSolver

        E = 70e9
        rho = 2700
        horizon = 0.006
        spacing = 0.002

        dt = ExplicitSolver.estimate_stable_dt(E, rho, horizon, spacing, safety_factor=0.5)

        # Should be on the order of microseconds
        assert 1e-8 < dt < 1e-5

        # Smaller spacing should give smaller dt
        dt_fine = ExplicitSolver.estimate_stable_dt(E, rho, horizon, spacing/2, safety_factor=0.5)
        assert dt_fine < dt

    def test_energy_conservation(self):
        """Test approximate energy conservation (no damping)."""
        from spine_sim.analysis.peridynamics.core.particles import ParticleSystem
        from spine_sim.analysis.peridynamics.core.neighbor import NeighborSearch
        from spine_sim.analysis.peridynamics.core.bonds import BondSystem
        from spine_sim.analysis.peridynamics.solver.explicit import ExplicitSolver
        from spine_sim.analysis.peridynamics.material.linear_elastic import LinearElasticMaterial

        # Small system for testing
        n = 9
        spacing = 0.01
        horizon = 3.015 * spacing  # Standard horizon factor

        ps = ParticleSystem(n, dim=2)
        ps.initialize_from_grid((0, 0), spacing, (3, 3), density=1000.0)

        ns = NeighborSearch(
            domain_min=(-0.05, -0.05), domain_max=(0.05, 0.05),
            horizon=horizon, max_particles=n, dim=2
        )
        ns.build(ps.X, n)

        bonds = BondSystem(n, max_bonds=32, dim=2)
        bonds.build_from_neighbor_search(ps, ns, horizon)

        # Material - use the material class for correct micromodulus
        E = 1e6  # Softer for faster dynamics
        rho = 1000.0
        material = LinearElasticMaterial(E, 0.25, horizon, thickness=1.0, dim=2)
        c = material.get_micromodulus()

        # Use very conservative time step
        dt = ExplicitSolver.estimate_stable_dt(E, rho, horizon, spacing, 0.01)
        solver = ExplicitSolver(ps, bonds, micromodulus=c, dt=dt, damping=0.0)

        # Apply very small initial velocity perturbation
        v = ps.v.to_numpy()
        v[4, 0] = 0.0001  # Very small kick to center particle
        ps.v.from_numpy(v)

        # Run a few steps and check energy doesn't explode
        for _ in range(10):
            solver.step()

        KE = solver.get_kinetic_energy()
        SE = solver.get_strain_energy()

        # Energy should be bounded and not NaN
        assert not np.isnan(KE), f"KE is NaN"
        assert not np.isnan(SE), f"SE is NaN"
        assert KE < 1e3
        assert SE < 1e3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
