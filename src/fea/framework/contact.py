"""접촉 알고리즘.

노드-노드 페널티 접촉을 구현한다.
KDTree 기반 근접 쌍 탐색 + 페널티 반발력 계산.
"""

import enum
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple


class ContactType(enum.Enum):
    """접촉 유형."""
    PENALTY = "penalty"   # 페널티 접촉 (반발력)
    TIED = "tied"         # 구속 접촉 (변위 공유, 향후 구현)


@dataclass
class ContactDefinition:
    """두 물체 간 접촉 정의.

    Args:
        body_idx_a: Scene 내 물체 A 인덱스
        body_idx_b: Scene 내 물체 B 인덱스
        method: 접촉 유형
        penalty: 페널티 강성 [N/m]
        gap_tolerance: 접촉 감지 거리 [m]
        surface_a: 물체 A 접촉면 인덱스 (None이면 전체 경계)
        surface_b: 물체 B 접촉면 인덱스 (None이면 전체 경계)
    """
    body_idx_a: int
    body_idx_b: int
    method: ContactType = ContactType.PENALTY
    penalty: float = 1e6
    gap_tolerance: float = 0.0
    surface_a: Optional[np.ndarray] = field(default=None, repr=False)
    surface_b: Optional[np.ndarray] = field(default=None, repr=False)


class NodeNodeContact:
    """노드-노드 페널티 접촉 계산.

    두 점집합(노드 또는 입자) 사이의 페널티 접촉력을 계산한다.
    """

    def detect(
        self,
        pos_a: np.ndarray,
        pos_b: np.ndarray,
        surface_a: np.ndarray,
        surface_b: np.ndarray,
        gap_tol: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """KDTree 기반 근접 노드 쌍 탐색.

        Args:
            pos_a: 물체 A 전체 좌표 (n_a, dim)
            pos_b: 물체 B 전체 좌표 (n_b, dim)
            surface_a: A 접촉면 인덱스
            surface_b: B 접촉면 인덱스
            gap_tol: 접촉 감지 거리

        Returns:
            pairs: (n_contacts, 2) — (idx_a, idx_b) 전역 인덱스 쌍
            gaps: (n_contacts,) — 각 쌍의 거리
        """
        from scipy.spatial import cKDTree

        # B 표면 노드로 KDTree 구성
        pts_b = pos_b[surface_b]
        tree_b = cKDTree(pts_b)

        # A 표면 노드에서 B까지 최근접 탐색
        pts_a = pos_a[surface_a]
        dists, local_b_indices = tree_b.query(pts_a)

        # gap_tol 이내인 쌍만 선택
        mask = dists < gap_tol
        if not np.any(mask):
            return np.empty((0, 2), dtype=np.int64), np.empty(0)

        pairs_a = surface_a[mask]
        pairs_b = surface_b[local_b_indices[mask]]
        gaps = dists[mask]

        pairs = np.column_stack([pairs_a, pairs_b])
        return pairs, gaps

    def compute_forces(
        self,
        pos_a: np.ndarray,
        pos_b: np.ndarray,
        pairs: np.ndarray,
        gaps: np.ndarray,
        penalty: float,
        gap_tol: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """페널티 접촉력 계산.

        접촉력 = penalty × penetration × normal
        penetration = gap_tol - distance (양수일 때만)
        normal = (pos_a[i] - pos_b[j]) / distance (A에서 B로의 방향)

        Args:
            pos_a: 물체 A 전체 좌표 (n_a, dim)
            pos_b: 물체 B 전체 좌표 (n_b, dim)
            pairs: 접촉 쌍 (n_contacts, 2)
            gaps: 각 쌍의 거리 (n_contacts,)
            penalty: 페널티 강성
            gap_tol: 접촉 감지 거리

        Returns:
            forces_a: (n_a, dim) — 물체 A에 가해지는 접촉력
            forces_b: (n_b, dim) — 물체 B에 가해지는 접촉력
        """
        dim = pos_a.shape[1]
        forces_a = np.zeros_like(pos_a)
        forces_b = np.zeros_like(pos_b)

        if len(pairs) == 0:
            return forces_a, forces_b

        idx_a = pairs[:, 0]
        idx_b = pairs[:, 1]

        # 관통 깊이
        penetration = gap_tol - gaps  # 양수 = 관통

        # 법선 방향 (A에서 B로의 반발 방향)
        diff = pos_a[idx_a] - pos_b[idx_b]  # (n_contacts, dim)
        norms = np.linalg.norm(diff, axis=1, keepdims=True)
        # 거리 0 방지
        norms = np.maximum(norms, 1e-15)
        normals = diff / norms  # A를 B에서 밀어내는 방향

        # 접촉력: 관통 시에만
        f_mag = penalty * penetration  # (n_contacts,)
        f_vec = f_mag[:, np.newaxis] * normals  # (n_contacts, dim)

        # 작용-반작용
        np.add.at(forces_a, idx_a, f_vec)
        np.add.at(forces_b, idx_b, -f_vec)

        return forces_a, forces_b
