"""척추 해부학 프로파일.

요추/경추/흉추 공용 재료 물성 및 접촉 규칙을 정의한다.
SpineLabel 열거형(segmentation/labels.py)을 재활용한다.
후관절(facet joint) 자동 인식 기능 포함.
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from backend.fea.framework.domain import Method
from backend.fea.framework.contact import ContactType
from backend.segmentation.labels import SpineLabel

from .base import AnatomyProfile, MaterialProps


@dataclass
class FacetJoint:
    """후관절(facet joint) 정보.

    인접 척추골 쌍의 후방 영역에서 탐지된 관절 접촉 정보.

    Attributes:
        superior_label: 상위 척추골 라벨
        inferior_label: 하위 척추골 라벨
        contact_points_sup: 상위 근접점 물리 좌표 (n, 3)
        contact_points_inf: 하위 근접점 물리 좌표 (n, 3)
        gap: 평균 간격 (물리 단위)
    """
    superior_label: int
    inferior_label: int
    contact_points_sup: np.ndarray
    contact_points_inf: np.ndarray
    gap: float


class SpineProfile(AnatomyProfile):
    """척추 해부학 프로파일.

    재료 물성 (문헌 기반 기본값):
      - 척추골(피질골): E=12 GPa, ν=0.3
      - 디스크(수핵+섬유륜 평균): E=4 MPa, ν=0.45
      - 인대(ligament): E=10 MPa, ν=0.4

    접촉 규칙:
      - 척추골-디스크: TIED (접착 접촉)
      - 척추골-척추골: PENALTY (후관절 마찰 접촉)
    """

    def __init__(
        self,
        bone_E: float = 12e9,
        bone_nu: float = 0.3,
        bone_density: float = 1800.0,
        disc_E: float = 4e6,
        disc_nu: float = 0.45,
        disc_density: float = 1060.0,
        ligament_E: float = 10e6,
        ligament_nu: float = 0.4,
        ligament_density: float = 1100.0,
        tied_penalty: float = 1e6,
        facet_penalty: float = 1e5,
        facet_friction: float = 0.1,
    ):
        """초기화.

        Args:
            bone_E: 뼈 영률 (Pa, 기본 12 GPa)
            bone_nu: 뼈 포아송비
            bone_density: 뼈 밀도 (kg/m³)
            disc_E: 디스크 영률 (Pa, 기본 4 MPa)
            disc_nu: 디스크 포아송비
            disc_density: 디스크 밀도 (kg/m³)
            ligament_E: 인대 영률 (Pa, 기본 10 MPa)
            ligament_nu: 인대 포아송비
            ligament_density: 인대 밀도 (kg/m³)
            tied_penalty: Tied 접촉 페널티 강성 (N/m)
            facet_penalty: 후관절 페널티 강성 (N/m)
            facet_friction: 후관절 마찰 계수
        """
        self._bone = MaterialProps(
            E=bone_E, nu=bone_nu, density=bone_density, method=Method.FEM,
        )
        self._disc = MaterialProps(
            E=disc_E, nu=disc_nu, density=disc_density, method=Method.FEM,
        )
        self._ligament = MaterialProps(
            E=ligament_E, nu=ligament_nu, density=ligament_density, method=Method.FEM,
        )
        self._tied_penalty = tied_penalty
        self._facet_penalty = facet_penalty
        self._facet_friction = facet_friction

    def get_material(self, label: int) -> MaterialProps:
        """라벨 → 재료 물성 반환."""
        if SpineLabel.is_vertebra(label):
            return self._bone
        elif SpineLabel.is_disc(label):
            return self._disc
        elif SpineLabel.is_soft_tissue(label):
            return self._ligament
        else:
            # 미분류 라벨 → 뼈 기본값
            return self._bone

    def get_contact_type(
        self, label_a: int, label_b: int,
    ) -> Optional[ContactType]:
        """인접 라벨 쌍 → 접촉 유형.

        척추골-디스크: TIED (접착)
        척추골-척추골: PENALTY (후관절, 마찰 접촉)
        그 외: None (접촉 무시)
        """
        is_vert_a = SpineLabel.is_vertebra(label_a)
        is_vert_b = SpineLabel.is_vertebra(label_b)
        is_disc_a = SpineLabel.is_disc(label_a)
        is_disc_b = SpineLabel.is_disc(label_b)

        # 척추골-디스크 쌍
        if (is_vert_a and is_disc_b) or (is_disc_a and is_vert_b):
            return ContactType.TIED

        # 척추골-척추골 쌍 (후관절)
        if is_vert_a and is_vert_b:
            return ContactType.PENALTY

        return None

    def get_contact_params(
        self, label_a: int, label_b: int,
    ) -> dict:
        """접촉 파라미터 반환."""
        contact_type = self.get_contact_type(label_a, label_b)

        if contact_type == ContactType.TIED:
            return {"penalty": self._tied_penalty}
        elif contact_type == ContactType.PENALTY:
            return {
                "penalty": self._facet_penalty,
                "friction": self._facet_friction,
            }
        else:
            return {}

    # ================================================================
    # 후관절(Facet Joint) 자동 탐지
    # ================================================================

    def detect_facet_joints(
        self,
        label_volume: np.ndarray,
        spacing: np.ndarray,
        origin: np.ndarray,
        vertebra_labels: List[int],
        gap_tol: float = 5.0,
        posterior_fraction: float = 0.4,
    ) -> List[FacetJoint]:
        """인접 척추골 쌍의 후방 영역에서 후관절 탐색.

        알고리즘:
          1. 인접 척추골 쌍 결정 (라벨 값 차이 = 1)
          2. 전후방(AP) 방향 결정 (척추관 위치 이용)
          3. 각 척추골의 후방 복셀 추출
          4. KDTree로 근접 쌍 탐색
          5. 간격 필터링

        Args:
            label_volume: 3D 라벨 볼륨 (I, J, K)
            spacing: 복셀 간격 (3,)
            origin: 원점 좌표 (3,)
            vertebra_labels: 탐색 대상 척추골 라벨 목록
            gap_tol: 최대 간격 허용치 (물리 단위, 기본 5.0)
            posterior_fraction: 후방 영역 비율 (0~1, 기본 0.4)

        Returns:
            검출된 FacetJoint 목록
        """
        spacing = np.asarray(spacing, dtype=np.float64)
        origin = np.asarray(origin, dtype=np.float64)

        # 척추골 라벨 정렬 (라벨값 오름차순)
        vert_labels = sorted(
            [l for l in vertebra_labels if SpineLabel.is_vertebra(l)]
        )

        if len(vert_labels) < 2:
            return []

        # AP 방향 결정
        ap_direction = self._compute_ap_direction(
            label_volume, spacing, origin, vert_labels,
        )

        # 인접 쌍별 후관절 탐색
        facets: List[FacetJoint] = []
        for i in range(len(vert_labels) - 1):
            superior = vert_labels[i]
            inferior = vert_labels[i + 1]

            # 인접 척추골만 (라벨 차이 1)
            if inferior - superior != 1:
                continue

            fj = self._detect_single_facet(
                label_volume, spacing, origin,
                superior, inferior, ap_direction,
                gap_tol, posterior_fraction,
            )
            if fj is not None:
                facets.append(fj)

        return facets

    def _compute_ap_direction(
        self,
        label_volume: np.ndarray,
        spacing: np.ndarray,
        origin: np.ndarray,
        vert_labels: List[int],
    ) -> np.ndarray:
        """전후방(AP) 방향 벡터 계산.

        척추관(SPINAL_CANAL) 위치를 이용하여 AP 방향을 결정한다.
        척추관이 없으면 Y축 양방향을 기본값으로 사용한다.

        Returns:
            정규화된 AP 방향 벡터 (3,)
        """
        # 척추골 전체 무게중심
        vert_mask = np.isin(label_volume, vert_labels)
        if not np.any(vert_mask):
            return np.array([0.0, 1.0, 0.0])

        vert_ijk = np.argwhere(vert_mask)
        vert_center = vert_ijk.mean(axis=0) * spacing + origin

        # 척추관 위치로 AP 방향 결정
        canal_mask = (label_volume == SpineLabel.SPINAL_CANAL)
        if np.any(canal_mask):
            canal_ijk = np.argwhere(canal_mask)
            canal_center = canal_ijk.mean(axis=0) * spacing + origin
            ap_vec = canal_center - vert_center
        else:
            # 척추관 없으면 기본 AP 방향 (Y축)
            return np.array([0.0, 1.0, 0.0])

        norm = np.linalg.norm(ap_vec)
        if norm < 1e-10:
            return np.array([0.0, 1.0, 0.0])

        return ap_vec / norm

    def _detect_single_facet(
        self,
        label_volume: np.ndarray,
        spacing: np.ndarray,
        origin: np.ndarray,
        superior_label: int,
        inferior_label: int,
        ap_direction: np.ndarray,
        gap_tol: float,
        posterior_fraction: float,
    ) -> Optional[FacetJoint]:
        """단일 인접 척추골 쌍에서 후관절 탐색.

        Args:
            superior_label: 상위 척추골 라벨
            inferior_label: 하위 척추골 라벨
            ap_direction: AP 방향 벡터
            gap_tol: 최대 간격
            posterior_fraction: 후방 영역 비율

        Returns:
            FacetJoint 또는 None (미발견 시)
        """
        from scipy.spatial import cKDTree

        # 상위/하위 척추골 복셀 물리 좌표
        sup_ijk = np.argwhere(label_volume == superior_label)
        inf_ijk = np.argwhere(label_volume == inferior_label)

        if len(sup_ijk) == 0 or len(inf_ijk) == 0:
            return None

        sup_pts = sup_ijk.astype(np.float64) * spacing + origin
        inf_pts = inf_ijk.astype(np.float64) * spacing + origin

        # 후방 영역 필터링
        sup_posterior = self._filter_posterior(
            sup_pts, ap_direction, posterior_fraction,
        )
        inf_posterior = self._filter_posterior(
            inf_pts, ap_direction, posterior_fraction,
        )

        if len(sup_posterior) == 0 or len(inf_posterior) == 0:
            return None

        # KDTree로 근접 쌍 탐색
        tree_inf = cKDTree(inf_posterior)
        dists, indices = tree_inf.query(sup_posterior)

        # 간격 필터링
        close_mask = dists < gap_tol
        if not np.any(close_mask):
            return None

        contact_sup = sup_posterior[close_mask]
        contact_inf = inf_posterior[indices[close_mask]]
        avg_gap = float(dists[close_mask].mean())

        return FacetJoint(
            superior_label=superior_label,
            inferior_label=inferior_label,
            contact_points_sup=contact_sup,
            contact_points_inf=contact_inf,
            gap=avg_gap,
        )

    @staticmethod
    def _filter_posterior(
        points: np.ndarray,
        ap_direction: np.ndarray,
        fraction: float,
    ) -> np.ndarray:
        """AP 방향 기준 후방 영역 복셀 필터링.

        AP 방향 투영값이 상위 fraction 비율에 해당하는
        점들만 선택한다.

        Args:
            points: 복셀 물리 좌표 (n, 3)
            ap_direction: AP 방향 벡터 (3,)
            fraction: 후방 비율 (0~1)

        Returns:
            후방 영역 좌표 (m, 3)
        """
        if len(points) == 0:
            return points

        # AP 방향 투영
        projections = points @ ap_direction
        threshold = np.percentile(projections, (1.0 - fraction) * 100)
        mask = projections >= threshold
        return points[mask]
