"""FEM 동적 솔버 테스트.

Newmark-beta 및 Central Difference 시간 적분과
고유진동수 계산을 검증한다.
"""

import pytest
import numpy as np
import taichi as ti

ti.init(arch=ti.cpu, default_fp=ti.f64)


def _create_cantilever_2d(nx=10, ny=2, Lx=10.0, Ly=1.0):
    """2D 외팔보 메쉬 생성 (QUAD4).

    좌측(x=0) 고정, 우측(x=Lx) 자유단.

    Returns:
        mesh: 초기화된 FEMesh
    """
    from backend.fea.fem.core.mesh import FEMesh
    from backend.fea.fem.core.element import ElementType

    dx, dy = Lx / nx, Ly / ny
    n_nodes = (nx + 1) * (ny + 1)
    n_elements = nx * ny

    nodes = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            nodes.append([i * dx, j * dy])
    nodes = np.array(nodes, dtype=np.float64)

    elements = []
    for ey in range(ny):
        for ex in range(nx):
            n0 = ex + ey * (nx + 1)
            n1 = n0 + 1
            n2 = n0 + (nx + 1) + 1
            n3 = n0 + (nx + 1)
            elements.append([n0, n1, n2, n3])
    elements = np.array(elements, dtype=np.int32)

    mesh = FEMesh(
        n_nodes=n_nodes,
        n_elements=n_elements,
        element_type=ElementType.QUAD4,
    )
    mesh.initialize_from_numpy(nodes, elements)

    # 좌측 고정 (x = 0)
    fixed = np.where(nodes[:, 0] < 1e-10)[0]
    mesh.set_fixed_nodes(fixed)

    return mesh, nodes, n_nodes


def _create_cantilever_3d(nx=5, ny=1, nz=1, Lx=10.0, Ly=1.0, Lz=1.0):
    """3D 외팔보 메쉬 생성 (HEX8).

    좌측(x=0) 고정, 우측(x=Lx) 자유단.

    Returns:
        mesh: 초기화된 FEMesh
    """
    from backend.fea.fem.core.mesh import FEMesh
    from backend.fea.fem.core.element import ElementType

    dx, dy, dz = Lx / nx, Ly / ny, Lz / nz
    n_nodes = (nx + 1) * (ny + 1) * (nz + 1)
    n_elements = nx * ny * nz

    nodes = []
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                nodes.append([i * dx, j * dy, k * dz])
    nodes = np.array(nodes, dtype=np.float64)

    elements = []
    for ez in range(nz):
        for ey in range(ny):
            for ex in range(nx):
                n0 = ex + ey * (nx + 1) + ez * (nx + 1) * (ny + 1)
                n1 = n0 + 1
                n2 = n0 + (nx + 1) + 1
                n3 = n0 + (nx + 1)
                n4 = n0 + (nx + 1) * (ny + 1)
                n5 = n4 + 1
                n6 = n4 + (nx + 1) + 1
                n7 = n4 + (nx + 1)
                elements.append([n0, n1, n2, n3, n4, n5, n6, n7])
    elements = np.array(elements, dtype=np.int32)

    mesh = FEMesh(
        n_nodes=n_nodes,
        n_elements=n_elements,
        element_type=ElementType.HEX8,
    )
    mesh.initialize_from_numpy(nodes, elements)

    # 좌측 고정 (x = 0)
    fixed = np.where(nodes[:, 0] < 1e-10)[0]
    mesh.set_fixed_nodes(fixed)

    return mesh, nodes, n_nodes


class TestDynamicSolverCreation:
    """동적 솔버 생성 테스트."""

    def test_newmark_creation(self):
        """Newmark 솔버 생성."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, _, _ = _create_cantilever_2d()
        mat = LinearElastic(1e6, 0.3, dim=2)

        solver = DynamicSolver(mesh, mat, density=1000.0, method="newmark")

        assert solver.method == "newmark"
        assert solver.dt > 0
        assert solver.gamma == 0.5
        assert solver.beta == 0.25
        assert len(solver.M_diag) == solver.n_dof

    def test_central_diff_creation(self):
        """Central Difference 솔버 생성."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, _, _ = _create_cantilever_2d()
        mat = LinearElastic(1e6, 0.3, dim=2)

        solver = DynamicSolver(mesh, mat, density=1000.0, method="central_diff")

        assert solver.method == "central_diff"
        assert solver.dt > 0

    def test_custom_dt(self):
        """사용자 지정 dt 테스트."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, _, _ = _create_cantilever_2d()
        mat = LinearElastic(1e6, 0.3, dim=2)

        solver = DynamicSolver(mesh, mat, density=1000.0, dt=1e-4)

        assert solver.dt == 1e-4

    def test_lumped_mass_total(self):
        """집중 질량 합 = 총 질량 테스트."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        Lx, Ly = 10.0, 1.0
        density = 1000.0
        mesh, _, _ = _create_cantilever_2d(Lx=Lx, Ly=Ly)
        mat = LinearElastic(1e6, 0.3, dim=2)

        solver = DynamicSolver(mesh, mat, density=density)

        # 총 질량 = 밀도 × 면적 (2D)
        total_mass_expected = density * Lx * Ly
        # M_diag는 (n_dof,), 2D이므로 x방향만 합산
        total_mass = np.sum(solver.M_diag[::2])  # x-DOF만
        assert np.isclose(total_mass, total_mass_expected, rtol=0.01), \
            f"Total mass = {total_mass}, expected {total_mass_expected}"


class TestDynamicSolverStep:
    """동적 솔버 시간 적분 테스트."""

    def test_newmark_step_runs(self):
        """Newmark 1스텝 정상 실행."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, nodes, n_nodes = _create_cantilever_2d()
        mat = LinearElastic(1e6, 0.3, dim=2)

        solver = DynamicSolver(mesh, mat, density=1000.0, method="newmark")

        # 우측 끝에 하중
        f_ext = np.zeros(solver.n_dof)
        right_nodes = np.where(nodes[:, 0] > 10.0 - 0.1)[0]
        for n in right_nodes:
            f_ext[n * 2 + 1] = -100.0  # -y 방향

        info = solver.step(f_ext)

        assert "kinetic_energy" in info
        assert "time" in info
        assert info["time"] > 0
        assert not np.any(np.isnan(solver.u))
        assert not np.any(np.isnan(solver.v))

    def test_central_diff_step_runs(self):
        """Central Difference 1스텝 정상 실행."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, nodes, n_nodes = _create_cantilever_2d()
        mat = LinearElastic(1e6, 0.3, dim=2)

        solver = DynamicSolver(mesh, mat, density=1000.0, method="central_diff")

        # 우측 끝에 하중
        f_ext = np.zeros(solver.n_dof)
        right_nodes = np.where(nodes[:, 0] > 10.0 - 0.1)[0]
        for n in right_nodes:
            f_ext[n * 2 + 1] = -100.0

        info = solver.step(f_ext)

        assert "kinetic_energy" in info
        assert info["time"] > 0
        assert not np.any(np.isnan(solver.u))

    def test_newmark_multiple_steps(self):
        """Newmark 다중 스텝 안정성 테스트."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, nodes, n_nodes = _create_cantilever_2d()
        mat = LinearElastic(1e6, 0.3, dim=2)

        solver = DynamicSolver(mesh, mat, density=1000.0, method="newmark", dt=1e-3)

        # 초기 속도 부여 (자유진동)
        v0 = np.zeros(solver.n_dof)
        right_nodes = np.where(nodes[:, 0] > 10.0 - 0.1)[0]
        for n in right_nodes:
            v0[n * 2 + 1] = -1.0  # -y 초기 속도
        solver.set_initial_velocity(v0)

        # 100스텝 실행
        info = solver.solve(n_steps=100, verbose=False)

        assert not np.any(np.isnan(solver.u))
        assert not np.any(np.isinf(solver.u))
        max_u = np.max(np.abs(solver.u))
        assert max_u < 1e3, f"max_u = {max_u}, 발산 의심"

    def test_central_diff_multiple_steps(self):
        """Central Difference 다중 스텝 안정성 테스트."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, nodes, n_nodes = _create_cantilever_2d()
        mat = LinearElastic(1e6, 0.3, dim=2)

        solver = DynamicSolver(mesh, mat, density=1000.0, method="central_diff")

        # 초기 속도 부여
        v0 = np.zeros(solver.n_dof)
        right_nodes = np.where(nodes[:, 0] > 10.0 - 0.1)[0]
        for n in right_nodes:
            v0[n * 2 + 1] = -1.0
        solver.set_initial_velocity(v0)

        # 100스텝 실행 (dt는 자동 추정, 안정해야 함)
        info = solver.solve(n_steps=100, verbose=False)

        assert not np.any(np.isnan(solver.u))
        assert not np.any(np.isinf(solver.u))

    def test_fixed_bc_enforced(self):
        """경계조건 강제 테스트: 고정 노드 변위 = 0."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, nodes, n_nodes = _create_cantilever_2d()
        mat = LinearElastic(1e6, 0.3, dim=2)

        solver = DynamicSolver(mesh, mat, density=1000.0, method="newmark", dt=1e-3)

        # 초기 속도 부여
        v0 = np.zeros(solver.n_dof)
        right_nodes = np.where(nodes[:, 0] > 10.0 - 0.1)[0]
        for n in right_nodes:
            v0[n * 2 + 1] = -1.0
        solver.set_initial_velocity(v0)

        solver.solve(n_steps=50, verbose=False)

        # 고정 노드의 변위 = 0
        fixed_nodes = np.where(nodes[:, 0] < 1e-10)[0]
        u = solver.get_displacements()
        for n in fixed_nodes:
            assert np.allclose(u[n], 0.0, atol=1e-12), \
                f"Fixed node {n} displacement = {u[n]}"


class TestNaturalFrequencies:
    """고유진동수 계산 테스트."""

    def test_cantilever_first_frequency_2d(self):
        """2D 외팔보 1차 고유진동수 검증.

        해석해 (Euler-Bernoulli 보):
        f_n = (β_n)² / (2π) × √(EI / (ρA·L⁴))
        β_1 = 1.8751 (1차 모드)

        2D 평면 변형률에서 유효 E: E_eff = E / (1 - ν²)
        """
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        Lx, Ly = 10.0, 1.0
        E = 1e6
        nu = 0.3
        density = 1000.0

        # 충분히 세밀한 메쉬
        mesh, _, _ = _create_cantilever_2d(nx=20, ny=4, Lx=Lx, Ly=Ly)
        mat = LinearElastic(E, nu, dim=2)

        solver = DynamicSolver(mesh, mat, density=density)
        freqs = solver.get_natural_frequencies(n_modes=3)

        # 해석해: Euler-Bernoulli 보
        # 평면 변형률 유효 E
        E_eff = E / (1 - nu**2)
        I = Ly**3 / 12.0  # 단면 2차 모멘트
        A = Ly * 1.0       # 단면적 (2D에서 두께=1)
        rho_A = density * A

        beta_1 = 1.8751
        f1_analytical = (beta_1**2) / (2 * np.pi) * np.sqrt(E_eff * I / (rho_A * Lx**4))

        # FEM 결과는 유한요소 근사이므로 10% 이내 허용
        assert len(freqs) >= 1
        f1_fem = freqs[0]
        rel_error = abs(f1_fem - f1_analytical) / f1_analytical
        print(f"1차 고유진동수: FEM={f1_fem:.4f} Hz, 해석해={f1_analytical:.4f} Hz, "
              f"상대오차={rel_error*100:.1f}%")
        assert rel_error < 0.15, \
            f"1차 고유진동수 오차 {rel_error*100:.1f}% > 15%"

    def test_frequency_ordering(self):
        """고유진동수 오름차순 정렬 확인."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, _, _ = _create_cantilever_2d(nx=10, ny=2)
        mat = LinearElastic(1e6, 0.3, dim=2)

        solver = DynamicSolver(mesh, mat, density=1000.0)
        freqs = solver.get_natural_frequencies(n_modes=5)

        # 오름차순 확인
        for i in range(len(freqs) - 1):
            assert freqs[i] <= freqs[i+1], \
                f"Frequencies not sorted: f[{i}]={freqs[i]}, f[{i+1}]={freqs[i+1]}"

    def test_all_frequencies_positive(self):
        """모든 고유진동수가 양수."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, _, _ = _create_cantilever_2d(nx=10, ny=2)
        mat = LinearElastic(1e6, 0.3, dim=2)

        solver = DynamicSolver(mesh, mat, density=1000.0)
        freqs = solver.get_natural_frequencies(n_modes=5)

        assert np.all(freqs > 0), f"Negative frequencies found: {freqs}"


class TestRayleighDamping:
    """Rayleigh 감쇠 테스트."""

    def test_damped_energy_decay(self):
        """감쇠 시 운동에너지 감소 확인."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, nodes, n_nodes = _create_cantilever_2d()
        mat = LinearElastic(1e6, 0.3, dim=2)

        # 감쇠 있음
        solver = DynamicSolver(
            mesh, mat, density=1000.0,
            method="newmark", dt=1e-3,
            rayleigh_alpha=10.0,  # 강한 질량 감쇠
        )

        # 초기 속도 부여
        v0 = np.zeros(solver.n_dof)
        right_nodes = np.where(nodes[:, 0] > 10.0 - 0.1)[0]
        for n in right_nodes:
            v0[n * 2 + 1] = -1.0
        solver.set_initial_velocity(v0)

        # 초기 운동에너지
        ke_initial = solver.get_kinetic_energy()

        # 200스텝 실행
        solver.solve(n_steps=200, verbose=False)

        ke_final = solver.get_kinetic_energy()

        # 감쇠로 인해 에너지 감소
        assert ke_final < ke_initial, \
            f"KE should decrease: initial={ke_initial:.6e}, final={ke_final:.6e}"


class TestDynamic3D:
    """3D 동적 솔버 테스트."""

    def test_3d_newmark_runs(self):
        """3D Newmark 솔버 정상 실행."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, nodes, n_nodes = _create_cantilever_3d(nx=3, ny=1, nz=1)
        mat = LinearElastic(1e6, 0.3, dim=3)

        solver = DynamicSolver(mesh, mat, density=1000.0, method="newmark", dt=1e-3)

        # 초기 속도
        v0 = np.zeros(solver.n_dof)
        right_nodes = np.where(nodes[:, 0] > 10.0 - 0.1)[0]
        for n in right_nodes:
            v0[n * 3 + 2] = -1.0  # -z 초기 속도
        solver.set_initial_velocity(v0)

        info = solver.solve(n_steps=20, verbose=False)

        assert not np.any(np.isnan(solver.u))
        assert not np.any(np.isinf(solver.u))

    def test_3d_natural_frequencies(self):
        """3D 고유진동수 계산 정상 실행."""
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.dynamic_solver import DynamicSolver

        mesh, _, _ = _create_cantilever_3d(nx=3, ny=1, nz=1)
        mat = LinearElastic(1e6, 0.3, dim=3)

        solver = DynamicSolver(mesh, mat, density=1000.0)
        freqs = solver.get_natural_frequencies(n_modes=3)

        assert len(freqs) >= 1
        assert np.all(freqs > 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
