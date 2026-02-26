"""통합 척추 라벨 체계.

TotalSegmentator(CT), TotalSpineSeg(MRI) 등 다양한 세그멘테이션 도구의
라벨을 하나의 표준 체계로 통합한다.
"""

from enum import IntEnum
from typing import Literal

import numpy as np


class SpineLabel(IntEnum):
    """척추 구조 통합 라벨.

    - 100번대: 척추골 (C1~SACRUM)
    - 200번대: 디스크 (C2C3~L5S1)
    - 300번대: 연조직 (척수, 척추관)
    """

    BACKGROUND = 0

    # 척추골 (101~125)
    C1 = 101
    C2 = 102
    C3 = 103
    C4 = 104
    C5 = 105
    C6 = 106
    C7 = 107
    T1 = 108
    T2 = 109
    T3 = 110
    T4 = 111
    T5 = 112
    T6 = 113
    T7 = 114
    T8 = 115
    T9 = 116
    T10 = 117
    T11 = 118
    T12 = 119
    L1 = 120
    L2 = 121
    L3 = 122
    L4 = 123
    L5 = 124
    SACRUM = 125

    # 디스크 (201~223)
    C2C3 = 201
    C3C4 = 202
    C4C5 = 203
    C5C6 = 204
    C6C7 = 205
    C7T1 = 206
    T1T2 = 207
    T2T3 = 208
    T3T4 = 209
    T4T5 = 210
    T5T6 = 211
    T6T7 = 212
    T7T8 = 213
    T8T9 = 214
    T9T10 = 215
    T10T11 = 216
    T11T12 = 217
    T12L1 = 218
    L1L2 = 219
    L2L3 = 220
    L3L4 = 221
    L4L5 = 222
    L5S1 = 223

    # 연조직 (301~)
    SPINAL_CORD = 301
    SPINAL_CANAL = 302

    @classmethod
    def is_vertebra(cls, label: int) -> bool:
        """척추골 라벨 여부."""
        return 101 <= label <= 125

    @classmethod
    def is_disc(cls, label: int) -> bool:
        """디스크 라벨 여부."""
        return 201 <= label <= 223

    @classmethod
    def is_soft_tissue(cls, label: int) -> bool:
        """연조직 라벨 여부."""
        return 301 <= label <= 399

    @classmethod
    def to_material_type(cls, label: int) -> int:
        """라벨 → 재료 타입 변환.

        Returns:
            0=empty, 1=bone, 2=disc, 3=soft tissue
        """
        if label == 0:
            return 0
        if cls.is_vertebra(label):
            return 1
        if cls.is_disc(label):
            return 2
        if cls.is_soft_tissue(label):
            return 3
        return 0

    @classmethod
    def vertebra_names(cls) -> list[str]:
        """모든 척추골 이름 목록."""
        return [m.name for m in cls if cls.is_vertebra(m.value)]

    @classmethod
    def disc_names(cls) -> list[str]:
        """모든 디스크 이름 목록."""
        return [m.name for m in cls if cls.is_disc(m.value)]


# TotalSegmentator 라벨 → SpineLabel 매핑
# TotalSegmentator v2: vertebrae_C1 ~ vertebrae_L5 (ID 26~50), sacrum(25)
TOTALSEG_TO_STANDARD: dict[int, int] = {
    25: SpineLabel.SACRUM,
    26: SpineLabel.C1,
    27: SpineLabel.C2,
    28: SpineLabel.C3,
    29: SpineLabel.C4,
    30: SpineLabel.C5,
    31: SpineLabel.C6,
    32: SpineLabel.C7,
    33: SpineLabel.T1,
    34: SpineLabel.T2,
    35: SpineLabel.T3,
    36: SpineLabel.T4,
    37: SpineLabel.T5,
    38: SpineLabel.T6,
    39: SpineLabel.T7,
    40: SpineLabel.T8,
    41: SpineLabel.T9,
    42: SpineLabel.T10,
    43: SpineLabel.T11,
    44: SpineLabel.T12,
    45: SpineLabel.L1,
    46: SpineLabel.L2,
    47: SpineLabel.L3,
    48: SpineLabel.L4,
    49: SpineLabel.L5,
}

# TotalSpineSeg 라벨 → SpineLabel 매핑
# C1-S: 11~50, 디스크: 63~100
TOTALSPINESEG_TO_STANDARD: dict[int, int] = {
    # 척추골
    11: SpineLabel.C1,
    12: SpineLabel.C2,
    13: SpineLabel.C3,
    14: SpineLabel.C4,
    15: SpineLabel.C5,
    16: SpineLabel.C6,
    17: SpineLabel.C7,
    18: SpineLabel.T1,
    19: SpineLabel.T2,
    20: SpineLabel.T3,
    21: SpineLabel.T4,
    22: SpineLabel.T5,
    23: SpineLabel.T6,
    24: SpineLabel.T7,
    25: SpineLabel.T8,
    26: SpineLabel.T9,
    27: SpineLabel.T10,
    28: SpineLabel.T11,
    29: SpineLabel.T12,
    30: SpineLabel.L1,
    31: SpineLabel.L2,
    32: SpineLabel.L3,
    33: SpineLabel.L4,
    34: SpineLabel.L5,
    # 천골 세부 분절 (일부 모델 버전에서 출력)
    41: SpineLabel.SACRUM,
    42: SpineLabel.SACRUM,
    43: SpineLabel.SACRUM,
    44: SpineLabel.SACRUM,
    45: SpineLabel.SACRUM,
    46: SpineLabel.SACRUM,
    47: SpineLabel.SACRUM,
    48: SpineLabel.SACRUM,
    49: SpineLabel.SACRUM,
    50: SpineLabel.SACRUM,
    # 디스크
    63: SpineLabel.C2C3,
    64: SpineLabel.C3C4,
    65: SpineLabel.C4C5,
    66: SpineLabel.C5C6,
    67: SpineLabel.C6C7,
    68: SpineLabel.C7T1,
    69: SpineLabel.T1T2,
    70: SpineLabel.T2T3,
    71: SpineLabel.T3T4,
    72: SpineLabel.T4T5,
    73: SpineLabel.T5T6,
    74: SpineLabel.T6T7,
    75: SpineLabel.T7T8,
    76: SpineLabel.T8T9,
    77: SpineLabel.T9T10,
    78: SpineLabel.T10T11,
    79: SpineLabel.T11T12,
    80: SpineLabel.T12L1,
    81: SpineLabel.L1L2,
    82: SpineLabel.L2L3,
    83: SpineLabel.L3L4,
    84: SpineLabel.L4L5,
    85: SpineLabel.L5S1,
    # 천골 디스크 (일부 모델 버전에서 출력)
    91: SpineLabel.L5S1,
    92: SpineLabel.L5S1,
    93: SpineLabel.L5S1,
    94: SpineLabel.L5S1,
    95: SpineLabel.L5S1,
    # 연조직
    100: SpineLabel.SPINAL_CANAL,
    200: SpineLabel.SPINAL_CORD,
    201: SpineLabel.SPINAL_CANAL,
}

# TotalSpineSeg step1_levels 레벨 값 → SpineLabel 매핑
# step1_levels는 1-based 연속 정수: C1=1, C2=2, ..., C7=7, T1=8, ..., T12=19, L1=20, ..., L5=24, SACRUM=25
LEVEL_TO_VERTEBRA: dict[int, int] = {
    1: SpineLabel.C1, 2: SpineLabel.C2, 3: SpineLabel.C3,
    4: SpineLabel.C4, 5: SpineLabel.C5, 6: SpineLabel.C6, 7: SpineLabel.C7,
    8: SpineLabel.T1, 9: SpineLabel.T2, 10: SpineLabel.T3,
    11: SpineLabel.T4, 12: SpineLabel.T5, 13: SpineLabel.T6,
    14: SpineLabel.T7, 15: SpineLabel.T8, 16: SpineLabel.T9,
    17: SpineLabel.T10, 18: SpineLabel.T11, 19: SpineLabel.T12,
    20: SpineLabel.L1, 21: SpineLabel.L2, 22: SpineLabel.L3,
    23: SpineLabel.L4, 24: SpineLabel.L5,
    25: SpineLabel.SACRUM,
}


def build_dynamic_totalspineseg_mapping(
    step1_levels_data: np.ndarray,
    step2_data: np.ndarray,
) -> dict[int, int]:
    """TotalSpineSeg step1_levels와 step2_output을 이용한 동적 라벨 매핑 생성.

    TotalSpineSeg는 step2에서 척추골 형태는 정확히 분할하지만,
    어떤 레벨인지(L1? L4?) 식별이 부정확할 수 있다.
    step1_levels에는 각 레벨의 정확한 위치 마커(1 voxel)가 있으므로,
    이를 이용하여 step2 raw 라벨을 올바른 SpineLabel로 매핑한다.

    Args:
        step1_levels_data: step1_levels NIfTI 데이터 (레벨 마커, 각 1 voxel)
        step2_data: step2_output NIfTI 데이터 (세그멘테이션 결과)

    Returns:
        step2 raw label → SpineLabel 매핑 딕셔너리
    """
    mapping: dict[int, int] = {}

    # 1. step1_levels에서 레벨→Z위치 매핑 추출
    level_markers: dict[int, float] = {}
    for level_val in np.unique(step1_levels_data):
        level_val = int(level_val)
        if level_val == 0:
            continue
        coords = np.argwhere(step1_levels_data == level_val)
        level_markers[level_val] = float(coords.mean(axis=0)[2])  # Z centroid

    if not level_markers:
        return {}

    # 2. step2에서 척추골 raw 라벨의 Z centroid 계산 (11~50 범위)
    vert_raws: list[tuple[int, float]] = []
    for raw_lbl in np.unique(step2_data):
        raw_lbl = int(raw_lbl)
        if raw_lbl == 0:
            continue
        if 11 <= raw_lbl <= 50:
            coords = np.argwhere(step2_data == raw_lbl)
            z = float(coords.mean(axis=0)[2])
            vert_raws.append((raw_lbl, z))

    # 3. Z 기준 내림차순 정렬 (상부 → 하부, 높은 Z = 상부)
    vert_raws.sort(key=lambda x: -x[1])
    levels_sorted = sorted(level_markers.items(), key=lambda x: -x[1])

    # 4. 순서 기반 1:1 매칭 (상부부터 순서대로)
    for i, (raw_lbl, _raw_z) in enumerate(vert_raws):
        if i < len(levels_sorted):
            level_val, _ = levels_sorted[i]
            spine_label = LEVEL_TO_VERTEBRA.get(level_val)
            if spine_label is not None:
                mapping[raw_lbl] = spine_label
            else:
                mapping[raw_lbl] = SpineLabel.SACRUM
        else:
            # 레벨 마커보다 더 많은 척추골 → 하부 천골로 매핑
            mapping[raw_lbl] = SpineLabel.SACRUM

    # 5. 디스크 매핑: 순서 기반 매칭
    # 디스크와 인접 레벨 간극을 각각 Z 내림차순 정렬 후 1:1 매칭
    # (위치 범위 검사 대신 순서 사용 → 경계값 오차에 강건)
    disc_raws: list[tuple[int, float]] = []
    for raw_lbl in np.unique(step2_data):
        raw_lbl = int(raw_lbl)
        if raw_lbl == 0:
            continue
        # 디스크 범위: 63~99 (100은 SPINAL_CANAL이므로 제외)
        if 63 <= raw_lbl <= 99:
            coords = np.argwhere(step2_data == raw_lbl)
            z = float(coords.mean(axis=0)[2])
            disc_raws.append((raw_lbl, z))

    disc_raws.sort(key=lambda x: -x[1])  # Z 내림차순 (상부 → 하부)

    # 인접 레벨 간극 목록 생성 (이미 내림차순)
    # 디스크 SpineLabel = 199 + upper_level (예: L1L2 = 199 + 20 = 219)
    gaps: list[int | None] = []
    for j in range(len(levels_sorted) - 1):
        upper_level, _ = levels_sorted[j]
        disc_spine_val = 199 + upper_level
        try:
            SpineLabel(disc_spine_val)  # 유효성 검증
            gaps.append(disc_spine_val)
        except ValueError:
            gaps.append(None)

    # 순서 기반 1:1 매칭 (상부 디스크 → 상부 간극)
    for i, (disc_raw, _disc_z) in enumerate(disc_raws):
        if i < len(gaps) and gaps[i] is not None:
            mapping[disc_raw] = gaps[i]

    # 6. 연조직은 정적 매핑 유지
    _soft_tissue_static = {
        100: SpineLabel.SPINAL_CANAL,
        200: SpineLabel.SPINAL_CORD,
        201: SpineLabel.SPINAL_CANAL,
    }
    for raw_lbl in np.unique(step2_data):
        raw_lbl = int(raw_lbl)
        if raw_lbl in _soft_tissue_static and raw_lbl not in mapping:
            mapping[raw_lbl] = _soft_tissue_static[raw_lbl]

    return mapping


# nnU-Net SpineUnified 라벨 → SpineLabel 매핑
# 연속 정수 0~50: 0=background, 1~24=척추골, 25~47=디스크, 48~49=연조직, 50(reserved)
NNUNET_SPINE_TO_STANDARD: dict[int, int] = {
    0: SpineLabel.BACKGROUND,
    # 척추골 (1~24)
    1: SpineLabel.C1,
    2: SpineLabel.C2,
    3: SpineLabel.C3,
    4: SpineLabel.C4,
    5: SpineLabel.C5,
    6: SpineLabel.C6,
    7: SpineLabel.C7,
    8: SpineLabel.T1,
    9: SpineLabel.T2,
    10: SpineLabel.T3,
    11: SpineLabel.T4,
    12: SpineLabel.T5,
    13: SpineLabel.T6,
    14: SpineLabel.T7,
    15: SpineLabel.T8,
    16: SpineLabel.T9,
    17: SpineLabel.T10,
    18: SpineLabel.T11,
    19: SpineLabel.T12,
    20: SpineLabel.L1,
    21: SpineLabel.L2,
    22: SpineLabel.L3,
    23: SpineLabel.L4,
    24: SpineLabel.L5,
    25: SpineLabel.SACRUM,
    # 디스크 (26~48)
    26: SpineLabel.C2C3,
    27: SpineLabel.C3C4,
    28: SpineLabel.C4C5,
    29: SpineLabel.C5C6,
    30: SpineLabel.C6C7,
    31: SpineLabel.C7T1,
    32: SpineLabel.T1T2,
    33: SpineLabel.T2T3,
    34: SpineLabel.T3T4,
    35: SpineLabel.T4T5,
    36: SpineLabel.T5T6,
    37: SpineLabel.T6T7,
    38: SpineLabel.T7T8,
    39: SpineLabel.T8T9,
    40: SpineLabel.T9T10,
    41: SpineLabel.T10T11,
    42: SpineLabel.T11T12,
    43: SpineLabel.T12L1,
    44: SpineLabel.L1L2,
    45: SpineLabel.L2L3,
    46: SpineLabel.L3L4,
    47: SpineLabel.L4L5,
    48: SpineLabel.L5S1,
    # 연조직 (49~50)
    49: SpineLabel.SPINAL_CORD,
    50: SpineLabel.SPINAL_CANAL,
}

# 역매핑: SpineLabel → nnU-Net 연속 정수 (학습 데이터 변환용)
STANDARD_TO_NNUNET_SPINE: dict[int, int] = {
    v: k for k, v in NNUNET_SPINE_TO_STANDARD.items()
}

# nnU-Net ignore 라벨 (Loss 계산 제외)
NNUNET_IGNORE_LABEL = 51

# nnU-Net 클래스 수 (background 포함, ignore 제외)
NNUNET_NUM_CLASSES = 51  # 0~50


def convert_to_standard(
    label_array,
    source_mapping: dict[int, int],
) -> "numpy.ndarray":
    """라벨 배열을 표준 라벨 체계로 변환.

    Args:
        label_array: 원본 라벨 배열 (numpy ndarray)
        source_mapping: 원본 라벨 → SpineLabel 매핑

    Returns:
        표준 라벨 배열
    """
    import numpy as np

    output = np.zeros_like(label_array, dtype=np.int32)
    for src_label, std_label in source_mapping.items():
        output[label_array == src_label] = std_label
    return output


# VerSe2020 원본 라벨 → SpineLabel 매핑
# VerSe2020: 1~24=C1~L5, 25=SACRUM (일부 버전은 26~28=S2~)
VERSE_TO_STANDARD: dict[int, int] = {
    1: SpineLabel.C1,
    2: SpineLabel.C2,
    3: SpineLabel.C3,
    4: SpineLabel.C4,
    5: SpineLabel.C5,
    6: SpineLabel.C6,
    7: SpineLabel.C7,
    8: SpineLabel.T1,
    9: SpineLabel.T2,
    10: SpineLabel.T3,
    11: SpineLabel.T4,
    12: SpineLabel.T5,
    13: SpineLabel.T6,
    14: SpineLabel.T7,
    15: SpineLabel.T8,
    16: SpineLabel.T9,
    17: SpineLabel.T10,
    18: SpineLabel.T11,
    19: SpineLabel.T12,
    20: SpineLabel.L1,
    21: SpineLabel.L2,
    22: SpineLabel.L3,
    23: SpineLabel.L4,
    24: SpineLabel.L5,
    25: SpineLabel.SACRUM,
    # 26~28: S2~S4 (일부 케이스만) → 모두 SACRUM으로 매핑
    26: SpineLabel.SACRUM,
    27: SpineLabel.SACRUM,
    28: SpineLabel.SACRUM,
}

# CTSpine1K 원본 라벨 → SpineLabel 매핑
# CTSpine1K: VerSe2020과 동일 체계 (1~25: C1~SACRUM)
CTSPINE1K_TO_STANDARD: dict[int, int] = {
    1: SpineLabel.C1,
    2: SpineLabel.C2,
    3: SpineLabel.C3,
    4: SpineLabel.C4,
    5: SpineLabel.C5,
    6: SpineLabel.C6,
    7: SpineLabel.C7,
    8: SpineLabel.T1,
    9: SpineLabel.T2,
    10: SpineLabel.T3,
    11: SpineLabel.T4,
    12: SpineLabel.T5,
    13: SpineLabel.T6,
    14: SpineLabel.T7,
    15: SpineLabel.T8,
    16: SpineLabel.T9,
    17: SpineLabel.T10,
    18: SpineLabel.T11,
    19: SpineLabel.T12,
    20: SpineLabel.L1,
    21: SpineLabel.L2,
    22: SpineLabel.L3,
    23: SpineLabel.L4,
    24: SpineLabel.L5,
    25: SpineLabel.SACRUM,
}


def build_spider_mapping(
    n_vertebrae: int,
    bottom_vertebra: str = "L5",
) -> dict[int, int]:
    """SPIDER 데이터셋 동적 라벨 매핑 생성.

    SPIDER는 상대적 순번(최하위=1)이므로 각 케이스별로 매핑을 생성해야 한다.
    척추 라벨: 1~N (1=최하위 척추골, N=최상위 척추골)
    디스크 라벨: 201~(200+N-1) (201=최하위 디스크)
    척추관 라벨: 100=SPINAL_CANAL

    Args:
        n_vertebrae: 해당 케이스의 척추골 수
        bottom_vertebra: 최하위 척추골 이름 (기본 "L5")

    Returns:
        SPIDER 라벨 → SpineLabel 매핑
    """
    # 모든 척추골 목록 (C1부터 SACRUM까지)
    all_vertebrae = [m for m in SpineLabel if SpineLabel.is_vertebra(m.value)]
    all_vertebrae.sort(key=lambda m: m.value)  # C1, C2, ..., SACRUM

    # 최하위 척추골 인덱스 찾기
    bottom_label = SpineLabel[bottom_vertebra.upper()]
    bottom_idx = next(i for i, m in enumerate(all_vertebrae) if m == bottom_label)

    mapping: dict[int, int] = {}

    # 척추골 매핑: SPIDER 1=bottom, 2=bottom-1, ...
    for spider_id in range(1, n_vertebrae + 1):
        vert_idx = bottom_idx - (spider_id - 1)
        if 0 <= vert_idx < len(all_vertebrae):
            mapping[spider_id] = all_vertebrae[vert_idx].value

    # 디스크 매핑: SPIDER 201=최하위 디스크 (bottom과 bottom+1 사이)
    all_discs = [m for m in SpineLabel if SpineLabel.is_disc(m.value)]
    all_discs.sort(key=lambda m: m.value)  # C2C3, C3C4, ..., L5S1

    # 디스크 인덱스: L4L5 디스크의 인덱스를 기준으로 계산
    # bottom이 L5이면 최하위 디스크는 L5S1(=222번째 디스크, all_discs 인덱스 22)
    # bottom이 L5이면 가장 아래 디스크가 L5S1
    # bottom_vertebra의 아래 디스크 = bottom과 그 아래(sacrum) 사이
    # 디스크 이름 체계: C2C3(idx0)는 C2(idx1)와 C3(idx2) 사이
    # 즉 disc[i]는 vertebra[i+1]과 vertebra[i+2] 사이
    # bottom_idx 척추골 아래 디스크 = disc[bottom_idx - 1]
    bottom_disc_idx = bottom_idx - 1  # L5→disc_idx=22(L5S1)이면 정확

    for spider_disc_id in range(201, 201 + n_vertebrae - 1):
        disc_offset = spider_disc_id - 201
        disc_idx = bottom_disc_idx - disc_offset
        if 0 <= disc_idx < len(all_discs):
            mapping[spider_disc_id] = all_discs[disc_idx].value

    # 척추관 매핑
    mapping[100] = SpineLabel.SPINAL_CANAL

    return mapping
