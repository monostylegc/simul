"""SpineProfile 단위 테스트."""

import pytest

from backend.fea.framework.domain import Method
from backend.fea.framework.contact import ContactType
from backend.anatomy.spine import SpineProfile
from backend.anatomy.base import MaterialProps


class TestSpineProfile:
    """SpineProfile 재료/접촉 규칙 테스트."""

    def setup_method(self):
        self.profile = SpineProfile()

    def test_vertebra_material(self):
        """척추골 라벨 → 뼈 물성."""
        mat = self.profile.get_material(101)  # L1
        assert mat.E == 12e9
        assert mat.nu == 0.3
        assert mat.method == Method.FEM

    def test_disc_material(self):
        """디스크 라벨 → 디스크 물성."""
        mat = self.profile.get_material(201)  # L1-L2 디스크
        assert mat.E == 4e6
        assert mat.nu == 0.45
        assert mat.method == Method.FEM

    def test_vertebra_disc_contact_is_tied(self):
        """척추골-디스크 → TIED 접촉."""
        ct = self.profile.get_contact_type(101, 201)
        assert ct == ContactType.TIED

        # 순서 반전도 동일
        ct2 = self.profile.get_contact_type(201, 101)
        assert ct2 == ContactType.TIED

    def test_vertebra_vertebra_penalty_contact(self):
        """척추골-척추골 → PENALTY 접촉 (후관절)."""
        ct = self.profile.get_contact_type(101, 102)
        assert ct == ContactType.PENALTY

    def test_vertebra_vertebra_facet_params(self):
        """척추골-척추골 접촉 파라미터 (후관절)."""
        params = self.profile.get_contact_params(101, 102)
        assert "penalty" in params
        assert "friction" in params
        assert params["penalty"] > 0
        assert params["friction"] > 0

    def test_disc_disc_no_contact(self):
        """디스크-디스크 → 접촉 없음."""
        ct = self.profile.get_contact_type(201, 202)
        assert ct is None

    def test_tied_contact_params(self):
        """TIED 접촉 파라미터."""
        params = self.profile.get_contact_params(101, 201)
        assert "penalty" in params
        assert params["penalty"] > 0

    def test_custom_properties(self):
        """커스텀 물성 설정."""
        profile = SpineProfile(bone_E=20e9, disc_E=8e6)
        mat_bone = profile.get_material(101)
        mat_disc = profile.get_material(201)
        assert mat_bone.E == 20e9
        assert mat_disc.E == 8e6
