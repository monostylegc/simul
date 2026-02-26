"""COUPLED 바디 assembly 통합 테스트.

FEM + COUPLED 바디가 혼합된 Scene의 자동 조립을 검증한다.
"""

import tempfile
import numpy as np
import pytest

from backend.fea.framework.domain import Method, CouplingConfig
from backend.fea.framework.contact import ContactType
from backend.anatomy.base import AnatomyProfile, MaterialProps
from backend.preprocessing.assembly import assemble, AssemblyResult, _create_coupled_body
from backend.preprocessing.voxel_to_hex import voxels_to_hex_mesh


class CoupledTestProfile(AnatomyProfile):
    """테스트용 프로파일: 라벨 100번대는 FEM, 200번대는 COUPLED."""

    def get_material(self, label: int) -> MaterialProps:
        """100번대 → FEM (뼈), 200번대 → COUPLED (디스크)."""
        if 100 <= label < 200:
            return MaterialProps(
                E=1000.0, nu=0.3, density=1800.0, method=Method.FEM,
            )
        else:
            return MaterialProps(
                E=100.0, nu=0.45, density=1060.0, method=Method.COUPLED,
            )

    def get_contact_type(self, label_a: int, label_b: int):
        """FEM-COUPLED 쌍: TIED."""
        a_fem = 100 <= label_a < 200
        b_fem = 100 <= label_b < 200
        a_coupled = 200 <= label_a < 300
        b_coupled = 200 <= label_b < 300

        if (a_fem and b_coupled) or (a_coupled and b_fem):
            return ContactType.TIED
        return None

    def get_contact_params(self, label_a: int, label_b: int):
        """기본 접촉 파라미터."""
        return {"penalty": 1e3}


def _create_coupled_test_npz(
    shape=(4, 4, 12),
    spacing=(1.0, 1.0, 1.0),
):
    """FEM + COUPLED 라벨맵 NPZ 생성.

    z=[0,3]: FEM 라벨 101
    z=[4,7]: COUPLED 라벨 201
    z=[8,11]: FEM 라벨 102
    """
    vol = np.zeros(shape, dtype=np.int32)
    nz = shape[2]
    third = nz // 3

    vol[:, :, :third] = 101       # FEM
    vol[:, :, third:2*third] = 201  # COUPLED
    vol[:, :, 2*third:] = 102     # FEM

    tmp = tempfile.NamedTemporaryFile(suffix=".npz", delete=False)
    np.savez(
        tmp.name,
        label_volume=vol,
        spacing=np.array(spacing),
        origin=np.array([0.0, 0.0, 0.0]),
    )
    return tmp.name


class TestCreateCoupledBody:
    """_create_coupled_body 단위 테스트."""

    def test_creates_coupled_domain(self):
        """COUPLED 도메인이 올바르게 생성되는지 확인."""
        centers = np.array([
            [0.5, 0.5, 0.5],
            [1.5, 0.5, 0.5],
            [0.5, 1.5, 0.5],
            [1.5, 1.5, 0.5],
        ])
        spacing = np.array([1.0, 1.0, 1.0])

        domain = _create_coupled_body(centers, spacing)

        assert domain.method == Method.COUPLED
        assert domain._coupling_config is not None
        assert domain._coupling_config.mode == "auto"
        assert domain._hex_nodes is not None
        assert domain._hex_elements is not None
        assert domain._custom_positions is not None

    def test_custom_coupling_config(self):
        """커스텀 CouplingConfig 전달."""
        centers = np.array([[0.5, 0.5, 0.5]])
        spacing = np.array([1.0, 1.0, 1.0])

        config = CouplingConfig(
            mode="manual",
            particle_method="spg",
            pd_element_indices=[0],
            coupling_tol=1e-3,
        )

        domain = _create_coupled_body(centers, spacing, coupling_config=config)

        assert domain._coupling_config.mode == "manual"
        assert domain._coupling_config.particle_method == "spg"

    def test_hex_mesh_data_stored(self):
        """HEX8 메쉬 데이터가 도메인에 저장되는지 확인."""
        centers = np.array([
            [0.5, 0.5, 0.5],
            [1.5, 0.5, 0.5],
        ])
        spacing = np.array([1.0, 1.0, 1.0])

        domain = _create_coupled_body(centers, spacing)

        # 노드와 요소가 올바른 형태
        assert domain._hex_nodes.ndim == 2
        assert domain._hex_nodes.shape[1] == 3
        assert domain._hex_elements.ndim == 2
        assert domain._hex_elements.shape[1] == 8  # HEX8

    def test_positions_match_hex_nodes(self):
        """_custom_positions가 _hex_nodes와 동일한지 확인."""
        centers = np.array([[0.5, 0.5, 0.5]])
        spacing = np.array([1.0, 1.0, 1.0])

        domain = _create_coupled_body(centers, spacing)

        np.testing.assert_array_equal(
            domain._custom_positions, domain._hex_nodes,
        )


class TestCoupledAssembly:
    """COUPLED 바디 포함 assembly 통합 테스트."""

    def test_mixed_fem_coupled_bodies(self):
        """FEM + COUPLED 혼합 라벨맵 → 3개 Body."""
        npz_path = _create_coupled_test_npz()
        profile = CoupledTestProfile()

        result = assemble(npz_path, profile, min_voxels=1)

        # 3개 라벨 → 3개 바디
        assert len(result.body_map) == 3
        assert 101 in result.body_map
        assert 102 in result.body_map
        assert 201 in result.body_map

    def test_coupled_domain_method(self):
        """COUPLED 라벨 도메인의 method가 COUPLED인지 확인."""
        npz_path = _create_coupled_test_npz()
        profile = CoupledTestProfile()

        result = assemble(npz_path, profile, min_voxels=1)

        # 라벨 201은 COUPLED
        domain_201 = result.label_domains[201]
        assert domain_201.method == Method.COUPLED
        assert domain_201._coupling_config is not None

        # 라벨 101, 102는 FEM
        assert result.label_domains[101].method == Method.FEM
        assert result.label_domains[102].method == Method.FEM

    def test_tied_contacts_with_coupled(self):
        """FEM-COUPLED 간 TIED 접촉이 생성되는지 확인."""
        npz_path = _create_coupled_test_npz()
        profile = CoupledTestProfile()

        result = assemble(npz_path, profile, min_voxels=1)

        # FEM-COUPLED 쌍에 TIED 접촉
        contact_labels = {(a, b) for a, b, _ in result.contact_pairs}
        assert (101, 201) in contact_labels or (201, 101) in contact_labels
        assert (102, 201) in contact_labels or (201, 102) in contact_labels

    def test_coupled_domain_has_positions(self):
        """COUPLED 도메인에 유효한 노드 좌표 존재."""
        npz_path = _create_coupled_test_npz()
        profile = CoupledTestProfile()

        result = assemble(npz_path, profile, min_voxels=1)

        domain_201 = result.label_domains[201]
        pos = domain_201.get_positions()
        assert len(pos) > 0
        assert pos.shape[1] == 3
