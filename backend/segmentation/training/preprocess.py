"""전처리 — CT HU 정규화, MRI z-score 정규화, 도메인 채널 생성."""

import numpy as np

from .config import PreprocessConfig


def normalize_ct(
    data: np.ndarray,
    config: PreprocessConfig | None = None,
) -> np.ndarray:
    """CT HU 클리핑 → 0-1 선형 정규화.

    Args:
        data: CT 볼륨 (HU 단위)
        config: 전처리 설정

    Returns:
        0-1 정규화된 배열
    """
    if config is None:
        config = PreprocessConfig()

    clipped = np.clip(data.astype(np.float32), config.ct_hu_min, config.ct_hu_max)
    normalized = (clipped - config.ct_hu_min) / (config.ct_hu_max - config.ct_hu_min)
    return normalized


def normalize_mri(
    data: np.ndarray,
    config: PreprocessConfig | None = None,
) -> np.ndarray:
    """MRI z-score 정규화 → 0-1 범위 클리핑.

    배경(0)을 제외하고 z-score 계산 후 ±3σ 클리핑.

    Args:
        data: MRI 볼륨
        config: 전처리 설정

    Returns:
        0-1 정규화된 배열
    """
    if config is None:
        config = PreprocessConfig()

    result = np.zeros_like(data, dtype=np.float32)
    mask = data > 0  # 배경 제외

    if mask.any():
        mean_val = float(np.mean(data[mask]))
        std_val = float(np.std(data[mask]))

        if std_val > 0:
            result = (data.astype(np.float32) - mean_val) / std_val
        else:
            result = np.zeros_like(data, dtype=np.float32)

        clip = config.mri_zscore_clip
        result = np.clip(result, -clip, clip)
        result = (result + clip) / (2 * clip)

    return result


def create_domain_channel(
    data: np.ndarray,
    modality: str,
) -> np.ndarray:
    """도메인 채널 생성 (CT=1.0, MRI=0.0).

    Args:
        data: 참조 볼륨 (형상 맞추기용)
        modality: "CT" 또는 "MRI"

    Returns:
        도메인 채널 배열 (동일 형상, float32)
    """
    domain_val = 1.0 if modality.upper() == "CT" else 0.0
    return np.full(data.shape, domain_val, dtype=np.float32)
