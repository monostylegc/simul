"""assembly 모듈 테스트.

합성 NPZ 라벨맵으로 assemble() E2E 검증.
"""

import tempfile
import numpy as np
import pytest

from backend.preprocessing.assembly import assemble, AssemblyResult
from backend.anatomy.spine import SpineProfile
from backend.fea.framework.contact import ContactType


def _create_synthetic_npz(
    shape: tuple = (4, 4, 12),
    spacing: tuple = (1.0, 1.0, 1.0),
    origin: tuple = (0.0, 0.0, 0.0),
) -> str:
    """합성 L4-disc-L5 라벨맵 NPZ 생성.

    z 방향으로:
      z=[0,3]: 라벨 101 (L4)
      z=[4,7]: 라벨 201 (L4-L5 디스크)
      z=[8,11]: 라벨 102 (L5)

    Returns:
        NPZ 파일 경로
    """
    vol = np.zeros(shape, dtype=np.int32)
    nz = shape[2]
    third = nz // 3

    vol[:, :, :third] = 101       # L4
    vol[:, :, third:2*third] = 201  # disc
    vol[:, :, 2*third:] = 102     # L5

    tmp = tempfile.NamedTemporaryFile(suffix=".npz", delete=False)
    np.savez(
        tmp.name,
        label_volume=vol,
        spacing=np.array(spacing),
        origin=np.array(origin),
    )
    return tmp.name


class TestAssemble:
    """assemble() 통합 테스트."""

    def test_three_body_spine(self):
        """L4-disc-L5 → 3개 Body + 2개 TIED 접촉."""
        npz_path = _create_synthetic_npz()
        profile = SpineProfile()

        result = assemble(npz_path, profile, min_voxels=1)

        # 3개 라벨 → 3개 Body
        assert len(result.body_map) == 3
        assert 101 in result.body_map
        assert 102 in result.body_map
        assert 201 in result.body_map

        # 2개 TIED 접촉: (101, 201), (102, 201)
        assert len(result.contact_pairs) == 2
        contact_labels = {(a, b) for a, b, _ in result.contact_pairs}
        assert (101, 201) in contact_labels
        assert (102, 201) in contact_labels

        # 모든 접촉이 TIED
        for _, _, ct in result.contact_pairs:
            assert ct == ContactType.TIED

    def test_domains_have_positions(self):
        """각 도메인에 유효한 노드 좌표 존재."""
        npz_path = _create_synthetic_npz()
        profile = SpineProfile()

        result = assemble(npz_path, profile, min_voxels=1)

        for label, domain in result.label_domains.items():
            pos = domain.get_positions()
            assert len(pos) > 0, f"라벨 {label}에 좌표 없음"
            assert pos.shape[1] == 3, f"라벨 {label}에 3D 좌표 아님"

    def test_min_voxels_filter(self):
        """최소 복셀 수 필터링."""
        # 작은 라벨맵에서 min_voxels를 높여서 필터링
        vol = np.zeros((3, 3, 6), dtype=np.int32)
        vol[:, :, :3] = 101  # 27 복셀
        vol[:, :, 3:] = 201  # 27 복셀
        vol[0, 0, 0] = 999   # 1 복셀만

        tmp = tempfile.NamedTemporaryFile(suffix=".npz", delete=False)
        np.savez(
            tmp.name,
            label_volume=vol,
            spacing=np.array([1.0, 1.0, 1.0]),
            origin=np.array([0.0, 0.0, 0.0]),
        )

        profile = SpineProfile()
        result = assemble(tmp.name, profile, min_voxels=5)

        # 999 라벨(1복셀)은 필터링
        assert 999 not in result.body_map
        # 101, 201은 포함 (26, 27 복셀)
        assert len(result.body_map) >= 2

    def test_single_label_no_contact(self):
        """단일 라벨 → Body만 생성, 접촉 없음."""
        vol = np.full((3, 3, 3), 101, dtype=np.int32)

        tmp = tempfile.NamedTemporaryFile(suffix=".npz", delete=False)
        np.savez(
            tmp.name,
            label_volume=vol,
            spacing=np.array([1.0, 1.0, 1.0]),
            origin=np.array([0.0, 0.0, 0.0]),
        )

        profile = SpineProfile()
        result = assemble(tmp.name, profile, min_voxels=1)

        assert len(result.body_map) == 1
        assert len(result.contact_pairs) == 0
