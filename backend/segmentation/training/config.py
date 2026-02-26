"""학습 데이터 준비 설정."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DatasetPaths:
    """데이터셋 경로 설정 (수동 다운로드 후 경로 지정)."""

    # VerSe2020: CT 척추 세그멘테이션 (300케이스)
    verse2020: Path = Path("data/VerSe2020")

    # CTSpine1K: CT 척추 (1005케이스)
    ctspine1k: Path = Path("data/CTSpine1K")

    # SPIDER: MRI 척추+디스크 (218케이스)
    spider: Path = Path("data/SPIDER")


@dataclass
class PseudoLabelConfig:
    """Pseudo-label 생성 설정."""

    # 디스크 voxel 최소 크기 (이하면 ignore)
    min_disc_voxels: int = 50

    # 연결 성분 최대/최소 크기 비율 (비정상이면 ignore)
    max_component_ratio: float = 10.0

    # TotalSpineSeg 모델 장치
    device: str = "gpu"


@dataclass
class PreprocessConfig:
    """전처리 설정."""

    # CT HU 클리핑 범위
    ct_hu_min: float = -200.0
    ct_hu_max: float = 1500.0

    # MRI z-score 클리핑 범위 (±sigma)
    mri_zscore_clip: float = 3.0


@dataclass
class NnunetConfig:
    """nnU-Net 변환 설정."""

    # 데이터셋 ID (200번대)
    dataset_id: int = 200

    # 데이터셋 이름
    dataset_name: str = "Dataset200_SpineUnified"

    # 클래스 수 (background 포함)
    num_classes: int = 51

    # Ignore 라벨
    ignore_label: int = 51

    # 출력 디렉토리
    output_dir: Path = Path("nnUNet_raw")

    # 채널 정보
    channel_names: dict = field(default_factory=lambda: {
        "0": "normalized_image",
        "1": "domain_channel",
    })

    # 파일 확장자
    file_ending: str = ".nii.gz"


@dataclass
class TrainingPipelineConfig:
    """학습 데이터 준비 전체 설정."""

    datasets: DatasetPaths = field(default_factory=DatasetPaths)
    pseudo_label: PseudoLabelConfig = field(default_factory=PseudoLabelConfig)
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    nnunet: NnunetConfig = field(default_factory=NnunetConfig)

    # 학습/검증 분할 비율
    val_ratio: float = 0.15

    # 랜덤 시드
    random_seed: int = 42

    # 병렬 처리 워커 수
    n_workers: int = 4
