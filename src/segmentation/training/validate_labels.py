"""해부학적 일관성 검증 — 인접 척추 위치, 크기, 순서 등 확인."""

from dataclasses import dataclass, field

import numpy as np

from src.segmentation.labels import SpineLabel


@dataclass
class ValidationResult:
    """라벨 검증 결과."""

    case_id: str
    is_valid: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def validate_label_map(
    label_array: np.ndarray,
    case_id: str = "unknown",
    spacing: tuple[float, ...] = (1.0, 1.0, 1.0),
) -> ValidationResult:
    """라벨맵 해부학적 일관성 검증.

    검증 항목:
      1. 척추골 순서 (위→아래: C1이 가장 위)
      2. 디스크 위치 (인접 척추골 사이)
      3. 구조물 크기 범위 (비정상적으로 크거나 작은 라벨)
      4. 겹침 없음 확인 (라벨이 중복되지 않는지)

    Args:
        label_array: 표준 라벨 배열 (SpineLabel 체계)
        case_id: 케이스 식별자
        spacing: 복셀 간격 (mm)

    Returns:
        ValidationResult
    """
    result = ValidationResult(case_id=case_id)

    unique_labels = np.unique(label_array)
    unique_labels = unique_labels[unique_labels > 0]  # 배경 제외

    if len(unique_labels) == 0:
        result.is_valid = False
        result.errors.append("라벨이 없음 (빈 라벨맵)")
        return result

    # 1. 척추골 순서 검증 (z축 centroid 기반)
    _validate_vertebra_order(label_array, unique_labels, result)

    # 2. 구조물 크기 검증
    voxel_volume_mm3 = float(np.prod(spacing))
    _validate_structure_sizes(label_array, unique_labels, voxel_volume_mm3, result)

    # 3. 디스크 위치 검증
    _validate_disc_positions(label_array, unique_labels, result)

    return result


def _validate_vertebra_order(
    label_array: np.ndarray,
    unique_labels: np.ndarray,
    result: ValidationResult,
):
    """척추골 순서 검증 — z축 centroid 증가 순서 확인."""
    vertebra_centroids = {}

    for lbl in unique_labels:
        lbl_int = int(lbl)
        if SpineLabel.is_vertebra(lbl_int):
            coords = np.argwhere(label_array == lbl_int)
            if len(coords) > 0:
                centroid_z = float(np.mean(coords[:, 0]))  # z축 (첫 번째 축)
                vertebra_centroids[lbl_int] = centroid_z

    if len(vertebra_centroids) < 2:
        return  # 척추골이 1개 이하면 순서 검증 불가

    # 라벨 값 순서대로 정렬 (C1=101, C2=102, ... L5=124, SACRUM=125)
    sorted_labels = sorted(vertebra_centroids.keys())
    sorted_z = [vertebra_centroids[lbl] for lbl in sorted_labels]

    # z축 방향 일관성 확인 (증가 또는 감소 중 하나)
    diffs = [sorted_z[i + 1] - sorted_z[i] for i in range(len(sorted_z) - 1)]

    if not diffs:
        return

    # 대부분 같은 방향이어야 함
    positive = sum(1 for d in diffs if d > 0)
    negative = sum(1 for d in diffs if d < 0)

    if positive > 0 and negative > 0:
        # 순서 역전이 있음
        n_inversions = min(positive, negative)
        if n_inversions > 1:
            result.warnings.append(
                f"척추골 순서 역전 {n_inversions}건 "
                f"(positive: {positive}, negative: {negative})"
            )


def _validate_structure_sizes(
    label_array: np.ndarray,
    unique_labels: np.ndarray,
    voxel_volume_mm3: float,
    result: ValidationResult,
):
    """구조물 크기 범위 검증."""
    # 척추골: 최소 100mm³, 최대 200,000mm³
    # 디스크: 최소 50mm³, 최대 50,000mm³
    size_ranges = {
        "vertebra": (100.0, 200_000.0),
        "disc": (50.0, 50_000.0),
        "soft_tissue": (10.0, 500_000.0),
    }

    for lbl in unique_labels:
        lbl_int = int(lbl)
        n_voxels = int(np.sum(label_array == lbl_int))
        volume_mm3 = n_voxels * voxel_volume_mm3

        if SpineLabel.is_vertebra(lbl_int):
            min_v, max_v = size_ranges["vertebra"]
        elif SpineLabel.is_disc(lbl_int):
            min_v, max_v = size_ranges["disc"]
        elif SpineLabel.is_soft_tissue(lbl_int):
            min_v, max_v = size_ranges["soft_tissue"]
        else:
            continue

        try:
            name = SpineLabel(lbl_int).name
        except ValueError:
            name = f"label_{lbl_int}"

        if volume_mm3 < min_v:
            result.warnings.append(
                f"{name}: 부피 {volume_mm3:.0f}mm³ (최소 {min_v:.0f}mm³ 미만)"
            )
        if volume_mm3 > max_v:
            result.warnings.append(
                f"{name}: 부피 {volume_mm3:.0f}mm³ (최대 {max_v:.0f}mm³ 초과)"
            )


def _validate_disc_positions(
    label_array: np.ndarray,
    unique_labels: np.ndarray,
    result: ValidationResult,
):
    """디스크가 인접 척추골 사이에 위치하는지 검증."""
    # 척추골 centroid 수집
    vertebra_centroids = {}
    for lbl in unique_labels:
        lbl_int = int(lbl)
        if SpineLabel.is_vertebra(lbl_int):
            coords = np.argwhere(label_array == lbl_int)
            if len(coords) > 0:
                vertebra_centroids[lbl_int] = np.mean(coords, axis=0)

    # 디스크 centroid와 인접 척추골 비교
    vertebrae_list = sorted([m for m in SpineLabel if SpineLabel.is_vertebra(m.value)],
                            key=lambda m: m.value)
    discs_list = sorted([m for m in SpineLabel if SpineLabel.is_disc(m.value)],
                        key=lambda m: m.value)

    for i, disc in enumerate(discs_list):
        disc_val = disc.value
        if disc_val not in [int(l) for l in unique_labels]:
            continue

        disc_coords = np.argwhere(label_array == disc_val)
        if len(disc_coords) == 0:
            continue

        disc_centroid = np.mean(disc_coords, axis=0)

        # 인접 척추골 (i+1, i+2 in vertebrae_list; C2=idx1, C3=idx2)
        upper_idx = i + 1
        lower_idx = i + 2

        if upper_idx < len(vertebrae_list) and lower_idx < len(vertebrae_list):
            upper_vert = vertebrae_list[upper_idx].value
            lower_vert = vertebrae_list[lower_idx].value

            # 두 척추골이 모두 존재할 때만 검증
            if upper_vert in vertebra_centroids and lower_vert in vertebra_centroids:
                upper_c = vertebra_centroids[upper_vert]
                lower_c = vertebra_centroids[lower_vert]

                # 디스크 centroid가 두 척추골 사이에 있는지 (z축 기준)
                z_min = min(upper_c[0], lower_c[0])
                z_max = max(upper_c[0], lower_c[0])

                margin = abs(z_max - z_min) * 0.5  # 50% 마진 허용

                if disc_centroid[0] < z_min - margin or disc_centroid[0] > z_max + margin:
                    try:
                        name = SpineLabel(disc_val).name
                    except ValueError:
                        name = f"label_{disc_val}"
                    result.warnings.append(
                        f"{name}: 인접 척추골 범위 밖에 위치 "
                        f"(disc_z={disc_centroid[0]:.1f}, range=[{z_min:.1f}, {z_max:.1f}])"
                    )
