"""라벨맵 → Scene 자동 조립 모듈.

NPZ 라벨맵과 AnatomyProfile을 받아 다물체 Scene을 자동 생성한다.
부위 무관한 범용 파이프라인.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from backend.fea.framework.domain import (
    Method, CouplingConfig, create_domain, create_particle_domain,
)
from backend.fea.framework.material import Material
from backend.fea.framework.contact import ContactType
from backend.fea.framework.scene import Scene

from backend.anatomy.base import AnatomyProfile, MaterialProps
from .adjacency import find_adjacent_pairs
from .voxel_to_hex import voxels_to_hex_mesh


@dataclass
class AssemblyResult:
    """조립 결과.

    Attributes:
        scene: 구성된 Scene 객체
        body_map: 라벨 → (body_name, domain) 매핑
        contact_pairs: 추가된 접촉 쌍 리스트 [(label_a, label_b, type), ...]
        label_domains: 라벨 → Domain 매핑 (외부에서 BC 설정 시 사용)
    """
    scene: Scene
    body_map: Dict[int, str] = field(default_factory=dict)
    contact_pairs: List[tuple] = field(default_factory=list)
    label_domains: Dict[int, object] = field(default_factory=dict)


def assemble(
    npz_path: str,
    profile: AnatomyProfile,
    min_voxels: int = 10,
) -> AssemblyResult:
    """NPZ 라벨맵 + AnatomyProfile → Scene 자동 생성.

    절차:
      1. NPZ 로드 (label_volume, spacing, origin)
      2. 라벨별 복셀 추출 (최소 크기 필터링)
      3. AnatomyProfile.get_material() → 재료/방법 결정
      4. FEM: voxels_to_hex → HEX8 메쉬 / PD·SPG: create_particle_domain
      5. adjacency → 인접 쌍 탐색
      6. profile.get_contact_type() → 접촉 자동 추가

    Args:
        npz_path: NPZ 파일 경로
            필요 키: label_volume (I,J,K), spacing (3,), origin (3,)
        profile: 해부학 프로파일 (재료/접촉 규칙 제공)
        min_voxels: 최소 복셀 수 (이보다 작은 라벨은 무시)

    Returns:
        AssemblyResult
    """
    # 1. NPZ 로드
    data = np.load(npz_path, allow_pickle=True)
    label_volume = data["label_volume"]
    spacing = data["spacing"]
    origin = data.get("origin", np.zeros(3))
    if isinstance(origin, np.lib.npyio.NpzFile):
        origin = np.zeros(3)
    origin = np.asarray(origin, dtype=np.float64)
    spacing = np.asarray(spacing, dtype=np.float64)

    # 2. 라벨별 복셀 추출
    unique_labels = np.unique(label_volume)
    unique_labels = unique_labels[unique_labels != 0]  # 배경 제거

    scene = Scene()
    result = AssemblyResult(scene=scene)

    label_to_domain = {}

    for label in unique_labels:
        label = int(label)
        mask = label_volume == label
        voxel_ijk = np.argwhere(mask)

        if len(voxel_ijk) < min_voxels:
            continue

        # 복셀 IJK → 물리 좌표 (복셀 중심)
        voxel_centers = voxel_ijk.astype(np.float64) * spacing + origin + spacing / 2.0

        # 3. 재료/방법 결정
        mat_props = profile.get_material(label)
        material = Material(E=mat_props.E, nu=mat_props.nu, dim=3)

        # 4. 도메인 생성
        if mat_props.method == Method.FEM:
            domain = _create_fem_body(voxel_centers, spacing)
        elif mat_props.method == Method.COUPLED:
            # COUPLED: FEM 메쉬 기반 + 자동 PD 전환 설정
            domain = _create_coupled_body(voxel_centers, spacing)
        else:
            # PD / SPG
            domain = create_particle_domain(
                voxel_centers, method=mat_props.method,
            )

        # Scene에 추가
        body_name = f"label_{label}"
        scene.add(domain, material)

        label_to_domain[label] = domain
        result.body_map[label] = body_name
        result.label_domains[label] = domain

    # 5. 인접 쌍 탐색
    adj_pairs = find_adjacent_pairs(label_volume)

    # 6. 접촉 자동 추가 (인접 기반: 척추골-디스크 TIED 등)
    for pair in adj_pairs:
        la, lb = pair.label_a, pair.label_b

        if la not in label_to_domain or lb not in label_to_domain:
            continue

        contact_type = profile.get_contact_type(la, lb)
        if contact_type is None:
            continue

        params = profile.get_contact_params(la, lb)
        dom_a = label_to_domain[la]
        dom_b = label_to_domain[lb]

        scene.add_contact(
            dom_a, dom_b,
            method=contact_type,
            penalty=params.get("penalty", None),
            static_friction=params.get("friction", 0.0),
        )

        result.contact_pairs.append((la, lb, contact_type))

    # 7. 후관절(Facet Joint) 자동 탐지 (프로파일이 지원하는 경우)
    if hasattr(profile, "detect_facet_joints"):
        _add_facet_contacts(
            profile, label_volume, spacing, origin,
            label_to_domain, scene, result,
        )

    return result


def _add_facet_contacts(
    profile,
    label_volume: np.ndarray,
    spacing: np.ndarray,
    origin: np.ndarray,
    label_to_domain: Dict,
    scene: Scene,
    result: AssemblyResult,
) -> None:
    """후관절 탐지 결과를 Scene에 PENALTY 접촉으로 추가.

    profile.detect_facet_joints()를 호출하여 후관절 쌍을 탐지하고,
    각 쌍에 대해 PENALTY + 마찰 접촉을 추가한다.
    """
    from backend.segmentation.labels import SpineLabel

    vert_labels = [
        l for l in label_to_domain.keys() if SpineLabel.is_vertebra(l)
    ]

    if len(vert_labels) < 2:
        return

    facets = profile.detect_facet_joints(
        label_volume, spacing, origin, vert_labels,
    )

    for fj in facets:
        sup = fj.superior_label
        inf = fj.inferior_label

        if sup not in label_to_domain or inf not in label_to_domain:
            continue

        # 이미 인접 기반으로 추가된 접촉이 있으면 건너뛰기
        existing = {(a, b) for a, b, _ in result.contact_pairs}
        if (sup, inf) in existing or (inf, sup) in existing:
            continue

        params = profile.get_contact_params(sup, inf)
        dom_a = label_to_domain[sup]
        dom_b = label_to_domain[inf]

        scene.add_contact(
            dom_a, dom_b,
            method=ContactType.PENALTY,
            penalty=params.get("penalty", 1e5),
            static_friction=params.get("friction", 0.1),
        )

        result.contact_pairs.append((sup, inf, ContactType.PENALTY))


def _create_fem_body(
    voxel_centers: np.ndarray,
    spacing: np.ndarray,
) -> object:
    """복셀 좌표 → FEM HEX8 도메인 생성.

    voxels_to_hex_mesh로 메쉬를 생성하고,
    FEMesh.initialize_from_numpy()를 사용하여 Domain에 래핑한다.
    """
    nodes, elements = voxels_to_hex_mesh(voxel_centers, spacing)

    # 바운딩 박스 계산
    pos_min = nodes.min(axis=0)
    pos_max = nodes.max(axis=0)
    domain_size = pos_max - pos_min

    # 퇴화 방지
    for d in range(3):
        if domain_size[d] < 1e-6:
            domain_size[d] = spacing[d]

    # 분할 수 추정 (정확하지 않아도 됨, horizon 계산 전용)
    n_per_axis = [
        max(1, int(round(domain_size[d] / spacing[d])))
        for d in range(3)
    ]

    domain = create_domain(
        method=Method.FEM,
        dim=3,
        origin=tuple(pos_min.tolist()),
        size=tuple(domain_size.tolist()),
        n_divisions=tuple(n_per_axis),
    )

    # 실제 메쉬 데이터 저장 (어댑터에서 initialize_from_numpy 사용)
    domain._hex_nodes = nodes
    domain._hex_elements = elements
    # 실제 노드 좌표로 positions 대체
    domain._custom_positions = nodes.copy()

    return domain


def _create_coupled_body(
    voxel_centers: np.ndarray,
    spacing: np.ndarray,
    coupling_config: Optional[CouplingConfig] = None,
) -> object:
    """복셀 좌표 → COUPLED (FEM+PD) 도메인 생성.

    FEM HEX8 메쉬를 생성하고 CouplingConfig를 부착한다.
    auto 모드: 해석 중 응력 기준으로 PD 영역을 자동 전환한다.

    Args:
        voxel_centers: 복셀 중심 좌표 (n, 3)
        spacing: 복셀 간격 (3,)
        coupling_config: 커플링 설정 (None이면 기본 auto 모드)
    """
    nodes, elements = voxels_to_hex_mesh(voxel_centers, spacing)

    # 바운딩 박스 계산
    pos_min = nodes.min(axis=0)
    pos_max = nodes.max(axis=0)
    domain_size = pos_max - pos_min

    # 퇴화 방지
    for d in range(3):
        if domain_size[d] < 1e-6:
            domain_size[d] = spacing[d]

    # 분할 수 추정
    n_per_axis = [
        max(1, int(round(domain_size[d] / spacing[d])))
        for d in range(3)
    ]

    domain = create_domain(
        method=Method.COUPLED,
        dim=3,
        origin=tuple(pos_min.tolist()),
        size=tuple(domain_size.tolist()),
        n_divisions=tuple(n_per_axis),
    )

    # 복셀 기반 HEX8 메쉬 저장 (CoupledAdapter가 감지하여 사용)
    domain._hex_nodes = nodes
    domain._hex_elements = elements
    domain._custom_positions = nodes.copy()

    # 커플링 설정: 기본값은 auto 모드 (응력 기반 PD 전환)
    if coupling_config is None:
        coupling_config = CouplingConfig(
            mode="auto",
            particle_method="pd",
            criteria={
                "von_mises_threshold": None,  # 자동 (재료 항복 응력의 80%)
                "max_strain_threshold": 0.05,  # 5% 변형률
                "buffer_layers": 1,
            },
            coupling_tol=1e-4,
            max_coupling_iters=20,
        )

    domain._coupling_config = coupling_config

    return domain
