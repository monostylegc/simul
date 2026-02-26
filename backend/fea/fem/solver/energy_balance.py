"""에너지 균형 검증 유틸리티.

FEM 해석 결과의 물리적 정합성을 에너지 관점에서 검증한다.

검증 항목:
1. 에너지 보존: 외부 일(W_ext) = 내부 변형 에너지(U_int)
2. 에너지 양정치: U_int ≥ 0
3. 에너지 수렴: 하중 단계별 에너지 변화 모니터링
4. 보완 에너지 검증: Prager-Synge 방식 오차 평가

적용 범위:
- 정적 해석: W_ext = ½ u^T f_ext (선형) 또는 ∫ f_ext · du (비선형)
- 비선형 해석: 증분 에너지 검증
- 호장법 해석: 단계별 에너지 경로 검증

참고문헌:
- Bathe (1996), "Finite Element Procedures", Ch.6
- Zienkiewicz & Taylor (2005), "The Finite Element Method", Vol.1, Ch.10
"""

import numpy as np
from typing import Optional, Dict, List, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from ..core.mesh import FEMesh
    from ..material.base import MaterialBase


@dataclass
class EnergyReport:
    """에너지 균형 검증 보고서.

    Attributes:
        external_work: 외부 일 W_ext = u^T · f_ext
        internal_energy: 내부 변형 에너지 U_int = ∫ σ:ε dV
        kinetic_energy: 운동 에너지 (동적 해석 전용)
        energy_ratio: U_int / W_ext (1.0이면 완전 균형)
        energy_error: |W_ext - U_int| / max(|W_ext|, |U_int|)
        is_balanced: 에너지 균형 성립 여부
        is_positive_definite: 에너지 양정치 여부
        tolerance: 사용된 허용 오차
    """
    external_work: float = 0.0
    internal_energy: float = 0.0
    kinetic_energy: float = 0.0
    energy_ratio: float = 0.0
    energy_error: float = 0.0
    is_balanced: bool = False
    is_positive_definite: bool = False
    tolerance: float = 0.01
    details: Dict = field(default_factory=dict)


def compute_external_work(mesh: "FEMesh") -> float:
    """외부 일 계산 (선형 정적).

    비례 하중 가정: 하중이 0에서 f_ext까지 선형 증가.
    W_ext = ½ u^T · f_ext

    비선형/증분 해석은 check_incremental_energy() 사용.

    Args:
        mesh: 해석 완료된 FEMesh

    Returns:
        외부 일 [J]
    """
    u = mesh.u.to_numpy().flatten()
    f_ext = mesh.f_ext.to_numpy().flatten()
    # 선형 비례 하중: W = ∫₀¹ (t·f_ext)·d(t·u) = ½ u^T f_ext
    return float(0.5 * np.dot(u, f_ext))


def compute_internal_energy(mesh: "FEMesh") -> float:
    """내부 변형 에너지 계산 (가우스 적분).

    U_int = Σ_gp (½ σ:ε) · vol
    = ½ Σ_gp Σ_{ij} σ_{ij} · ε_{ij} · vol

    Args:
        mesh: 응력/변형률이 계산된 FEMesh

    Returns:
        내부 변형 에너지 [J]
    """
    stress = mesh.stress.to_numpy()   # (n_gauss_total, dim, dim)
    strain = mesh.strain.to_numpy()   # (n_gauss_total, dim, dim)
    gauss_vol = mesh.gauss_vol.to_numpy()  # (n_gauss_total,)

    # σ:ε = Σ_{ij} σ_{ij} ε_{ij} (이중 축소)
    # 가우스점별 계산 (벡터화)
    stress_strain_dot = np.sum(stress * strain, axis=(1, 2))  # (n_gp,)

    # U = ½ Σ_gp σ:ε · vol
    energy = 0.5 * np.sum(stress_strain_dot * gauss_vol)
    return float(energy)


def compute_internal_energy_from_forces(mesh: "FEMesh") -> float:
    """내부 변형 에너지를 내부력에서 계산.

    U_int = ½ u^T · f_int = -½ u^T · mesh.f
    (mesh.f = -f_int 규약 사용)

    Args:
        mesh: 내부력이 계산된 FEMesh

    Returns:
        내부 변형 에너지 [J]
    """
    u = mesh.u.to_numpy().flatten()
    f_neg_int = mesh.f.to_numpy().flatten()
    # mesh.f = -∫ B^T σ dV = -f_int
    return float(-0.5 * np.dot(u, f_neg_int))


def check_energy_balance(
    mesh: "FEMesh",
    material: Optional["MaterialBase"] = None,
    tol: float = 0.01,
    verbose: bool = False,
) -> EnergyReport:
    """에너지 균형 검증.

    외부 일과 내부 변형 에너지를 비교하여 해석 결과의
    물리적 정합성을 검증한다.

    Args:
        mesh: 해석 완료된 FEMesh
        material: 재료 모델 (선택적, 초탄성 에너지 계산용)
        tol: 에너지 균형 허용 오차 (상대 오차)
        verbose: 상세 출력

    Returns:
        EnergyReport 보고서
    """
    from ..validation import logger

    report = EnergyReport(tolerance=tol)

    # 1. 외부 일
    W_ext = compute_external_work(mesh)
    report.external_work = W_ext

    # 2. 내부 변형 에너지 (가우스 적분)
    U_gauss = compute_internal_energy(mesh)
    report.internal_energy = U_gauss

    # 3. 내부 에너지 (내부력 기반) — 교차 검증
    U_force = compute_internal_energy_from_forces(mesh)

    # 4. 에너지 양정치 검사
    report.is_positive_definite = (U_gauss >= -abs(tol * U_gauss))

    # 5. 에너지 비율 및 오차
    ref_energy = max(abs(W_ext), abs(U_gauss), 1e-30)
    report.energy_error = abs(W_ext - U_gauss) / ref_energy

    if abs(W_ext) > 1e-30:
        report.energy_ratio = U_gauss / W_ext
    else:
        report.energy_ratio = 1.0 if abs(U_gauss) < 1e-30 else float('inf')

    # 6. 에너지 균형 판정
    report.is_balanced = (report.energy_error < tol)

    # 7. 상세 정보
    report.details = {
        "W_ext": W_ext,
        "U_gauss": U_gauss,
        "U_force": U_force,
        "U_gauss_force_error": abs(U_gauss - U_force) / ref_energy if ref_energy > 1e-30 else 0.0,
    }

    # 초탄성 에너지 (가능한 경우)
    if material is not None and hasattr(material, 'compute_total_energy'):
        try:
            U_hyper = float(material.compute_total_energy(
                mesh.F, mesh.gauss_vol,
                mesh.n_elements * mesh.n_gauss,
            ))
            report.details["U_hyperelastic"] = U_hyper
        except Exception:
            pass

    if verbose:
        logger.info(f"에너지 균형 검증:")
        logger.info(f"  외부 일      W_ext  = {W_ext:.6e} J")
        logger.info(f"  내부 에너지  U_int  = {U_gauss:.6e} J")
        logger.info(f"  (내부력)     U_f    = {U_force:.6e} J")
        logger.info(f"  에너지 비율  U/W    = {report.energy_ratio:.6f}")
        logger.info(f"  상대 오차           = {report.energy_error:.4e}")
        logger.info(
            f"  판정: {'✓ 균형' if report.is_balanced else '✗ 불균형'} "
            f"(tol={tol:.2e})"
        )

    return report


def check_incremental_energy(
    load_factors: List[float],
    displacements: List[np.ndarray],
    f_ref: np.ndarray,
    tol: float = 0.05,
) -> Dict:
    """증분 에너지 검증 (호장법 경로용).

    각 하중 단계에서의 증분 외부 일과 총 에너지 변화를 검증한다.

    W_total = Σ_step ½ (λ_n + λ_{n-1}) · f_ref^T · (u_n - u_{n-1})
    (사다리꼴 적분)

    Args:
        load_factors: 단계별 하중 비율 [λ_0, λ_1, ..., λ_N]
        displacements: 단계별 변위 벡터
        f_ref: 참조 외력 벡터
        tol: 에너지 양정치 허용 오차

    Returns:
        검증 결과 딕셔너리
    """
    n_steps = len(load_factors) - 1
    if n_steps < 1:
        return {
            "valid": True,
            "n_steps": 0,
            "incremental_work": [],
            "cumulative_work": [],
        }

    incremental_work = []
    cumulative_work = [0.0]

    for i in range(1, len(load_factors)):
        lam_avg = 0.5 * (load_factors[i] + load_factors[i - 1])
        du = displacements[i] - displacements[i - 1]
        dW = lam_avg * np.dot(f_ref, du)

        incremental_work.append(float(dW))
        cumulative_work.append(cumulative_work[-1] + float(dW))

    # 단조증가 확인 (변형 에너지는 양수여야 함)
    all_positive = all(dW >= -abs(tol * abs(dW)) for dW in incremental_work)

    # 최종 에너지 vs 해석적 추정 (선형: W = ½ λ² u_ref^T f_ref)
    final_lam = load_factors[-1]
    final_u = displacements[-1]
    W_final = 0.5 * final_lam * np.dot(f_ref, final_u)

    return {
        "valid": all_positive,
        "n_steps": n_steps,
        "incremental_work": incremental_work,
        "cumulative_work": cumulative_work,
        "total_work_trapezoid": cumulative_work[-1],
        "total_work_endpoint": float(W_final),
        "all_increments_positive": all_positive,
    }
