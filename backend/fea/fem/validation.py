"""FEM 입력 검증 유틸리티.

재료 상수, 메쉬 품질, 솔버 파라미터의 유효성을 검사한다.
의료 도구이므로 오류 메시지는 명확하고 실행 가능해야 한다.
"""

import logging
import numpy as np
from typing import Optional

# 모듈 전용 로거 (print() 대체)
logger = logging.getLogger("fea.fem")


# ───────────────── 커스텀 예외 ─────────────────


class FEAValidationError(ValueError):
    """FEA 입력 검증 오류.

    Attributes:
        parameter: 문제가 된 매개변수 이름
        value: 전달된 값
        suggestion: 수정 제안
    """

    def __init__(
        self,
        message: str,
        parameter: str = "",
        value=None,
        suggestion: str = "",
    ):
        self.parameter = parameter
        self.value = value
        self.suggestion = suggestion
        full_msg = f"[FEA 검증 오류] {message}"
        if suggestion:
            full_msg += f" → 제안: {suggestion}"
        super().__init__(full_msg)


class FEAConvergenceError(RuntimeError):
    """FEA 수렴 실패 오류.

    Attributes:
        iterations: 수행한 반복 횟수
        residual: 최종 잔차 노름
        reason: 발산 원인 설명
    """

    def __init__(
        self,
        message: str,
        iterations: int = 0,
        residual: float = 0.0,
        reason: str = "",
    ):
        self.iterations = iterations
        self.residual = residual
        self.reason = reason
        super().__init__(f"[FEA 수렴 실패] {message}")


# ───────────────── 재료 상수 검증 ─────────────────


def validate_elastic_constants(
    E: float, nu: float, name: str = "재료"
):
    """등방 탄성 상수 검증.

    Args:
        E: 영 계수 [Pa]
        nu: 푸아송 비
        name: 재료 이름 (오류 메시지용)

    Raises:
        FEAValidationError: 무효한 값
    """
    if E <= 0:
        raise FEAValidationError(
            f"{name}의 영 계수(E)가 {E}입니다. 양수여야 합니다.",
            parameter="E",
            value=E,
            suggestion="뼈: 10-20 GPa, 티타늄: 110 GPa, 연조직: 0.1-10 MPa",
        )
    if nu < -1.0 or nu >= 0.5:
        raise FEAValidationError(
            f"{name}의 푸아송 비(ν)가 {nu}입니다. -1.0 < ν < 0.5 범위여야 합니다.",
            parameter="nu",
            value=nu,
            suggestion="비압축성 재료: ν≈0.49, 뼈: 0.2-0.35, 금속: 0.25-0.33",
        )


def validate_density(density: float, name: str = "재료"):
    """밀도 검증.

    Args:
        density: 밀도 [kg/m³]
        name: 재료 이름
    """
    if density <= 0:
        raise FEAValidationError(
            f"{name}의 밀도가 {density} kg/m³입니다. 양수여야 합니다.",
            parameter="density",
            value=density,
            suggestion="뼈: 1800 kg/m³, 티타늄: 4500 kg/m³, 연조직: 1000 kg/m³",
        )


def validate_yield_stress(sigma_y: float, name: str = "재료"):
    """항복 응력 검증.

    Args:
        sigma_y: 항복 응력 [Pa]
        name: 재료 이름
    """
    if sigma_y <= 0:
        raise FEAValidationError(
            f"{name}의 항복 응력(σ_y)이 {sigma_y}입니다. 양수여야 합니다.",
            parameter="yield_stress",
            value=sigma_y,
            suggestion="티타늄 Ti-6Al-4V: 880 MPa, 스테인리스강: 200-700 MPa, 뼈: 100-200 MPa",
        )


def validate_hardening_modulus(H: float, name: str = "재료"):
    """경화 계수 검증.

    Args:
        H: 경화 계수 [Pa] (0 = 완전 소성)
        name: 재료 이름
    """
    if H < 0:
        raise FEAValidationError(
            f"{name}의 경화 계수(H)가 {H}입니다. 0 이상이어야 합니다.",
            parameter="hardening_modulus",
            value=H,
            suggestion="완전 소성: H=0, 선형 경화: H = E × 0.01~0.05",
        )


def validate_mooney_rivlin(C10: float, C01: float, D1: float):
    """Mooney-Rivlin 상수 검증."""
    if C10 + C01 <= 0:
        raise FEAValidationError(
            f"C10({C10}) + C01({C01}) ≤ 0: 초기 전단 계수(μ=2(C10+C01))가 비양수입니다.",
            parameter="C10+C01",
            value=C10 + C01,
            suggestion="C10, C01 모두 양수로 설정 권장",
        )
    if D1 < 0:
        raise FEAValidationError(
            f"D1({D1}) < 0: 비압축성 파라미터가 음수입니다.",
            parameter="D1",
            value=D1,
        )


def validate_ogden(mu: float, alpha: float, D1: float):
    """Ogden 파라미터 검증."""
    if mu <= 0:
        raise FEAValidationError(
            f"μ({mu}) ≤ 0: 전단 계수가 비양수입니다.",
            parameter="mu",
            value=mu,
        )
    if alpha == 0:
        raise FEAValidationError(
            f"α = 0: Ogden 지수가 0이면 에너지 함수가 정의되지 않습니다.",
            parameter="alpha",
            value=alpha,
            suggestion="α=2 → Neo-Hookean, α<2 → 연조직, α>2 → 경질 재료",
        )
    if D1 < 0:
        raise FEAValidationError(
            f"D1({D1}) < 0: 비압축성 파라미터가 음수입니다.",
            parameter="D1",
            value=D1,
        )


# ───────────────── 경계 조건 검증 ─────────────────


def validate_bc_indices(
    indices, n_nodes: int, name: str = "경계조건"
):
    """경계조건 노드 인덱스 범위 검증.

    Args:
        indices: 노드 인덱스 배열
        n_nodes: 전체 노드 수
        name: BC 종류명 (오류 메시지용)
    """
    arr = np.asarray(indices)
    if arr.size == 0:
        return
    if arr.min() < 0:
        raise FEAValidationError(
            f"{name} 인덱스에 음수({int(arr.min())})가 포함되어 있습니다.",
            parameter="indices",
            value=int(arr.min()),
        )
    if arr.max() >= n_nodes:
        raise FEAValidationError(
            f"{name} 인덱스({int(arr.max())})가 노드 수({n_nodes})를 초과합니다.",
            parameter="indices",
            value=int(arr.max()),
            suggestion=f"유효 범위: 0 ~ {n_nodes - 1}",
        )


# ───────────────── PD / SPG 검증 ─────────────────


def validate_horizon(horizon: float, spacing: float = 0.0):
    """PD/SPG 호라이즌 검증.

    Args:
        horizon: 호라이즌 반경
        spacing: 입자 간격 (0이면 비교 생략)
    """
    if horizon <= 0:
        raise FEAValidationError(
            f"호라이즌이 {horizon}입니다. 양수여야 합니다.",
            parameter="horizon",
            value=horizon,
            suggestion="일반적으로 호라이즌 = 3.015 × 입자 간격",
        )
    if spacing > 0 and horizon < spacing:
        logger.warning(
            f"호라이즌({horizon:.4e})이 입자 간격({spacing:.4e})보다 작습니다. "
            f"이웃이 매우 적을 수 있습니다. 호라이즌 ≥ 2 × 입자 간격 권장."
        )


def validate_support_radius(radius: float):
    """SPG 지지 반경 검증."""
    if radius <= 0:
        raise FEAValidationError(
            f"지지 반경이 {radius}입니다. 양수여야 합니다.",
            parameter="support_radius",
            value=radius,
        )


# ───────────────── 횡이방성 검증 ─────────────────


def validate_transverse_isotropic(
    E1: float, E2: float, nu12: float, nu23: float, G12: float,
    name: str = "횡이방성 재료",
):
    """횡이방성 재료 상수 검증.

    Args:
        E1: 섬유 방향 영 계수 [Pa]
        E2: 횡 방향 영 계수 [Pa]
        nu12: 주 푸아송 비
        nu23: 횡면 내 푸아송 비
        G12: 면 내 전단 계수 [Pa]
        name: 재료 이름
    """
    if E1 <= 0:
        raise FEAValidationError(
            f"{name}: E1({E1})이 양수가 아닙니다.",
            parameter="E1", value=E1,
            suggestion="피질골: E1≈17 GPa",
        )
    if E2 <= 0:
        raise FEAValidationError(
            f"{name}: E2({E2})가 양수가 아닙니다.",
            parameter="E2", value=E2,
            suggestion="피질골: E2≈11.5 GPa",
        )
    if G12 <= 0:
        raise FEAValidationError(
            f"{name}: G12({G12})가 양수가 아닙니다.",
            parameter="G12", value=G12,
            suggestion="피질골: G12≈3.3 GPa",
        )
    # 열역학적 안정성: 1 - nu12*nu21 - nu23² - 2*nu12*nu21*nu23 > 0
    nu21 = nu12 * E2 / E1 if E1 > 0 else 0
    D = 1.0 - nu12 * nu21 - nu23 * nu23 - 2.0 * nu12 * nu21 * nu23
    if D <= 0:
        raise FEAValidationError(
            f"{name}: 탄성 텐서가 양정치가 아닙니다 (D={D:.4f}). "
            f"푸아송 비 조합이 열역학적으로 불안정합니다.",
            parameter="nu12,nu23",
            suggestion="피질골: ν12≈0.32, ν23≈0.33",
        )
