"""해석 파이프라인 — FEA framework 호출 + 진행률 콜백."""

import numpy as np
import time
from typing import Callable, Optional

from .models import AnalysisRequest


def run_analysis(
    request: AnalysisRequest,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """해석 실행 파이프라인.

    1. Taichi 런타임 초기화 (GPU 자동 선택)
    2. 도메인 생성 + 경계조건 적용
    3. 재료 설정
    4. 솔버 실행
    5. 결과 반환

    Args:
        request: 해석 요청 데이터
        progress_callback: 진행률 콜백 (step, detail)

    Returns:
        해석 결과 딕셔너리 {displacements, stress, damage, info}
    """
    # 1. 런타임 초기화 (GPU 자동 감지)
    if progress_callback:
        progress_callback("init", {"message": "Taichi 런타임 초기화 중..."})

    from src.fea.framework.runtime import init, Backend
    runtime_info = init(Backend.AUTO)

    if progress_callback:
        progress_callback("init", {
            "message": f"백엔드: {runtime_info['backend']}",
            "backend": runtime_info["backend"],
        })

    # 2. 입자 데이터 준비
    positions = np.array(request.positions, dtype=np.float64)
    n_particles = len(positions)

    if progress_callback:
        progress_callback("setup", {"message": f"입자 {n_particles}개 설정 중..."})

    # 바운딩 박스 계산
    pos_min = positions.min(axis=0)
    pos_max = positions.max(axis=0)
    origin = tuple(pos_min.tolist())
    size = tuple((pos_max - pos_min).tolist())

    # 분할 수 추정 (입자 수의 세제곱근 기반)
    n_per_axis = max(2, int(round(n_particles ** (1.0 / 3.0))))
    n_divisions = (n_per_axis, n_per_axis, n_per_axis)

    # 3. 도메인 생성
    from src.fea.framework.domain import create_domain, Method

    method_map = {"fem": Method.FEM, "pd": Method.PD, "spg": Method.SPG}
    method = method_map[request.method]

    domain = create_domain(
        method=method,
        dim=3,
        origin=origin,
        size=size,
        n_divisions=n_divisions,
    )

    # 4. 경계조건 적용
    if progress_callback:
        progress_callback("bc", {"message": "경계조건 적용 중..."})

    for bc in request.boundary_conditions:
        indices = np.array(bc.node_indices, dtype=np.int64)
        # 인덱스가 도메인 범위 내인지 클리핑
        max_idx = domain.n_points - 1
        indices = indices[indices <= max_idx]

        if len(indices) == 0:
            continue

        if bc.type == "fixed":
            domain.set_fixed(indices)
        elif bc.type == "force":
            forces = np.array(bc.values, dtype=np.float64)
            if forces.ndim == 2 and len(forces) == 1:
                forces = forces[0]  # 단일 힘 벡터 → 모든 노드 동일
            domain.set_force(indices, forces)

    # 5. 재료 설정 (첫 번째 재료 사용)
    if progress_callback:
        progress_callback("material", {"message": "재료 설정 중..."})

    from src.fea.framework.material import Material

    if request.materials:
        mat_data = request.materials[0]
        material = Material(
            E=mat_data.E,
            nu=mat_data.nu,
            density=mat_data.density,
            dim=3,
        )
    else:
        # 기본 재료: 뼈
        material = Material(E=15e9, nu=0.3, density=1850.0, dim=3)

    # 6. 솔버 생성 + 실행
    if progress_callback:
        progress_callback("solving", {"message": "해석 실행 중...", "iteration": 0})

    from src.fea.framework.solver import Solver

    solver = Solver(domain, material, **request.options)

    start_time = time.time()
    result = solver.solve()
    elapsed = time.time() - start_time

    if progress_callback:
        progress_callback("solving", {
            "message": f"수렴: {result.converged}, 반복: {result.iterations}",
            "iteration": result.iterations,
            "residual": result.residual,
            "converged": result.converged,
        })

    # 7. 결과 추출
    if progress_callback:
        progress_callback("postprocess", {"message": "결과 추출 중..."})

    displacements = solver.get_displacements()
    stress = solver.get_stress()
    damage = solver.get_damage()

    # numpy → list 변환 (JSON 직렬화)
    result_data = {
        "displacements": displacements.tolist() if displacements is not None else [],
        "stress": stress.tolist() if stress is not None else [],
        "damage": damage.tolist() if damage is not None else [],
        "info": {
            "converged": result.converged,
            "iterations": result.iterations,
            "residual": float(result.residual),
            "elapsed_time": elapsed,
            "backend": runtime_info["backend"],
            "n_particles": n_particles,
            "method": request.method,
        },
    }

    if progress_callback:
        progress_callback("done", {"message": f"완료 ({elapsed:.2f}초)"})

    return result_data
