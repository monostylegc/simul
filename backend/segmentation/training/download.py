"""데이터셋 다운로드/검증 — 수동 다운로드 후 경로 지정 + 자동 검증.

지원 데이터셋:
  - VerSe2020: CT 척추 (300케이스) - 직접 다운로드 필요
  - CTSpine1K: CT 척추 (1005케이스) - 직접 다운로드 필요
  - SPIDER: MRI 척추+디스크 (218케이스) - 직접 다운로드 필요
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import DatasetPaths


@dataclass
class DatasetInfo:
    """데이터셋 검증 결과."""

    name: str
    path: Path
    exists: bool
    n_images: int = 0
    n_labels: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @property
    def is_valid(self) -> bool:
        return self.exists and self.n_images > 0 and len(self.errors) == 0


def validate_verse2020(data_dir: Path) -> DatasetInfo:
    """VerSe2020 데이터셋 검증.

    예상 구조:
      data_dir/
        rawdata/ or dataset-verse20training/
          sub-verse*/
            sub-verse*_ct.nii.gz         (CT 영상)
        derivatives/
          sub-verse*/
            sub-verse*_seg-vert_msk.nii.gz  (척추 라벨)
    """
    info = DatasetInfo(name="VerSe2020", path=data_dir, exists=data_dir.exists())
    if not data_dir.exists():
        info.errors.append(f"디렉토리 없음: {data_dir}")
        return info

    # CT 영상 찾기
    images = list(data_dir.rglob("*_ct.nii.gz"))
    labels = list(data_dir.rglob("*_seg-vert_msk.nii.gz"))

    info.n_images = len(images)
    info.n_labels = len(labels)

    if info.n_images == 0:
        info.errors.append("CT 영상 파일을 찾을 수 없음 (*_ct.nii.gz)")
    if info.n_labels == 0:
        info.errors.append("라벨 파일을 찾을 수 없음 (*_seg-vert_msk.nii.gz)")
    if info.n_images > 0 and info.n_labels > 0 and abs(info.n_images - info.n_labels) > 10:
        info.errors.append(f"영상({info.n_images})과 라벨({info.n_labels}) 수 불일치")

    return info


def validate_ctspine1k(data_dir: Path) -> DatasetInfo:
    """CTSpine1K 데이터셋 검증.

    예상 구조:
      data_dir/
        image/ or trainset/
          *.nii.gz               (CT 영상)
        mask/ or labelset/
          *.nii.gz               (척추 라벨)
    """
    info = DatasetInfo(name="CTSpine1K", path=data_dir, exists=data_dir.exists())
    if not data_dir.exists():
        info.errors.append(f"디렉토리 없음: {data_dir}")
        return info

    # 유연한 구조 탐색
    images = []
    labels = []

    for img_dir_name in ["image", "trainset", "Image"]:
        img_dir = data_dir / img_dir_name
        if img_dir.exists():
            images.extend(img_dir.rglob("*.nii.gz"))
    for lbl_dir_name in ["mask", "labelset", "Mask"]:
        lbl_dir = data_dir / lbl_dir_name
        if lbl_dir.exists():
            labels.extend(lbl_dir.rglob("*.nii.gz"))

    # 영상/라벨이 없으면 rglob으로 전체 탐색
    if not images:
        images = list(data_dir.rglob("*.nii.gz"))
        # 라벨 파일 제외 (mask, seg, label 키워드 포함)
        images = [f for f in images if not any(k in f.name.lower() for k in ["mask", "seg", "label"])]

    info.n_images = len(images)
    info.n_labels = len(labels)

    if info.n_images == 0:
        info.errors.append("CT 영상 파일을 찾을 수 없음")
    if info.n_labels == 0:
        info.errors.append("라벨 파일을 찾을 수 없음")

    return info


def validate_spider(data_dir: Path) -> DatasetInfo:
    """SPIDER 데이터셋 검증 (MRI).

    예상 구조:
      data_dir/
        images/
          *.nii.gz               (MRI 영상)
        masks/
          *.nii.gz               (척추+디스크 라벨)
    """
    info = DatasetInfo(name="SPIDER", path=data_dir, exists=data_dir.exists())
    if not data_dir.exists():
        info.errors.append(f"디렉토리 없음: {data_dir}")
        return info

    # 유연한 구조 탐색
    images = []
    labels = []

    for img_dir_name in ["images", "image", "Image"]:
        img_dir = data_dir / img_dir_name
        if img_dir.exists():
            images.extend(img_dir.rglob("*.nii.gz"))
    for lbl_dir_name in ["masks", "mask", "Mask"]:
        lbl_dir = data_dir / lbl_dir_name
        if lbl_dir.exists():
            labels.extend(lbl_dir.rglob("*.nii.gz"))

    info.n_images = len(images)
    info.n_labels = len(labels)

    if info.n_images == 0:
        info.errors.append("MRI 영상 파일을 찾을 수 없음")
    if info.n_labels == 0:
        info.errors.append("라벨 파일을 찾을 수 없음")

    return info


def validate_all(paths: Optional[DatasetPaths] = None) -> list[DatasetInfo]:
    """모든 데이터셋 검증.

    Args:
        paths: 데이터셋 경로 (None이면 기본값)

    Returns:
        DatasetInfo 목록
    """
    if paths is None:
        paths = DatasetPaths()

    return [
        validate_verse2020(paths.verse2020),
        validate_ctspine1k(paths.ctspine1k),
        validate_spider(paths.spider),
    ]


def print_validation_report(infos: list[DatasetInfo]):
    """검증 결과 출력."""
    print("\n=== 데이터셋 검증 결과 ===\n")
    total_images = 0
    total_labels = 0

    for info in infos:
        status = "OK" if info.is_valid else "FAIL"
        print(f"[{status}] {info.name}")
        print(f"     경로: {info.path}")
        print(f"     영상: {info.n_images}, 라벨: {info.n_labels}")
        if info.errors:
            for err in info.errors:
                print(f"     ! {err}")
        total_images += info.n_images
        total_labels += info.n_labels
        print()

    print(f"총 영상: {total_images}, 총 라벨: {total_labels}")
    valid_count = sum(1 for i in infos if i.is_valid)
    print(f"유효 데이터셋: {valid_count}/{len(infos)}")
