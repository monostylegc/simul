"""GMSH .msh v4 파일 리더.

GMSH v4 ASCII 형식의 메쉬 파일에서 데이터를 파싱한다.

지원 섹션:
- $MeshFormat: 버전/타입 확인
- $Nodes: 노드 좌표 (엔터티 블록 형식)
- $Elements: 요소 연결 (엔터티 블록 형식)
- $PhysicalNames: 물리 그룹 이름

참고: GMSH는 0-based 또는 1-based가 아닌 엔터티 기반 인덱싱.
    최종 출력은 0-based 연속 인덱스로 변환.
"""

import numpy as np
from typing import Dict, Optional, Union
from pathlib import Path

from ..core.element import ElementType
from .abaqus_reader import MeshData

# GMSH 요소 타입 코드 → (ElementType, 차원)
_GMSH_ELEMENT_TYPES = {
    1: (None, 1),                  # 2노드 선분 (경계용, 체적 아님)
    2: (ElementType.TRI3, 2),      # 3노드 삼각형
    3: (ElementType.QUAD4, 2),     # 4노드 사각형
    4: (ElementType.TET4, 3),      # 4노드 사면체
    5: (ElementType.HEX8, 3),      # 8노드 육면체
    8: (None, 1),                  # 3노드 2차 선분
    9: (ElementType.TRI6, 2),      # 6노드 2차 삼각형
    10: (ElementType.QUAD8, 2),    # 8노드 2차 사각형 (Serendipity)
    11: (ElementType.TET10, 3),    # 10노드 2차 사면체
    12: (ElementType.HEX20, 3),    # 20노드 2차 육면체 (Serendipity)
    15: (None, 0),                 # 1노드 점 (경계)
}


def read_gmsh_msh(source: Union[str, Path]) -> MeshData:
    """GMSH .msh v4 ASCII 파일 파싱.

    Args:
        source: 파일 경로 또는 .msh 형식 문자열

    Returns:
        MeshData 파싱 결과 (체적 요소만)
    """
    source_path = Path(source) if not isinstance(source, Path) else source
    if source_path.exists():
        text = source_path.read_text(encoding="utf-8")
    else:
        text = str(source)

    lines = text.splitlines()
    n_lines = len(lines)

    # 파싱 결과
    raw_nodes = {}          # 노드 태그 → 좌표
    raw_elements = []       # (요소 태그, gmsh_type, 노드 태그 리스트)
    physical_names = {}     # (dim, tag) → 이름
    physical_entities = {}  # (dim, entity_tag) → physical_tag

    i = 0
    while i < n_lines:
        line = lines[i].strip()

        if line == "$MeshFormat":
            i += 1
            parts = lines[i].strip().split()
            version = float(parts[0])
            file_type = int(parts[1])  # 0=ASCII
            if version < 4.0:
                raise ValueError(
                    f"GMSH v{version} 미지원. v4.0 이상만 지원합니다."
                )
            if file_type != 0:
                raise ValueError("바이너리 .msh 미지원. ASCII로 내보내기하세요.")
            i += 1  # $EndMeshFormat

        elif line == "$PhysicalNames":
            i += 1
            n_names = int(lines[i].strip())
            i += 1
            for _ in range(n_names):
                parts = lines[i].strip().split()
                dim = int(parts[0])
                tag = int(parts[1])
                name = parts[2].strip('"')
                physical_names[(dim, tag)] = name
                i += 1

        elif line == "$Entities":
            i += 1
            counts = lines[i].strip().split()
            n_points = int(counts[0])
            n_curves = int(counts[1])
            n_surfaces = int(counts[2])
            n_volumes = int(counts[3])
            i += 1

            # 점 엔터티
            for _ in range(n_points):
                parts = lines[i].strip().split()
                entity_tag = int(parts[0])
                # 점: x, y, z, numPhysicalTags, [physicalTags...]
                n_phys = int(parts[4])
                if n_phys > 0:
                    phys_tag = int(parts[5])
                    physical_entities[(0, entity_tag)] = phys_tag
                i += 1

            # 곡선 엔터티
            for _ in range(n_curves):
                parts = lines[i].strip().split()
                entity_tag = int(parts[0])
                # 곡선: minX, minY, minZ, maxX, maxY, maxZ, numPhys, [phys...], numBndPts, [bnd...]
                n_phys = int(parts[7])
                if n_phys > 0:
                    phys_tag = int(parts[8])
                    physical_entities[(1, entity_tag)] = phys_tag
                i += 1

            # 면 엔터티
            for _ in range(n_surfaces):
                parts = lines[i].strip().split()
                entity_tag = int(parts[0])
                n_phys = int(parts[7])
                if n_phys > 0:
                    phys_tag = int(parts[8])
                    physical_entities[(2, entity_tag)] = phys_tag
                i += 1

            # 체적 엔터티
            for _ in range(n_volumes):
                parts = lines[i].strip().split()
                entity_tag = int(parts[0])
                n_phys = int(parts[7])
                if n_phys > 0:
                    phys_tag = int(parts[8])
                    physical_entities[(3, entity_tag)] = phys_tag
                i += 1

        elif line == "$Nodes":
            i += 1
            header = lines[i].strip().split()
            n_entity_blocks = int(header[0])
            # n_total_nodes = int(header[1])
            i += 1

            for _ in range(n_entity_blocks):
                block_header = lines[i].strip().split()
                # entity_dim = int(block_header[0])
                # entity_tag = int(block_header[1])
                # parametric = int(block_header[2])
                n_block_nodes = int(block_header[3])
                i += 1

                # 노드 태그 읽기
                tags = []
                for _ in range(n_block_nodes):
                    tags.append(int(lines[i].strip()))
                    i += 1

                # 좌표 읽기
                for j, tag in enumerate(tags):
                    parts = lines[i].strip().split()
                    coords = [float(p) for p in parts]
                    raw_nodes[tag] = coords
                    i += 1

        elif line == "$Elements":
            i += 1
            header = lines[i].strip().split()
            n_entity_blocks = int(header[0])
            i += 1

            for _ in range(n_entity_blocks):
                block_header = lines[i].strip().split()
                entity_dim = int(block_header[0])
                entity_tag = int(block_header[1])
                gmsh_type = int(block_header[2])
                n_block_elems = int(block_header[3])
                i += 1

                for _ in range(n_block_elems):
                    parts = lines[i].strip().split()
                    elem_tag = int(parts[0])
                    node_tags = [int(p) for p in parts[1:]]
                    raw_elements.append(
                        (elem_tag, gmsh_type, node_tags, entity_dim, entity_tag)
                    )
                    i += 1
        else:
            i += 1

    # ─── 검증 ───
    if not raw_nodes:
        raise ValueError("$Nodes 섹션이 없거나 비어 있습니다.")
    if not raw_elements:
        raise ValueError("$Elements 섹션이 없거나 비어 있습니다.")

    # ─── 최고 차원 요소 필터링 ───
    max_dim = max(e[3] for e in raw_elements)
    volume_elements = [e for e in raw_elements if e[3] == max_dim]

    if not volume_elements:
        raise ValueError("체적(최고 차원) 요소가 없습니다.")

    # 요소 타입 결정 (단일 타입만 지원)
    gmsh_types_used = set(e[1] for e in volume_elements)
    if len(gmsh_types_used) > 1:
        raise ValueError(
            f"혼합 요소 타입 미지원: GMSH 타입 {gmsh_types_used}. "
            "단일 요소 타입만 지원합니다."
        )

    gmsh_type = gmsh_types_used.pop()
    if gmsh_type not in _GMSH_ELEMENT_TYPES:
        raise ValueError(f"미지원 GMSH 요소 타입: {gmsh_type}")

    element_type, _ = _GMSH_ELEMENT_TYPES[gmsh_type]
    if element_type is None:
        raise ValueError(
            f"GMSH 요소 타입 {gmsh_type}은 체적 요소가 아닙니다."
        )

    # ─── 노드 태그 → 연속 인덱스 매핑 ───
    # 체적 요소가 참조하는 노드만 추출
    used_node_tags = set()
    for _, _, node_tags, _, _ in volume_elements:
        used_node_tags.update(node_tags)

    sorted_tags = sorted(used_node_tags)
    tag_to_idx = {tag: idx for idx, tag in enumerate(sorted_tags)}

    # 차원 결정
    sample_coords = raw_nodes[sorted_tags[0]]
    dim = len(sample_coords)
    # 3D 좌표인데 2D 요소이면 z=0 확인 후 2D로 축소
    if dim == 3 and max_dim == 2:
        all_z = [raw_nodes[t][2] for t in sorted_tags]
        if all(abs(z) < 1e-10 for z in all_z):
            dim = 2

    # 노드 좌표 배열
    nodes = np.array(
        [raw_nodes[tag][:dim] for tag in sorted_tags], dtype=np.float64
    )

    # 요소 배열 (0-based)
    elements = np.array(
        [[tag_to_idx[t] for t in e[2]] for e in volume_elements],
        dtype=np.int32,
    )

    # 물리 그룹 → 노드/요소 집합
    node_sets = {}
    element_sets = {}

    for _, _, _, entity_dim, entity_tag in volume_elements:
        phys_key = (entity_dim, entity_tag)
        if phys_key in physical_entities:
            phys_tag = physical_entities[phys_key]
            name_key = (entity_dim, phys_tag)
            if name_key in physical_names:
                name = physical_names[name_key]
            else:
                name = f"Physical{entity_dim}D_{phys_tag}"

            if name not in element_sets:
                element_sets[name] = []

    # 요소 집합 채우기
    for idx, (_, _, node_tags, entity_dim, entity_tag) in enumerate(
        volume_elements
    ):
        phys_key = (entity_dim, entity_tag)
        if phys_key in physical_entities:
            phys_tag = physical_entities[phys_key]
            name_key = (entity_dim, phys_tag)
            name = physical_names.get(name_key, f"Physical{entity_dim}D_{phys_tag}")
            if name not in element_sets:
                element_sets[name] = []
            element_sets[name].append(idx)

    # numpy 변환
    for name in element_sets:
        element_sets[name] = np.array(element_sets[name], dtype=np.int64)

    return MeshData(
        nodes=nodes,
        elements=elements,
        element_type=element_type,
        node_sets=node_sets,
        element_sets=element_sets,
    )
