"""표면 하중 테스트.

표면 압력의 등가 절점력 변환과 해석 검증.
"""

import numpy as np
import pytest
import taichi as ti

# Taichi 초기화
ti.init(arch=ti.cpu, default_fp=ti.f64)

from ..core.element import ElementType, ELEMENT_FACES, get_face_nodes
from ..core.mesh import FEMesh
from ..solver.surface_load import (
    compute_pressure_load,
    find_surface_faces,
    _shape_line,
    _shape_tri,
    _shape_quad,
    _compute_line_normal_and_det,
    _compute_tri_normal_and_det,
    _compute_quad_normal_and_det,
)
from ..material.linear_elastic import LinearElastic
from ..solver.static_solver import StaticSolver


# ──────────── 헬퍼: 메쉬 생성 ────────────

def _create_quad4_mesh(nx, ny, lx=1.0, ly=1.0):
    """2D QUAD4 메쉬 생성.

    Args:
        nx, ny: x/y 분할 수
        lx, ly: x/y 길이
    """
    dx, dy = lx / nx, ly / ny
    nodes = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            nodes.append([i * dx, j * dy])
    nodes = np.array(nodes, dtype=np.float64)

    elements = []
    for j in range(ny):
        for i in range(nx):
            n0 = j * (nx + 1) + i
            n1 = n0 + 1
            n2 = n1 + (nx + 1)
            n3 = n0 + (nx + 1)
            elements.append([n0, n1, n2, n3])
    elements = np.array(elements, dtype=np.int32)

    mesh = FEMesh(len(nodes), len(elements), ElementType.QUAD4)
    mesh.initialize_from_numpy(nodes, elements)
    return mesh


def _create_hex8_mesh(nx, ny, nz, lx=1.0, ly=1.0, lz=1.0):
    """3D HEX8 메쉬 생성.

    Args:
        nx, ny, nz: x/y/z 분할 수
        lx, ly, lz: x/y/z 길이
    """
    dx, dy, dz = lx / nx, ly / ny, lz / nz
    nodes = []
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                nodes.append([i * dx, j * dy, k * dz])
    nodes = np.array(nodes, dtype=np.float64)

    elements = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                n0 = k * (ny + 1) * (nx + 1) + j * (nx + 1) + i
                n1 = n0 + 1
                n2 = n1 + (nx + 1)
                n3 = n0 + (nx + 1)
                n4 = n0 + (ny + 1) * (nx + 1)
                n5 = n4 + 1
                n6 = n5 + (nx + 1)
                n7 = n4 + (nx + 1)
                elements.append([n0, n1, n2, n3, n4, n5, n6, n7])
    elements = np.array(elements, dtype=np.int32)

    mesh = FEMesh(len(nodes), len(elements), ElementType.HEX8)
    mesh.initialize_from_numpy(nodes, elements)
    return mesh


# ──────────── 형상함수 테스트 ────────────

class TestShapeFunctions:
    """면 형상함수 기본 검증."""

    def test_line_partition_of_unity(self):
        """선분 형상함수 합 = 1."""
        for xi in [-1, 0, 0.5, 1]:
            N = _shape_line(xi)
            assert abs(np.sum(N) - 1.0) < 1e-12

    def test_tri_partition_of_unity(self):
        """삼각형 형상함수 합 = 1."""
        for xi, eta in [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1/3, 1/3)]:
            N = _shape_tri(xi, eta)
            assert abs(np.sum(N) - 1.0) < 1e-12

    def test_quad_partition_of_unity(self):
        """사각형 형상함수 합 = 1."""
        for xi, eta in [(-1, -1), (0, 0), (1, 1), (0.5, -0.5)]:
            N = _shape_quad(xi, eta)
            assert abs(np.sum(N) - 1.0) < 1e-12


# ──────────── 법선/야코비안 테스트 ────────────

class TestNormalComputation:
    """면 법선 계산 검증."""

    def test_line_horizontal(self):
        """수평 선분 (y=0): 법선 = (0, -1)."""
        coords = np.array([[0.0, 0.0], [2.0, 0.0]])
        n, det = _compute_line_normal_and_det(coords, 0.0)
        assert abs(det - 1.0) < 1e-12  # 길이/2 = 1
        assert abs(n[0]) < 1e-12
        assert abs(n[1] - (-1.0)) < 1e-12  # 아래쪽

    def test_line_vertical(self):
        """수직 선분 (x=1, 위로): 법선 = (1, 0)."""
        coords = np.array([[1.0, 0.0], [1.0, 2.0]])
        n, det = _compute_line_normal_and_det(coords, 0.0)
        assert abs(det - 1.0) < 1e-12
        assert abs(n[0] - 1.0) < 1e-12
        assert abs(n[1]) < 1e-12

    def test_tri_xy_plane(self):
        """xy평면 삼각형: 법선 = (0, 0, 1)."""
        coords = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ])
        n, det = _compute_tri_normal_and_det(coords, 1/3, 1/3)
        assert abs(n[2] - 1.0) < 1e-12
        assert abs(det - 1.0) < 1e-12  # |e1 × e2| = 1

    def test_quad_xy_plane(self):
        """xy평면 단위 사각형: 법선 = (0, 0, 1)."""
        coords = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
        ])
        n, det = _compute_quad_normal_and_det(coords, 0.0, 0.0)
        assert abs(n[2] - 1.0) < 1e-12
        # det = |dx/dξ × dx/dη| = |0.5e1 × 0.5e2| = 0.25
        assert abs(det - 0.25) < 1e-12


# ──────────── ELEMENT_FACES 정의 테스트 ────────────

class TestElementFaces:
    """면 정의 유효성."""

    def test_tet4_has_4_faces(self):
        faces = get_face_nodes(ElementType.TET4)
        assert len(faces) == 4
        for f in faces:
            assert len(f) == 3  # 삼각형 면

    def test_hex8_has_6_faces(self):
        faces = get_face_nodes(ElementType.HEX8)
        assert len(faces) == 6
        for f in faces:
            assert len(f) == 4  # 사각형 면

    def test_quad4_has_4_edges(self):
        faces = get_face_nodes(ElementType.QUAD4)
        assert len(faces) == 4
        for f in faces:
            assert len(f) == 2  # 선분 변

    def test_unsupported_raises(self):
        """미지원 요소 → ValueError."""
        with pytest.raises(ValueError, match="미지원"):
            get_face_nodes(ElementType.TET10)


# ──────────── 2D 압력 하중 테스트 ────────────

class TestPressureLoad2D:
    """2D 요소 표면 압력 검증."""

    def test_single_quad_right_edge_pressure(self):
        """단위 QUAD4 우측 변 압력: 총 힘 = p × 길이 = 1 × 1.

        우측 변 (x=1) 법선 = (+1, 0) → 양수 압력은 -x 방향.
        find_surface_faces를 사용하여 정확한 면을 검색.
        """
        mesh = _create_quad4_mesh(1, 1)
        pressure = 1.0

        # 우측 변 자동 검색
        fe, fi = find_surface_faces(mesh, axis=0, value=1.0)
        assert len(fe) == 1

        f = compute_pressure_load(mesh, fe, fi, pressure)

        # 총 힘 = -p × n × 길이 = -1 × (1,0) × 1 = (-1, 0)
        total_f = np.sum(f, axis=0)
        assert abs(total_f[0] - (-1.0)) < 1e-10
        assert abs(total_f[1]) < 1e-10

        # 우측 노드 (x=1)에만 힘 분배
        X = mesh.X.to_numpy()
        right = np.where(np.abs(X[:, 0] - 1.0) < 1e-10)[0]
        for n in right:
            assert abs(f[n, 0] - (-0.5)) < 1e-10

    def test_single_quad_top_edge_pressure(self):
        """단위 QUAD4 상단 변 압력: 총 힘 = p × 길이.

        면 2 (상단): 노드 2,3 (y=1)
        법선 = (0, +1) → 양수 압력은 -y 방향
        """
        mesh = _create_quad4_mesh(1, 1)
        pressure = 2.0

        f = compute_pressure_load(
            mesh, np.array([0]), np.array([2]), pressure
        )

        total_f = np.sum(f, axis=0)
        assert abs(total_f[0]) < 1e-10
        assert abs(total_f[1] - (-2.0)) < 1e-10  # -p × 1

    def test_multi_element_bottom_pressure(self):
        """2요소 메쉬 하단 변 압력.

        2×1 QUAD4 메쉬, 하단(y=0)에 p=10 압력.
        총 힘 = p × 길이 = 10 × 2 = 20 (y 방향)
        """
        mesh = _create_quad4_mesh(2, 1, lx=2.0, ly=1.0)
        pressure = 10.0

        # 하단 면 자동 검색
        fe, fi = find_surface_faces(mesh, axis=1, value=0.0)

        assert len(fe) == 2  # 2요소

        f = compute_pressure_load(mesh, fe, fi, pressure)

        total_f = np.sum(f, axis=0)
        # 하단 법선 = (0, -1) → 양수 압력 힘 = (0, +10×2)
        assert abs(total_f[0]) < 1e-10
        assert abs(total_f[1] - 20.0) < 1e-10


# ──────────── 3D 압력 하중 테스트 ────────────

class TestPressureLoad3D:
    """3D 요소 표면 압력 검증."""

    def test_single_hex_top_pressure(self):
        """단위 HEX8 상단면 압력: 총 힘 = p × 면적.

        면 1 (상단, z=1): 노드 4,5,6,7
        법선 = (0,0,+1) → 양수 압력은 (0,0,-1) 방향
        """
        mesh = _create_hex8_mesh(1, 1, 1)
        pressure = 5.0

        f = compute_pressure_load(
            mesh, np.array([0]), np.array([1]), pressure
        )

        total_f = np.sum(f, axis=0)
        # 총 힘 = -p × n × 면적 = -5 × (0,0,1) × 1 = (0,0,-5)
        assert abs(total_f[0]) < 1e-10
        assert abs(total_f[1]) < 1e-10
        assert abs(total_f[2] - (-5.0)) < 1e-10

        # 4 노드에 균등 배분: 각 -5/4 = -1.25
        for n in [4, 5, 6, 7]:
            assert abs(f[n, 2] - (-1.25)) < 1e-10

    def test_single_hex_bottom_pressure(self):
        """단위 HEX8 바닥면 압력: 법선 (0,0,-1).

        면 0 (바닥, z=0): 노드 0,3,2,1
        양수 압력 → 힘 = (0,0,+p)
        """
        mesh = _create_hex8_mesh(1, 1, 1)
        pressure = 3.0

        f = compute_pressure_load(
            mesh, np.array([0]), np.array([0]), pressure
        )

        total_f = np.sum(f, axis=0)
        assert abs(total_f[0]) < 1e-10
        assert abs(total_f[1]) < 1e-10
        assert abs(total_f[2] - 3.0) < 1e-10  # +z 방향

    def test_multi_hex_top_pressure(self):
        """2×2×1 HEX8 메쉬 상단면 압력.

        총 면적 = 2 × 2 = 4
        총 힘 = p × 면적 = 10 × 4 = 40 (z 방향)
        """
        mesh = _create_hex8_mesh(2, 2, 1, lx=2.0, ly=2.0, lz=1.0)
        pressure = 10.0

        fe, fi = find_surface_faces(mesh, axis=2, value=1.0)

        assert len(fe) == 4  # 2×2 = 4 요소

        f = compute_pressure_load(mesh, fe, fi, pressure)

        total_f = np.sum(f, axis=0)
        assert abs(total_f[0]) < 1e-10
        assert abs(total_f[1]) < 1e-10
        assert abs(total_f[2] - (-40.0)) < 1e-10  # -z (압축)

    def test_opposite_faces_cancel(self):
        """상단+바닥 동일 압력 → 순 힘 = 0 (내부 평형)."""
        mesh = _create_hex8_mesh(1, 1, 1)
        pressure = 5.0

        # 상단 + 바닥
        fe = np.array([0, 0])
        fi = np.array([0, 1])  # 바닥, 상단

        f = compute_pressure_load(mesh, fe, fi, pressure)
        total_f = np.sum(f, axis=0)

        # 순 힘 ≈ 0
        assert np.linalg.norm(total_f) < 1e-10


# ──────────── find_surface_faces 테스트 ────────────

class TestFindSurfaceFaces:
    """면 자동 검색 검증."""

    def test_2d_bottom(self):
        """2D QUAD4 메쉬 하단 변 검색."""
        mesh = _create_quad4_mesh(3, 2)
        fe, fi = find_surface_faces(mesh, axis=1, value=0.0)
        assert len(fe) == 3  # 3개 요소

    def test_2d_right(self):
        """2D QUAD4 메쉬 우측 변 검색."""
        mesh = _create_quad4_mesh(3, 2)
        fe, fi = find_surface_faces(mesh, axis=0, value=1.0)
        assert len(fe) == 2  # 2개 요소

    def test_3d_top(self):
        """3D HEX8 메쉬 상단면 검색."""
        mesh = _create_hex8_mesh(2, 2, 2)
        fe, fi = find_surface_faces(mesh, axis=2, value=1.0)
        assert len(fe) == 4  # 2×2 = 4 요소

    def test_3d_front(self):
        """3D HEX8 메쉬 전면(y=0) 검색."""
        mesh = _create_hex8_mesh(2, 2, 2)
        fe, fi = find_surface_faces(mesh, axis=1, value=0.0)
        assert len(fe) == 4  # 2×2 = 4 요소

    def test_empty_result(self):
        """면이 없는 좌표값 → 빈 결과."""
        mesh = _create_quad4_mesh(2, 2)
        # x=0.7은 노드 위치가 아님 (노드: 0, 0.5, 1.0)
        # 자동 tol이 클 수 있으므로 작은 tol 명시
        fe, fi = find_surface_faces(mesh, axis=0, value=0.7, tol=0.1)
        assert len(fe) == 0


# ──────────── mesh.py API 통합 테스트 ────────────

class TestMeshPressureAPI:
    """FEMesh.add_pressure_load / find_surface_faces 통합 테스트."""

    def test_add_pressure_accumulates(self):
        """add_pressure_load가 기존 f_ext에 누적되는지 확인."""
        mesh = _create_quad4_mesh(1, 1)

        # 기존 절점력 설정
        mesh.set_nodal_forces(np.array([2]), np.array([[10.0, 0.0]]))

        # 압력 추가
        mesh.add_pressure_load(np.array([0]), np.array([1]), 1.0)

        f_ext = mesh.f_ext.to_numpy()
        # 노드 2: 기존 (10, 0) + 압력에 의한 힘
        assert f_ext[2, 0] != 0  # 누적됨

    def test_mesh_find_surface(self):
        """mesh.find_surface_faces() 메서드 호출."""
        mesh = _create_hex8_mesh(2, 2, 1)
        fe, fi = mesh.find_surface_faces(axis=2, value=1.0)
        assert len(fe) == 4


# ──────────── 왕복 테스트: 압력 → 해석 → 검증 ────────────

class TestPressureSolve:
    """압력 하중 → 정적 해석 왕복 테스트."""

    def test_cantilever_tip_pressure_2d(self):
        """2D 캔틸레버 우측 변 압력.

        좌측 고정, 우측에 단위 압력.
        변위가 우측에서 최대, 압력 방향과 반대.
        """
        mesh = _create_quad4_mesh(4, 1, lx=4.0, ly=1.0)

        # 좌측 고정 (x=0)
        X = mesh.X.to_numpy()
        left = np.where(np.abs(X[:, 0]) < 1e-10)[0]
        mesh.set_fixed_nodes(left)

        # 우측 압력 (x=4, 법선 = +x → 힘은 -x)
        fe, fi = mesh.find_surface_faces(axis=0, value=4.0)
        assert len(fe) > 0
        mesh.add_pressure_load(fe, fi, 100.0)

        mat = LinearElastic(1e6, 0.3, dim=2)
        solver = StaticSolver(mesh, mat)
        result = solver.solve(verbose=False)

        assert result["converged"]

        u = mesh.get_displacements()
        # 좌측 고정: 변위 ≈ 0
        for n in left:
            assert np.linalg.norm(u[n]) < 1e-8

        # 우측 노드: -x 변위
        right = np.where(np.abs(X[:, 0] - 4.0) < 1e-10)[0]
        for n in right:
            assert u[n, 0] < 0  # -x 방향 변위

    def test_cube_top_compression_3d(self):
        """3D 큐브 상단 압력 → 바닥 고정.

        z축 방향 압축, 균일한 z-변위 분포.
        """
        mesh = _create_hex8_mesh(2, 2, 2)

        # 바닥 고정 (z=0)
        X = mesh.X.to_numpy()
        bottom = np.where(np.abs(X[:, 2]) < 1e-10)[0]
        mesh.set_fixed_nodes(bottom)

        # 상단 압력 (z=1)
        fe, fi = mesh.find_surface_faces(axis=2, value=1.0)
        mesh.add_pressure_load(fe, fi, 1000.0)

        mat = LinearElastic(1e6, 0.3, dim=3)
        solver = StaticSolver(mesh, mat)
        result = solver.solve(verbose=False)

        assert result["converged"]

        u = mesh.get_displacements()
        # 바닥 고정
        for n in bottom:
            assert np.linalg.norm(u[n]) < 1e-8

        # 상단 노드: -z 변위 (압축)
        top = np.where(np.abs(X[:, 2] - 1.0) < 1e-10)[0]
        for n in top:
            assert u[n, 2] < 0  # -z (압축)

        # 상단 노드 z-변위가 거의 균일
        top_uz = u[top, 2]
        assert np.std(top_uz) / abs(np.mean(top_uz)) < 0.01  # 변동계수 < 1%
