"""데이터셋 케이스 탐색 — VerSe2020/CTSpine1K/SPIDER 파일 수집.

각 데이터셋의 디렉토리 구조를 탐색하여 이미지-라벨 쌍 목록을 생성한다.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import DatasetPaths


@dataclass
class CaseInfo:
    """단일 학습 케이스 정보."""

    case_id: str
    image_path: Path
    label_path: Path
    dataset: str  # "verse2020", "ctspine1k", "spider"
    modality: str  # "CT" 또는 "MRI"


def crawl_verse2020(data_dir: Path) -> list[CaseInfo]:
    """VerSe2020 케이스 탐색.

    파일 패턴:
      *_ct.nii.gz (CT 영상)
      *_seg-vert_msk.nii.gz (척추 라벨)

    Args:
        data_dir: VerSe2020 루트 디렉토리

    Returns:
        CaseInfo 목록
    """
    if not data_dir.exists():
        return []

    cases = []

    # CT 영상 수집
    images = {f.name.replace("_ct.nii.gz", ""): f for f in data_dir.rglob("*_ct.nii.gz")}

    # 라벨 매칭
    for label_path in data_dir.rglob("*_seg-vert_msk.nii.gz"):
        # sub-verse004_seg-vert_msk.nii.gz → sub-verse004
        subject = label_path.name.replace("_seg-vert_msk.nii.gz", "")
        if subject in images:
            cases.append(CaseInfo(
                case_id=f"verse_{subject}",
                image_path=images[subject],
                label_path=label_path,
                dataset="verse2020",
                modality="CT",
            ))

    return sorted(cases, key=lambda c: c.case_id)


def crawl_ctspine1k(data_dir: Path) -> list[CaseInfo]:
    """CTSpine1K 케이스 탐색.

    파일 패턴:
      image/*.nii.gz 또는 trainset/*.nii.gz (CT 영상)
      mask/*.nii.gz 또는 labelset/*.nii.gz (척추 라벨)

    Args:
        data_dir: CTSpine1K 루트 디렉토리

    Returns:
        CaseInfo 목록
    """
    if not data_dir.exists():
        return []

    # 영상 디렉토리 탐색
    images: dict[str, Path] = {}
    for dir_name in ["image", "trainset", "Image"]:
        img_dir = data_dir / dir_name
        if img_dir.exists():
            for f in img_dir.rglob("*.nii.gz"):
                stem = f.name.replace(".nii.gz", "")
                images[stem] = f

    # 라벨 디렉토리 탐색
    labels: dict[str, Path] = {}
    for dir_name in ["mask", "labelset", "Mask"]:
        lbl_dir = data_dir / dir_name
        if lbl_dir.exists():
            for f in lbl_dir.rglob("*.nii.gz"):
                stem = f.name.replace(".nii.gz", "")
                labels[stem] = f

    # 매칭 (동일 파일명)
    cases = []
    for stem, img_path in images.items():
        if stem in labels:
            cases.append(CaseInfo(
                case_id=f"ctspine_{stem}",
                image_path=img_path,
                label_path=labels[stem],
                dataset="ctspine1k",
                modality="CT",
            ))

    return sorted(cases, key=lambda c: c.case_id)


def crawl_spider(data_dir: Path) -> list[CaseInfo]:
    """SPIDER 케이스 탐색.

    파일 패턴:
      images/*.nii.gz (MRI 영상)
      masks/*.nii.gz (척추+디스크 라벨)

    Args:
        data_dir: SPIDER 루트 디렉토리

    Returns:
        CaseInfo 목록
    """
    if not data_dir.exists():
        return []

    # 영상 디렉토리 탐색
    images: dict[str, Path] = {}
    for dir_name in ["images", "image", "Image"]:
        img_dir = data_dir / dir_name
        if img_dir.exists():
            for f in img_dir.rglob("*.nii.gz"):
                stem = f.name.replace(".nii.gz", "")
                images[stem] = f

    # 라벨 디렉토리 탐색
    labels: dict[str, Path] = {}
    for dir_name in ["masks", "mask", "Mask"]:
        lbl_dir = data_dir / dir_name
        if lbl_dir.exists():
            for f in lbl_dir.rglob("*.nii.gz"):
                stem = f.name.replace(".nii.gz", "")
                labels[stem] = f

    # 매칭
    cases = []
    for stem, img_path in images.items():
        if stem in labels:
            cases.append(CaseInfo(
                case_id=f"spider_{stem}",
                image_path=img_path,
                label_path=labels[stem],
                dataset="spider",
                modality="MRI",
            ))

    return sorted(cases, key=lambda c: c.case_id)


def crawl_all(paths: Optional[DatasetPaths] = None) -> list[CaseInfo]:
    """모든 데이터셋 케이스를 통합 탐색.

    Args:
        paths: 데이터셋 경로 설정 (None이면 기본값)

    Returns:
        전체 CaseInfo 목록
    """
    if paths is None:
        paths = DatasetPaths()

    all_cases: list[CaseInfo] = []
    all_cases.extend(crawl_verse2020(paths.verse2020))
    all_cases.extend(crawl_ctspine1k(paths.ctspine1k))
    all_cases.extend(crawl_spider(paths.spider))

    return all_cases
