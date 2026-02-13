"""통합 척추 라벨 체계.

TotalSegmentator(CT), TotalSpineSeg(MRI) 등 다양한 세그멘테이션 도구의
라벨을 하나의 표준 체계로 통합한다.
"""

from enum import IntEnum
from typing import Literal


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
    # 연조직
    200: SpineLabel.SPINAL_CORD,
    201: SpineLabel.SPINAL_CANAL,
}


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
