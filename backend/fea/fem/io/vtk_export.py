"""VTK/VTU 내보내기 — FEM 해석 결과를 ParaView 호환 형식으로 저장.

VTK XML Unstructured Grid (.vtu) 형식으로 내보내며,
ASCII 및 binary 모드를 지원한다.

지원하는 데이터:
- 절점 변위, 절점 힘
- 가우스점 → 절점 평활 응력 (von Mises, 주응력, 텐서 성분)
- 소성 변형률 (J2 소성)
- 요소 material ID
- PD/SPG damage 필드

사용 예:
    from backend.fea.fem.io import export_vtk
    export_vtk("result.vtu", mesh, fields={"displacement": disp, "stress": stress})

참고문헌:
- VTK File Formats: https://vtk.org/wp-content/uploads/2015/04/file-formats.pdf
"""

import numpy as np
from pathlib import Path
from typing import Dict, Optional, Any
import struct
import base64
import xml.etree.ElementTree as ET

# VTK 요소 타입 매핑 (요소별 노드 수 → VTK 셀 타입)
_VTK_CELL_TYPES = {
    # (dim, nodes_per_elem) → VTK type
    (2, 3): 5,    # VTK_TRIANGLE
    (2, 4): 9,    # VTK_QUAD
    (2, 6): 22,   # VTK_QUADRATIC_TRIANGLE
    (2, 8): 23,   # VTK_QUADRATIC_QUAD
    (3, 4): 10,   # VTK_TETRA
    (3, 8): 12,   # VTK_HEXAHEDRON
    (3, 10): 24,  # VTK_QUADRATIC_TETRA
    (3, 20): 25,  # VTK_QUADRATIC_HEXAHEDRON
}


def _get_vtk_cell_type(dim: int, nodes_per_elem: int) -> int:
    """요소 정보로부터 VTK 셀 타입 반환."""
    key = (dim, nodes_per_elem)
    if key not in _VTK_CELL_TYPES:
        raise ValueError(
            f"지원하지 않는 요소 타입: dim={dim}, nodes={nodes_per_elem}"
        )
    return _VTK_CELL_TYPES[key]


def _encode_binary(data: np.ndarray) -> str:
    """NumPy 배열을 VTK binary (base64) 인코딩."""
    # VTK는 앞에 데이터 크기 (바이트) 헤더를 추가
    raw = data.tobytes()
    header = struct.pack('<I', len(raw))  # 32-bit LE 크기 헤더
    return base64.b64encode(header + raw).decode('ascii')


def export_vtk(
    filename: str,
    nodes: np.ndarray,
    elements: np.ndarray,
    dim: int = 3,
    nodes_per_elem: int = 8,
    fields: Optional[Dict[str, np.ndarray]] = None,
    cell_fields: Optional[Dict[str, np.ndarray]] = None,
    binary: bool = False,
) -> str:
    """FEM 결과를 VTK XML Unstructured Grid (.vtu) 파일로 내보내기.

    Args:
        filename: 출력 파일 경로 (.vtu)
        nodes: 절점 좌표 (n_nodes, dim)
        elements: 요소 연결성 (n_elements, nodes_per_elem)
        dim: 공간 차원 (2 또는 3)
        nodes_per_elem: 요소당 절점 수
        fields: 절점 데이터 딕셔너리
            - 스칼라: (n_nodes,) → PointData
            - 벡터: (n_nodes, dim) → PointData (VTK 3D 패딩)
            - 텐서: (n_nodes, dim, dim) → 6성분 Voigt로 변환
        cell_fields: 요소 데이터 딕셔너리
            - 스칼라: (n_elements,) → CellData
        binary: True면 binary, False면 ASCII

    Returns:
        저장된 파일 경로
    """
    if fields is None:
        fields = {}
    if cell_fields is None:
        cell_fields = {}

    filepath = Path(filename)
    if filepath.suffix != '.vtu':
        filepath = filepath.with_suffix('.vtu')

    n_nodes = len(nodes)
    n_elements = len(elements)
    vtk_type = _get_vtk_cell_type(dim, nodes_per_elem)

    # 2D 노드를 3D로 패딩 (VTK는 항상 3D)
    if dim == 2:
        nodes_3d = np.zeros((n_nodes, 3), dtype=np.float64)
        nodes_3d[:, :2] = nodes[:, :2]
    else:
        nodes_3d = nodes

    # XML 구조 생성
    root = ET.Element("VTKFile", {
        "type": "UnstructuredGrid",
        "version": "0.1",
        "byte_order": "LittleEndian",
    })
    grid = ET.SubElement(root, "UnstructuredGrid")
    piece = ET.SubElement(grid, "Piece", {
        "NumberOfPoints": str(n_nodes),
        "NumberOfCells": str(n_elements),
    })

    # ─── Points ───
    points = ET.SubElement(piece, "Points")
    _add_data_array(points, "Points", nodes_3d.flatten(), 3, binary)

    # ─── Cells ───
    cells = ET.SubElement(piece, "Cells")

    # 연결성 (connectivity)
    connectivity = elements.flatten().astype(np.int32)
    _add_data_array(cells, "connectivity", connectivity, 1, binary, dtype="Int32")

    # 오프셋 (offsets)
    offsets = np.arange(1, n_elements + 1, dtype=np.int32) * nodes_per_elem
    _add_data_array(cells, "offsets", offsets, 1, binary, dtype="Int32")

    # 셀 타입 (types)
    types = np.full(n_elements, vtk_type, dtype=np.int32)
    _add_data_array(cells, "types", types, 1, binary, dtype="Int32")

    # ─── PointData (절점 필드) ───
    point_data = ET.SubElement(piece, "PointData")
    for name, data in fields.items():
        if data.ndim == 1:
            # 스칼라
            _add_data_array(point_data, name, data, 1, binary)
        elif data.ndim == 2 and data.shape[1] <= 3:
            # 벡터 (2D → 3D 패딩)
            n_comp = data.shape[1]
            if n_comp == 2:
                data_3d = np.zeros((n_nodes, 3), dtype=np.float64)
                data_3d[:, :2] = data
            else:
                data_3d = data
            _add_data_array(point_data, name, data_3d.flatten(), 3, binary)
        elif data.ndim == 3:
            # 텐서 → Voigt 6성분 (xx, yy, zz, yz, xz, xy)
            voigt = _tensor_to_voigt(data, dim)
            _add_data_array(point_data, name, voigt.flatten(), voigt.shape[1], binary)
        else:
            # 그 외: 그냥 flatten
            _add_data_array(point_data, name, data.flatten(),
                            data.shape[1] if data.ndim > 1 else 1, binary)

    # ─── CellData (요소 필드) ───
    cell_data = ET.SubElement(piece, "CellData")
    for name, data in cell_fields.items():
        if data.ndim == 1:
            _add_data_array(cell_data, name, data, 1, binary)
        else:
            _add_data_array(cell_data, name, data.flatten(),
                            data.shape[1] if data.ndim > 1 else 1, binary)

    # 파일 저장
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(filepath), xml_declaration=True, encoding="unicode")

    return str(filepath)


def _add_data_array(
    parent: ET.Element,
    name: str,
    data: np.ndarray,
    n_components: int,
    binary: bool,
    dtype: str = "Float64",
):
    """VTK DataArray 요소 추가."""
    if isinstance(data, np.ndarray) and data.dtype in (np.int32, np.int64):
        dtype = "Int32"
        data = data.astype(np.int32)
    elif isinstance(data, np.ndarray) and data.dtype in (np.float32, np.float64):
        dtype = "Float64"
        data = data.astype(np.float64)

    attrs = {
        "type": dtype,
        "Name": name,
        "NumberOfComponents": str(n_components),
    }

    if binary:
        attrs["format"] = "binary"
        elem = ET.SubElement(parent, "DataArray", attrs)
        elem.text = "\n" + _encode_binary(data) + "\n"
    else:
        attrs["format"] = "ascii"
        elem = ET.SubElement(parent, "DataArray", attrs)
        # ASCII 포맷: 공백 구분 숫자
        if dtype == "Int32":
            elem.text = "\n" + " ".join(str(int(v)) for v in data.flatten()) + "\n"
        else:
            elem.text = "\n" + " ".join(f"{v:.8e}" for v in data.flatten()) + "\n"


def _tensor_to_voigt(tensor: np.ndarray, dim: int) -> np.ndarray:
    """텐서 배열을 Voigt 6성분으로 변환.

    Args:
        tensor: (n, dim, dim) 텐서 배열
        dim: 2 또는 3

    Returns:
        (n, 6) Voigt 성분 [xx, yy, zz, yz, xz, xy]
    """
    n = tensor.shape[0]
    voigt = np.zeros((n, 6), dtype=np.float64)

    voigt[:, 0] = tensor[:, 0, 0]  # xx
    voigt[:, 1] = tensor[:, 1, 1]  # yy

    if dim == 3:
        voigt[:, 2] = tensor[:, 2, 2]  # zz
        voigt[:, 3] = tensor[:, 1, 2]  # yz
        voigt[:, 4] = tensor[:, 0, 2]  # xz
    voigt[:, 5] = tensor[:, 0, 1]  # xy

    return voigt


def export_vtk_series(
    base_filename: str,
    step_data: list,
    nodes: np.ndarray,
    elements: np.ndarray,
    dim: int = 3,
    nodes_per_elem: int = 8,
    binary: bool = False,
) -> str:
    """시간/하중 단계별 VTK 시리즈 내보내기 (.pvd + .vtu).

    Args:
        base_filename: 기본 파일명 (확장자 제외)
        step_data: 각 단계의 (time, fields_dict, cell_fields_dict) 리스트
        nodes: 절점 좌표 (n_nodes, dim)
        elements: 요소 연결성 (n_elements, nodes_per_elem)
        dim: 공간 차원
        nodes_per_elem: 요소당 절점 수
        binary: binary 인코딩 여부

    Returns:
        PVD 파일 경로
    """
    base_path = Path(base_filename)
    base_dir = base_path.parent
    base_name = base_path.stem

    # 각 단계별 VTU 파일 생성
    vtu_files = []
    for i, step in enumerate(step_data):
        if len(step) == 3:
            time_val, fields, cell_fields = step
        else:
            time_val, fields = step
            cell_fields = {}

        vtu_name = f"{base_name}_{i:04d}.vtu"
        vtu_path = base_dir / vtu_name
        export_vtk(
            str(vtu_path), nodes, elements, dim, nodes_per_elem,
            fields, cell_fields, binary,
        )
        vtu_files.append((time_val, vtu_name))

    # PVD 파일 생성
    pvd_path = base_dir / f"{base_name}.pvd"
    root = ET.Element("VTKFile", {
        "type": "Collection",
        "version": "0.1",
    })
    collection = ET.SubElement(root, "Collection")

    for time_val, vtu_name in vtu_files:
        ET.SubElement(collection, "DataSet", {
            "timestep": str(time_val),
            "file": vtu_name,
        })

    pvd_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(pvd_path), xml_declaration=True, encoding="unicode")

    return str(pvd_path)


def export_mesh_result(
    filename: str,
    mesh,
    material=None,
    include_stress: bool = True,
    include_strain: bool = False,
    include_von_mises: bool = True,
    include_plastic_strain: bool = True,
    binary: bool = False,
) -> str:
    """FEMesh 결과를 VTK로 직접 내보내기 (편의 함수).

    Args:
        filename: 출력 파일 경로
        mesh: FEMesh 객체
        material: 재료 모델 (소성 변형률 추출용)
        include_stress: 응력 포함 여부
        include_strain: 변형률 포함 여부
        include_von_mises: von Mises 응력 포함 여부
        include_plastic_strain: 소성 변형률 포함 여부 (J2 전용)
        binary: binary 인코딩 여부

    Returns:
        저장된 파일 경로
    """
    nodes = mesh.X.to_numpy()
    elements = mesh.elements.to_numpy()

    fields = {}

    # 변위
    disp = mesh.get_displacements()
    fields["displacement"] = disp

    # 절점 힘
    forces = mesh.get_nodal_forces()
    if np.any(np.abs(forces) > 0):
        fields["internal_force"] = forces

    # 응력/변형률 → 절점 평활 (가우스점에서 절점으로 보간)
    stress_gp = mesh.stress.to_numpy()
    if include_stress and np.any(np.abs(stress_gp) > 0):
        # 가우스점 → 절점 평균 (간단 평균)
        stress_nodal = _gauss_to_nodal(
            stress_gp, elements, mesh.n_nodes, mesh.n_gauss,
        )
        fields["stress"] = stress_nodal

    if include_strain:
        strain_gp = mesh.strain.to_numpy()
        if np.any(np.abs(strain_gp) > 0):
            strain_nodal = _gauss_to_nodal(
                strain_gp, elements, mesh.n_nodes, mesh.n_gauss,
            )
            fields["strain"] = strain_nodal

    if include_von_mises:
        # von Mises: 가우스점별 → 절점 평균
        if stress_gp.shape[0] > 0 and np.any(np.abs(stress_gp) > 0):
            vm_gp = _compute_von_mises_gauss(stress_gp, mesh.dim)
            vm_nodal = _gauss_scalar_to_nodal(
                vm_gp, elements, mesh.n_nodes, mesh.n_gauss,
            )
            fields["von_mises"] = vm_nodal

    if include_plastic_strain and material is not None:
        if hasattr(material, 'get_plastic_strain'):
            epe = material.get_plastic_strain()
            if epe.size > 0 and np.any(epe > 0):
                epe_nodal = _gauss_scalar_to_nodal(
                    epe, elements, mesh.n_nodes, mesh.n_gauss,
                )
                fields["eq_plastic_strain"] = epe_nodal

    return export_vtk(
        filename, nodes, elements, mesh.dim,
        mesh.nodes_per_elem, fields, binary=binary,
    )


def _gauss_to_nodal(
    gauss_data: np.ndarray,
    elements: np.ndarray,
    n_nodes: int,
    n_gauss_per_elem: int,
) -> np.ndarray:
    """가우스점 텐서 데이터를 절점으로 평균 보간.

    Args:
        gauss_data: (n_total_gauss, dim, dim) 텐서
        elements: (n_elements, npe)
        n_nodes: 전체 절점 수
        n_gauss_per_elem: 요소당 가우스점 수

    Returns:
        (n_nodes, dim, dim) 절점 평균 텐서
    """
    shape = gauss_data.shape[1:]  # (dim, dim)
    nodal = np.zeros((n_nodes, *shape), dtype=np.float64)
    count = np.zeros(n_nodes, dtype=np.int32)

    n_elements = len(elements)
    for e in range(n_elements):
        # 요소의 가우스점 평균
        gp_start = e * n_gauss_per_elem
        gp_end = gp_start + n_gauss_per_elem
        elem_avg = np.mean(gauss_data[gp_start:gp_end], axis=0)

        for node in elements[e]:
            nodal[node] += elem_avg
            count[node] += 1

    # 평균
    mask = count > 0
    nodal[mask] /= count[mask].reshape(-1, *([1] * len(shape)))

    return nodal


def _gauss_scalar_to_nodal(
    gauss_data: np.ndarray,
    elements: np.ndarray,
    n_nodes: int,
    n_gauss_per_elem: int,
) -> np.ndarray:
    """가우스점 스칼라 데이터를 절점으로 평균 보간."""
    nodal = np.zeros(n_nodes, dtype=np.float64)
    count = np.zeros(n_nodes, dtype=np.int32)

    n_elements = len(elements)
    for e in range(n_elements):
        gp_start = e * n_gauss_per_elem
        gp_end = gp_start + n_gauss_per_elem
        elem_avg = np.mean(gauss_data[gp_start:gp_end])

        for node in elements[e]:
            nodal[node] += elem_avg
            count[node] += 1

    mask = count > 0
    nodal[mask] /= count[mask]
    return nodal


def _compute_von_mises_gauss(stress_gp: np.ndarray, dim: int) -> np.ndarray:
    """가우스점 응력 텐서에서 von Mises 응력 계산.

    Args:
        stress_gp: (n_gauss, dim, dim)
        dim: 2 또는 3

    Returns:
        (n_gauss,) von Mises 스칼라
    """
    n = stress_gp.shape[0]
    vm = np.zeros(n, dtype=np.float64)

    for i in range(n):
        s = stress_gp[i]
        if dim == 3:
            p = (s[0, 0] + s[1, 1] + s[2, 2]) / 3.0
            dev = s.copy()
            dev[0, 0] -= p
            dev[1, 1] -= p
            dev[2, 2] -= p
            vm[i] = np.sqrt(1.5 * np.sum(dev * dev))
        else:
            # 2D: 평면변형 von Mises (σ₃₃ = 0 근사)
            p = (s[0, 0] + s[1, 1]) / 3.0  # σ₃₃ ≈ 0
            d11 = s[0, 0] - p
            d22 = s[1, 1] - p
            d33 = -p
            vm[i] = np.sqrt(1.5 * (d11**2 + d22**2 + d33**2 + 2 * s[0, 1]**2))

    return vm
