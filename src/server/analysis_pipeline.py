"""해석 파이프라인 — FEM 볼륨 메쉬 + PD/SPG 포인트 클라우드 멀티솔버.

핵심 설계:
  - FEM 영역: 클라이언트가 보낸 HEX8 노드/요소 → FEMesh 직접 생성
  - PD/SPG 영역: 클라이언트가 보낸 입자 좌표 사용
  - 결과: 영역별 구조화된 결과 (fem_regions, particle_regions)

예시:
  L4 (bone)   → FEM   (HEX8 볼륨 메쉬, 복셀에서 생성)
  L5 (bone)   → FEM
  disc        → PD    (포인트 클라우드, 복셀 중심)
  ligament    → SPG   (포인트 클라우드, 복셀 중심)
"""

import numpy as np
import time
from typing import Callable, Optional

from .models import AnalysisRequest, MaterialRegion


def run_analysis(
    request: AnalysisRequest,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """해석 실행 파이프라인.

    각 영역의 method와 데이터 타입에 따라 자동 분기:
    - FEM + nodes/elements 있음 → FEMesh 직접 사용
    - PD/SPG → 입자 기반 도메인

    Args:
        request: 해석 요청 데이터
        progress_callback: 진행률 콜백 (step, detail)

    Returns:
        해석 결과 딕셔너리 {displacements, stress, damage, info, fem_regions, particle_regions}
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

    # 2. 영역별 솔버 실행
    start_time = time.time()
    total_converged = True
    total_iterations = 0

    fem_regions_result = []
    particle_regions_result = []

    # 레거시 플랫 배열 (하위 호환)
    all_displacements_list = []
    all_stress_list = []
    all_damage_list = []

    n_regions = len(request.materials)

    for region_idx, mat in enumerate(request.materials):
        region_num = region_idx + 1

        if mat.method == "fem" and mat.nodes and mat.elements:
            # ━━━ FEM 영역: HEX8 볼륨 메쉬 직접 사용 ━━━
            if progress_callback:
                progress_callback("solving", {
                    "message": f"[{region_num}/{n_regions}] FEM — "
                               f"{len(mat.nodes)}개 노드, {len(mat.elements)}개 요소 해석 중..."
                })

            result = _run_fem_region(mat, runtime_info, progress_callback)
            fem_regions_result.append(result)

            total_converged = total_converged and result.get("converged", False)
            total_iterations += result.get("iterations", 0)

            # 레거시: FEM 노드 변위를 플랫 배열에 추가
            all_displacements_list.extend(result.get("displacements", []))
            all_stress_list.extend(result.get("stress", []))

        else:
            # ━━━ PD/SPG 영역: 입자 기반 ━━━
            if progress_callback:
                n_particles = len(mat.node_indices)
                progress_callback("solving", {
                    "message": f"[{region_num}/{n_regions}] {mat.method.upper()} — "
                               f"{n_particles}개 입자 해석 중..."
                })

            result = _run_particle_region(mat, request, runtime_info, progress_callback)
            particle_regions_result.append(result)

            total_converged = total_converged and result.get("converged", False)
            total_iterations += result.get("iterations", 0)

            # 레거시: 입자 결과를 플랫 배열에 추가
            all_displacements_list.extend(result.get("displacements", []))
            all_stress_list.extend(result.get("stress", []))
            all_damage_list.extend(result.get("damage", []))

    elapsed = time.time() - start_time

    # 결과 조립
    methods_used = list(set(m.method for m in request.materials))
    method_str = '+'.join(m.upper() for m in methods_used)

    n_total = len(all_displacements_list)

    result_data = {
        # 레거시 플랫 배열
        "displacements": all_displacements_list,
        "stress": all_stress_list,
        "damage": all_damage_list if all_damage_list else [0.0] * n_total,
        "info": {
            "converged": total_converged,
            "iterations": total_iterations,
            "residual": 0.0,
            "elapsed_time": elapsed,
            "backend": runtime_info["backend"],
            "n_particles": n_total,
            "method": method_str,
            "multi_solver": len(methods_used) > 1,
            "solver_groups": {
                m.method: m.name for m in request.materials
            },
        },
        # 영역별 구조화된 결과
        "fem_regions": fem_regions_result if fem_regions_result else None,
        "particle_regions": particle_regions_result if particle_regions_result else None,
    }

    if progress_callback:
        progress_callback("done", {
            "message": f"해석 완료: {method_str} ({elapsed:.2f}초, "
                       f"FEM {len(fem_regions_result)}개 + 입자 {len(particle_regions_result)}개 영역)"
        })

    return result_data


def _run_fem_region(
    mat: MaterialRegion,
    runtime_info: dict,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """FEM 영역 해석 — HEX8 볼륨 메쉬 직접 사용.

    클라이언트가 복셀 그리드에서 생성한 HEX8 노드/요소를 받아
    FEMesh에 직접 초기화하고 정적 해석을 수행한다.
    """
    nodes = np.array(mat.nodes, dtype=np.float64)
    elements = np.array(mat.elements, dtype=np.int64)
    n_nodes = len(nodes)
    n_elements = len(elements)

    # FEMesh 직접 생성
    from src.fea.fem.core.mesh import FEMesh, ElementType
    from src.fea.fem.material import LinearElastic
    from src.fea.fem.solver.static_solver import StaticSolver

    mesh = FEMesh(n_nodes, n_elements, ElementType.HEX8)
    mesh.initialize_from_numpy(nodes, elements)

    # 경계조건 적용
    if mat.boundary_conditions:
        for bc in mat.boundary_conditions:
            indices = np.array(bc.node_indices, dtype=np.int64)
            # 유효 인덱스만 사용
            indices = indices[indices < n_nodes]
            if len(indices) == 0:
                continue

            if bc.type == "fixed":
                mesh.set_fixed_nodes(indices)
            elif bc.type == "force":
                forces = np.array(bc.values, dtype=np.float64)
                if forces.ndim == 2 and len(forces) == 1:
                    forces = np.tile(forces[0], (len(indices), 1))
                elif forces.ndim == 1:
                    forces = np.tile(forces, (len(indices), 1))
                # 노드 수에 맞게 잘라내기
                if len(forces) != len(indices):
                    forces = np.tile(forces[0] if forces.ndim == 2 else forces,
                                     (len(indices), 1))
                mesh.set_nodal_forces(indices, forces)

    # 재료 생성
    material = LinearElastic(E=mat.E, nu=mat.nu, dim=3)

    # 정적 솔버 실행
    solver = StaticSolver(mesh, material)
    solve_result = solver.solve(verbose=False)

    # 결과 추출
    displacements = mesh.get_displacements()  # (n_nodes, 3)

    # von Mises 응력 (노드별)
    try:
        mesh.compute_mises_stress()
        mises = mesh.mises.to_numpy()  # (n_nodes,)
    except Exception:
        mises = np.zeros(n_nodes, dtype=np.float64)

    return {
        "name": mat.name,
        "converged": solve_result.get("converged", False),
        "iterations": solve_result.get("iterations", 0),
        # 결과 데이터
        "displacements": displacements.tolist(),
        "stress": mises.tolist(),
        # FEM 메쉬 데이터 (프론트엔드 시각화용)
        "nodes": nodes.tolist(),
        "elements": elements.tolist(),
    }


def _run_particle_region(
    mat: MaterialRegion,
    request: AnalysisRequest,
    runtime_info: dict,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """PD/SPG 영역 해석 — 입자 기반 도메인.

    클라이언트가 보낸 입자 좌표를 사용하여 도메인을 생성하고
    PD/SPG 솔버를 실행한다.
    """
    positions = np.array(request.positions, dtype=np.float64)

    # 이 영역의 입자만 추출
    group_indices = np.array(sorted(set(mat.node_indices)), dtype=np.int64)
    # 유효 범위 체크
    group_indices = group_indices[group_indices < len(positions)]

    if len(group_indices) == 0:
        return {
            "name": mat.name,
            "converged": True,
            "iterations": 0,
            "displacements": [],
            "stress": [],
            "damage": [],
            "positions": [],
        }

    n_group = len(group_indices)
    group_positions = positions[group_indices]

    # 바운딩 박스
    pos_min = group_positions.min(axis=0)
    pos_max = group_positions.max(axis=0)
    domain_size = pos_max - pos_min

    # 최소 도메인 크기 보장
    for d in range(3):
        if domain_size[d] < 1e-3:
            domain_size[d] = 1e-3

    origin = tuple(pos_min.tolist())
    size = tuple(domain_size.tolist())

    # 분할 수 추정
    n_per_axis = max(2, int(round(n_group ** (1.0 / 3.0))))
    n_divisions = (n_per_axis, n_per_axis, n_per_axis)

    # 도메인 생성
    from src.fea.framework.domain import create_domain, Method
    from src.fea.framework.material import Material
    from src.fea.framework.solver import Solver

    method_map = {"pd": Method.PD, "spg": Method.SPG, "fem": Method.FEM}
    method_enum = method_map.get(mat.method, Method.PD)

    domain = create_domain(
        method=method_enum, dim=3, origin=origin,
        size=size, n_divisions=n_divisions,
    )

    # 경계조건 적용 (글로벌 인덱스 → 도메인 로컬 인덱스)
    global_to_local = {int(g): i for i, g in enumerate(group_indices)}

    # 영역별 BC 적용
    if mat.boundary_conditions:
        for bc in mat.boundary_conditions:
            local_indices = []
            for gi in bc.node_indices:
                if gi in global_to_local:
                    local_indices.append(global_to_local[gi])

            if not local_indices:
                continue

            local_arr = np.array(local_indices, dtype=np.int64)
            max_idx = domain.n_points - 1
            local_arr = local_arr[local_arr <= max_idx]

            if len(local_arr) == 0:
                continue

            if bc.type == "fixed":
                domain.set_fixed(local_arr)
            elif bc.type == "force":
                forces = np.array(bc.values, dtype=np.float64)
                if forces.ndim == 2 and len(forces) == 1:
                    forces = forces[0]
                domain.set_force(local_arr, forces)

    # 글로벌 BC도 적용
    for bc in request.boundary_conditions:
        local_indices = []
        for gi in bc.node_indices:
            if gi in global_to_local:
                local_indices.append(global_to_local[gi])

        if not local_indices:
            continue

        local_arr = np.array(local_indices, dtype=np.int64)
        max_idx = domain.n_points - 1
        local_arr = local_arr[local_arr <= max_idx]

        if len(local_arr) == 0:
            continue

        if bc.type == "fixed":
            domain.set_fixed(local_arr)
        elif bc.type == "force":
            forces = np.array(bc.values, dtype=np.float64)
            if forces.ndim == 2 and len(forces) == 1:
                forces = forces[0]
            domain.set_force(local_arr, forces)

    # 재료 + 솔버
    material = Material(E=mat.E, nu=mat.nu, density=mat.density, dim=3)
    solver = Solver(domain, material, **request.options)
    result = solver.solve()

    # 결과 추출
    disps = solver.get_displacements()
    stress = solver.get_stress()
    damage = solver.get_damage()

    # 응력 스칼라화 (텐서 → von Mises 근사)
    if stress is not None and stress.ndim > 1:
        stress_flat = np.sqrt(np.sum(stress ** 2, axis=-1))
        if stress_flat.ndim > 1:
            stress_flat = np.sqrt(np.sum(stress_flat ** 2, axis=-1))
        stress = stress_flat

    return {
        "name": mat.name,
        "converged": result.converged,
        "iterations": result.iterations,
        # 결과 데이터
        "displacements": disps.tolist() if disps is not None else [],
        "stress": stress.tolist() if stress is not None else [],
        "damage": damage.tolist() if damage is not None else [],
        "positions": group_positions.tolist(),
    }
