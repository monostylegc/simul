"""통합 구조 해석 클래스.

FEM과 Peridynamics를 통합하는 고수준 API.
"""

import taichi as ti
import numpy as np
import pyvista as pv
from typing import Dict, List, Optional, Literal, Tuple
from dataclasses import dataclass, field
from scipy.spatial import cKDTree
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve

from .materials import Material, MaterialLibrary
from .mesh import MeshGenerator, FEMMesh, PDParticles


@dataclass
class Part:
    """해석 파트 (단일 STL)."""
    name: str
    material: Material
    filepath: str

    # 메쉬 데이터 (해석 시 생성)
    fem_mesh: Optional[FEMMesh] = None
    pd_particles: Optional[PDParticles] = None

    # 오프셋 (복합체 해석용)
    node_offset: int = 0
    particle_offset: int = 0

    # 기하 정보
    z_min: float = 0.0
    z_max: float = 0.0


@dataclass
class BoundaryCondition:
    """경계 조건."""
    type: Literal["fixed", "displacement", "force"]
    location: Literal["top", "bottom", "custom"]
    value: np.ndarray = field(default_factory=lambda: np.zeros(3))
    node_indices: np.ndarray = field(default_factory=lambda: np.array([]))


@dataclass
class AnalysisResult:
    """해석 결과."""
    method: str
    converged: bool
    displacements: np.ndarray
    parts: Dict[str, dict]

    # 통계
    max_displacement: float = 0.0
    total_nodes: int = 0

    def plot(self, scale: float = 10.0, off_screen: bool = False,
             save_path: Optional[str] = None):
        """결과 시각화.

        Args:
            scale: 변위 확대 배율
            off_screen: 화면 없이 렌더링
            save_path: 이미지 저장 경로
        """
        pl = pv.Plotter(off_screen=off_screen, window_size=(1600, 900))

        for name, part_data in self.parts.items():
            nodes = part_data["nodes"]
            disp = part_data["displacements"]
            deformed = nodes + disp * scale

            if "elements" in part_data:
                # FEM 메쉬
                elements = part_data["elements"]
                cells = np.hstack([np.full((len(elements), 1), 4), elements]).flatten()
                cell_types = np.full(len(elements), pv.CellType.TETRA)
                grid = pv.UnstructuredGrid(cells, cell_types, deformed)
            else:
                # PD 입자
                grid = pv.PolyData(deformed)

            disp_mag = np.linalg.norm(disp, axis=1)
            grid.point_data["displacement"] = disp_mag

            if "elements" in part_data:
                pl.add_mesh(grid, scalars="displacement", cmap="jet",
                            opacity=0.9, scalar_bar_args={"title": f"{name} [mm]"})
            else:
                pl.add_mesh(grid, scalars="displacement", cmap="jet",
                            point_size=6, render_points_as_spheres=True,
                            scalar_bar_args={"title": f"{name} [mm]"})

        pl.add_text(f"{self.method.upper()} Result\nMax: {self.max_displacement:.3f} mm",
                    font_size=12, position="upper_left")
        pl.camera_position = "xz"

        if save_path:
            pl.screenshot(save_path)
            print(f"저장됨: {save_path}")

        if not off_screen:
            pl.show()

        return pl

    def save(self, filepath: str):
        """결과 이미지 저장."""
        self.plot(off_screen=True, save_path=filepath)

    def summary(self) -> str:
        """결과 요약."""
        lines = [
            f"해석 방법: {self.method.upper()}",
            f"수렴 여부: {self.converged}",
            f"총 노드/입자: {self.total_nodes}",
            f"최대 변위: {self.max_displacement:.4f} mm",
            "",
            "파트별 결과:",
        ]
        for name, data in self.parts.items():
            disp = np.linalg.norm(data["displacements"], axis=1)
            lines.append(f"  {name}: {disp.min():.4f} ~ {disp.max():.4f} mm")

        return "\n".join(lines)


class SpineAnalysis:
    """척추 구조 해석 프레임워크.

    사용 예시:
        analysis = SpineAnalysis()
        analysis.load_stl("L4.stl", "L4", "bone")
        analysis.load_stl("disc.stl", "disc", "disc")
        analysis.load_stl("L5.stl", "L5", "bone")

        analysis.fix_bottom()
        analysis.apply_load(top=True, force=-3000)

        result = analysis.solve(method="fem")
        result.plot()
    """

    def __init__(self):
        """초기화."""
        self.parts: Dict[str, Part] = {}
        self.boundary_conditions: List[BoundaryCondition] = []
        self._initialized = False

    def load_stl(self, filepath: str, name: str,
                 material: str = "bone") -> "SpineAnalysis":
        """STL 파일 로드.

        Args:
            filepath: STL 파일 경로
            name: 파트 이름
            material: 재료 이름 (MaterialLibrary에서 조회)

        Returns:
            self (체이닝용)
        """
        mat = MaterialLibrary.get(material)

        # 기하 정보 로드
        vertices, faces = MeshGenerator.load_stl(filepath)
        z_min, z_max = vertices[:, 2].min(), vertices[:, 2].max()

        self.parts[name] = Part(
            name=name,
            material=mat,
            filepath=filepath,
            z_min=z_min,
            z_max=z_max
        )

        print(f"로드됨: {name} ({mat.name}), z=[{z_min:.1f}, {z_max:.1f}] mm")
        return self

    def fix_bottom(self, tolerance: float = 0.03) -> "SpineAnalysis":
        """하단 고정 경계 조건.

        Args:
            tolerance: 전체 높이 대비 비율

        Returns:
            self
        """
        self.boundary_conditions.append(BoundaryCondition(
            type="fixed",
            location="bottom",
            value=np.array([tolerance, 0, 0])  # tolerance 저장
        ))
        return self

    def fix_top(self, tolerance: float = 0.03) -> "SpineAnalysis":
        """상단 고정 경계 조건."""
        self.boundary_conditions.append(BoundaryCondition(
            type="fixed",
            location="top",
            value=np.array([tolerance, 0, 0])
        ))
        return self

    def apply_load(self, force: float = -1000.0,
                   top: bool = True, tolerance: float = 0.03) -> "SpineAnalysis":
        """하중 적용.

        Args:
            force: 힘 [N] (음수 = 압축)
            top: True면 상단, False면 하단
            tolerance: 전체 높이 대비 비율

        Returns:
            self
        """
        self.boundary_conditions.append(BoundaryCondition(
            type="force",
            location="top" if top else "bottom",
            value=np.array([force, tolerance, 0])  # force, tolerance 저장
        ))
        return self

    def apply_strain(self, strain: float = 0.02,
                     compression: bool = True) -> "SpineAnalysis":
        """변형률 적용 (PD용).

        Args:
            strain: 변형률 (0.02 = 2%)
            compression: True면 압축, False면 인장

        Returns:
            self
        """
        value = -strain if compression else strain
        self.boundary_conditions.append(BoundaryCondition(
            type="displacement",
            location="top",
            value=np.array([value, 0, 0])
        ))
        return self

    def solve(self, method: Literal["fem", "pd"] = "fem",
              fem_quality: float = 2.0,
              pd_spacing: float = 2.0,
              verbose: bool = True) -> AnalysisResult:
        """해석 실행.

        Args:
            method: "fem" 또는 "pd"
            fem_quality: FEM 메쉬 품질 (낮을수록 조밀)
            pd_spacing: PD 입자 간격 [mm]
            verbose: 진행 상황 출력

        Returns:
            AnalysisResult 객체
        """
        if method == "fem":
            return self._solve_fem(fem_quality, verbose)
        else:
            return self._solve_pd(pd_spacing, verbose)

    def _solve_fem(self, quality: float, verbose: bool) -> AnalysisResult:
        """FEM 해석."""
        from spine_sim.analysis.fem.core.mesh import FEMesh as TAFEMesh
        from spine_sim.analysis.fem.core.element import ElementType
        from spine_sim.analysis.fem.material.linear_elastic import LinearElastic
        from spine_sim.analysis.fem.solver.static_solver import StaticSolver
        from spine_sim.analysis.fem.solver.contact import TiedContact

        if verbose:
            print("\n" + "=" * 50)
            print("FEM 해석 시작")
            print("=" * 50)

        # 메쉬 생성
        if verbose:
            print("\n메쉬 생성...")

        node_offset = 0
        for name, part in self.parts.items():
            vertices, faces = MeshGenerator.load_stl(part.filepath)
            part.fem_mesh = MeshGenerator.create_fem_mesh(vertices, faces, quality)
            part.node_offset = node_offset
            node_offset += part.fem_mesh.n_nodes

            if verbose:
                print(f"  {name}: {part.fem_mesh.n_nodes} nodes, {part.fem_mesh.n_elements} elements")

        total_nodes = node_offset
        n_dof = total_nodes * 3

        # 전체 노드 배열
        all_nodes = np.zeros((total_nodes, 3), dtype=np.float32)
        for part in self.parts.values():
            off = part.node_offset
            all_nodes[off:off + part.fem_mesh.n_nodes] = part.fem_mesh.nodes

        # Tied contact 찾기
        if verbose:
            print("\n인터페이스 탐색...")

        tied_pairs = self._find_tied_pairs_fem()
        if verbose:
            print(f"  총 tied pairs: {len(tied_pairs)}")

        # 강성 행렬 조립
        if verbose:
            print("\n강성 행렬 조립...")

        K = lil_matrix((n_dof, n_dof))

        for name, part in self.parts.items():
            mesh = part.fem_mesh
            fem_mesh = TAFEMesh(
                n_nodes=mesh.n_nodes,
                n_elements=mesh.n_elements,
                element_type=ElementType.TET4
            )
            fem_mesh.initialize_from_numpy(mesh.nodes, mesh.elements)

            material = LinearElastic(
                youngs_modulus=part.material.E,
                poisson_ratio=part.material.nu,
                dim=3
            )
            solver = StaticSolver(fem_mesh, material)
            K_local = solver._assemble_stiffness_matrix()

            offset = part.node_offset
            for i in range(K_local.nnz):
                r, c, v = K_local.row[i], K_local.col[i], K_local.data[i]
                gr = (offset + r // 3) * 3 + r % 3
                gc = (offset + c // 3) * 3 + c % 3
                K[gr, gc] += v

        # Tied constraint
        penalty = 1e12
        for slave, master in tied_pairs:
            for d in range(3):
                sd, md = slave * 3 + d, master * 3 + d
                K[sd, sd] += penalty
                K[sd, md] -= penalty
                K[md, sd] -= penalty
                K[md, md] += penalty

        # 경계 조건 적용
        z_min, z_max = all_nodes[:, 2].min(), all_nodes[:, 2].max()
        height = z_max - z_min

        f = np.zeros(n_dof)
        fixed_nodes = []

        for bc in self.boundary_conditions:
            tol = bc.value[0] if bc.type == "fixed" else bc.value[1]
            tol = tol * height

            if bc.location == "bottom":
                indices = np.where(all_nodes[:, 2] < z_min + tol)[0]
            else:
                indices = np.where(all_nodes[:, 2] > z_max - tol)[0]

            if bc.type == "fixed":
                fixed_nodes.extend(indices)
            elif bc.type == "force":
                force = bc.value[0]
                force_per_node = force / len(indices)
                for node in indices:
                    f[node * 3 + 2] = force_per_node

        # 고정 경계 조건
        bc_penalty = 1e30
        for node in fixed_nodes:
            for d in range(3):
                dof = node * 3 + d
                K[dof, dof] += bc_penalty
                f[dof] = 0

        if verbose:
            print(f"  고정: {len(fixed_nodes)} nodes")

        # 풀기
        if verbose:
            print("\n연립방정식 풀이...")

        K = K.tocsr()
        u = spsolve(K, f)
        displacements = u.reshape(-1, 3)

        # 결과 정리
        parts_result = {}
        for name, part in self.parts.items():
            off = part.node_offset
            n = part.fem_mesh.n_nodes
            parts_result[name] = {
                "nodes": part.fem_mesh.nodes,
                "elements": part.fem_mesh.elements,
                "displacements": displacements[off:off + n],
            }

        result = AnalysisResult(
            method="fem",
            converged=True,
            displacements=displacements,
            parts=parts_result,
            max_displacement=float(np.max(np.linalg.norm(displacements, axis=1))),
            total_nodes=total_nodes
        )

        if verbose:
            print("\n" + result.summary())

        return result

    def _solve_pd(self, spacing: float, verbose: bool) -> AnalysisResult:
        """Peridynamics 해석."""
        from spine_sim.analysis.peridynamics.core.particles import ParticleSystem
        from spine_sim.analysis.peridynamics.core.bonds import BondSystem
        from spine_sim.analysis.peridynamics.core.neighbor import NeighborSearch
        from spine_sim.analysis.peridynamics.core.nosb import NOSBCompute, NOSBMaterial

        if verbose:
            print("\n" + "=" * 50)
            print("NOSB-PD 해석 시작")
            print("=" * 50)

        # 입자 생성
        if verbose:
            print(f"\n입자 생성 (spacing={spacing}mm)...")

        particle_offset = 0
        for name, part in self.parts.items():
            vertices, faces = MeshGenerator.load_stl(part.filepath)
            part.pd_particles = MeshGenerator.create_pd_particles(vertices, faces, spacing)
            part.particle_offset = particle_offset
            particle_offset += part.pd_particles.n_particles

            if verbose:
                print(f"  {name}: {part.pd_particles.n_particles} particles")

        total_particles = particle_offset

        # 전체 입자 배열
        all_positions = np.zeros((total_particles, 3), dtype=np.float32)
        for part in self.parts.values():
            off = part.particle_offset
            all_positions[off:off + part.pd_particles.n_particles] = part.pd_particles.positions

        # Tied contact
        if verbose:
            print("\n인터페이스 탐색...")

        tied_pairs = self._find_tied_pairs_pd(spacing)
        if verbose:
            print(f"  총 tied pairs: {len(tied_pairs)}")

        # 입자 시스템 생성
        horizon = 3.015 * spacing
        rho = 1.85e-6

        particles = ParticleSystem(total_particles, dim=3)
        particles.X.from_numpy(all_positions)
        particles.x.from_numpy(all_positions.copy())

        vol = spacing ** 3
        particles.volume.from_numpy(np.full(total_particles, vol, dtype=np.float32))
        particles.mass.from_numpy(np.full(total_particles, rho * vol, dtype=np.float32))

        # 이웃 탐색
        mins, maxs = all_positions.min(axis=0), all_positions.max(axis=0)
        neighbor_search = NeighborSearch(
            domain_min=tuple(mins - horizon),
            domain_max=tuple(maxs + horizon),
            horizon=horizon,
            max_particles=total_particles,
            max_neighbors=100,
            dim=3
        )
        neighbor_search.build(particles.X, total_particles)

        if verbose:
            n_neighbors = neighbor_search.get_all_neighbor_counts()
            print(f"  이웃 통계: min={n_neighbors.min()}, max={n_neighbors.max()}, mean={n_neighbors.mean():.1f}")

        # 본드 및 NOSB
        bonds = BondSystem(total_particles, max_bonds=100, dim=3)
        bonds.build_from_neighbor_search(particles, neighbor_search, horizon)

        # 평균 재료 (단순화)
        avg_E = np.mean([p.material.E for p in self.parts.values()])
        avg_nu = np.mean([p.material.nu for p in self.parts.values()])
        material = NOSBMaterial(avg_E, avg_nu, dim=3)

        nosb = NOSBCompute(particles, bonds, stabilization=0.1)
        nosb.compute_shape_tensor()

        # 경계 조건
        z_min, z_max = all_positions[:, 2].min(), all_positions[:, 2].max()
        height = z_max - z_min

        # 고정 입자
        fixed_indices = []
        strain = 0.0

        for bc in self.boundary_conditions:
            tol_ratio = bc.value[0] if bc.type in ["fixed", "displacement"] else bc.value[1]
            tol = tol_ratio * height

            if bc.location == "bottom":
                indices = np.where(all_positions[:, 2] < z_min + tol)[0]
            else:
                indices = np.where(all_positions[:, 2] > z_max - tol)[0]

            if bc.type == "fixed":
                fixed_indices.extend(indices)
            elif bc.type == "displacement":
                strain = abs(bc.value[0])

        particles.set_fixed_particles(np.array(fixed_indices, dtype=np.int32))

        if verbose:
            print(f"\n경계 조건:")
            print(f"  고정: {len(fixed_indices)} particles")
            print(f"  변형률: {strain*100:.1f}%")

        # 변위 적용
        if strain > 0:
            x = particles.x.to_numpy()
            X = particles.X.to_numpy()
            for i in range(total_particles):
                if i not in fixed_indices:
                    x[i, 2] = X[i, 2] - strain * (X[i, 2] - z_min)
            particles.x.from_numpy(x.astype(np.float32))

        # 계산
        if verbose:
            print("\nNOSB-PD 계산...")

        nosb.compute_deformation_gradient()
        nosb.compute_force_state_linear_elastic(material.K, material.mu)

        # 결과
        displacements = particles.get_displacements()

        parts_result = {}
        for name, part in self.parts.items():
            off = part.particle_offset
            n = part.pd_particles.n_particles
            parts_result[name] = {
                "nodes": part.pd_particles.positions,
                "displacements": displacements[off:off + n],
            }

        result = AnalysisResult(
            method="pd",
            converged=True,
            displacements=displacements,
            parts=parts_result,
            max_displacement=float(np.max(np.linalg.norm(displacements, axis=1))),
            total_nodes=total_particles
        )

        if verbose:
            print("\n" + result.summary())

        return result

    def _find_tied_pairs_fem(self) -> List[Tuple[int, int]]:
        """FEM 인터페이스 tied pairs 찾기."""
        from spine_sim.analysis.fem.solver.contact import TiedContact

        tied_pairs = []
        parts_list = list(self.parts.values())

        for i in range(len(parts_list) - 1):
            p1, p2 = parts_list[i], parts_list[i + 1]

            overlap_min = max(p1.z_min, p2.z_min)
            overlap_max = min(p1.z_max, p2.z_max)

            if overlap_max > overlap_min:
                interface_tol = 10.0
                tie_tol = 5.0

                idx1 = np.where(
                    (p1.fem_mesh.nodes[:, 2] >= overlap_min - interface_tol) &
                    (p1.fem_mesh.nodes[:, 2] <= overlap_max + interface_tol)
                )[0]
                idx2 = np.where(
                    (p2.fem_mesh.nodes[:, 2] >= overlap_min - interface_tol) &
                    (p2.fem_mesh.nodes[:, 2] <= overlap_max + interface_tol)
                )[0]

                if len(idx1) > 0 and len(idx2) > 0:
                    tied = TiedContact(tolerance=tie_tol)
                    pairs = tied.find_tied_nodes(
                        p2.fem_mesh.nodes[idx2], idx2 + p2.node_offset,
                        p1.fem_mesh.nodes[idx1], idx1 + p1.node_offset
                    )
                    tied_pairs.extend(pairs)

        return tied_pairs

    def _find_tied_pairs_pd(self, spacing: float) -> List[Tuple[int, int]]:
        """PD 인터페이스 tied pairs 찾기."""
        tied_pairs = []
        parts_list = list(self.parts.values())
        tie_tol = spacing * 1.5

        for i in range(len(parts_list) - 1):
            p1, p2 = parts_list[i], parts_list[i + 1]

            overlap_min = max(p1.z_min, p2.z_min)
            overlap_max = min(p1.z_max, p2.z_max)

            if overlap_max > overlap_min:
                interface_tol = 10.0

                pos1 = p1.pd_particles.positions
                pos2 = p2.pd_particles.positions

                idx1 = np.where(
                    (pos1[:, 2] >= overlap_min - interface_tol) &
                    (pos1[:, 2] <= overlap_max + interface_tol)
                )[0]
                idx2 = np.where(
                    (pos2[:, 2] >= overlap_min - interface_tol) &
                    (pos2[:, 2] <= overlap_max + interface_tol)
                )[0]

                if len(idx1) > 0 and len(idx2) > 0:
                    tree = cKDTree(pos1[idx1])
                    for local_idx in idx2:
                        dist, nearest = tree.query(pos2[local_idx])
                        if dist <= tie_tol:
                            global1 = idx1[nearest] + p1.particle_offset
                            global2 = local_idx + p2.particle_offset
                            tied_pairs.append((global1, global2))

        return tied_pairs
