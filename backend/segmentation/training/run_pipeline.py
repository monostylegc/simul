"""데이터 준비 파이프라인 — 원본 데이터셋 → nnU-Net 형식 변환 오케스트레이션.

처리 흐름:
  CT 케이스 (VerSe2020, CTSpine1K):
    1. NIfTI 로드
    2. 원본 라벨 → SpineLabel 변환
    3. (선택) pseudo-label 생성 → 필터링 → merge_ct_labels
    4. validate_label_map
    5. normalize_ct + create_domain_channel("CT")
    6. convert_to_nnunet_labels
    7. save_nnunet_case

  MRI 케이스 (SPIDER):
    1. NIfTI 로드
    2. build_spider_mapping → convert_to_standard
    3. validate_label_map
    4. normalize_mri + create_domain_channel("MRI")
    5. convert_to_nnunet_labels
    6. save_nnunet_case
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from backend.segmentation.labels import (
    SpineLabel,
    VERSE_TO_STANDARD,
    CTSPINE1K_TO_STANDARD,
    build_spider_mapping,
    convert_to_standard,
)
from .config import (
    TrainingPipelineConfig,
    NnunetConfig,
    PreprocessConfig,
    PseudoLabelConfig,
)
from .convert_nnunet import convert_to_nnunet_labels, save_nnunet_case, generate_dataset_json
from .dataset_crawl import CaseInfo, crawl_all
from .label_merge import merge_ct_labels
from .preprocess import normalize_ct, normalize_mri, create_domain_channel
from .validate_labels import validate_label_map

logger = logging.getLogger(__name__)

# 콜백 타입 정의
ProgressCallback = Optional[Callable[[str, dict], None]]


@dataclass
class CaseResult:
    """단일 케이스 처리 결과."""

    case_id: str
    success: bool
    message: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """파이프라인 전체 결과."""

    total: int = 0
    success: int = 0
    skipped: int = 0
    failed: int = 0
    case_results: list[CaseResult] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """결과 요약 문자열."""
        return (
            f"총 {self.total}건: 성공 {self.success}, "
            f"스킵 {self.skipped}, 실패 {self.failed}"
        )


def _get_source_mapping(dataset: str) -> dict[int, int]:
    """데이터셋별 소스 매핑 반환."""
    if dataset == "verse2020":
        return VERSE_TO_STANDARD
    elif dataset == "ctspine1k":
        return CTSPINE1K_TO_STANDARD
    else:
        raise ValueError(f"CT 데이터셋이 아님: {dataset}")


def _build_case_id(index: int) -> str:
    """nnU-Net 케이스 ID 생성 (예: SpineUnified_0001)."""
    return f"SpineUnified_{index:04d}"


def _load_nifti(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """NIfTI 파일 로드 → (데이터, affine)."""
    import nibabel as nib

    img = nib.load(str(path))
    data = np.asarray(img.dataobj)
    return data, img.affine


def _process_ct_case(
    case: CaseInfo,
    case_index: int,
    output_dir: Path,
    config: TrainingPipelineConfig,
    use_pseudo_labels: bool = False,
) -> CaseResult:
    """CT 케이스 처리 (VerSe2020, CTSpine1K).

    Args:
        case: 케이스 정보
        case_index: nnU-Net 케이스 번호
        output_dir: nnU-Net 데이터셋 디렉토리
        config: 파이프라인 설정
        use_pseudo_labels: pseudo-label 사용 여부
    """
    nnunet_case_id = _build_case_id(case_index)

    try:
        # 1. NIfTI 로드
        image_data, affine = _load_nifti(case.image_path)
        label_data, _ = _load_nifti(case.label_path)

        # 2. 원본 라벨 → SpineLabel 변환
        source_mapping = _get_source_mapping(case.dataset)
        standard_labels = convert_to_standard(label_data, source_mapping)

        # 3. (선택) pseudo-label 병합
        if use_pseudo_labels:
            try:
                from .pseudo_label import generate_pseudo_labels, filter_pseudo_labels

                pseudo_path = output_dir / "_pseudo_tmp" / f"{nnunet_case_id}_pseudo.nii.gz"
                pseudo_path.parent.mkdir(parents=True, exist_ok=True)
                generate_pseudo_labels(case.image_path, pseudo_path, config.pseudo_label)

                pseudo_data, _ = _load_nifti(pseudo_path)
                from backend.segmentation.labels import TOTALSPINESEG_TO_STANDARD
                pseudo_standard = convert_to_standard(pseudo_data, TOTALSPINESEG_TO_STANDARD)
                pseudo_filtered = filter_pseudo_labels(
                    pseudo_standard, standard_labels, config.pseudo_label,
                )
                standard_labels = merge_ct_labels(standard_labels, pseudo_filtered)
            except Exception as e:
                logger.warning(
                    "%s: pseudo-label 실패, GT만 사용 — %s", case.case_id, e,
                )

        # 4. 라벨 검증
        validation = validate_label_map(standard_labels, case.case_id)
        warnings = validation.warnings.copy()
        if validation.errors:
            logger.warning("%s: 검증 에러 — %s", case.case_id, validation.errors)

        # 5. 전처리
        normalized = normalize_ct(image_data, config.preprocess)
        domain = create_domain_channel(image_data, "CT")

        # 6. nnU-Net 라벨 변환
        nnunet_labels = convert_to_nnunet_labels(standard_labels)

        # 7. 저장
        save_nnunet_case(
            nnunet_case_id, normalized, domain, nnunet_labels,
            affine, output_dir, config.nnunet,
        )

        return CaseResult(
            case_id=case.case_id,
            success=True,
            message=f"→ {nnunet_case_id}",
            warnings=warnings,
        )

    except Exception as e:
        logger.error("%s: 처리 실패 — %s", case.case_id, e)
        return CaseResult(case_id=case.case_id, success=False, message=str(e))


def _process_mri_case(
    case: CaseInfo,
    case_index: int,
    output_dir: Path,
    config: TrainingPipelineConfig,
) -> CaseResult:
    """MRI 케이스 처리 (SPIDER).

    Args:
        case: 케이스 정보
        case_index: nnU-Net 케이스 번호
        output_dir: nnU-Net 데이터셋 디렉토리
        config: 파이프라인 설정
    """
    nnunet_case_id = _build_case_id(case_index)

    try:
        # 1. NIfTI 로드
        image_data, affine = _load_nifti(case.image_path)
        label_data, _ = _load_nifti(case.label_path)

        # 2. SPIDER 동적 매핑 생성
        unique_labels = np.unique(label_data)
        # 척추골 라벨: 1~N (100, 200번대 제외)
        vertebra_labels = [int(v) for v in unique_labels if 1 <= v <= 99]
        n_vertebrae = len(vertebra_labels)

        if n_vertebrae == 0:
            return CaseResult(
                case_id=case.case_id, success=False,
                message="척추골 라벨이 없음",
            )

        spider_mapping = build_spider_mapping(n_vertebrae, bottom_vertebra="L5")
        standard_labels = convert_to_standard(label_data, spider_mapping)

        # 3. 라벨 검증
        validation = validate_label_map(standard_labels, case.case_id)
        warnings = validation.warnings.copy()

        # 4. 전처리
        normalized = normalize_mri(image_data, config.preprocess)
        domain = create_domain_channel(image_data, "MRI")

        # 5. nnU-Net 라벨 변환
        nnunet_labels = convert_to_nnunet_labels(standard_labels)

        # 6. 저장
        save_nnunet_case(
            nnunet_case_id, normalized, domain, nnunet_labels,
            affine, output_dir, config.nnunet,
        )

        return CaseResult(
            case_id=case.case_id,
            success=True,
            message=f"→ {nnunet_case_id}",
            warnings=warnings,
        )

    except Exception as e:
        logger.error("%s: 처리 실패 — %s", case.case_id, e)
        return CaseResult(case_id=case.case_id, success=False, message=str(e))


def _case_already_exists(case_index: int, output_dir: Path, config: NnunetConfig) -> bool:
    """이미 변환된 케이스인지 확인."""
    case_id = _build_case_id(case_index)
    label_path = output_dir / "labelsTr" / f"{case_id}{config.file_ending}"
    return label_path.exists()


def run_training_pipeline(
    config: TrainingPipelineConfig,
    progress_callback: ProgressCallback = None,
    use_pseudo_labels: bool = False,
    continue_on_error: bool = True,
    skip_existing: bool = True,
) -> PipelineResult:
    """학습 데이터 준비 파이프라인 실행.

    모든 데이터셋(VerSe2020, CTSpine1K, SPIDER)을 탐색하고 nnU-Net 형식으로 변환한다.

    Args:
        config: 파이프라인 전체 설정
        progress_callback: 진행 상황 콜백 (stage, details)
        use_pseudo_labels: CT 데이터에 pseudo-label 사용 여부
        continue_on_error: 개별 실패 시 계속 진행 여부
        skip_existing: 이미 변환된 케이스 스킵 여부

    Returns:
        PipelineResult
    """
    result = PipelineResult()

    # 데이터셋 디렉토리 설정
    output_dir = config.nnunet.output_dir / config.nnunet.dataset_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # 케이스 탐색
    if progress_callback:
        progress_callback("탐색", {"message": "데이터셋 케이스 수집 중..."})

    all_cases = crawl_all(config.datasets)
    result.total = len(all_cases)

    if result.total == 0:
        logger.warning("변환할 케이스가 없음")
        return result

    logger.info("총 %d건 발견: CT %d, MRI %d",
                result.total,
                sum(1 for c in all_cases if c.modality == "CT"),
                sum(1 for c in all_cases if c.modality == "MRI"))

    # 케이스별 처리
    for i, case in enumerate(all_cases, start=1):
        if progress_callback:
            progress_callback("변환", {
                "message": f"[{i}/{result.total}] {case.case_id}",
                "current": i,
                "total": result.total,
            })

        # 스킵 확인
        if skip_existing and _case_already_exists(i, output_dir, config.nnunet):
            result.skipped += 1
            logger.info("%s: 이미 존재, 스킵", case.case_id)
            continue

        # 모달리티별 처리
        if case.modality == "CT":
            case_result = _process_ct_case(
                case, i, output_dir, config, use_pseudo_labels,
            )
        else:
            case_result = _process_mri_case(case, i, output_dir, config)

        result.case_results.append(case_result)

        if case_result.success:
            result.success += 1
        else:
            result.failed += 1
            if not continue_on_error:
                logger.error("처리 중단: %s", case_result.message)
                break

    # dataset.json 생성
    n_converted = result.success + result.skipped
    if n_converted > 0:
        if progress_callback:
            progress_callback("완료", {"message": "dataset.json 생성 중..."})
        generate_dataset_json(output_dir, n_converted, config.nnunet)
        logger.info("dataset.json 생성 완료 (총 %d 케이스)", n_converted)

    return result
