"""메쉬 영역 분할기.

FEM 메쉬를 FEM 서브메쉬 + PD/SPG 입자 영역으로 분할한다.
PD 입자는 FEM 노드 위치에 직접 배치하여 인터페이스 보간을 제거한다.

인터페이스 판별:
    S_fem = FEM 요소가 사용하는 노드 집합
    S_pd  = PD  요소가 사용하는 노드 집합
    인터페이스 = S_fem ∩ S_pd
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class ZoneSplit:
    """메쉬 분할 결과.

    Attributes:
        fem_elements: FEM 영역 요소 연결 (재번호, n_fem_elem × npe)
        fem_nodes: FEM 영역 노드 좌표 (n_fem_nodes × dim)
        fem_node_global: FEM 로컬→원본 인덱스 매핑 (n_fem_nodes,)
        global_to_fem: 원본→FEM 로컬 딕셔너리 (인터페이스 전용도 포함)
        pd_nodes: PD 입자 좌표 (n_pd_particles × dim)
        pd_volumes: PD 입자 부피 (n_pd_particles,)
        pd_node_global: PD 로컬→원본 인덱스 매핑 (n_pd_particles,)
        global_to_pd: 원본→PD 로컬 딕셔너리
        interface_global: 인터페이스 노드 원본 인덱스 (n_interface,)
        interface_fem: 인터페이스 노드 FEM 로컬 인덱스 (n_interface,)
        interface_pd: 인터페이스 노드 PD 로컬 인덱스 (n_interface,)
        pd_element_mask: PD 영역 요소 마스크 (n_elements,)
    """
    fem_elements: np.ndarray
    fem_nodes: np.ndarray
    fem_node_global: np.ndarray
    global_to_fem: dict
    pd_nodes: np.ndarray
    pd_volumes: np.ndarray
    pd_node_global: np.ndarray
    global_to_pd: dict
    interface_global: np.ndarray
    interface_fem: np.ndarray
    interface_pd: np.ndarray
    pd_element_mask: np.ndarray


def split_mesh(
    nodes: np.ndarray,
    elements: np.ndarray,
    pd_element_mask: np.ndarray,
    element_volumes: Optional[np.ndarray] = None,
) -> ZoneSplit:
    """메쉬를 FEM/PD 영역으로 분할.

    Args:
        nodes: (n_nodes, dim) 전체 노드 좌표
        elements: (n_elements, npe) 전체 요소 연결
        pd_element_mask: (n_elements,) bool — PD 영역 요소 마스크
        element_volumes: (n_elements,) 요소 부피 (None이면 자동 계산)

    Returns:
        ZoneSplit 객체
    """
    n_nodes = len(nodes)
    n_elements = len(elements)
    npe = elements.shape[1]
    dim = nodes.shape[1]
    pd_element_mask = np.asarray(pd_element_mask, dtype=bool)

    # ── 노드 집합 구분 ──
    fem_elem_mask = ~pd_element_mask
    fem_elem_indices = np.where(fem_elem_mask)[0]
    pd_elem_indices = np.where(pd_element_mask)[0]

    # 각 영역이 사용하는 노드 집합
    fem_node_set = set(elements[fem_elem_indices].ravel())
    pd_node_set = set(elements[pd_elem_indices].ravel())

    # 인터페이스 = 양쪽 공유 노드
    interface_set = fem_node_set & pd_node_set

    # FEM 영역: FEM 요소가 사용하는 모든 노드 (인터페이스 포함)
    fem_node_sorted = np.array(sorted(fem_node_set), dtype=np.int64)
    # PD 영역: PD 요소가 사용하는 모든 노드 (인터페이스 포함)
    pd_node_sorted = np.array(sorted(pd_node_set), dtype=np.int64)
    # 인터페이스
    interface_sorted = np.array(sorted(interface_set), dtype=np.int64)

    # ── FEM 서브메쉬 (노드 재번호) ──
    global_to_fem = {g: i for i, g in enumerate(fem_node_sorted)}
    fem_nodes_out = nodes[fem_node_sorted]

    # FEM 요소 재번호
    fem_elements_out = np.empty((len(fem_elem_indices), npe), dtype=np.int64)
    for col in range(npe):
        for row_idx, elem_idx in enumerate(fem_elem_indices):
            fem_elements_out[row_idx, col] = global_to_fem[elements[elem_idx, col]]

    # ── PD 입자 배열 ──
    global_to_pd = {g: i for i, g in enumerate(pd_node_sorted)}
    pd_nodes_out = nodes[pd_node_sorted]

    # PD 입자 부피: 요소 부피를 노드에 균등 분배
    pd_volumes_out = _compute_particle_volumes(
        nodes, elements, pd_elem_indices, pd_node_sorted, global_to_pd,
        npe, dim, element_volumes,
    )

    # ── 인터페이스 인덱스 매핑 ──
    interface_fem = np.array(
        [global_to_fem[g] for g in interface_sorted], dtype=np.int64
    )
    interface_pd = np.array(
        [global_to_pd[g] for g in interface_sorted], dtype=np.int64
    )

    return ZoneSplit(
        fem_elements=fem_elements_out,
        fem_nodes=fem_nodes_out,
        fem_node_global=fem_node_sorted,
        global_to_fem=global_to_fem,
        pd_nodes=pd_nodes_out,
        pd_volumes=pd_volumes_out,
        pd_node_global=pd_node_sorted,
        global_to_pd=global_to_pd,
        interface_global=interface_sorted,
        interface_fem=interface_fem,
        interface_pd=interface_pd,
        pd_element_mask=pd_element_mask,
    )


def _compute_particle_volumes(
    nodes: np.ndarray,
    elements: np.ndarray,
    pd_elem_indices: np.ndarray,
    pd_node_sorted: np.ndarray,
    global_to_pd: dict,
    npe: int,
    dim: int,
    element_volumes: Optional[np.ndarray],
) -> np.ndarray:
    """PD 입자 부피 계산.

    각 PD 요소의 부피를 그 요소의 노드에 균등 분배한다.
    (노드별 기여 부피 합산)

    Args:
        nodes: 전체 노드 좌표
        elements: 전체 요소 연결
        pd_elem_indices: PD 영역 요소 인덱스
        pd_node_sorted: PD 노드 원본 인덱스 (정렬)
        global_to_pd: 원본→PD 로컬 매핑
        npe: 요소당 노드 수
        dim: 공간 차원
        element_volumes: 요소 부피 (None이면 자동 계산)

    Returns:
        (n_pd_particles,) 입자 부피
    """
    n_pd = len(pd_node_sorted)
    volumes = np.zeros(n_pd, dtype=np.float64)

    for e_idx in pd_elem_indices:
        if element_volumes is not None:
            vol = element_volumes[e_idx]
        else:
            vol = _estimate_element_volume(nodes, elements[e_idx], dim)

        # 요소 부피를 노드에 균등 분배
        vol_per_node = vol / npe
        for local_node in elements[e_idx]:
            if local_node in global_to_pd:
                volumes[global_to_pd[local_node]] += vol_per_node

    return volumes


def _estimate_element_volume(
    nodes: np.ndarray,
    elem_conn: np.ndarray,
    dim: int,
) -> float:
    """요소 부피 근사 (바운딩박스 기반).

    정확한 가우스 적분 부피가 없을 때 사용하는 간단한 근사값.

    Args:
        nodes: 전체 노드 좌표
        elem_conn: 요소 연결 (npe,)
        dim: 공간 차원

    Returns:
        요소 부피 근사값
    """
    elem_nodes = nodes[elem_conn]
    bbox_min = elem_nodes.min(axis=0)
    bbox_max = elem_nodes.max(axis=0)
    size = bbox_max - bbox_min

    # HEX8/QUAD4: 바운딩박스 부피 ≈ 실제 부피 (정렬 요소 가정)
    vol = 1.0
    for d in range(dim):
        vol *= max(size[d], 1e-20)
    return vol
