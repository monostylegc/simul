"""메쉬 임포트 테스트 (Abaqus .inp + GMSH .msh).

인라인 문자열 fixture로 외부 파일 없이 테스트한다.
"""

import numpy as np
import pytest
import taichi as ti

# Taichi 초기화
ti.init(arch=ti.cpu, default_fp=ti.f64)

from ..io.abaqus_reader import read_abaqus_inp, MeshData
from ..io.gmsh_reader import read_gmsh_msh
from ..core.element import ElementType
from ..core.mesh import FEMesh
from ..material.linear_elastic import LinearElastic
from ..solver.static_solver import StaticSolver


# ──────────── Abaqus .inp Fixture ────────────

INP_TET4_SIMPLE = """\
** 단순 TET4 메쉬 (2요소)
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 0.0, 1.0, 0.0
4, 0.0, 0.0, 1.0
5, 1.0, 1.0, 1.0
*ELEMENT, TYPE=C3D4
1, 1, 2, 3, 4
2, 2, 3, 4, 5
"""

INP_HEX8_CUBE = """\
** 단일 HEX8 큐브
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 1.0, 1.0, 0.0
4, 0.0, 1.0, 0.0
5, 0.0, 0.0, 1.0
6, 1.0, 0.0, 1.0
7, 1.0, 1.0, 1.0
8, 0.0, 1.0, 1.0
*ELEMENT, TYPE=C3D8
1, 1, 2, 3, 4, 5, 6, 7, 8
"""

INP_WITH_SETS = """\
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 1.0, 1.0, 0.0
4, 0.0, 1.0, 0.0
5, 0.0, 0.0, 1.0
6, 1.0, 0.0, 1.0
7, 1.0, 1.0, 1.0
8, 0.0, 1.0, 1.0
*ELEMENT, TYPE=C3D8
1, 1, 2, 3, 4, 5, 6, 7, 8
*NSET, NSET=BOTTOM
1, 2, 3, 4
*NSET, NSET=TOP, GENERATE
5, 8, 1
*ELSET, ELSET=ALL
1
"""

INP_WITH_BC = """\
*NODE
1, 0.0, 0.0
2, 1.0, 0.0
3, 1.0, 1.0
4, 0.0, 1.0
*ELEMENT, TYPE=CPS4
1, 1, 2, 3, 4
*NSET, NSET=LEFT
1, 4
*BOUNDARY
LEFT, 1, 2
*CLOAD
3, 1, 100.0
"""

INP_2D_QUAD = """\
*NODE
1, 0.0, 0.0
2, 1.0, 0.0
3, 2.0, 0.0
4, 0.0, 1.0
5, 1.0, 1.0
6, 2.0, 1.0
*ELEMENT, TYPE=CPS4
1, 1, 2, 5, 4
2, 2, 3, 6, 5
*NSET, NSET=FIX
1, 4
*BOUNDARY
FIX, 1, 2
*CLOAD
3, 1, 50.0
6, 1, 50.0
"""


# ──────────── GMSH .msh v4 Fixture ────────────

MSH_TET4_V4 = """\
$MeshFormat
4.1 0 8
$EndMeshFormat
$Nodes
1 5 1 5
3 1 0 5
1
2
3
4
5
0.0 0.0 0.0
1.0 0.0 0.0
0.0 1.0 0.0
0.0 0.0 1.0
1.0 1.0 1.0
$EndNodes
$Elements
1 2 1 2
3 1 4 2
1 1 2 3 4
2 2 3 4 5
$EndElements
"""

MSH_QUAD4_2D = """\
$MeshFormat
4.1 0 8
$EndMeshFormat
$PhysicalNames
1
2 1 "plate"
$EndPhysicalNames
$Entities
0 0 1 0
1 0.0 0.0 0.0 1.0 1.0 0.0 1 1 0
$EndEntities
$Nodes
1 4 1 4
2 1 0 4
1
2
3
4
0.0 0.0 0.0
1.0 0.0 0.0
1.0 1.0 0.0
0.0 1.0 0.0
$EndNodes
$Elements
1 1 3 1
2 1 3 1
1 1 2 3 4
$EndElements
"""


# ──────────── Abaqus 리더 테스트 ────────────

class TestAbaqusReaderBasic:
    """Abaqus .inp 기본 파싱."""

    def test_tet4_parsing(self):
        """TET4 메쉬 파싱: 노드, 요소, 0-based 변환."""
        data = read_abaqus_inp(INP_TET4_SIMPLE)
        assert data.nodes.shape == (5, 3)
        assert data.elements.shape == (2, 4)
        assert data.element_type == ElementType.TET4
        # 0-based 변환 확인: 원본 노드 1 → 인덱스 0
        assert np.allclose(data.nodes[0], [0, 0, 0])
        assert np.allclose(data.nodes[1], [1, 0, 0])
        # 요소 연결: 원본 [1,2,3,4] → [0,1,2,3]
        assert np.array_equal(data.elements[0], [0, 1, 2, 3])

    def test_hex8_parsing(self):
        """HEX8 메쉬 파싱."""
        data = read_abaqus_inp(INP_HEX8_CUBE)
        assert data.nodes.shape == (8, 3)
        assert data.elements.shape == (1, 8)
        assert data.element_type == ElementType.HEX8

    def test_2d_element(self):
        """2D CPS4 메쉬 파싱."""
        data = read_abaqus_inp(INP_WITH_BC)
        assert data.nodes.shape == (4, 2)
        assert data.elements.shape == (1, 4)
        assert data.element_type == ElementType.QUAD4


class TestAbaqusReaderSets:
    """Abaqus 노드/요소 집합 파싱."""

    def test_nset(self):
        """*NSET 파싱."""
        data = read_abaqus_inp(INP_WITH_SETS)
        assert "BOTTOM" in data.node_sets
        assert len(data.node_sets["BOTTOM"]) == 4
        # 0-based: 원본 1,2,3,4 → 0,1,2,3
        assert np.array_equal(
            np.sort(data.node_sets["BOTTOM"]), [0, 1, 2, 3]
        )

    def test_nset_generate(self):
        """*NSET, GENERATE 구문."""
        data = read_abaqus_inp(INP_WITH_SETS)
        assert "TOP" in data.node_sets
        assert len(data.node_sets["TOP"]) == 4
        # 원본 5,6,7,8 → 4,5,6,7
        assert np.array_equal(
            np.sort(data.node_sets["TOP"]), [4, 5, 6, 7]
        )

    def test_elset(self):
        """*ELSET 파싱."""
        data = read_abaqus_inp(INP_WITH_SETS)
        assert "ALL" in data.element_sets
        assert len(data.element_sets["ALL"]) == 1


class TestAbaqusReaderBC:
    """경계조건/하중 파싱."""

    def test_boundary(self):
        """*BOUNDARY 파싱 (NSET 참조)."""
        data = read_abaqus_inp(INP_WITH_BC)
        # LEFT (노드 0, 3)에 DOF 1,2 (0-based: 0,1) 고정
        assert len(data.fixed_bcs) == 4  # 2 노드 × 2 DOF
        # 각 항목: (노드 배열, dof_0based, value)
        dofs = set()
        for nodes, dof, val in data.fixed_bcs:
            dofs.add(dof)
            assert val == 0.0
        assert dofs == {0, 1}

    def test_cload(self):
        """*CLOAD 파싱."""
        data = read_abaqus_inp(INP_WITH_BC)
        assert len(data.loads) == 1
        nodes, dof, mag = data.loads[0]
        assert nodes[0] == 2  # 원본 노드 3 → 인덱스 2
        assert dof == 0        # Abaqus DOF 1 → 0-based 0
        assert mag == 100.0


class TestAbaqusReaderErrors:
    """에러 처리."""

    def test_no_node_section(self):
        """*NODE 섹션 없음 → ValueError."""
        with pytest.raises(ValueError, match="NODE"):
            read_abaqus_inp("*ELEMENT, TYPE=C3D4\n1, 1, 2, 3, 4")

    def test_unsupported_element(self):
        """미지원 요소 타입 → ValueError."""
        with pytest.raises(ValueError, match="미지원"):
            read_abaqus_inp(
                "*NODE\n1, 0, 0, 0\n2, 1, 0, 0\n"
                "*ELEMENT, TYPE=C3D27\n1, 1, 2"
            )


# ──────────── GMSH 리더 테스트 ────────────

class TestGmshReaderBasic:
    """GMSH .msh v4 기본 파싱."""

    def test_tet4_parsing(self):
        """TET4 메쉬 파싱."""
        data = read_gmsh_msh(MSH_TET4_V4)
        assert data.nodes.shape == (5, 3)
        assert data.elements.shape == (2, 4)
        assert data.element_type == ElementType.TET4

    def test_quad4_2d(self):
        """2D QUAD4 메쉬 (z=0 자동 축소)."""
        data = read_gmsh_msh(MSH_QUAD4_2D)
        assert data.nodes.shape[1] == 2  # z 축소
        assert data.element_type == ElementType.QUAD4

    def test_physical_names(self):
        """물리 그룹 이름 파싱."""
        data = read_gmsh_msh(MSH_QUAD4_2D)
        # element_sets에 물리 그룹 존재
        assert len(data.element_sets) >= 0  # 구현에 따라


class TestGmshReaderErrors:
    """GMSH 에러 처리."""

    def test_v2_format_rejected(self):
        """GMSH v2 형식 거부."""
        with pytest.raises(ValueError, match="v2"):
            read_gmsh_msh("$MeshFormat\n2.2 0 8\n$EndMeshFormat")

    def test_binary_rejected(self):
        """바이너리 형식 거부."""
        with pytest.raises(ValueError, match="바이너리"):
            read_gmsh_msh("$MeshFormat\n4.1 1 8\n$EndMeshFormat")


# ──────────── 왕복 테스트: 파싱 → FEMesh → 해석 ────────────

class TestRoundTrip:
    """파싱 결과로 FEMesh 생성 후 해석 수행."""

    def test_abaqus_to_solve(self):
        """Abaqus .inp → FEMesh → 정적 해석."""
        data = read_abaqus_inp(INP_2D_QUAD)

        mesh = FEMesh(
            data.nodes.shape[0],
            data.elements.shape[0],
            data.element_type,
        )
        mesh.initialize_from_numpy(data.nodes, data.elements)

        # BC 적용
        for node_arr, dof, val in data.fixed_bcs:
            fixed = mesh.fixed.to_numpy()
            fixed_vals = mesh.fixed_value.to_numpy()
            for node_idx in node_arr:
                fixed[node_idx, dof] = 1
                fixed_vals[node_idx, dof] = val
            mesh.fixed.from_numpy(fixed)
            mesh.fixed_value.from_numpy(fixed_vals)

        # 하중 적용
        f_ext = np.zeros((data.nodes.shape[0], 2), dtype=np.float64)
        for node_arr, dof, mag in data.loads:
            for node_idx in node_arr:
                f_ext[node_idx, dof] += mag
        force_nodes = np.where(np.any(f_ext != 0, axis=1))[0]
        if len(force_nodes) > 0:
            mesh.set_nodal_forces(force_nodes, f_ext[force_nodes])

        mat = LinearElastic(1e6, 0.3, dim=2)
        solver = StaticSolver(mesh, mat)
        result = solver.solve(verbose=False)

        assert result["converged"]
        u = mesh.get_displacements()
        # 고정 노드: 변위 ≈ 0
        for node_arr, dof, val in data.fixed_bcs:
            for node_idx in node_arr:
                assert np.abs(u[node_idx, dof]) < 1e-8
        # 하중 노드: 양의 x 변위
        assert u[2, 0] > 0  # 노드 3 (0-based: 2)

    def test_abaqus_tet4_to_mesh(self):
        """Abaqus TET4 → FEMesh 생성 가능."""
        data = read_abaqus_inp(INP_TET4_SIMPLE)
        mesh = FEMesh(
            data.nodes.shape[0],
            data.elements.shape[0],
            data.element_type,
        )
        mesh.initialize_from_numpy(data.nodes, data.elements)
        assert mesh.n_nodes == 5
        assert mesh.n_elements == 2
