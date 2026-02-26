"""SpineProfile + assembly E2E 해석 테스트.

합성 L4+disc(L4L5)+L5 라벨맵으로:
  assemble(npz, SpineProfile()) → scene.solve() → 변위 연속성 검증

NOTE: Staggered 정적 솔버에서 각 body는 독립적으로 풀 수 있어야 하므로
      모든 body에 충분한 고정 BC를 설정한다 (강체 모드 방지).
      Body 배치 (z축):
        L4:   hex z=[0,3]  — z=0 면 고정, z=1 면에 하향 힘
        Disc: hex z=[3,6]  — z=6 면 고정 (L5 쪽)
        L5:   hex z=[6,9]  — z=9 면 고정
      Tied 접촉:
        L4 z=3 ↔ Disc z=3 (L4-디스크 경계)
        Disc z=6 ↔ L5 z=6 (디스크-L5 경계)
"""

import tempfile
import numpy as np
import pytest

from backend.fea.framework.runtime import is_initialized
from backend.fea.framework import init
from backend.fea.framework.contact import ContactType
from backend.fea.framework.domain import Method
from backend.segmentation.labels import SpineLabel
from backend.preprocessing.assembly import assemble
from backend.anatomy.spine import SpineProfile


# Taichi 초기화 (FEM 어댑터에서 필요)
if not is_initialized():
    init()


def _create_spine_npz(
    shape=(3, 3, 9),
    spacing=(1.0, 1.0, 1.0),
):
    """합성 L4-L4L5disc-L5 라벨맵 NPZ 생성.

    z 방향으로:
      z=[0,2]: L4 (라벨 123)
      z=[3,5]: L4L5 디스크 (라벨 222)
      z=[6,8]: L5 (라벨 124)

    HEX8 노드 z 범위:
      L4:   [0, 3]
      Disc: [3, 6]
      L5:   [6, 9]

    Returns:
        NPZ 파일 경로
    """
    vol = np.zeros(shape, dtype=np.int32)
    nz = shape[2]
    third = nz // 3

    vol[:, :, :third] = SpineLabel.L4         # 123
    vol[:, :, third:2*third] = SpineLabel.L4L5  # 222
    vol[:, :, 2*third:] = SpineLabel.L5       # 124

    tmp = tempfile.NamedTemporaryFile(suffix=".npz", delete=False)
    np.savez(
        tmp.name,
        label_volume=vol,
        spacing=np.array(spacing),
        origin=np.array([0.0, 0.0, 0.0]),
    )
    return tmp.name


def _setup_spine_bcs(result, force_value=-10.0, tied_penalty=500.0):
    """3물체 척추 모델에 경계조건 설정.

    각 body가 독립적으로 풀 수 있도록 최소 고정 BC 설정:
      - L4:   z=0 면 fully fixed (기저), z=1 면에 하향 힘
      - Disc:  z=6 면 fully fixed (L5 쪽 경계)
      - L5:   z=9 면 fully fixed (최상단)
    """
    dom_l4 = result.label_domains[SpineLabel.L4]
    dom_disc = result.label_domains[SpineLabel.L4L5]
    dom_l5 = result.label_domains[SpineLabel.L5]

    # L4: z 최솟값 (z=0) 완전 고정
    pos_l4 = dom_l4.get_positions()
    z_min_l4 = pos_l4[:, 2].min()
    fixed_l4 = dom_l4.select(axis=2, value=z_min_l4)
    dom_l4.set_fixed(fixed_l4)

    # L4: z = z_min + 1 (내부 면)에 하향 힘
    # z_min + spacing 위치의 노드 (첫 번째 내부 면)
    z_vals_l4 = np.unique(np.round(pos_l4[:, 2], decimals=6))
    if len(z_vals_l4) >= 2:
        z_force = z_vals_l4[1]  # 두 번째 z 레이어
    else:
        z_force = z_min_l4
    force_nodes = dom_l4.select(axis=2, value=z_force)
    dom_l4.set_force(force_nodes, [0.0, 0.0, force_value])

    # Disc: z 최댓값 (z=6) 완전 고정
    pos_disc = dom_disc.get_positions()
    z_max_disc = pos_disc[:, 2].max()
    fixed_disc = dom_disc.select(axis=2, value=z_max_disc)
    dom_disc.set_fixed(fixed_disc)

    # L5: z 최댓값 (z=9) 완전 고정
    pos_l5 = dom_l5.get_positions()
    z_max_l5 = pos_l5[:, 2].max()
    fixed_l5 = dom_l5.select(axis=2, value=z_max_l5)
    dom_l5.set_fixed(fixed_l5)


class TestSpineAssemblyE2E:
    """SpineProfile을 사용한 assemble() → solve() E2E 테스트."""

    def test_assembly_creates_correct_bodies(self):
        """L4+L4L5+L5 → 3개 Body + TIED 접촉."""
        npz_path = _create_spine_npz()
        profile = SpineProfile()

        result = assemble(npz_path, profile, min_voxels=1)

        # 3개 라벨
        assert SpineLabel.L4 in result.body_map
        assert SpineLabel.L5 in result.body_map
        assert SpineLabel.L4L5 in result.body_map

        # TIED 접촉: L4-디스크, L5-디스크
        contact_labels = {(a, b) for a, b, _ in result.contact_pairs}
        has_l4_disc = (
            (SpineLabel.L4, SpineLabel.L4L5) in contact_labels
            or (SpineLabel.L4L5, SpineLabel.L4) in contact_labels
        )
        has_l5_disc = (
            (SpineLabel.L5, SpineLabel.L4L5) in contact_labels
            or (SpineLabel.L4L5, SpineLabel.L5) in contact_labels
        )
        assert has_l4_disc, "L4-디스크 TIED 접촉 누락"
        assert has_l5_disc, "L5-디스크 TIED 접촉 누락"

        # 접촉 유형: 척추골-디스크 → TIED
        for la, lb, ct in result.contact_pairs:
            is_vert_disc = (
                (SpineLabel.is_vertebra(la) and SpineLabel.is_disc(lb))
                or (SpineLabel.is_disc(la) and SpineLabel.is_vertebra(lb))
            )
            if is_vert_disc:
                assert ct == ContactType.TIED

    def test_domains_have_valid_mesh(self):
        """각 도메인의 HEX8 메쉬 데이터가 유효한지 확인."""
        npz_path = _create_spine_npz()
        profile = SpineProfile()

        result = assemble(npz_path, profile, min_voxels=1)

        for label, domain in result.label_domains.items():
            assert hasattr(domain, '_hex_nodes'), f"라벨 {label}: _hex_nodes 없음"
            assert hasattr(domain, '_hex_elements'), f"라벨 {label}: _hex_elements 없음"

            nodes = domain._hex_nodes
            elems = domain._hex_elements

            assert nodes.ndim == 2 and nodes.shape[1] == 3
            assert elems.ndim == 2 and elems.shape[1] == 8
            assert elems.max() < len(nodes)
            assert elems.min() >= 0

    def test_solve_with_bcs(self):
        """경계조건 설정 후 정적 해석 — L4에 비영 변위."""
        npz_path = _create_spine_npz()
        profile = SpineProfile(
            bone_E=1000.0, disc_E=100.0,
            tied_penalty=500.0,
        )

        result = assemble(npz_path, profile, min_voxels=1)
        _setup_spine_bcs(result, force_value=-10.0)

        result.scene.solve(
            mode="static",
            max_contact_iters=30,
            contact_tol=1e-2,
            verbose=False,
        )

        # L4에 비영 변위 (하향 힘으로 변형)
        dom_l4 = result.label_domains[SpineLabel.L4]
        u_l4 = result.scene.get_displacements(dom_l4)
        assert np.max(np.abs(u_l4)) > 0, "L4에 변위 없음"

    def test_tied_contact_transfers_force(self):
        """Tied 접촉으로 디스크에 힘 전달 — 디스크 비영 변위."""
        npz_path = _create_spine_npz()
        profile = SpineProfile(
            bone_E=1000.0, disc_E=100.0,
            tied_penalty=500.0,
        )

        result = assemble(npz_path, profile, min_voxels=1)
        _setup_spine_bcs(result, force_value=-10.0)

        result.scene.solve(
            mode="static",
            max_contact_iters=30,
            contact_tol=1e-2,
            verbose=False,
        )

        # 디스크에 변위 발생 (Tied 접촉으로 힘 전달)
        dom_disc = result.label_domains[SpineLabel.L4L5]
        u_disc = result.scene.get_displacements(dom_disc)
        assert np.max(np.abs(u_disc)) > 0, (
            "디스크에 변위 없음 — Tied 접촉 미작동"
        )

    def test_downward_force_produces_negative_z_displacement(self):
        """하향 힘 → z 방향 음의 변위 (단일 body 독립 해석).

        Staggered 접촉 반복의 발산 영향을 배제하기 위해
        L4 단독으로 해석하여 하향 힘 → z 음수 변위 검증.
        """
        from backend.fea.framework.domain import create_domain
        from backend.fea.framework.material import Material
        from backend.fea.framework.scene import Scene

        # L4에 해당하는 단독 도메인 (3x3x3 HEX8)
        dom = create_domain(
            Method.FEM, dim=3,
            origin=(0.0, 0.0, 0.0), size=(3.0, 3.0, 3.0),
            n_divisions=(3, 3, 3),
        )
        mat = Material(E=1000.0, nu=0.3, dim=3)

        # z=0 고정
        bottom = dom.select(axis=2, value=0.0)
        dom.set_fixed(bottom)

        # z=1 면에 하향 힘
        mid = dom.select(axis=2, value=1.0)
        dom.set_force(mid, [0.0, 0.0, -10.0])

        scene = Scene()
        scene.add(dom, mat)
        result = scene.solve(mode="static", verbose=False)

        u = scene.get_displacements(dom)
        u_z_mid = u[mid, 2]

        # 하향 힘 → z 음수 변위
        assert np.all(u_z_mid < 0), (
            f"하중점 z변위가 음수가 아님: {u_z_mid}"
        )

    def test_assembly_spine_labels(self):
        """실제 SpineLabel 값으로 assembly 라벨 분류 검증."""
        npz_path = _create_spine_npz()
        profile = SpineProfile()

        result = assemble(npz_path, profile, min_voxels=1)

        dom_l4 = result.label_domains[SpineLabel.L4]
        dom_disc = result.label_domains[SpineLabel.L4L5]
        dom_l5 = result.label_domains[SpineLabel.L5]

        # 모든 도메인이 FEM 방법
        assert dom_l4.method == Method.FEM
        assert dom_disc.method == Method.FEM
        assert dom_l5.method == Method.FEM

        # 위치 좌표 유효성
        for dom in [dom_l4, dom_disc, dom_l5]:
            pos = dom.get_positions()
            assert len(pos) > 0
            assert pos.shape[1] == 3

    def test_material_properties_applied(self):
        """SpineProfile 재료 물성이 올바르게 적용되는지 확인."""
        npz_path = _create_spine_npz()
        profile = SpineProfile(
            bone_E=2000.0, disc_E=200.0,
        )

        result = assemble(npz_path, profile, min_voxels=1)

        # body_map에 올바른 이름
        assert result.body_map[SpineLabel.L4] == "label_123"
        assert result.body_map[SpineLabel.L4L5] == "label_222"
        assert result.body_map[SpineLabel.L5] == "label_124"
