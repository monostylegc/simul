"""Pseudo-label 생성 — TotalSpineSeg로 CT 디스크 라벨 보충.

CT 데이터(VerSe, CTSpine1K)에는 척추골 라벨만 있으므로,
TotalSpineSeg를 돌려서 디스크/연조직 pseudo-label을 생성한다.
"""

from pathlib import Path
from typing import Optional

import numpy as np

from .config import PseudoLabelConfig


def generate_pseudo_labels(
    ct_image_path: Path,
    output_path: Path,
    config: Optional[PseudoLabelConfig] = None,
) -> Path:
    """CT 영상에 TotalSpineSeg를 실행하여 pseudo-label 생성.

    Args:
        ct_image_path: CT NIfTI 파일 경로
        output_path: 출력 라벨맵 경로
        config: pseudo-label 설정

    Returns:
        생성된 pseudo-label 파일 경로
    """
    if config is None:
        config = PseudoLabelConfig()

    from src.segmentation.factory import create_engine

    engine = create_engine("totalspineseg")
    output_dir = output_path.parent / "_pseudo_tmp"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result_path = engine.segment(
            input_path=str(ct_image_path),
            output_path=str(output_dir),
            device=config.device,
        )
        # 결과를 최종 경로로 이동
        import shutil
        shutil.copy2(str(result_path), str(output_path))
    finally:
        import shutil
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)

    return output_path


def filter_pseudo_labels(
    pseudo_label_array: np.ndarray,
    gt_vertebra_array: np.ndarray,
    config: Optional[PseudoLabelConfig] = None,
) -> np.ndarray:
    """Pseudo-label 신뢰도 필터링.

    규칙:
      1. 디스크 voxel 수 < min_disc_voxels → ignore (51)
      2. 인접 척추골 사이에 위치하지 않는 디스크 → ignore
      3. 연결 성분 비정상 크기 → ignore

    Args:
        pseudo_label_array: TotalSpineSeg 출력 라벨 (SpineLabel 체계)
        gt_vertebra_array: Ground-truth 척추골 라벨 (SpineLabel 체계)
        config: 필터 설정

    Returns:
        필터링된 라벨 배열 (불확실 영역 = 51)
    """
    from scipy import ndimage

    from src.segmentation.labels import SpineLabel, NNUNET_IGNORE_LABEL

    if config is None:
        config = PseudoLabelConfig()

    filtered = pseudo_label_array.copy()

    # 디스크 라벨 범위 (SpineLabel: 201~223)
    disc_labels = [m.value for m in SpineLabel if SpineLabel.is_disc(m.value)]

    for disc_label in disc_labels:
        disc_mask = (pseudo_label_array == disc_label)
        disc_voxels = np.sum(disc_mask)

        # 규칙 1: 최소 크기 미달
        if disc_voxels < config.min_disc_voxels:
            filtered[disc_mask] = NNUNET_IGNORE_LABEL
            continue

        # 규칙 2: 인접 척추골 확인
        if disc_voxels > 0 and not _is_between_vertebrae(disc_mask, gt_vertebra_array, disc_label):
            filtered[disc_mask] = NNUNET_IGNORE_LABEL
            continue

        # 규칙 3: 연결 성분 크기 필터
        labeled_array, n_components = ndimage.label(disc_mask)
        if n_components > 1:
            sizes = ndimage.sum(disc_mask, labeled_array, range(1, n_components + 1))
            max_size = max(sizes)
            for i, sz in enumerate(sizes, 1):
                if max_size / max(sz, 1) > config.max_component_ratio:
                    # 비정상적으로 작은 성분 → ignore
                    filtered[labeled_array == i] = NNUNET_IGNORE_LABEL

    return filtered


def _is_between_vertebrae(
    disc_mask: np.ndarray,
    vertebra_array: np.ndarray,
    disc_label: int,
) -> bool:
    """디스크가 인접 척추골 사이에 위치하는지 확인.

    디스크 C3C4(202)는 C3(103)과 C4(104) 사이에 있어야 함.
    """
    from src.segmentation.labels import SpineLabel

    # 디스크 라벨 → 인접 척추골 쌍 매핑
    disc_to_vertebrae = {}
    vertebrae = [m for m in SpineLabel if SpineLabel.is_vertebra(m.value)]
    discs = [m for m in SpineLabel if SpineLabel.is_disc(m.value)]

    # 디스크는 두 인접 척추골 사이 (C2C3 → C2, C3)
    for i, disc in enumerate(discs):
        # 디스크 인덱스 i → 척추골 인덱스 i+1 (C2=1), i+2 (C3=2)
        # C2C3는 첫 번째 디스크, C2는 두 번째 척추골 (C1=0, C2=1)
        upper_idx = i + 1  # C2 인덱스 (0-based, C1=0)
        lower_idx = i + 2  # C3 인덱스
        if upper_idx < len(vertebrae) and lower_idx < len(vertebrae):
            disc_to_vertebrae[disc.value] = (
                vertebrae[upper_idx].value,
                vertebrae[lower_idx].value,
            )

    if disc_label not in disc_to_vertebrae:
        return False

    upper_vert, lower_vert = disc_to_vertebrae[disc_label]

    # 인접 척추골이 GT에 존재하는지 확인
    has_upper = np.any(vertebra_array == upper_vert)
    has_lower = np.any(vertebra_array == lower_vert)

    # 둘 중 하나라도 존재하면 허용 (부분 FOV 고려)
    return has_upper or has_lower
