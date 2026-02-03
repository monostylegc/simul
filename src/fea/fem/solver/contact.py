"""접촉 조건 (Contact) 모듈.

Penalty method 기반 노드-표면 접촉.
두 개의 메쉬 사이 접촉력 계산.
"""

import numpy as np
from scipy.spatial import cKDTree
from typing import Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class ContactPair:
    """접촉 쌍 정의."""
    master_vertices: np.ndarray  # 마스터 표면 정점 (N, 3)
    master_faces: np.ndarray     # 마스터 표면 삼각형 (M, 3)
    slave_node_ids: np.ndarray   # 슬레이브 노드 인덱스
    penalty: float = 1e6         # 페널티 강성 [N/mm³]


class PenaltyContact:
    """Penalty method 기반 접촉 처리.

    마스터 표면에 슬레이브 노드가 관통하면 페널티 힘 적용.
    """

    def __init__(self, penalty: float = 1e6):
        """
        Args:
            penalty: 페널티 강성 [N/mm³]
        """
        self.penalty = penalty
        self.contact_pairs: List[ContactPair] = []

    def add_contact_pair(
        self,
        master_vertices: np.ndarray,
        master_faces: np.ndarray,
        slave_node_ids: np.ndarray,
        penalty: Optional[float] = None
    ):
        """접촉 쌍 추가.

        Args:
            master_vertices: 마스터 표면 정점
            master_faces: 마스터 표면 삼각형
            slave_node_ids: 슬레이브 노드 인덱스 (전체 메쉬 기준)
            penalty: 이 쌍의 페널티 강성 (없으면 기본값)
        """
        pair = ContactPair(
            master_vertices=master_vertices.astype(np.float32),
            master_faces=master_faces.astype(np.int32),
            slave_node_ids=slave_node_ids.astype(np.int32),
            penalty=penalty if penalty else self.penalty
        )
        self.contact_pairs.append(pair)

    def compute_contact_forces(
        self,
        current_positions: np.ndarray,
        gap_tolerance: float = 0.1
    ) -> Tuple[np.ndarray, np.ndarray]:
        """접촉력 계산.

        Args:
            current_positions: 현재 노드 위치 (n_nodes, 3)
            gap_tolerance: 접촉 감지 허용치 [mm]

        Returns:
            contact_forces: 접촉력 (n_nodes, 3)
            penetrations: 관통량 (n_contact_nodes,)
        """
        n_nodes = len(current_positions)
        contact_forces = np.zeros((n_nodes, 3), dtype=np.float32)
        all_penetrations = []

        for pair in self.contact_pairs:
            # 슬레이브 노드 위치
            slave_positions = current_positions[pair.slave_node_ids]

            # 마스터 표면과의 거리 및 관통 계산
            forces, penetrations = self._compute_pair_forces(
                pair.master_vertices,
                pair.master_faces,
                slave_positions,
                pair.penalty,
                gap_tolerance
            )

            # 전체 힘 배열에 추가
            contact_forces[pair.slave_node_ids] += forces
            all_penetrations.extend(penetrations)

        return contact_forces, np.array(all_penetrations)

    def _compute_pair_forces(
        self,
        master_verts: np.ndarray,
        master_faces: np.ndarray,
        slave_pos: np.ndarray,
        penalty: float,
        gap_tol: float
    ) -> Tuple[np.ndarray, List[float]]:
        """단일 접촉 쌍의 힘 계산."""
        n_slaves = len(slave_pos)
        forces = np.zeros((n_slaves, 3), dtype=np.float32)
        penetrations = []

        # KD-tree로 가까운 삼각형 빠르게 찾기
        # 삼각형 중심점 사용
        face_centers = master_verts[master_faces].mean(axis=1)
        tree = cKDTree(face_centers)

        for i, pos in enumerate(slave_pos):
            # 가장 가까운 삼각형 찾기
            dist, idx = tree.query(pos, k=5)  # 가까운 5개 확인

            min_gap = float('inf')
            best_normal = None

            for face_idx in idx:
                if face_idx >= len(master_faces):
                    continue

                # 삼각형 정점
                tri = master_verts[master_faces[face_idx]]

                # 점과 삼각형 사이 거리 및 법선
                gap, normal, inside = self._point_triangle_distance(pos, tri)

                if gap < min_gap:
                    min_gap = gap
                    best_normal = normal

            # 관통 시 페널티 힘 적용
            if min_gap < gap_tol and best_normal is not None:
                penetration = gap_tol - min_gap
                penetrations.append(penetration)

                # 힘 = penalty * penetration * normal (표면 밖으로)
                force_mag = penalty * penetration
                forces[i] = force_mag * best_normal

        return forces, penetrations

    def _point_triangle_distance(
        self,
        point: np.ndarray,
        triangle: np.ndarray
    ) -> Tuple[float, np.ndarray, bool]:
        """점과 삼각형 사이 거리 계산.

        Args:
            point: 점 위치 (3,)
            triangle: 삼각형 정점 (3, 3)

        Returns:
            distance: 거리 (음수면 관통)
            normal: 표면 법선 (바깥쪽)
            inside: 점이 삼각형 투영 내부인지
        """
        v0, v1, v2 = triangle

        # 삼각형 법선
        edge1 = v1 - v0
        edge2 = v2 - v0
        normal = np.cross(edge1, edge2)
        normal_len = np.linalg.norm(normal)

        if normal_len < 1e-10:
            return float('inf'), np.array([0, 0, 1]), False

        normal = normal / normal_len

        # 점과 삼각형 평면 사이 거리 (부호 있음)
        d = np.dot(point - v0, normal)

        # 투영점
        proj = point - d * normal

        # 투영점이 삼각형 내부인지 확인 (barycentric)
        inside = self._point_in_triangle(proj, v0, v1, v2)

        return d, normal, inside

    def _point_in_triangle(
        self,
        p: np.ndarray,
        v0: np.ndarray,
        v1: np.ndarray,
        v2: np.ndarray
    ) -> bool:
        """점이 삼각형 내부인지 확인 (barycentric coordinates)."""
        v0v1 = v1 - v0
        v0v2 = v2 - v0
        v0p = p - v0

        dot00 = np.dot(v0v2, v0v2)
        dot01 = np.dot(v0v2, v0v1)
        dot02 = np.dot(v0v2, v0p)
        dot11 = np.dot(v0v1, v0v1)
        dot12 = np.dot(v0v1, v0p)

        denom = dot00 * dot11 - dot01 * dot01
        if abs(denom) < 1e-10:
            return False

        inv_denom = 1.0 / denom
        u = (dot11 * dot02 - dot01 * dot12) * inv_denom
        v = (dot00 * dot12 - dot01 * dot02) * inv_denom

        return (u >= 0) and (v >= 0) and (u + v <= 1)


class TiedContact:
    """Tied contact - 노드를 표면에 구속.

    경계면 노드를 가장 가까운 표면에 tie (고정).
    실질적으로 두 메쉬를 연결.
    """

    def __init__(self, tolerance: float = 1.0):
        """
        Args:
            tolerance: 연결 거리 허용치 [mm]
        """
        self.tolerance = tolerance
        self.tied_pairs: List[Tuple[int, int, float]] = []  # (slave_id, master_id, weight)

    def find_tied_nodes(
        self,
        slave_positions: np.ndarray,
        slave_node_ids: np.ndarray,
        master_positions: np.ndarray,
        master_node_ids: np.ndarray
    ) -> List[Tuple[int, int]]:
        """가까운 노드 쌍 찾기.

        Args:
            slave_positions: 슬레이브 노드 위치
            slave_node_ids: 슬레이브 노드 전체 인덱스
            master_positions: 마스터 노드 위치
            master_node_ids: 마스터 노드 전체 인덱스

        Returns:
            tied_pairs: (slave_global_id, master_global_id) 쌍 목록
        """
        tree = cKDTree(master_positions)
        pairs = []

        for i, pos in enumerate(slave_positions):
            dist, idx = tree.query(pos)
            if dist <= self.tolerance:
                slave_global = slave_node_ids[i]
                master_global = master_node_ids[idx]
                pairs.append((slave_global, master_global))

        return pairs

    def apply_tied_constraint(
        self,
        tied_pairs: List[Tuple[int, int]],
        n_nodes: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Tied constraint를 위한 MPC (Multi-Point Constraint) 생성.

        슬레이브 노드 변위 = 마스터 노드 변위
        이를 penalty로 구현.

        Returns:
            slave_ids: 슬레이브 노드 인덱스
            master_ids: 대응 마스터 노드 인덱스
        """
        if not tied_pairs:
            return np.array([], dtype=np.int32), np.array([], dtype=np.int32)

        slave_ids = np.array([p[0] for p in tied_pairs], dtype=np.int32)
        master_ids = np.array([p[1] for p in tied_pairs], dtype=np.int32)

        return slave_ids, master_ids


def create_interface_contact(
    mesh1_nodes: np.ndarray,
    mesh1_surface_nodes: np.ndarray,  # 경계면 노드 인덱스
    mesh2_nodes: np.ndarray,
    mesh2_surface_nodes: np.ndarray,
    method: str = "tied",
    tolerance: float = 2.0
) -> dict:
    """두 메쉬 사이 인터페이스 접촉 생성.

    Args:
        mesh1_nodes: 첫 번째 메쉬 노드 위치
        mesh1_surface_nodes: 첫 번째 메쉬 경계면 노드
        mesh2_nodes: 두 번째 메쉬 노드 위치
        mesh2_surface_nodes: 두 번째 메쉬 경계면 노드
        method: "tied" 또는 "penalty"
        tolerance: 연결 거리

    Returns:
        contact_info: 접촉 정보 딕셔너리
    """
    if method == "tied":
        tied = TiedContact(tolerance=tolerance)

        # mesh1 -> mesh2
        pairs_1to2 = tied.find_tied_nodes(
            mesh1_nodes[mesh1_surface_nodes],
            mesh1_surface_nodes,
            mesh2_nodes[mesh2_surface_nodes],
            mesh2_surface_nodes
        )

        return {
            "method": "tied",
            "pairs": pairs_1to2,
            "n_tied": len(pairs_1to2)
        }

    else:
        # Penalty contact
        return {
            "method": "penalty",
            "mesh1_surface": mesh1_surface_nodes,
            "mesh2_surface": mesh2_surface_nodes
        }
