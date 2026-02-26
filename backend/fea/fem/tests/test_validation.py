"""입력 검증 유틸리티 테스트.

Phase 0-A: 재료 상수, BC 인덱스, PD/SPG 파라미터 검증 로직을 테스트한다.
"""

import pytest
import numpy as np
import taichi as ti

from backend.fea.fem.validation import (
    FEAValidationError,
    FEAConvergenceError,
    validate_elastic_constants,
    validate_density,
    validate_yield_stress,
    validate_hardening_modulus,
    validate_mooney_rivlin,
    validate_ogden,
    validate_bc_indices,
    validate_horizon,
    validate_support_radius,
    validate_transverse_isotropic,
)


# ───────────────── 탄성 상수 검증 ─────────────────


class TestElasticValidation:
    """등방 탄성 상수 검증 테스트."""

    def test_valid_params_pass(self):
        """유효한 파라미터는 예외 없이 통과."""
        validate_elastic_constants(200e9, 0.3, "Steel")

    def test_valid_near_zero_nu_pass(self):
        """ν≈0 (코르크)도 유효."""
        validate_elastic_constants(1e6, 0.0)

    def test_valid_negative_nu_pass(self):
        """음의 ν (auxetic 재료) -1 < ν < 0."""
        validate_elastic_constants(1e6, -0.5)

    def test_valid_near_half_nu_pass(self):
        """ν=0.499 (거의 비압축성)도 통과."""
        validate_elastic_constants(1e6, 0.499)

    def test_negative_E_raises(self):
        """E <= 0 → FEAValidationError."""
        with pytest.raises(FEAValidationError, match="영 계수"):
            validate_elastic_constants(-100, 0.3)

    def test_zero_E_raises(self):
        """E = 0 → FEAValidationError."""
        with pytest.raises(FEAValidationError, match="영 계수"):
            validate_elastic_constants(0, 0.3)

    def test_nu_equals_half_raises(self):
        """ν = 0.5 → 완전 비압축성 (특이)."""
        with pytest.raises(FEAValidationError, match="푸아송"):
            validate_elastic_constants(1e6, 0.5)

    def test_nu_greater_than_half_raises(self):
        """ν > 0.5 → 열역학적 불안정."""
        with pytest.raises(FEAValidationError, match="푸아송"):
            validate_elastic_constants(1e6, 0.6)

    def test_nu_less_than_minus_one_raises(self):
        """ν < -1 → 불안정."""
        with pytest.raises(FEAValidationError, match="푸아송"):
            validate_elastic_constants(1e6, -1.5)

    def test_error_includes_suggestion(self):
        """오류 메시지에 수정 제안이 포함."""
        with pytest.raises(FEAValidationError) as exc_info:
            validate_elastic_constants(-1, 0.3)
        assert exc_info.value.suggestion != ""
        assert exc_info.value.parameter == "E"
        assert exc_info.value.value == -1


# ───────────────── 밀도 검증 ─────────────────


class TestDensityValidation:
    """밀도 검증 테스트."""

    def test_valid_density(self):
        validate_density(1800.0)

    def test_zero_density_raises(self):
        with pytest.raises(FEAValidationError, match="밀도"):
            validate_density(0.0)

    def test_negative_density_raises(self):
        with pytest.raises(FEAValidationError, match="밀도"):
            validate_density(-500.0)


# ───────────────── 초탄성 상수 검증 ─────────────────


class TestHyperelasticValidation:
    """Mooney-Rivlin / Ogden 상수 검증 테스트."""

    def test_mooney_rivlin_valid(self):
        validate_mooney_rivlin(0.5e6, 0.3e6, 1e-9)

    def test_mooney_rivlin_negative_sum_raises(self):
        with pytest.raises(FEAValidationError, match="전단 계수"):
            validate_mooney_rivlin(-1.0, -2.0, 1e-9)

    def test_mooney_rivlin_negative_D1_raises(self):
        with pytest.raises(FEAValidationError, match="D1"):
            validate_mooney_rivlin(0.5e6, 0.3e6, -1.0)

    def test_ogden_valid(self):
        validate_ogden(1e6, 2.0, 1e-9)

    def test_ogden_zero_mu_raises(self):
        with pytest.raises(FEAValidationError, match="전단 계수"):
            validate_ogden(0.0, 2.0, 1e-9)

    def test_ogden_zero_alpha_raises(self):
        with pytest.raises(FEAValidationError, match="α"):
            validate_ogden(1e6, 0.0, 1e-9)

    def test_ogden_negative_D1_raises(self):
        with pytest.raises(FEAValidationError, match="D1"):
            validate_ogden(1e6, 2.0, -1.0)


# ───────────────── 소성 파라미터 검증 ─────────────────


class TestPlasticityValidation:
    """J2 소성 파라미터 검증 테스트."""

    def test_valid_yield_stress(self):
        validate_yield_stress(250e6)

    def test_zero_yield_stress_raises(self):
        with pytest.raises(FEAValidationError, match="항복"):
            validate_yield_stress(0.0)

    def test_negative_yield_stress_raises(self):
        with pytest.raises(FEAValidationError, match="항복"):
            validate_yield_stress(-100e6)

    def test_valid_hardening(self):
        validate_hardening_modulus(1e9)
        validate_hardening_modulus(0.0)  # 완전 소성도 유효

    def test_negative_hardening_raises(self):
        with pytest.raises(FEAValidationError, match="경화"):
            validate_hardening_modulus(-1e9)


# ───────────────── BC 인덱스 검증 ─────────────────


class TestBCValidation:
    """경계조건 인덱스 범위 검증 테스트."""

    def test_valid_indices(self):
        validate_bc_indices(np.array([0, 5, 9]), n_nodes=10)

    def test_empty_indices_pass(self):
        validate_bc_indices(np.array([]), n_nodes=10)

    def test_out_of_range_raises(self):
        with pytest.raises(FEAValidationError, match="초과"):
            validate_bc_indices(np.array([100]), n_nodes=50)

    def test_negative_index_raises(self):
        with pytest.raises(FEAValidationError, match="음수"):
            validate_bc_indices(np.array([-1, 0, 5]), n_nodes=10)

    def test_boundary_index_pass(self):
        """최대 인덱스 n_nodes-1은 유효."""
        validate_bc_indices(np.array([9]), n_nodes=10)

    def test_exactly_n_nodes_raises(self):
        """인덱스 == n_nodes → 초과."""
        with pytest.raises(FEAValidationError, match="초과"):
            validate_bc_indices(np.array([10]), n_nodes=10)


# ───────────────── PD / SPG 검증 ─────────────────


class TestPDSPGValidation:
    """PD 호라이즌 / SPG 지지 반경 검증 테스트."""

    def test_valid_horizon(self):
        validate_horizon(0.1)

    def test_zero_horizon_raises(self):
        with pytest.raises(FEAValidationError, match="호라이즌"):
            validate_horizon(0.0)

    def test_negative_horizon_raises(self):
        with pytest.raises(FEAValidationError, match="호라이즌"):
            validate_horizon(-0.5)

    def test_horizon_smaller_than_spacing_warns(self, caplog):
        """호라이즌 < 입자 간격 → 경고 (예외 아님)."""
        import logging
        with caplog.at_level(logging.WARNING, logger="fea.fem"):
            validate_horizon(0.01, spacing=0.05)
        assert "입자 간격" in caplog.text

    def test_valid_support_radius(self):
        validate_support_radius(0.1)

    def test_zero_support_radius_raises(self):
        with pytest.raises(FEAValidationError, match="지지 반경"):
            validate_support_radius(0.0)

    def test_negative_support_radius_raises(self):
        with pytest.raises(FEAValidationError, match="지지 반경"):
            validate_support_radius(-1.0)


# ───────────────── 횡이방성 검증 ─────────────────


class TestTransverseIsotropicValidation:
    """횡이방성 재료 상수 검증 테스트."""

    def test_valid_cortical_bone(self):
        """피질골 물성 — 유효."""
        validate_transverse_isotropic(
            E1=17e9, E2=11.5e9, nu12=0.32, nu23=0.33, G12=3.3e9,
        )

    def test_negative_E1_raises(self):
        with pytest.raises(FEAValidationError, match="E1"):
            validate_transverse_isotropic(
                E1=-17e9, E2=11.5e9, nu12=0.32, nu23=0.33, G12=3.3e9,
            )

    def test_negative_G12_raises(self):
        with pytest.raises(FEAValidationError, match="G12"):
            validate_transverse_isotropic(
                E1=17e9, E2=11.5e9, nu12=0.32, nu23=0.33, G12=-3.3e9,
            )

    def test_thermodynamic_instability_raises(self):
        """열역학적 불안정한 조합 → 오류."""
        with pytest.raises(FEAValidationError, match="양정치"):
            validate_transverse_isotropic(
                E1=17e9, E2=11.5e9, nu12=0.99, nu23=0.99, G12=3.3e9,
            )


# ───────────────── 재료 모델 통합 검증 ─────────────────


class TestMaterialIntegration:
    """재료 모델 생성자에서 검증이 실행되는지 테스트."""

    def test_linear_elastic_invalid_E(self):
        from backend.fea.fem.material.linear_elastic import LinearElastic
        with pytest.raises(FEAValidationError):
            LinearElastic(-1e6, 0.3)

    def test_linear_elastic_invalid_nu(self):
        from backend.fea.fem.material.linear_elastic import LinearElastic
        with pytest.raises(FEAValidationError):
            LinearElastic(1e6, 0.5)

    def test_neo_hookean_invalid_E(self):
        from backend.fea.fem.material.neo_hookean import NeoHookean
        with pytest.raises(FEAValidationError):
            NeoHookean(0, 0.3)

    def test_mooney_rivlin_invalid_params(self):
        from backend.fea.fem.material.mooney_rivlin import MooneyRivlin
        with pytest.raises(FEAValidationError):
            MooneyRivlin(-1.0, -2.0, 1e-9)

    def test_ogden_invalid_alpha(self):
        from backend.fea.fem.material.ogden import Ogden
        with pytest.raises(FEAValidationError):
            Ogden(1e6, 0.0, 1e-9)

    def test_framework_material_invalid_E(self):
        """프레임워크 Material 데이터클래스 검증."""
        from backend.fea.framework.material import Material
        with pytest.raises(FEAValidationError):
            Material(E=-1e6, nu=0.3)

    def test_framework_material_invalid_density(self):
        from backend.fea.framework.material import Material
        with pytest.raises(FEAValidationError):
            Material(E=1e6, nu=0.3, density=-100)


# ───────────────── 커스텀 예외 속성 ─────────────────


class TestExceptionAttributes:
    """커스텀 예외 클래스 속성 테스트."""

    def test_validation_error_attributes(self):
        err = FEAValidationError("테스트", parameter="E", value=-1, suggestion="양수")
        assert err.parameter == "E"
        assert err.value == -1
        assert err.suggestion == "양수"
        assert "FEA 검증 오류" in str(err)
        assert "제안" in str(err)

    def test_convergence_error_attributes(self):
        err = FEAConvergenceError("발산", iterations=10, residual=1e5, reason="nan")
        assert err.iterations == 10
        assert err.residual == 1e5
        assert err.reason == "nan"
        assert "FEA 수렴 실패" in str(err)
