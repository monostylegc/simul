"""FEM-PD/SPG 인터페이스 관리자.

공유 경계 노드에서 FEM ↔ PD/SPG 간 DOF 전달을 관리한다.

커플링 알고리즘 (Dirichlet-Neumann 교대법):
1. FEM solve → 인터페이스 변위 추출
2. FEM 변위 → PD 고스트 입자 Dirichlet BC 설정
3. PD solve → 인터페이스 반력 추출
4. PD 반력 → FEM 인터페이스 노드 외력 (Neumann BC)
5. 인터페이스 변위 변화 < tol → 수렴
"""

import numpy as np
from typing import Tuple


class InterfaceManager:
    """FEM-PD/SPG 공유 경계 DOF 전달 관리자.

    인터페이스 노드는 FEM 메쉬와 PD 입자 양쪽에 동시에 존재한다.
    (FEM 노드 위치 = PD 입자 위치이므로 보간 불필요)

    Args:
        interface_fem: FEM 로컬 인덱스 (n_interface,)
        interface_pd: PD 로컬 인덱스 (n_interface,)
        dim: 공간 차원
    """

    def __init__(
        self,
        interface_fem: np.ndarray,
        interface_pd: np.ndarray,
        dim: int,
    ):
        self.interface_fem = np.asarray(interface_fem, dtype=np.int64)
        self.interface_pd = np.asarray(interface_pd, dtype=np.int64)
        self.dim = dim
        self.n_interface = len(interface_fem)

        if len(interface_fem) != len(interface_pd):
            raise ValueError(
                f"인터페이스 매핑 불일치: "
                f"FEM={len(interface_fem)}, PD={len(interface_pd)}"
            )

        # 이전 스텝 인터페이스 변위 (수렴 체크용)
        self._prev_interface_disp = np.zeros(
            (self.n_interface, dim), dtype=np.float64
        )

    def fem_to_pd_displacements(
        self,
        fem_displacements: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """FEM 인터페이스 변위 → PD 고스트 입자 변위 (Dirichlet BC).

        Args:
            fem_displacements: FEM 전체 변위 (n_fem_nodes, dim)

        Returns:
            (pd_indices, pd_displacements):
                pd_indices: PD 고스트 입자 인덱스 (n_interface,)
                pd_displacements: 고스트 입자 변위 (n_interface, dim)
        """
        interface_disp = fem_displacements[self.interface_fem]
        return self.interface_pd.copy(), interface_disp.copy()

    def pd_to_fem_forces(
        self,
        pd_internal_forces: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """PD 인터페이스 반력 → FEM 인터페이스 외력 (Neumann BC).

        PD 고스트 입자의 내부력(반력)을 FEM 인터페이스 노드에 전달한다.
        부호 반전: PD 내부력의 반대 방향이 FEM에 가해지는 외력.

        Args:
            pd_internal_forces: PD 전체 내부력 (n_pd_particles, dim)

        Returns:
            (fem_indices, fem_forces):
                fem_indices: FEM 인터페이스 노드 인덱스 (n_interface,)
                fem_forces: 인터페이스 외력 (n_interface, dim)
        """
        # PD 인터페이스 입자의 내부력 추출
        interface_forces = pd_internal_forces[self.interface_pd]

        # 부호 반전: PD 내부력의 반작용 = FEM 외력
        return self.interface_fem.copy(), -interface_forces.copy()

    def check_convergence(
        self,
        fem_displacements: np.ndarray,
        tol: float = 1e-4,
    ) -> Tuple[bool, float]:
        """인터페이스 변위 변화로 수렴 판정.

        Args:
            fem_displacements: 현재 FEM 전체 변위
            tol: 상대 허용 오차

        Returns:
            (converged, relative_change)
        """
        current_disp = fem_displacements[self.interface_fem]

        # 절대 변화량
        diff = current_disp - self._prev_interface_disp
        diff_norm = np.linalg.norm(diff)

        # 기준값 (현재 변위 크기)
        ref_norm = np.linalg.norm(current_disp)
        if ref_norm < 1e-30:
            # 변위가 거의 0이면 절대 기준 사용
            rel_change = diff_norm
        else:
            rel_change = diff_norm / ref_norm

        # 이전 값 갱신
        self._prev_interface_disp = current_disp.copy()

        return rel_change < tol, float(rel_change)

    def reset(self):
        """수렴 추적 초기화."""
        self._prev_interface_disp[:] = 0.0
