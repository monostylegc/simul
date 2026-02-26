"""VTK 내보내기 테스트.

Phase 1-C: VTU/PVD 파일 생성, 필드 검증, ParaView 호환 형식 확인.
"""

import pytest
import numpy as np
import tempfile
import os
from pathlib import Path
import xml.etree.ElementTree as ET

from backend.fea.fem.io.vtk_export import (
    export_vtk, export_vtk_series, export_mesh_result,
    _tensor_to_voigt, _get_vtk_cell_type,
)


# ───────────────── VTK 셀 타입 ─────────────────


class TestVTKCellType:
    """VTK 셀 타입 매핑 테스트."""

    def test_quad4(self):
        assert _get_vtk_cell_type(2, 4) == 9

    def test_tri3(self):
        assert _get_vtk_cell_type(2, 3) == 5

    def test_hex8(self):
        assert _get_vtk_cell_type(3, 8) == 12

    def test_tet4(self):
        assert _get_vtk_cell_type(3, 4) == 10

    def test_unsupported_raises(self):
        with pytest.raises(ValueError, match="지원하지 않는"):
            _get_vtk_cell_type(2, 5)


# ───────────────── Voigt 변환 ─────────────────


class TestTensorToVoigt:
    """텐서 → Voigt 변환 테스트."""

    def test_3d_identity(self):
        """3D 단위 텐서 → [1,1,1,0,0,0]."""
        I = np.eye(3).reshape(1, 3, 3)
        v = _tensor_to_voigt(I, 3)
        np.testing.assert_allclose(v[0], [1, 1, 1, 0, 0, 0])

    def test_2d_identity(self):
        """2D 단위 텐서 → [1,1,0,0,0,0]."""
        I = np.eye(2).reshape(1, 2, 2)
        v = _tensor_to_voigt(I, 2)
        np.testing.assert_allclose(v[0], [1, 1, 0, 0, 0, 0])

    def test_shear_component(self):
        """전단 성분 매핑 확인."""
        t = np.zeros((1, 3, 3))
        t[0, 0, 1] = 5.0
        t[0, 1, 0] = 5.0
        v = _tensor_to_voigt(t, 3)
        assert v[0, 5] == 5.0  # xy 성분


# ───────────────── 기본 VTU 내보내기 ─────────────────


class TestExportVTK:
    """VTU 파일 생성 테스트."""

    def _make_quad4_mesh(self):
        """2D QUAD4 테스트 메쉬 생성."""
        nodes = np.array([
            [0, 0], [1, 0], [2, 0],
            [0, 1], [1, 1], [2, 1],
        ], dtype=np.float64)
        elements = np.array([
            [0, 1, 4, 3],
            [1, 2, 5, 4],
        ], dtype=np.int32)
        return nodes, elements

    def _make_hex8_mesh(self):
        """3D HEX8 테스트 메쉬 생성."""
        nodes = np.array([
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        ], dtype=np.float64)
        elements = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)
        return nodes, elements

    def test_basic_2d_ascii(self):
        """2D 메쉬 ASCII VTU 생성."""
        nodes, elems = self._make_quad4_mesh()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_vtk(
                os.path.join(tmpdir, "test.vtu"),
                nodes, elems, dim=2, nodes_per_elem=4,
            )
            assert os.path.exists(path)
            assert path.endswith(".vtu")

            # XML 유효성 확인
            tree = ET.parse(path)
            root = tree.getroot()
            assert root.tag == "VTKFile"
            assert root.attrib["type"] == "UnstructuredGrid"

    def test_basic_3d_ascii(self):
        """3D 메쉬 ASCII VTU 생성."""
        nodes, elems = self._make_hex8_mesh()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_vtk(
                os.path.join(tmpdir, "test3d.vtu"),
                nodes, elems, dim=3, nodes_per_elem=8,
            )
            assert os.path.exists(path)

    def test_binary_mode(self):
        """binary 인코딩 VTU 생성."""
        nodes, elems = self._make_quad4_mesh()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_vtk(
                os.path.join(tmpdir, "test_bin.vtu"),
                nodes, elems, dim=2, nodes_per_elem=4, binary=True,
            )
            assert os.path.exists(path)
            # binary DataArray 존재 확인
            tree = ET.parse(path)
            data_arrays = tree.findall(".//" + "DataArray")
            for da in data_arrays:
                assert da.attrib["format"] == "binary"

    def test_with_scalar_field(self):
        """스칼라 절점 필드 포함."""
        nodes, elems = self._make_quad4_mesh()
        temperature = np.array([100, 200, 300, 150, 250, 350], dtype=np.float64)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_vtk(
                os.path.join(tmpdir, "with_scalar.vtu"),
                nodes, elems, dim=2, nodes_per_elem=4,
                fields={"temperature": temperature},
            )
            tree = ET.parse(path)
            # PointData에 temperature 존재
            pd = tree.find(".//PointData")
            names = [da.attrib["Name"] for da in pd.findall("DataArray")]
            assert "temperature" in names

    def test_with_vector_field(self):
        """벡터 절점 필드 포함 (2D → 3D 패딩)."""
        nodes, elems = self._make_quad4_mesh()
        disp = np.random.rand(6, 2)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_vtk(
                os.path.join(tmpdir, "with_vector.vtu"),
                nodes, elems, dim=2, nodes_per_elem=4,
                fields={"displacement": disp},
            )
            tree = ET.parse(path)
            pd = tree.find(".//PointData")
            da = pd.find("DataArray[@Name='displacement']")
            assert da.attrib["NumberOfComponents"] == "3"  # 3D 패딩

    def test_with_tensor_field(self):
        """텐서 절점 필드 → Voigt 6성분."""
        nodes, elems = self._make_hex8_mesh()
        stress = np.random.rand(8, 3, 3)
        stress = 0.5 * (stress + np.transpose(stress, (0, 2, 1)))  # 대칭화

        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_vtk(
                os.path.join(tmpdir, "with_tensor.vtu"),
                nodes, elems, dim=3, nodes_per_elem=8,
                fields={"stress": stress},
            )
            tree = ET.parse(path)
            pd = tree.find(".//PointData")
            da = pd.find("DataArray[@Name='stress']")
            assert da.attrib["NumberOfComponents"] == "6"

    def test_with_cell_field(self):
        """요소 필드 포함."""
        nodes, elems = self._make_quad4_mesh()
        mat_id = np.array([0, 1], dtype=np.int32)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_vtk(
                os.path.join(tmpdir, "with_cell.vtu"),
                nodes, elems, dim=2, nodes_per_elem=4,
                cell_fields={"material_id": mat_id},
            )
            tree = ET.parse(path)
            cd = tree.find(".//CellData")
            names = [da.attrib["Name"] for da in cd.findall("DataArray")]
            assert "material_id" in names

    def test_auto_vtu_extension(self):
        """확장자가 없으면 .vtu 자동 추가."""
        nodes, elems = self._make_quad4_mesh()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_vtk(
                os.path.join(tmpdir, "noext"),
                nodes, elems, dim=2, nodes_per_elem=4,
            )
            assert path.endswith(".vtu")


# ───────────────── VTK 시리즈 ─────────────────


class TestExportVTKSeries:
    """PVD + VTU 시리즈 테스트."""

    def test_series_generation(self):
        """다중 타임스텝 시리즈 생성."""
        nodes = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
        elems = np.array([[0, 1, 2, 3]], dtype=np.int32)

        steps = []
        for t in range(5):
            disp = np.random.rand(4, 2) * (t + 1) * 0.001
            steps.append((float(t), {"displacement": disp}))

        with tempfile.TemporaryDirectory() as tmpdir:
            pvd_path = export_vtk_series(
                os.path.join(tmpdir, "series"),
                steps, nodes, elems, dim=2, nodes_per_elem=4,
            )

            # PVD 파일 존재
            assert os.path.exists(pvd_path)
            assert pvd_path.endswith(".pvd")

            # VTU 파일들 존재
            for i in range(5):
                vtu_path = os.path.join(tmpdir, f"series_{i:04d}.vtu")
                assert os.path.exists(vtu_path), f"VTU 파일 누락: {vtu_path}"

            # PVD 내용 확인
            tree = ET.parse(pvd_path)
            datasets = tree.findall(".//DataSet")
            assert len(datasets) == 5
            assert datasets[0].attrib["timestep"] == "0.0"
            assert datasets[4].attrib["timestep"] == "4.0"


# ───────────────── FEMesh 통합 ─────────────────


class TestExportMeshResult:
    """FEMesh 결과 내보내기 통합 테스트."""

    def test_mesh_result_export(self):
        """FEMesh에서 직접 VTK 내보내기."""
        import taichi as ti
        try:
            ti.init(arch=ti.cpu, default_fp=ti.f64)
        except RuntimeError:
            pass  # 이미 초기화됨
        from backend.fea.fem.core.mesh import FEMesh
        from backend.fea.fem.core.element import ElementType
        from backend.fea.fem.material.linear_elastic import LinearElastic
        from backend.fea.fem.solver.static_solver import StaticSolver

        # 간단한 2D 외팔보
        nodes = np.array([
            [0, 0], [0.5, 0], [1, 0],
            [0, 0.5], [0.5, 0.5], [1, 0.5],
        ], dtype=np.float64)
        elems = np.array([
            [0, 1, 4, 3],
            [1, 2, 5, 4],
        ], dtype=np.int32)

        mesh = FEMesh(6, 2, ElementType.QUAD4)
        mesh.initialize_from_numpy(nodes, elems)
        mesh.set_fixed_nodes(np.array([0, 3]))
        mesh.set_nodal_forces(np.array([2, 5]), np.array([[0, -1e6], [0, -1e6]]))

        mat = LinearElastic(200e9, 0.3, dim=2)
        solver = StaticSolver(mesh, mat)
        solver.solve(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_mesh_result(
                os.path.join(tmpdir, "result.vtu"),
                mesh, material=mat,
            )
            assert os.path.exists(path)

            # 필드 존재 확인
            tree = ET.parse(path)
            pd = tree.find(".//PointData")
            field_names = [da.attrib["Name"] for da in pd.findall("DataArray")]
            assert "displacement" in field_names
            assert "von_mises" in field_names
