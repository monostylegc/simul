"""FEM-PD/SPG 커플링 모듈 테스트.

zone_splitter, interface_manager, criteria의 단위 테스트 +
CoupledSolver 통합 테스트를 수행한다.
"""

import numpy as np
import pytest


# ──────────────────────────────────────────────────────────
# 1. zone_splitter 테스트
# ──────────────────────────────────────────────────────────

class TestZoneSplitter:
    """메쉬 분할기 테스트."""

    @staticmethod
    def _make_2x2_quad4():
        """2×2 QUAD4 메쉬 생성 (9 노드, 4 요소).

            6─7─8
            │ │ │
            3─4─5
            │ │ │
            0─1─2
        """
        nodes = np.array([
            [0, 0], [1, 0], [2, 0],
            [0, 1], [1, 1], [2, 1],
            [0, 2], [1, 2], [2, 2],
        ], dtype=np.float64)

        elements = np.array([
            [0, 1, 4, 3],  # 요소 0: 좌하
            [1, 2, 5, 4],  # 요소 1: 우하
            [3, 4, 7, 6],  # 요소 2: 좌상
            [4, 5, 8, 7],  # 요소 3: 우상
        ], dtype=np.int64)

        return nodes, elements

    def test_split_basic(self):
        """기본 분할: 좌측 2요소 FEM, 우측 2요소 PD."""
        from ..coupling.zone_splitter import split_mesh

        nodes, elements = self._make_2x2_quad4()
        # 우측 요소(1, 3)를 PD로
        pd_mask = np.array([False, True, False, True])

        split = split_mesh(nodes, elements, pd_mask)

        # FEM 영역: 요소 0, 2 → 노드 {0,1,3,4,6,7}
        assert len(split.fem_elements) == 2
        assert len(split.fem_nodes) == 6

        # PD 영역: 요소 1, 3 → 노드 {1,2,4,5,7,8}
        assert len(split.pd_nodes) == 6

        # 인터페이스: 노드 {1, 4, 7} (양쪽 공유)
        assert len(split.interface_global) == 3
        assert set(split.interface_global) == {1, 4, 7}

    def test_interface_indices_match(self):
        """인터페이스 FEM/PD 인덱스가 같은 물리적 노드를 가리키는지 확인."""
        from ..coupling.zone_splitter import split_mesh

        nodes, elements = self._make_2x2_quad4()
        pd_mask = np.array([False, True, False, True])
        split = split_mesh(nodes, elements, pd_mask)

        # 인터페이스 FEM 좌표 = 인터페이스 PD 좌표
        fem_coords = split.fem_nodes[split.interface_fem]
        pd_coords = split.pd_nodes[split.interface_pd]
        np.testing.assert_allclose(fem_coords, pd_coords, atol=1e-12)

    def test_empty_pd_zone(self):
        """PD 영역이 비어있으면 전체가 FEM."""
        from ..coupling.zone_splitter import split_mesh

        nodes, elements = self._make_2x2_quad4()
        pd_mask = np.zeros(4, dtype=bool)  # 전부 FEM

        split = split_mesh(nodes, elements, pd_mask)

        assert len(split.fem_elements) == 4
        assert len(split.pd_nodes) == 0
        assert len(split.interface_global) == 0

    def test_full_pd_zone(self):
        """전체가 PD이면 FEM 요소 없음."""
        from ..coupling.zone_splitter import split_mesh

        nodes, elements = self._make_2x2_quad4()
        pd_mask = np.ones(4, dtype=bool)  # 전부 PD

        split = split_mesh(nodes, elements, pd_mask)

        assert len(split.fem_elements) == 0
        assert len(split.pd_nodes) == 9
        assert len(split.interface_global) == 0

    def test_volumes_positive(self):
        """PD 입자 부피가 양수인지 확인."""
        from ..coupling.zone_splitter import split_mesh

        nodes, elements = self._make_2x2_quad4()
        pd_mask = np.array([False, True, False, True])
        split = split_mesh(nodes, elements, pd_mask)

        assert np.all(split.pd_volumes > 0)


# ──────────────────────────────────────────────────────────
# 2. interface_manager 테스트
# ──────────────────────────────────────────────────────────

class TestInterfaceManager:
    """인터페이스 관리자 테스트."""

    def test_fem_to_pd(self):
        """FEM 변위 → PD 변위 전달 확인."""
        from ..coupling.interface_manager import InterfaceManager

        # 3개 인터페이스 노드 (FEM 인덱스: 0,2,4, PD 인덱스: 1,3,5)
        mgr = InterfaceManager(
            interface_fem=np.array([0, 2, 4]),
            interface_pd=np.array([1, 3, 5]),
            dim=2,
        )

        # FEM 변위: 5 노드
        fem_disp = np.array([
            [1.0, 0.5],  # FEM 노드 0 (인터페이스)
            [0.0, 0.0],
            [2.0, 1.0],  # FEM 노드 2 (인터페이스)
            [0.0, 0.0],
            [3.0, 1.5],  # FEM 노드 4 (인터페이스)
        ])

        pd_idx, pd_disp = mgr.fem_to_pd_displacements(fem_disp)

        assert list(pd_idx) == [1, 3, 5]
        np.testing.assert_allclose(pd_disp[0], [1.0, 0.5])
        np.testing.assert_allclose(pd_disp[1], [2.0, 1.0])
        np.testing.assert_allclose(pd_disp[2], [3.0, 1.5])

    def test_pd_to_fem(self):
        """PD 반력 → FEM 외력 전달 (부호 반전) 확인."""
        from ..coupling.interface_manager import InterfaceManager

        mgr = InterfaceManager(
            interface_fem=np.array([0, 2]),
            interface_pd=np.array([1, 3]),
            dim=2,
        )

        pd_forces = np.array([
            [0.0, 0.0],
            [10.0, 5.0],   # PD 노드 1 (인터페이스)
            [0.0, 0.0],
            [20.0, 10.0],  # PD 노드 3 (인터페이스)
        ])

        fem_idx, fem_forces = mgr.pd_to_fem_forces(pd_forces)

        assert list(fem_idx) == [0, 2]
        # 부호 반전
        np.testing.assert_allclose(fem_forces[0], [-10.0, -5.0])
        np.testing.assert_allclose(fem_forces[1], [-20.0, -10.0])

    def test_convergence_check(self):
        """수렴 체크: 동일 변위 → 수렴."""
        from ..coupling.interface_manager import InterfaceManager

        mgr = InterfaceManager(
            interface_fem=np.array([0]),
            interface_pd=np.array([0]),
            dim=2,
        )

        disp = np.array([[1.0, 2.0]])

        # 첫 호출: prev=0 → 변화 있음
        conv1, _ = mgr.check_convergence(disp, tol=1e-6)
        assert not conv1

        # 두 번째: 동일 변위 → 수렴
        conv2, change = mgr.check_convergence(disp, tol=1e-6)
        assert conv2
        assert change == 0.0


# ──────────────────────────────────────────────────────────
# 3. criteria 테스트
# ──────────────────────────────────────────────────────────

class TestSwitchingCriteria:
    """자동 전환 기준 테스트."""

    def test_von_mises_threshold(self):
        """Von Mises 임계값 초과 요소 판별."""
        from ..coupling.criteria import SwitchingCriteria

        criteria = SwitchingCriteria(
            von_mises_threshold=100.0,
            buffer_layers=0,
        )

        # 2 요소, 각 1 가우스점, 2D
        # 요소 0: σ_xx=50, σ_yy=50, σ_xy=0 → VM ≈ 50
        # 요소 1: σ_xx=200, σ_yy=0, σ_xy=0 → VM = 200
        gauss_stress = np.zeros((2, 2, 2))
        gauss_stress[0, 0, 0] = 50.0
        gauss_stress[0, 1, 1] = 50.0
        gauss_stress[1, 0, 0] = 200.0

        mask = criteria.evaluate(gauss_stress, None, n_elements=2, n_gauss=1)

        assert mask[0] == False  # VM=50 < 100
        assert mask[1] == True   # VM=200 > 100

    def test_buffer_expansion(self):
        """버퍼 레이어 확장 테스트."""
        from ..coupling.criteria import SwitchingCriteria

        criteria = SwitchingCriteria(
            von_mises_threshold=100.0,
            buffer_layers=1,
        )

        # 3 요소 (1D 체인), 요소 1만 초과
        elements = np.array([
            [0, 1],
            [1, 2],
            [2, 3],
        ], dtype=np.int64)

        gauss_stress = np.zeros((3, 2, 2))
        gauss_stress[1, 0, 0] = 200.0  # 요소 1만 초과

        mask = criteria.evaluate(
            gauss_stress, None, n_elements=3, n_gauss=1,
            elements=elements,
        )

        # 요소 1 초과 → 인접 요소 0, 2도 포함
        assert mask[0] == True   # 인접
        assert mask[1] == True   # 초과
        assert mask[2] == True   # 인접


# ──────────────────────────────────────────────────────────
# 4. Domain COUPLED Method 테스트
# ──────────────────────────────────────────────────────────

class TestDomainCoupled:
    """COUPLED Method 통합 테스트."""

    def test_method_enum(self):
        """Method.COUPLED enum 확인."""
        from ..domain import Method
        assert Method.COUPLED.value == "coupled"

    def test_coupling_config(self):
        """CouplingConfig 데이터클래스 확인."""
        from ..domain import CouplingConfig

        config = CouplingConfig(
            mode="auto",
            particle_method="spg",
            criteria={"von_mises_threshold": 50e6},
        )
        assert config.mode == "auto"
        assert config.particle_method == "spg"
        assert config.criteria["von_mises_threshold"] == 50e6
        assert config.coupling_tol == 1e-4

    def test_domain_with_coupling_config(self):
        """Domain에 CouplingConfig 설정."""
        from ..domain import Domain, Method, CouplingConfig

        domain = Domain(
            Method.COUPLED, dim=2,
            origin=(0, 0), size=(1, 1),
            n_divisions=(4, 4),
        )
        domain._coupling_config = CouplingConfig(
            mode="manual",
            pd_element_indices=[0, 1, 2],
        )

        assert domain.method == Method.COUPLED
        assert domain._coupling_config.pd_element_indices == [0, 1, 2]
