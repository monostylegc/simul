"""Abaqus .inp 파일 리더.

Abaqus/CalculiX 형식의 입력 파일에서 메쉬 데이터를 파싱한다.

지원 키워드:
- *NODE: 노드 좌표
- *ELEMENT, TYPE=: 요소 연결
- *NSET: 노드 집합 (GENERATE 포함)
- *ELSET: 요소 집합 (GENERATE 포함)
- *BOUNDARY: 고정 경계조건
- *CLOAD: 집중 하중

참고: Abaqus는 1-based 인덱스, 파싱 후 0-based로 변환.
"""

import re
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Union
from pathlib import Path

from ..core.element import ElementType

# Abaqus 요소 타입 → ElementType 매핑
_ABAQUS_TO_ELEMENT_TYPE = {
    "C3D4": ElementType.TET4,
    "C3D10": ElementType.TET10,
    "C3D8": ElementType.HEX8,
    "C3D20": ElementType.HEX20,
    "CPS3": ElementType.TRI3,
    "CPE3": ElementType.TRI3_PE,
    "CPS4": ElementType.QUAD4,
    "CPE4": ElementType.QUAD4_PE,
    "CPS6": ElementType.TRI6,
    "CPE6": ElementType.TRI6_PE,
    "CPS8": ElementType.QUAD8,
    "CPE8": ElementType.QUAD8_PE,
    # CalculiX 호환
    "S3": ElementType.TRI3,
    "S4": ElementType.QUAD4,
}


@dataclass
class MeshData:
    """파싱된 메쉬 데이터.

    Attributes:
        nodes: 노드 좌표 (n_nodes, dim)
        elements: 요소 연결 (n_elements, npe), 0-based
        element_type: 요소 타입
        node_sets: 이름 → 노드 인덱스 (0-based)
        element_sets: 이름 → 요소 인덱스 (0-based)
        fixed_bcs: (노드 인덱스 배열, DOF 인덱스, 값) 리스트
        loads: (노드 인덱스 배열, DOF 인덱스, 크기) 리스트
        material_ids: 요소별 재료 ID (선택적)
    """
    nodes: np.ndarray
    elements: np.ndarray
    element_type: ElementType
    node_sets: Dict[str, np.ndarray] = field(default_factory=dict)
    element_sets: Dict[str, np.ndarray] = field(default_factory=dict)
    fixed_bcs: List[Tuple[np.ndarray, Optional[int], float]] = field(
        default_factory=list
    )
    loads: List[Tuple[np.ndarray, int, float]] = field(default_factory=list)
    material_ids: Optional[np.ndarray] = None


def read_abaqus_inp(source: Union[str, Path]) -> MeshData:
    """Abaqus .inp 파일 파싱.

    Args:
        source: 파일 경로 또는 .inp 형식 문자열

    Returns:
        MeshData 파싱 결과
    """
    # 파일 경로인지 문자열인지 판별
    source_path = Path(source) if not isinstance(source, Path) else source
    if source_path.exists():
        text = source_path.read_text(encoding="utf-8")
    else:
        text = str(source)

    lines = text.splitlines()
    n_lines = len(lines)

    # 파싱 결과 저장
    raw_nodes = {}      # 원본ID → 좌표
    raw_elements = {}   # 원본ID → 노드ID 리스트
    elem_type_str = None
    node_sets = {}
    element_sets = {}
    boundaries = []     # (원본 노드ID, first_dof, last_dof, value)
    cloads = []         # (원본 노드ID, dof, magnitude)

    i = 0
    while i < n_lines:
        line = lines[i].strip()

        # 빈 줄 또는 주석 무시
        if not line or line.startswith("**"):
            i += 1
            continue

        upper = line.upper()

        if upper.startswith("*NODE"):
            i += 1
            while i < n_lines and not lines[i].strip().startswith("*"):
                parts = lines[i].strip().split(",")
                if len(parts) >= 2:
                    nid = int(parts[0].strip())
                    coords = [float(p.strip()) for p in parts[1:] if p.strip()]
                    raw_nodes[nid] = coords
                i += 1

        elif upper.startswith("*ELEMENT"):
            # TYPE= 파라미터 추출
            match = re.search(r"TYPE\s*=\s*(\w+)", upper)
            if match:
                elem_type_str = match.group(1)
            # ELSET= 파라미터 (선택적)
            elset_match = re.search(r"ELSET\s*=\s*(\S+)", upper)
            elset_name = elset_match.group(1).rstrip(",") if elset_match else None

            elset_ids = []
            i += 1
            while i < n_lines and not lines[i].strip().startswith("*"):
                parts = lines[i].strip().rstrip(",").split(",")
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) >= 2:
                    eid = int(parts[0])
                    node_ids = [int(p) for p in parts[1:]]
                    raw_elements[eid] = node_ids
                    elset_ids.append(eid)
                i += 1

            if elset_name:
                element_sets[elset_name.upper()] = elset_ids

        elif upper.startswith("*NSET"):
            # 이름 추출 (후행 쉼표 제거)
            match = re.search(r"NSET\s*=\s*(\S+)", upper)
            name = match.group(1).rstrip(",").upper() if match else "UNNAMED"
            is_generate = "GENERATE" in upper

            ids = []
            i += 1
            while i < n_lines and not lines[i].strip().startswith("*"):
                parts = lines[i].strip().rstrip(",").split(",")
                parts = [p.strip() for p in parts if p.strip()]
                if is_generate and len(parts) >= 2:
                    # GENERATE: start, end[, increment]
                    start = int(parts[0])
                    end = int(parts[1])
                    inc = int(parts[2]) if len(parts) > 2 else 1
                    ids.extend(range(start, end + 1, inc))
                else:
                    ids.extend(int(p) for p in parts if p)
                i += 1
            node_sets[name] = ids

        elif upper.startswith("*ELSET"):
            match = re.search(r"ELSET\s*=\s*(\S+)", upper)
            name = match.group(1).rstrip(",").upper() if match else "UNNAMED"
            is_generate = "GENERATE" in upper

            ids = []
            i += 1
            while i < n_lines and not lines[i].strip().startswith("*"):
                parts = lines[i].strip().rstrip(",").split(",")
                parts = [p.strip() for p in parts if p.strip()]
                if is_generate and len(parts) >= 2:
                    start = int(parts[0])
                    end = int(parts[1])
                    inc = int(parts[2]) if len(parts) > 2 else 1
                    ids.extend(range(start, end + 1, inc))
                else:
                    ids.extend(int(p) for p in parts if p)
                i += 1
            element_sets[name] = ids

        elif upper.startswith("*BOUNDARY"):
            i += 1
            while i < n_lines and not lines[i].strip().startswith("*"):
                parts = lines[i].strip().rstrip(",").split(",")
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) >= 2:
                    # 노드 ID 또는 NSET 이름
                    node_ref = parts[0]
                    first_dof = int(parts[1])
                    last_dof = int(parts[2]) if len(parts) > 2 and parts[2] else first_dof
                    value = float(parts[3]) if len(parts) > 3 and parts[3] else 0.0

                    try:
                        nid = int(node_ref)
                        boundaries.append((nid, first_dof, last_dof, value))
                    except ValueError:
                        # NSET 이름 참조
                        nset_name = node_ref.upper()
                        if nset_name in node_sets:
                            for nid in node_sets[nset_name]:
                                boundaries.append(
                                    (nid, first_dof, last_dof, value)
                                )
                i += 1

        elif upper.startswith("*CLOAD"):
            i += 1
            while i < n_lines and not lines[i].strip().startswith("*"):
                parts = lines[i].strip().rstrip(",").split(",")
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) >= 3:
                    node_ref = parts[0]
                    dof = int(parts[1])
                    magnitude = float(parts[2])

                    try:
                        nid = int(node_ref)
                        cloads.append((nid, dof, magnitude))
                    except ValueError:
                        nset_name = node_ref.upper()
                        if nset_name in node_sets:
                            for nid in node_sets[nset_name]:
                                cloads.append((nid, dof, magnitude))
                i += 1
        else:
            i += 1

    # ─── 검증 ───
    if not raw_nodes:
        raise ValueError("*NODE 섹션이 없거나 비어 있습니다.")
    if not raw_elements:
        raise ValueError("*ELEMENT 섹션이 없거나 비어 있습니다.")
    if elem_type_str is None:
        raise ValueError("*ELEMENT에 TYPE= 파라미터가 없습니다.")

    elem_type_upper = elem_type_str.upper()
    if elem_type_upper not in _ABAQUS_TO_ELEMENT_TYPE:
        raise ValueError(
            f"미지원 요소 타입: {elem_type_str}. "
            f"지원: {list(_ABAQUS_TO_ELEMENT_TYPE.keys())}"
        )
    element_type = _ABAQUS_TO_ELEMENT_TYPE[elem_type_upper]

    # ─── 1-based → 0-based 변환 ───
    # 노드 ID → 연속 인덱스 매핑
    sorted_node_ids = sorted(raw_nodes.keys())
    node_id_to_idx = {nid: idx for idx, nid in enumerate(sorted_node_ids)}

    # 차원 결정
    dim = len(raw_nodes[sorted_node_ids[0]])

    # 노드 좌표 배열
    nodes = np.array(
        [raw_nodes[nid] for nid in sorted_node_ids], dtype=np.float64
    )

    # 요소 연결 배열 (0-based)
    sorted_elem_ids = sorted(raw_elements.keys())
    elem_id_to_idx = {eid: idx for idx, eid in enumerate(sorted_elem_ids)}

    elements = np.array(
        [[node_id_to_idx[nid] for nid in raw_elements[eid]]
         for eid in sorted_elem_ids],
        dtype=np.int32,
    )

    # 노드 집합 변환 (0-based)
    converted_nsets = {}
    for name, ids in node_sets.items():
        converted_nsets[name] = np.array(
            [node_id_to_idx[nid] for nid in ids if nid in node_id_to_idx],
            dtype=np.int64,
        )

    # 요소 집합 변환 (0-based)
    converted_elsets = {}
    for name, ids in element_sets.items():
        converted_elsets[name] = np.array(
            [elem_id_to_idx[eid] for eid in ids if eid in elem_id_to_idx],
            dtype=np.int64,
        )

    # 경계조건 변환 (Abaqus DOF: 1-based → 0-based)
    fixed_bcs = []
    for nid, first_dof, last_dof, value in boundaries:
        if nid not in node_id_to_idx:
            continue
        node_idx = node_id_to_idx[nid]
        for dof in range(first_dof, last_dof + 1):
            dof_0based = dof - 1  # Abaqus 1-based → 0-based
            fixed_bcs.append(
                (np.array([node_idx], dtype=np.int64), dof_0based, value)
            )

    # 집중 하중 변환
    loads = []
    for nid, dof, magnitude in cloads:
        if nid not in node_id_to_idx:
            continue
        node_idx = node_id_to_idx[nid]
        dof_0based = dof - 1
        loads.append(
            (np.array([node_idx], dtype=np.int64), dof_0based, magnitude)
        )

    return MeshData(
        nodes=nodes,
        elements=elements,
        element_type=element_type,
        node_sets=converted_nsets,
        element_sets=converted_elsets,
        fixed_bcs=fixed_bcs,
        loads=loads,
    )
