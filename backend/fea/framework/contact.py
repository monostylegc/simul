"""접촉 알고리즘.

노드-노드 페널티 접촉을 구현한다.
KDTree 기반 근접 쌍 탐색 + 페널티 반발력 + 접촉 감쇠.
"""

import enum
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple


class ContactType(enum.Enum):
    """접촉 유형."""
    PENALTY = "penalty"   # 페널티 접촉 (반발력)
    TIED = "tied"         # 구속 접촉 (초기 상대 위치 유지)


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
    static_friction: float = 0.0   # 정적 마찰 계수 (0이면 마찰 없음)
    dynamic_friction: float = 0.0  # 동적 마찰 계수 (0이면 static과 동일)


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
        vel_a: Optional[np.ndarray] = None,
        vel_b: Optional[np.ndarray] = None,
        damping_ratio: float = 0.0,
        mass_a: Optional[np.ndarray] = None,
        mass_b: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """페널티 접촉력 + 법선 감쇠력 계산.

        접촉력 = penalty × penetration × normal
        감쇠력 = -c × v_rel_n × normal  (c = 2ξ√(k·m))
        penetration = gap_tol - distance (양수일 때만)
        normal = (pos_a[i] - pos_b[j]) / distance (A에서 B로의 방향)

        Args:
            pos_a: 물체 A 전체 좌표 (n_a, dim)
            pos_b: 물체 B 전체 좌표 (n_b, dim)
            pairs: 접촉 쌍 (n_contacts, 2)
            gaps: 각 쌍의 거리 (n_contacts,)
            penalty: 페널티 강성
            gap_tol: 접촉 감지 거리
            vel_a: 물체 A 속도 (n_a, dim), 감쇠 시 필요
            vel_b: 물체 B 속도 (n_b, dim), 감쇠 시 필요
            damping_ratio: 감쇠비 ξ (0~1, 0이면 감쇠 없음)
            mass_a: 물체 A 질량 (n_a,), 감쇠 시 필요
            mass_b: 물체 B 질량 (n_b,), 감쇠 시 필요

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

        # 페널티 접촉력: 관통 시에만
        f_mag = penalty * penetration  # (n_contacts,)
        f_vec = f_mag[:, np.newaxis] * normals  # (n_contacts, dim)

        # 접촉 감쇠력 (법선 방향 점성 감쇠)
        if damping_ratio > 0.0 and vel_a is not None and vel_b is not None:
            v_rel = vel_a[idx_a] - vel_b[idx_b]  # 상대 속도
            v_rel_n = np.sum(v_rel * normals, axis=1)  # 법선 방향 상대 속도

            # 유효 질량: m_eff = m_a * m_b / (m_a + m_b)
            if mass_a is not None and mass_b is not None:
                m_a = mass_a[idx_a]
                m_b = mass_b[idx_b]
                m_eff = m_a * m_b / (m_a + m_b + 1e-30)
            else:
                m_eff = np.ones(len(pairs))

            # 감쇠 계수: c = 2ξ√(k·m)
            c_damp = 2.0 * damping_ratio * np.sqrt(penalty * m_eff)
            f_damp = -c_damp * v_rel_n  # (n_contacts,)
            f_vec += f_damp[:, np.newaxis] * normals

        # 작용-반작용
        np.add.at(forces_a, idx_a, f_vec)
        np.add.at(forces_b, idx_b, -f_vec)

        return forces_a, forces_b

    def detect_tied_pairs(
        self,
        pos_a: np.ndarray,
        pos_b: np.ndarray,
        surface_a: np.ndarray,
        surface_b: np.ndarray,
        gap_tol: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Tied 접촉을 위한 초기 쌍 및 기준 오프셋 계산.

        gap_tol 이내의 최근접 노드 쌍을 찾고,
        초기 상대 변위 벡터(ref_offsets)를 저장한다.

        Args:
            pos_a: 물체 A 전체 좌표 (n_a, dim)
            pos_b: 물체 B 전체 좌표 (n_b, dim)
            surface_a: A 접촉면 인덱스
            surface_b: B 접촉면 인덱스
            gap_tol: 접촉 감지 거리

        Returns:
            pairs: (n_tied, 2) — 고정된 (idx_a, idx_b) 전역 인덱스 쌍
            ref_offsets: (n_tied, dim) — 초기 상대 변위 벡터
        """
        from scipy.spatial import cKDTree

        pts_b = pos_b[surface_b]
        tree_b = cKDTree(pts_b)

        pts_a = pos_a[surface_a]
        dists, local_b_indices = tree_b.query(pts_a)

        # gap_tol 이내 쌍 선택
        mask = dists < gap_tol
        if not np.any(mask):
            dim = pos_a.shape[1]
            return np.empty((0, 2), dtype=np.int64), np.empty((0, dim))

        pairs_a = surface_a[mask]
        pairs_b = surface_b[local_b_indices[mask]]
        pairs = np.column_stack([pairs_a, pairs_b])

        # 초기 상대 변위 벡터 저장
        ref_offsets = pos_a[pairs_a] - pos_b[pairs_b]

        return pairs, ref_offsets

    def compute_tied_forces(
        self,
        pos_a: np.ndarray,
        pos_b: np.ndarray,
        pairs: np.ndarray,
        ref_offsets: np.ndarray,
        penalty: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """구속(Tied) 접촉력 계산.

        초기 상대 위치를 유지하는 양방향 페널티 스프링.
        인장과 압축 모두에 저항한다 (= 접착 접촉).

        deviation = (pos_a[i] - pos_b[j]) - ref_offset[k]
        force = -penalty × deviation  (A에 작용)
        반작용 = +penalty × deviation (B에 작용)

        Args:
            pos_a: 물체 A 현재 좌표 (n_a, dim)
            pos_b: 물체 B 현재 좌표 (n_b, dim)
            pairs: 사전 계산된 고정 쌍 (n_tied, 2)
            ref_offsets: 초기 상대 변위 벡터 (n_tied, dim)
            penalty: 페널티 강성 [N/m]

        Returns:
            forces_a: (n_a, dim) — 물체 A에 가해지는 접촉력
            forces_b: (n_b, dim) — 물체 B에 가해지는 접촉력
        """
        forces_a = np.zeros_like(pos_a)
        forces_b = np.zeros_like(pos_b)

        if len(pairs) == 0:
            return forces_a, forces_b

        idx_a = pairs[:, 0]
        idx_b = pairs[:, 1]

        # 현재 상대 변위 - 초기 상대 변위 = 이탈량
        current_offset = pos_a[idx_a] - pos_b[idx_b]
        deviation = current_offset - ref_offsets

        # 양방향 페널티 스프링 (인장+압축 모두 저항)
        f_vec = -penalty * deviation  # A에 작용하는 복원력

        # 작용-반작용
        np.add.at(forces_a, idx_a, f_vec)
        np.add.at(forces_b, idx_b, -f_vec)

        return forces_a, forces_b

    def compute_forces_with_friction(
        self,
        pos_a: np.ndarray,
        pos_b: np.ndarray,
        pairs: np.ndarray,
        gaps: np.ndarray,
        penalty: float,
        gap_tol: float,
        vel_a: np.ndarray,
        vel_b: np.ndarray,
        static_friction: float,
        dynamic_friction: float,
        dt: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """페널티 접촉력 + Coulomb 마찰력 계산.

        법선력은 기존과 동일하게 계산하고,
        접선 방향으로 penalty-regularized Coulomb 마찰력을 추가한다.

        Stick 조건: |f_t_trial| ≤ μ_s × |f_n| → f_t = f_t_trial
        Slip 조건: |f_t_trial| > μ_s × |f_n| → f_t = μ_d × |f_n| × direction

        Args:
            pos_a, pos_b: 물체 좌표
            pairs, gaps: 접촉 쌍과 거리
            penalty: 페널티 강성
            gap_tol: 접촉 감지 거리
            vel_a, vel_b: 물체 속도 (n, dim)
            static_friction: 정적 마찰 계수
            dynamic_friction: 동적 마찰 계수
            dt: 시간 간격

        Returns:
            forces_a, forces_b: 법선 + 접선 합산 접촉력
        """
        dim = pos_a.shape[1]
        forces_a = np.zeros_like(pos_a)
        forces_b = np.zeros_like(pos_b)

        if len(pairs) == 0:
            return forces_a, forces_b

        idx_a = pairs[:, 0]
        idx_b = pairs[:, 1]

        # 관통 깊이
        penetration = gap_tol - gaps

        # 법선 방향
        diff = pos_a[idx_a] - pos_b[idx_b]
        norms = np.linalg.norm(diff, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-15)
        normals = diff / norms

        # 법선 접촉력
        f_n_mag = penalty * penetration
        f_n_vec = f_n_mag[:, np.newaxis] * normals

        # 상대 속도
        v_rel = vel_a[idx_a] - vel_b[idx_b]

        # 법선 방향 상대 속도
        v_rel_n = np.sum(v_rel * normals, axis=1, keepdims=True)

        # 접선 방향 상대 속도
        v_t = v_rel - v_rel_n * normals

        # 시도 마찰력: penalty 기반 접선력
        v_t_mag = np.linalg.norm(v_t, axis=1, keepdims=True)
        v_t_mag = np.maximum(v_t_mag, 1e-30)

        # 접선 페널티로 시도 마찰력 계산
        f_t_trial = penalty * v_t * dt

        f_t_trial_mag = np.linalg.norm(f_t_trial, axis=1)

        # Coulomb 제한
        f_n_abs = np.abs(f_n_mag)
        coulomb_limit = static_friction * f_n_abs

        # Stick/Slip 분류
        is_slip = f_t_trial_mag > coulomb_limit
        is_stick = ~is_slip

        # 마찰력 계산
        f_t_vec = np.zeros_like(f_t_trial)

        # Stick: 시도 마찰력 그대로
        if np.any(is_stick):
            f_t_vec[is_stick] = f_t_trial[is_stick]

        # Slip: 동적 마찰 × |f_n| × 방향
        if np.any(is_slip):
            slip_dir = f_t_trial[is_slip] / (
                f_t_trial_mag[is_slip, np.newaxis] + 1e-30
            )
            f_t_vec[is_slip] = (
                dynamic_friction * f_n_abs[is_slip, np.newaxis] * slip_dir
            )

        # 총 접촉력 = 법선 + 접선
        f_total = f_n_vec + f_t_vec

        # 작용-반작용
        np.add.at(forces_a, idx_a, f_total)
        np.add.at(forces_b, idx_b, -f_total)

        return forces_a, forces_b
