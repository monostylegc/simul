"""nnU-Net 형식 변환 — 전처리된 데이터 → nnU-Net 표준 디렉토리 구조.

출력 구조:
  nnUNet_raw/Dataset200_SpineUnified/
  ├── imagesTr/
  │   ├── SpineUnified_0001_0000.nii.gz  # 정규화 영상
  │   └── SpineUnified_0001_0001.nii.gz  # 도메인 채널
  ├── labelsTr/
  │   └── SpineUnified_0001.nii.gz       # 병합 라벨 (0~50, 51=ignore)
  └── dataset.json
"""

import json
from pathlib import Path
from typing import Optional

import numpy as np

from src.segmentation.labels import (
    SpineLabel,
    STANDARD_TO_NNUNET_SPINE,
    NNUNET_IGNORE_LABEL,
    NNUNET_NUM_CLASSES,
)
from .config import NnunetConfig


def convert_to_nnunet_labels(
    standard_label_array: np.ndarray,
) -> np.ndarray:
    """SpineLabel 표준 라벨 → nnU-Net 연속 정수(0~50) 변환.

    매핑되지 않는 라벨은 ignore(51)로 변환.

    Args:
        standard_label_array: 표준 라벨 배열 (SpineLabel 체계)

    Returns:
        nnU-Net 라벨 배열 (0~50, 51=ignore)
    """
    output = np.full_like(standard_label_array, 0, dtype=np.uint8)

    for std_val, nn_val in STANDARD_TO_NNUNET_SPINE.items():
        mask = (standard_label_array == std_val)
        output[mask] = nn_val

    # ignore 라벨 유지 (입력에 이미 51이 있을 수 있음)
    ignore_mask = (standard_label_array == NNUNET_IGNORE_LABEL)
    output[ignore_mask] = NNUNET_IGNORE_LABEL

    # 매핑 안 된 비-배경 라벨 → ignore
    known_values = set(STANDARD_TO_NNUNET_SPINE.keys()) | {0, NNUNET_IGNORE_LABEL}
    unmapped_mask = ~np.isin(standard_label_array, list(known_values))
    output[unmapped_mask] = NNUNET_IGNORE_LABEL

    return output


def save_nnunet_case(
    case_id: str,
    normalized_image: np.ndarray,
    domain_channel: np.ndarray,
    nnunet_labels: np.ndarray,
    affine: np.ndarray,
    output_dir: Path,
    config: Optional[NnunetConfig] = None,
):
    """단일 케이스를 nnU-Net 형식으로 저장.

    Args:
        case_id: 케이스 식별자 (예: "SpineUnified_0001")
        normalized_image: 정규화 영상 (채널 0)
        domain_channel: 도메인 채널 (채널 1)
        nnunet_labels: nnU-Net 라벨 (0~50, 51=ignore)
        affine: NIfTI affine 행렬
        output_dir: nnU-Net 데이터셋 루트 디렉토리
        config: nnU-Net 설정
    """
    import nibabel as nib

    if config is None:
        config = NnunetConfig()

    images_dir = output_dir / "imagesTr"
    labels_dir = output_dir / "labelsTr"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    # 채널 0: 정규화 영상
    ch0_img = nib.Nifti1Image(normalized_image.astype(np.float32), affine)
    nib.save(ch0_img, str(images_dir / f"{case_id}_0000{config.file_ending}"))

    # 채널 1: 도메인 채널
    ch1_img = nib.Nifti1Image(domain_channel.astype(np.float32), affine)
    nib.save(ch1_img, str(images_dir / f"{case_id}_0001{config.file_ending}"))

    # 라벨
    lbl_img = nib.Nifti1Image(nnunet_labels.astype(np.uint8), affine)
    nib.save(lbl_img, str(labels_dir / f"{case_id}{config.file_ending}"))


def generate_dataset_json(
    output_dir: Path,
    n_cases: int,
    config: Optional[NnunetConfig] = None,
) -> Path:
    """dataset.json 생성.

    Args:
        output_dir: nnU-Net 데이터셋 루트 디렉토리
        n_cases: 총 학습 케이스 수
        config: nnU-Net 설정

    Returns:
        dataset.json 경로
    """
    if config is None:
        config = NnunetConfig()

    # 라벨 이름 생성
    label_names = {"0": "background"}
    for nn_id in range(1, config.num_classes):
        from src.segmentation.labels import NNUNET_SPINE_TO_STANDARD
        std_val = NNUNET_SPINE_TO_STANDARD.get(nn_id)
        if std_val is not None:
            try:
                name = SpineLabel(std_val).name
            except ValueError:
                name = f"class_{nn_id}"
        else:
            name = f"class_{nn_id}"
        label_names[str(nn_id)] = name

    dataset_info = {
        "channel_names": config.channel_names,
        "labels": label_names,
        "numTraining": n_cases,
        "file_ending": config.file_ending,
        "overwrite_image_reader_writer": "SimpleITKIO",
        # ignore 라벨 설정
        "regions_class_order": None,
    }

    json_path = output_dir / "dataset.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dataset_info, f, indent=2, ensure_ascii=False)

    return json_path
