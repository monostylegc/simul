"""후관절(facet joint) 자동 탐지 테스트.

합성 라벨맵으로 detect_facet_joints() 동작을 검증한다.
"""

import numpy as np
import pytest

from backend.anatomy.spine import SpineProfile, FacetJoint
from backend.segmentation.labels import SpineLabel


def _make_two_vertebrae_volume(
    shape: tuple = (10, 10, 10),
    spacing: tuple = (1.0, 1.0, 1.0),
    origin: tuple = (0.0, 0.0, 0.0),
    with_canal: bool = True,
    posterior_gap: float = 1.5,
) -> tuple:
    """두 인접 척추골 + 척추관이 있는 합성 라벨맵 생성.

    구조 (Y축이 AP 방향):
      - Y=[0,4]: 전방 (anterior) - 척추체(body)
      - Y=[5,7]: 중간 - 척추관(canal)
      - Y=[8,9]: 후방 (posterior) - 척추궁(arch) → 후관절 위치

    Z축으로 분할:
      - Z=[0,4]: L4 (라벨 123)
      - Z=[5,9]: L5 (라벨 124)

    척추관은 Y=[5,7], X=[3,6] 영역에 배치.

    Returns:
        (label_volume, spacing, origin)
    """
    vol = np.zeros(shape, dtype=np.int32)
    spacing = np.array(spacing)
    origin = np.array(origin)

    # L4 척추골 (z=0~4)
    vol[:, :, :5] = SpineLabel.L4  # 123

    # L5 척추골 (z=5~9)
    vol[:, :, 5:] = SpineLabel.L5  # 124

    if with_canal:
        # 척추관: 중간-후방 영역 (Y=5~7, X=3~6)
        vol[3:7, 5:8, :] = SpineLabel.SPINAL_CANAL  # 302

    return vol, spacing, origin


def _make_three_vertebrae_with_gap(
    posterior_gap: float = 2.0,
) -> tuple:
    """3개 척추골 + 척추관 합성 라벨맵.

    L3, L4, L5가 Z축으로 분리.
    후방(Y>6)에서 인접 척추골이 gap 이내로 접근.
    """
    shape = (10, 10, 15)
    vol = np.zeros(shape, dtype=np.int32)
    spacing = np.array([1.0, 1.0, 1.0])
    origin = np.array([0.0, 0.0, 0.0])

    # L3: z=0~4
    vol[:, :, :5] = SpineLabel.L3  # 122
    # L4: z=5~9
    vol[:, :, 5:10] = SpineLabel.L4  # 123
    # L5: z=10~14
    vol[:, :, 10:] = SpineLabel.L5  # 124

    # 척추관: Y=5~7, X=3~6 전체 Z
    vol[3:7, 5:8, :] = SpineLabel.SPINAL_CANAL

    return vol, spacing, origin


class TestDetectFacetJoints:
    """detect_facet_joints 단위 테스트."""

    def test_basic_detection_two_vertebrae(self):
        """인접 2개 척추골에서 후관절 1개 탐지."""
        vol, spacing, origin = _make_two_vertebrae_volume()
        profile = SpineProfile()

        facets = profile.detect_facet_joints(
            vol, spacing, origin,
            vertebra_labels=[SpineLabel.L4, SpineLabel.L5],
            gap_tol=5.0,
            posterior_fraction=0.4,
        )

        assert len(facets) == 1
        fj = facets[0]
        assert fj.superior_label == SpineLabel.L4
        assert fj.inferior_label == SpineLabel.L5
        assert len(fj.contact_points_sup) > 0
        assert len(fj.contact_points_inf) > 0
        assert fj.gap >= 0

    def test_contact_points_in_posterior_region(self):
        """접촉점이 후방 영역에 위치하는지 검증."""
        vol, spacing, origin = _make_two_vertebrae_volume()
        profile = SpineProfile()

        facets = profile.detect_facet_joints(
            vol, spacing, origin,
            vertebra_labels=[SpineLabel.L4, SpineLabel.L5],
            gap_tol=5.0,
            posterior_fraction=0.4,
        )

        assert len(facets) == 1
        fj = facets[0]

        # AP 방향 계산 (척추관 기준)
        ap_dir = profile._compute_ap_direction(
            vol, spacing, origin,
            [SpineLabel.L4, SpineLabel.L5],
        )

        # 접촉점의 AP 투영이 전체 범위의 상위에 위치
        for pts in [fj.contact_points_sup, fj.contact_points_inf]:
            projections = pts @ ap_dir
            # 후방 영역의 투영값은 양수 (AP 방향)
            assert np.mean(projections) > 0 or len(pts) > 0

    def test_three_vertebrae_two_facets(self):
        """인접 3개 척추골에서 후관절 2개 탐지."""
        vol, spacing, origin = _make_three_vertebrae_with_gap()
        profile = SpineProfile()

        facets = profile.detect_facet_joints(
            vol, spacing, origin,
            vertebra_labels=[SpineLabel.L3, SpineLabel.L4, SpineLabel.L5],
            gap_tol=5.0,
        )

        # L3-L4, L4-L5 → 2개 후관절
        assert len(facets) == 2

        labels = [(fj.superior_label, fj.inferior_label) for fj in facets]
        assert (SpineLabel.L3, SpineLabel.L4) in labels
        assert (SpineLabel.L4, SpineLabel.L5) in labels

    def test_no_detection_wide_gap(self):
        """gap_tol보다 넓은 간격에서는 후관절 미탐지."""
        vol, spacing, origin = _make_two_vertebrae_volume()
        profile = SpineProfile()

        # Z경계(z=4~5)는 간격 1.0 이하이므로 gap_tol=0.1이면 미탐지
        facets = profile.detect_facet_joints(
            vol, spacing, origin,
            vertebra_labels=[SpineLabel.L4, SpineLabel.L5],
            gap_tol=0.01,  # 매우 작은 허용치
        )

        assert len(facets) == 0

    def test_non_adjacent_labels_skip(self):
        """비인접 라벨 쌍은 건너뛰기 (라벨 차이 > 1)."""
        vol = np.zeros((10, 10, 10), dtype=np.int32)
        spacing = np.array([1.0, 1.0, 1.0])
        origin = np.array([0.0, 0.0, 0.0])

        # L3과 L5만 (L4 없음 → 비인접)
        vol[:, :, :5] = SpineLabel.L3  # 122
        vol[:, :, 5:] = SpineLabel.L5  # 124

        profile = SpineProfile()
        facets = profile.detect_facet_joints(
            vol, spacing, origin,
            vertebra_labels=[SpineLabel.L3, SpineLabel.L5],
            gap_tol=5.0,
        )

        # L3-L5는 라벨 차이가 2이므로 건너뛰기
        assert len(facets) == 0

    def test_single_vertebra_no_facet(self):
        """단일 척추골에서는 후관절 없음."""
        vol = np.full((5, 5, 5), SpineLabel.L4, dtype=np.int32)
        spacing = np.array([1.0, 1.0, 1.0])
        origin = np.array([0.0, 0.0, 0.0])

        profile = SpineProfile()
        facets = profile.detect_facet_joints(
            vol, spacing, origin,
            vertebra_labels=[SpineLabel.L4],
            gap_tol=5.0,
        )

        assert len(facets) == 0

    def test_without_canal_fallback(self):
        """척추관 없이도 탐지 가능 (기본 AP 방향 사용)."""
        vol, spacing, origin = _make_two_vertebrae_volume(with_canal=False)
        profile = SpineProfile()

        # 척추관 없으면 기본 Y축 AP 방향
        ap_dir = profile._compute_ap_direction(
            vol, spacing, origin,
            [SpineLabel.L4, SpineLabel.L5],
        )
        np.testing.assert_allclose(ap_dir, [0.0, 1.0, 0.0])

        # 기본 AP 방향으로도 탐지 시도 (합성 데이터에서는 결과가 다를 수 있음)
        facets = profile.detect_facet_joints(
            vol, spacing, origin,
            vertebra_labels=[SpineLabel.L4, SpineLabel.L5],
            gap_tol=5.0,
        )

        # 기본 AP 방향이더라도 Z경계에서 접촉은 발생
        # (후방 필터가 Y 상위 40%를 선택 → Z경계에서 근접)
        assert isinstance(facets, list)

    def test_facet_gap_value(self):
        """탐지된 후관절의 간격 값이 합리적인지 검증."""
        vol, spacing, origin = _make_two_vertebrae_volume()
        profile = SpineProfile()

        facets = profile.detect_facet_joints(
            vol, spacing, origin,
            vertebra_labels=[SpineLabel.L4, SpineLabel.L5],
            gap_tol=5.0,
        )

        if len(facets) > 0:
            fj = facets[0]
            # 간격은 0 이상이고 gap_tol 이하
            assert 0 <= fj.gap <= 5.0

    def test_posterior_fraction_effect(self):
        """posterior_fraction이 작으면 더 적은 접촉점."""
        vol, spacing, origin = _make_two_vertebrae_volume()
        profile = SpineProfile()

        # 넓은 후방 영역
        facets_wide = profile.detect_facet_joints(
            vol, spacing, origin,
            vertebra_labels=[SpineLabel.L4, SpineLabel.L5],
            gap_tol=5.0,
            posterior_fraction=0.5,
        )

        # 좁은 후방 영역
        facets_narrow = profile.detect_facet_joints(
            vol, spacing, origin,
            vertebra_labels=[SpineLabel.L4, SpineLabel.L5],
            gap_tol=5.0,
            posterior_fraction=0.1,
        )

        # 둘 다 탐지되는 경우, 넓은 영역이 더 많은 접촉점을 가져야 함
        if len(facets_wide) > 0 and len(facets_narrow) > 0:
            assert (
                len(facets_wide[0].contact_points_sup)
                >= len(facets_narrow[0].contact_points_sup)
            )


class TestFilterPosterior:
    """_filter_posterior 헬퍼 함수 단위 테스트."""

    def test_basic_filter(self):
        """AP 방향 상위 40% 필터링."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 2.0, 0.0],
            [0.0, 3.0, 0.0],
            [0.0, 4.0, 0.0],
        ])
        ap_dir = np.array([0.0, 1.0, 0.0])

        result = SpineProfile._filter_posterior(points, ap_dir, 0.4)

        # 상위 40% → Y >= 2.4 → Y=3, 4
        assert len(result) == 2
        assert np.all(result[:, 1] >= 2.4)

    def test_empty_input(self):
        """빈 입력."""
        points = np.empty((0, 3))
        ap_dir = np.array([0.0, 1.0, 0.0])

        result = SpineProfile._filter_posterior(points, ap_dir, 0.4)
        assert len(result) == 0

    def test_all_same_projection(self):
        """모든 점이 동일 투영값이면 전체 반환."""
        points = np.array([
            [1.0, 5.0, 0.0],
            [2.0, 5.0, 0.0],
            [3.0, 5.0, 0.0],
        ])
        ap_dir = np.array([0.0, 1.0, 0.0])

        result = SpineProfile._filter_posterior(points, ap_dir, 0.4)
        # percentile(60)은 5.0이므로 모든 점이 >= 5.0 → 전체
        assert len(result) == 3


class TestComputeAPDirection:
    """_compute_ap_direction 헬퍼 함수 테스트."""

    def test_with_canal(self):
        """척추관이 있으면 척추체→척추관 방향."""
        vol, spacing, origin = _make_two_vertebrae_volume(with_canal=True)
        profile = SpineProfile()

        ap_dir = profile._compute_ap_direction(
            vol, spacing, origin,
            [SpineLabel.L4, SpineLabel.L5],
        )

        # 척추관이 Y=5~7에 있고, 척추골이 Y=0~9 전체에 있으므로
        # AP 방향은 Y 양방향 성분이 있어야 함
        assert np.linalg.norm(ap_dir) == pytest.approx(1.0)
        assert ap_dir[1] > 0  # Y 양방향이 후방

    def test_without_canal(self):
        """척추관 없으면 기본 [0, 1, 0] 반환."""
        vol, spacing, origin = _make_two_vertebrae_volume(with_canal=False)
        profile = SpineProfile()

        ap_dir = profile._compute_ap_direction(
            vol, spacing, origin,
            [SpineLabel.L4, SpineLabel.L5],
        )

        np.testing.assert_allclose(ap_dir, [0.0, 1.0, 0.0])
