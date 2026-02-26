"""라벨 병합 — GT 척추골 + pseudo-label 디스크/연조직 → 통합 라벨맵.

병합 규칙 (CT 데이터):
  | 영역        | 라벨 소스                   | 비고               |
  |------------|----------------------------|--------------------|
  | 척추골      | Ground-truth (VerSe/CTSpine1K) | 높은 신뢰도        |
  | 디스크      | TotalSpineSeg pseudo-label  | 신뢰도 필터링 후    |
  | 연조직      | TotalSpineSeg pseudo-label  | 선택적             |
  | 불확실 영역 | ignore (라벨 51)            | Loss 계산 제외      |

MRI 데이터(SPIDER):
  - GT 라벨이 이미 척추골+디스크를 포함하므로 병합 불필요
  - 표준 라벨로 변환만 수행
"""

import numpy as np

from backend.segmentation.labels import SpineLabel, NNUNET_IGNORE_LABEL


def merge_ct_labels(
    gt_vertebra: np.ndarray,
    pseudo_full: np.ndarray,
    trust_gt_vertebra: bool = True,
) -> np.ndarray:
    """CT 데이터의 GT 척추골 + pseudo-label 병합.

    Args:
        gt_vertebra: Ground-truth 척추골 라벨 (SpineLabel 체계)
        pseudo_full: TotalSpineSeg pseudo-label (필터링 완료, SpineLabel 체계)
        trust_gt_vertebra: True면 GT 척추골을 항상 우선

    Returns:
        병합된 라벨 배열 (SpineLabel 체계, 불확실=51)
    """
    merged = np.zeros_like(gt_vertebra, dtype=np.int32)

    # 1단계: pseudo-label에서 디스크/연조직 복사
    for lbl_val in np.unique(pseudo_full):
        lbl_int = int(lbl_val)
        if lbl_int == 0:
            continue
        if lbl_int == NNUNET_IGNORE_LABEL:
            # ignore 영역 유지
            merged[pseudo_full == lbl_int] = NNUNET_IGNORE_LABEL
            continue
        if SpineLabel.is_disc(lbl_int) or SpineLabel.is_soft_tissue(lbl_int):
            merged[pseudo_full == lbl_int] = lbl_int

    # 2단계: GT 척추골 덮어쓰기 (최우선)
    if trust_gt_vertebra:
        for lbl_val in np.unique(gt_vertebra):
            lbl_int = int(lbl_val)
            if lbl_int == 0:
                continue
            if SpineLabel.is_vertebra(lbl_int):
                merged[gt_vertebra == lbl_int] = lbl_int

    # 3단계: GT 척추골 영역과 겹치는 디스크/연조직 → ignore
    # (GT 척추골이 더 정확하므로, 겹치면 pseudo-label을 무시)
    gt_bone_mask = np.zeros_like(gt_vertebra, dtype=bool)
    for lbl_val in np.unique(gt_vertebra):
        lbl_int = int(lbl_val)
        if SpineLabel.is_vertebra(lbl_int):
            gt_bone_mask |= (gt_vertebra == lbl_int)

    # 뼈 영역에서 디스크/연조직이 할당된 부분 → 뼈로 복원
    overlap = gt_bone_mask & (merged != gt_vertebra) & (gt_vertebra > 0)
    merged[overlap] = gt_vertebra[overlap]

    return merged


def convert_mri_labels(
    spider_labels: np.ndarray,
    source_mapping: dict[int, int],
) -> np.ndarray:
    """SPIDER MRI 라벨을 표준 체계로 변환.

    Args:
        spider_labels: SPIDER 원본 라벨
        source_mapping: SPIDER 라벨 → SpineLabel 매핑

    Returns:
        표준 라벨 배열
    """
    from backend.segmentation.labels import convert_to_standard
    return convert_to_standard(spider_labels, source_mapping)
