"""다중 물체 접촉 해석 장면.

Scene 클래스로 여러 물체(Body)를 관리하고,
Staggered(정적) 또는 Synchronized(명시적) 접촉 해석을 수행한다.
"""

import time
import numpy as np
from typing import Optional, List, Dict, Union, Tuple
from dataclasses import dataclass, field

from .domain import Domain, Method
from .material import Material
from .result import SolveResult
from .contact import ContactType, ContactDefinition, NodeNodeContact


@dataclass
class Body:
    """장면 내 물체.

    Args:
        domain: 통합 Domain 또는 RigidBody 객체
        material: 통합 Material 객체 (강체는 None)
        options: 솔버 추가 옵션
    """
    domain: object  # Domain 또는 RigidBody
    material: Optional[Material] = None
    options: dict = field(default_factory=dict)
    adapter: Optional[object] = field(default=None, repr=False)
    _index: int = -1


class Scene:
    """다중 물체 접촉 해석 장면.

    여러 물체를 등록하고 접촉 조건을 추가한 뒤,
    정적 또는 명시적 해석을 수행할 수 있다.

    사용 예:
        scene = Scene()
        scene.add(bone_domain, bone_mat)
        scene.add(screw_domain, screw_mat)
        scene.add_contact(bone_domain, screw_domain, penalty=1e8)
        result = scene.solve(mode="static")
    """

    def __init__(self):
        self._bodies: List[Body] = []
        self._contacts: List[ContactDefinition] = []
        self._domain_to_body: Dict[int, Body] = {}  # id(domain) → Body
        self._built = False

    def add(
        self,
        domain,
        material: Optional[Material] = None,
        **options,
    ) -> Body:
        """물체 추가.

        Args:
            domain: 통합 Domain 또는 RigidBody 객체
            material: 통합 Material 객체 (강체는 None 가능)
            **options: 솔버별 추가 옵션

        Returns:
            Body 객체
        """
        body = Body(domain=domain, material=material, options=options)
        body._index = len(self._bodies)
        self._bodies.append(body)
        self._domain_to_body[id(domain)] = body
        return body

    def add_contact(
        self,
        domain_a,
        domain_b,
        method: ContactType = ContactType.PENALTY,
        penalty: Optional[float] = None,
        gap_tolerance: Optional[float] = None,
        surface_a: Optional[np.ndarray] = None,
        surface_b: Optional[np.ndarray] = None,
        static_friction: float = 0.0,
        dynamic_friction: float = 0.0,
    ):
        """접촉 조건 추가.

        Args:
            domain_a: 물체 A의 Domain 또는 RigidBody
            domain_b: 물체 B의 Domain 또는 RigidBody
            method: 접촉 유형
            penalty: 페널티 강성 (None이면 자동 추정)
            gap_tolerance: 접촉 감지 거리 (None이면 자동 추정)
            surface_a: A 접촉면 인덱스 (None이면 전체 경계)
            surface_b: B 접촉면 인덱스 (None이면 전체 경계)
            static_friction: 정적 마찰 계수 (0이면 마찰 없음)
            dynamic_friction: 동적 마찰 계수 (0이면 static_friction 사용)
        """
        body_a = self._domain_to_body.get(id(domain_a))
        body_b = self._domain_to_body.get(id(domain_b))
        if body_a is None or body_b is None:
            raise ValueError("접촉 정의에 사용된 도메인이 Scene에 추가되지 않음")

        # dynamic_friction 기본값: static_friction과 동일
        if dynamic_friction == 0.0 and static_friction > 0.0:
            dynamic_friction = static_friction

        contact_def = ContactDefinition(
            body_idx_a=body_a._index,
            body_idx_b=body_b._index,
            method=method,
            penalty=penalty if penalty is not None else 0.0,
            gap_tolerance=gap_tolerance if gap_tolerance is not None else 0.0,
            surface_a=surface_a,
            surface_b=surface_b,
            static_friction=static_friction,
            dynamic_friction=dynamic_friction,
        )
        # penalty/gap_tolerance 자동 추정을 위해 flag 저장
        contact_def._auto_penalty = (penalty is None)
        contact_def._auto_gap = (gap_tolerance is None)
        self._contacts.append(contact_def)

    def _build(self):
        """어댑터 생성 및 접촉 매개변수 자동 추정."""
        if self._built:
            return

        # 각 Body에 어댑터 생성
        for body in self._bodies:
            method = body.domain.method
            if method == Method.FEM:
                from ._adapters.fem_adapter import FEMAdapter
                body.adapter = FEMAdapter(body.domain, body.material, **body.options)
            elif method == Method.PD:
                from ._adapters.pd_adapter import PDAdapter
                body.adapter = PDAdapter(body.domain, body.material, **body.options)
            elif method == Method.SPG:
                from ._adapters.spg_adapter import SPGAdapter
                body.adapter = SPGAdapter(body.domain, body.material, **body.options)
            elif method == Method.COUPLED:
                from ._adapters.coupled_adapter import CoupledAdapter
                body.adapter = CoupledAdapter(body.domain, body.material, **body.options)
            elif method == Method.RIGID:
                from ._adapters.rigid_adapter import RigidBodyAdapter
                body.adapter = RigidBodyAdapter(body.domain, **body.options)
            else:
                raise ValueError(f"지원하지 않는 해석 방법: {method}")
            body.domain._adapter = body.adapter

        # 접촉 매개변수 자동 추정
        for cdef in self._contacts:
            body_a = self._bodies[cdef.body_idx_a]
            body_b = self._bodies[cdef.body_idx_b]

            # 접촉면 자동 설정 (전체 경계 사용)
            if cdef.surface_a is None:
                cdef.surface_a = self._detect_boundary(body_a)
            if cdef.surface_b is None:
                cdef.surface_b = self._detect_boundary(body_b)

            # 간격 자동 계산
            spacing_a = self._estimate_spacing(body_a)
            spacing_b = self._estimate_spacing(body_b)

            if cdef._auto_gap:
                cdef.gap_tolerance = max(spacing_a, spacing_b) * 1.5

            if cdef._auto_penalty:
                # 강체(material=None)는 상대 물체의 E 사용
                E_a = body_a.material.E if body_a.material is not None else 0.0
                E_b = body_b.material.E if body_b.material is not None else 0.0
                E_avg = max(E_a, E_b) if (E_a == 0.0 or E_b == 0.0) else (E_a + E_b) / 2
                char_length = min(spacing_a, spacing_b)
                cdef.penalty = E_avg / char_length if char_length > 0 else 1e6

        # Tied 접촉 초기화: 쌍 + 오프셋 사전 계산
        tied_algo = NodeNodeContact()
        for cdef in self._contacts:
            if cdef.method == ContactType.TIED:
                body_a = self._bodies[cdef.body_idx_a]
                body_b = self._bodies[cdef.body_idx_b]
                pos_a = body_a.domain.get_positions()
                pos_b = body_b.domain.get_positions()
                pairs, ref_offsets = tied_algo.detect_tied_pairs(
                    pos_a, pos_b,
                    cdef.surface_a, cdef.surface_b,
                    cdef.gap_tolerance,
                )
                cdef._tied_pairs = pairs
                cdef._tied_ref_offsets = ref_offsets

        self._built = True

    def _detect_boundary(self, body: Body) -> np.ndarray:
        """도메인 외곽 노드/입자 인덱스 자동 감지."""
        # 강체는 전체 표면이 경계
        if body.domain.method == Method.RIGID:
            return body.domain.select_boundary()

        pos = body.domain.get_positions()
        dim = body.domain.dim

        # 각 축의 min/max 노드 = 경계
        boundary = set()
        for ax in range(dim):
            coords = pos[:, ax]
            min_val, max_val = coords.min(), coords.max()
            # 해당 축 최소 간격으로 허용 오차 결정
            unique_sorted = np.unique(np.round(coords, decimals=10))
            if len(unique_sorted) > 1:
                tol = np.min(np.diff(unique_sorted)) * 0.5
            else:
                tol = 1e-6
            boundary.update(np.where(np.abs(coords - min_val) < tol)[0])
            boundary.update(np.where(np.abs(coords - max_val) < tol)[0])

        return np.array(sorted(boundary), dtype=np.int64)

    def _estimate_spacing(self, body: Body) -> float:
        """물체의 평균 노드/입자 간격 추정."""
        # 강체: 최근접 이웃 평균 거리로 추정
        if body.domain.method == Method.RIGID:
            pos = body.domain.get_positions()
            if len(pos) < 2:
                return 1.0
            from scipy.spatial import cKDTree
            tree = cKDTree(pos)
            dists, _ = tree.query(pos, k=2)
            return float(np.mean(dists[:, 1]))

        n_div = body.domain.n_divisions
        size = body.domain.size

        if body.domain.method == Method.FEM:
            # FEM: 요소 크기
            return size[0] / n_div[0]
        else:
            # PD/SPG: 입자 간격
            return size[0] / (n_div[0] - 1) if n_div[0] > 1 else size[0]

    def solve(
        self,
        mode: str = "quasi_static",
        max_iterations: int = 100000,
        tol: float = 1e-3,
        max_contact_iters: int = 50,
        contact_tol: float = 1e-3,
        n_steps: int = 10000,
        verbose: bool = False,
        print_interval: int = 5000,
        **kwargs,
    ) -> dict:
        """접촉 해석 수행.

        Args:
            mode: 해석 모드
                - "quasi_static": 동기화된 준정적 해석 (권장, 기본값)
                  모든 body가 매 스텝 동시 전진 + 접촉력 갱신 + KE 수렴 판정
                - "static": Staggered 정적 (FEM-FEM 전용, 매 반복 완전 re-solve)
                - "explicit": 동기화된 명시적 (수렴 체크 없이 n_steps 진행)
            max_iterations: 최대 반복 수 (quasi_static)
            tol: 수렴 허용 오차 (quasi_static)
            max_contact_iters: 최대 접촉 반복 (static)
            contact_tol: 접촉력 수렴 허용 오차 (static)
            n_steps: 시간 스텝 수 (explicit)
            verbose: 상세 출력
            print_interval: 출력 주기 (quasi_static)
            **kwargs: 각 body 솔버에 전달할 추가 인자

        Returns:
            해석 결과 dict (모드별 차이)
        """
        self._build()

        if mode == "quasi_static":
            return self._solve_quasi_static(
                max_iterations, tol, verbose, print_interval, **kwargs
            )
        elif mode == "static":
            return self._solve_static(
                max_contact_iters, contact_tol, verbose, **kwargs
            )
        elif mode == "explicit":
            return self._solve_explicit(n_steps, verbose, **kwargs)
        else:
            raise ValueError(f"지원하지 않는 해석 모드: {mode}")

    def _compute_and_inject_contact(self, contact_algo: NodeNodeContact):
        """모든 접촉 쌍에 대해 접촉력 계산 및 주입.

        Returns:
            total_contact_force: 접촉력 절대값 합
        """
        # 접촉력 초기화
        for body in self._bodies:
            body.adapter.clear_contact_forces()

        total_contact_force = 0.0
        for cdef in self._contacts:
            body_a = self._bodies[cdef.body_idx_a]
            body_b = self._bodies[cdef.body_idx_b]

            pos_a = body_a.adapter.get_current_positions()
            pos_b = body_b.adapter.get_current_positions()

            # Tied 접촉: 사전 계산된 쌍/오프셋 사용
            if cdef.method == ContactType.TIED:
                tied_pairs = getattr(cdef, '_tied_pairs', None)
                tied_offsets = getattr(cdef, '_tied_ref_offsets', None)
                if tied_pairs is None or len(tied_pairs) == 0:
                    continue
                forces_a, forces_b = contact_algo.compute_tied_forces(
                    pos_a, pos_b,
                    tied_pairs, tied_offsets,
                    cdef.penalty,
                )
            else:
                # 일반 페널티/마찰 접촉
                pairs, gaps = contact_algo.detect(
                    pos_a, pos_b,
                    cdef.surface_a, cdef.surface_b,
                    cdef.gap_tolerance,
                )

                if len(pairs) == 0:
                    continue

                # 마찰 계수가 있으면 마찰력 포함 계산
                if cdef.static_friction > 0.0:
                    vel_a = self._get_velocity(body_a)
                    vel_b = self._get_velocity(body_b)
                    forces_a, forces_b = contact_algo.compute_forces_with_friction(
                        pos_a, pos_b, pairs, gaps,
                        cdef.penalty, cdef.gap_tolerance,
                        vel_a=vel_a, vel_b=vel_b,
                        static_friction=cdef.static_friction,
                        dynamic_friction=cdef.dynamic_friction,
                        dt=self._current_dt if hasattr(self, '_current_dt') else 1e-6,
                    )
                else:
                    forces_a, forces_b = contact_algo.compute_forces(
                        pos_a, pos_b, pairs, gaps,
                        cdef.penalty, cdef.gap_tolerance,
                    )

            active_a = np.where(np.any(forces_a != 0, axis=1))[0]
            active_b = np.where(np.any(forces_b != 0, axis=1))[0]

            if len(active_a) > 0:
                body_a.adapter.inject_contact_forces(active_a, forces_a[active_a])
            if len(active_b) > 0:
                body_b.adapter.inject_contact_forces(active_b, forces_b[active_b])

            total_contact_force += np.sum(np.abs(forces_a))

        return total_contact_force

    def _solve_quasi_static(
        self,
        max_iterations: int,
        tol: float,
        verbose: bool,
        print_interval: int,
        **kwargs,
    ) -> dict:
        """동기화된 준정적 접촉 해석.

        모든 body가 매 스텝 동시에 1스텝 전진하면서,
        접촉력도 매 스텝 갱신한다.
        전체 운동에너지가 수렴하면 종료.

        FEM body가 포함된 경우:
        - FEM body는 매 fem_update_interval 스텝마다 정적 re-solve
        - PD/SPG body는 매 스텝 step()
        """
        t0 = time.time()
        contact_algo = NodeNodeContact()

        # body 분류: 명시적(SPG/PD), 정적(FEM), 강체(RIGID)
        explicit_bodies = []
        static_bodies = []
        rigid_bodies = []
        for body in self._bodies:
            if body.domain.method == Method.RIGID:
                rigid_bodies.append(body)
            elif body.domain.method == Method.FEM:
                static_bodies.append(body)
            else:
                explicit_bodies.append(body)

        # dt 결정 (명시적 body만, 강체 제외)
        if explicit_bodies:
            safety = kwargs.get("dt_safety", 0.5)
            dt = min(b.adapter.get_stable_dt() for b in explicit_bodies) * safety
        elif rigid_bodies and not static_bodies:
            # 강체만 있으면 (접촉 대상이 없으므로) 임의 dt
            dt = 1e-4
        else:
            # FEM만 있으면 Staggered 정적으로 위임
            return self._solve_static(
                max_contact_iters=max_iterations,
                contact_tol=tol,
                verbose=verbose,
                **kwargs,
            )

        # 현재 dt 저장 (마찰 계산에서 사용)
        self._current_dt = dt

        # FEM re-solve 주기 (매 N 스텝마다)
        fem_update_interval = kwargs.get("fem_update_interval", 500)

        # 초기 접촉력 계산
        total_contact_force = self._compute_and_inject_contact(contact_algo)

        # FEM body 초기 해석
        for body in static_bodies:
            body.adapter.solve(verbose=False)

        converged = False
        prev_ke = 0.0
        ke_increasing_count = 0

        for step_i in range(max_iterations):
            # 명시적 body 1스텝 전진
            for body in explicit_bodies:
                body.adapter.step(dt)

            # 강체 1스텝 전진 (규정 운동)
            for body in rigid_bodies:
                body.adapter.step(dt)

            # 접촉력 갱신
            total_contact_force = self._compute_and_inject_contact(contact_algo)

            # FEM body 주기적 re-solve (접촉력이 변경되었으므로)
            if static_bodies and (step_i + 1) % fem_update_interval == 0:
                for body in static_bodies:
                    body.adapter.solve(verbose=False)

            # 운동에너지 기반 수렴 체크
            total_ke = 0.0
            for body in explicit_bodies:
                u = body.adapter.get_displacements()
                # 속도 근사: (현재 위치 - 참조 위치) 변화율 → 변위의 norm으로 근사
                # 실제 KE는 adapter의 내부 solver에서 가져와야 함
                total_ke += self._get_kinetic_energy(body)

            if step_i > 0 and total_ke < prev_ke:
                ke_increasing_count = 0
            else:
                ke_increasing_count += 1

            # 수렴 판정: KE가 충분히 작아지면
            if step_i > 100 and total_ke > 0:
                # 잔차 = KE / (외력 에너지 스케일)
                ref_energy = self._estimate_reference_energy()
                if ref_energy > 0:
                    rel_ke = total_ke / ref_energy
                    if rel_ke < tol:
                        converged = True
                        if verbose:
                            print(
                                f"  준정적 수렴: 스텝 {step_i}, "
                                f"KE/E_ref={rel_ke:.4e} < {tol:.0e}"
                            )
                        break

            if verbose and step_i % print_interval == 0:
                print(
                    f"  스텝 {step_i}/{max_iterations}: "
                    f"KE={total_ke:.4e}, "
                    f"|F_c|={total_contact_force:.4e}"
                )

            prev_ke = total_ke

        # FEM body 최종 해석
        if static_bodies:
            for body in static_bodies:
                body.adapter.solve(verbose=False)

        elapsed = time.time() - t0
        return {
            "converged": converged,
            "iterations": step_i + 1,
            "total_contact_force": total_contact_force,
            "kinetic_energy": total_ke if 'total_ke' in dir() else 0.0,
            "dt": dt,
            "elapsed_time": elapsed,
        }

    def _get_kinetic_energy(self, body: Body) -> float:
        """body의 운동에너지 추출."""
        # 강체는 KE 없음 (규정 운동이므로 수렴 판정 불필요)
        if body.domain.method == Method.RIGID:
            return 0.0
        adapter = body.adapter
        # SPG/PD 솔버의 내부 KE 가져오기
        if hasattr(adapter, 'solver') and hasattr(adapter.solver, 'prev_ke'):
            return float(adapter.solver.prev_ke)
        return 0.0

    def _get_velocity(self, body: Body) -> np.ndarray:
        """body의 속도장 추출 (마찰 계산용)."""
        adapter = body.adapter
        # SPG/PD: 내부 속도 필드 사용
        if hasattr(adapter, 'ps') and hasattr(adapter.ps, 'v'):
            return adapter.ps.v.to_numpy()
        # 강체: 규정 운동 속도 근사 (변위 차이 / dt)
        if body.domain.method == Method.RIGID:
            # 강체 속도를 motion에서 추정
            rb = body.domain
            if rb.motions and rb._motion_idx < len(rb.motions):
                motion = rb.motions[rb._motion_idx]
                n = rb.n_points
                vel = np.zeros((n, rb.dim), dtype=np.float64)
                if motion.motion_type == "translation":
                    vel[:] = motion.axis[:rb.dim] * motion.rate
                # 회전은 각 점마다 다르므로 선속도 = ω × r
                elif motion.motion_type == "rotation":
                    if rb.dim == 2:
                        r = rb._current_positions - motion.center[:2]
                        # v = ω × r (2D: v_x = -ω*r_y, v_y = ω*r_x)
                        vel[:, 0] = -motion.rate * r[:, 1]
                        vel[:, 1] = motion.rate * r[:, 0]
                    else:
                        r = rb._current_positions - motion.center[:3]
                        vel = np.cross(motion.axis * motion.rate, r)
                return vel
            return np.zeros((rb.n_points, rb.dim), dtype=np.float64)
        # FEM: 정적이므로 속도 0
        pos = adapter.get_current_positions()
        return np.zeros_like(pos)

    def _estimate_reference_energy(self) -> float:
        """외력 기반 기준 에너지 추정 (수렴 판정용)."""
        ref = 0.0
        for body in self._bodies:
            # 강체는 외력/재료 에너지 기여 없음
            if body.material is None:
                continue
            domain = body.domain
            if domain._force_indices is not None and domain._force_values is not None:
                forces = domain._force_values
                if forces.ndim == 1:
                    f_mag = np.linalg.norm(forces)
                    n_loaded = len(domain._force_indices)
                    ref += f_mag * n_loaded
                else:
                    ref += np.sum(np.linalg.norm(forces, axis=1))
            # 재료 기반 보조 추정
            ref += body.material.E * 1e-10  # 최소값 보장
        return ref

    def _solve_static(
        self,
        max_contact_iters: int,
        contact_tol: float,
        verbose: bool,
        **kwargs,
    ) -> dict:
        """Staggered 정적 접촉 해석.

        FEM-FEM 접촉에 최적화된 모드.
        1. 각 body 독립 해석
        2. 접촉력 계산
        3. 접촉력 주입 후 재해석
        4. 접촉력 수렴까지 반복
        """
        t0 = time.time()
        contact_algo = NodeNodeContact()
        prev_total_contact_force = 0.0
        converged = False
        body_results = [None] * len(self._bodies)
        total_contact_force = 0.0

        for contact_iter in range(max_contact_iters):
            # 첫 반복은 참조좌표로 접촉 계산
            if contact_iter == 0:
                # 구속이 있는 body만 독립 해석 (고정 노드 없으면 특이 행렬)
                for body in self._bodies:
                    body.adapter.clear_contact_forces()
                for i, body in enumerate(self._bodies):
                    has_fixed = np.any(body.adapter.mesh.fixed.to_numpy() > 0) \
                        if hasattr(body.adapter, 'mesh') else True
                    if has_fixed:
                        body_results[i] = body.adapter.solve(verbose=verbose, **kwargs)

            # 접촉력 계산 (현재 변형 좌표 사용)
            total_contact_force = self._compute_and_inject_contact(contact_algo)

            # 접촉이 없으면 종료
            if total_contact_force == 0:
                converged = True
                break

            # 접촉력 주입 상태에서 재해석
            for i, body in enumerate(self._bodies):
                body_results[i] = body.adapter.solve(verbose=verbose, **kwargs)

            # 수렴 체크
            if contact_iter > 0:
                change = abs(total_contact_force - prev_total_contact_force)
                rel_change = change / (total_contact_force + 1e-30)
                if verbose:
                    print(
                        f"  접촉 반복 {contact_iter}: "
                        f"|F_c|={total_contact_force:.4e}, "
                        f"변화={rel_change:.4e}"
                    )
                if rel_change < contact_tol:
                    converged = True
                    break

            prev_total_contact_force = total_contact_force

        # 접촉이 없으면 수렴
        if len(self._contacts) == 0:
            converged = True

        elapsed = time.time() - t0
        return {
            "converged": converged,
            "contact_iterations": contact_iter + 1,
            "total_contact_force": total_contact_force,
            "elapsed_time": elapsed,
            "body_results": body_results,
        }

    def _solve_explicit(
        self,
        n_steps: int,
        verbose: bool,
        **kwargs,
    ) -> dict:
        """동기화된 명시적 접촉 해석.

        모든 body가 동일한 dt로 동시에 전진하며,
        매 스텝 접촉력을 갱신한다. 수렴 체크 없이 n_steps 진행.
        """
        t0 = time.time()
        contact_algo = NodeNodeContact()

        # 공통 dt 결정 (명시적 body만, FEM/RIGID 제외)
        explicit_dts = [
            b.adapter.get_stable_dt() for b in self._bodies
            if b.domain.method not in (Method.FEM, Method.RIGID)
        ]
        if not explicit_dts:
            explicit_dts = [1e-6]  # FEM만 있으면 임의 dt
        safety = kwargs.get("dt_safety", 0.8)
        dt = min(explicit_dts) * safety
        self._current_dt = dt

        total_contact_force = 0.0
        for step_i in range(n_steps):
            # 접촉력 갱신
            total_contact_force = self._compute_and_inject_contact(contact_algo)

            # 모든 body 1스텝 전진
            for body in self._bodies:
                body.adapter.step(dt)

            if verbose and step_i % 1000 == 0:
                print(f"  명시적 스텝 {step_i}/{n_steps}")

        elapsed = time.time() - t0
        return {
            "n_steps": n_steps,
            "dt": dt,
            "total_contact_force": total_contact_force,
            "elapsed_time": elapsed,
        }

    def get_displacements(self, domain: Domain) -> np.ndarray:
        """특정 물체의 변위 반환."""
        body = self._domain_to_body.get(id(domain))
        if body is None or body.adapter is None:
            raise ValueError("해당 도메인의 물체를 찾을 수 없거나 아직 해석되지 않음")
        return body.adapter.get_displacements()

    def get_stress(self, domain: Domain) -> np.ndarray:
        """특정 물체의 응력 반환."""
        body = self._domain_to_body.get(id(domain))
        if body is None or body.adapter is None:
            raise ValueError("해당 도메인의 물체를 찾을 수 없거나 아직 해석되지 않음")
        return body.adapter.get_stress()

    def get_damage(self, domain: Domain) -> Optional[np.ndarray]:
        """특정 물체의 손상도 반환."""
        body = self._domain_to_body.get(id(domain))
        if body is None or body.adapter is None:
            raise ValueError("해당 도메인의 물체를 찾을 수 없거나 아직 해석되지 않음")
        return body.adapter.get_damage()
