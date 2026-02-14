"""nnU-Net v2 학습 실행 — subprocess 기반 학습/전처리/모델 내보내기.

GPU 메모리 격리와 Windows 호환성을 위해 subprocess로 nnU-Net 명령을 실행한다.
"""

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TrainConfig:
    """nnU-Net 학습 설정."""

    # 데이터셋 ID (nnU-Net 데이터셋 번호)
    dataset_id: int = 200

    # nnU-Net 학습 설정 (3d_fullres, 2d, 3d_lowres 등)
    configuration: str = "3d_fullres"

    # 학습할 fold 목록 (None이면 0~4)
    folds: Optional[list[int]] = None

    # 최대 에폭 수 (None이면 nnU-Net 기본값 1000)
    epochs: Optional[int] = None

    # nnU-Net 경로 설정
    nnunet_raw: Path = Path("nnUNet_raw")
    nnunet_preprocessed: Path = Path("nnUNet_preprocessed")
    nnunet_results: Path = Path("nnUNet_results")

    # 연산 장치
    device: str = "cuda"

    # 디버그 모드 (5 에폭, fold 0만)
    debug: bool = False

    # 모델 내보내기 경로
    export_path: Optional[Path] = None

    def __post_init__(self):
        """디버그 모드 기본값 적용."""
        if self.debug:
            self.epochs = self.epochs or 5
            self.folds = self.folds or [0]
        if self.folds is None:
            self.folds = [0, 1, 2, 3, 4]

    @property
    def dataset_name(self) -> str:
        """nnU-Net 데이터셋 이름."""
        return f"Dataset{self.dataset_id:03d}_SpineUnified"

    @property
    def trainer_class(self) -> str:
        """nnU-Net 트레이너 클래스."""
        return "nnUNetTrainer"


def setup_environment(config: TrainConfig) -> dict[str, str]:
    """nnU-Net 환경변수 설정.

    Args:
        config: 학습 설정

    Returns:
        환경변수 딕셔너리
    """
    env = os.environ.copy()
    env["nnUNet_raw"] = str(config.nnunet_raw.resolve())
    env["nnUNet_preprocessed"] = str(config.nnunet_preprocessed.resolve())
    env["nnUNet_results"] = str(config.nnunet_results.resolve())

    # GPU 설정
    if config.device == "cpu":
        env["CUDA_VISIBLE_DEVICES"] = ""
    elif config.device.startswith("cuda:"):
        gpu_id = config.device.split(":")[1]
        env["CUDA_VISIBLE_DEVICES"] = gpu_id

    return env


def _run_subprocess(args: list[str], env: dict[str, str], description: str) -> bool:
    """subprocess 실행 헬퍼.

    Args:
        args: 실행할 명령어 리스트
        env: 환경변수
        description: 작업 설명 (로깅용)

    Returns:
        성공 여부
    """
    logger.info("%s 시작: %s", description, " ".join(args))

    try:
        result = subprocess.run(
            args,
            env=env,
            capture_output=True,
            text=True,
            timeout=86400,  # 24시간 제한
        )

        if result.returncode == 0:
            logger.info("%s 완료", description)
            if result.stdout:
                logger.debug("stdout: %s", result.stdout[-500:])
            return True
        else:
            logger.error("%s 실패 (code %d)", description, result.returncode)
            if result.stderr:
                logger.error("stderr: %s", result.stderr[-1000:])
            if result.stdout:
                logger.error("stdout: %s", result.stdout[-500:])
            return False

    except subprocess.TimeoutExpired:
        logger.error("%s: 시간 초과 (24시간)", description)
        return False
    except FileNotFoundError:
        logger.error("%s: Python 실행 파일을 찾을 수 없음 — %s", description, args[0])
        return False


def run_plan_and_preprocess(config: TrainConfig) -> bool:
    """nnU-Net 전처리 및 실험 계획 실행.

    Args:
        config: 학습 설정

    Returns:
        성공 여부
    """
    env = setup_environment(config)

    # nnU-Net 전처리 디렉토리 생성
    config.nnunet_preprocessed.mkdir(parents=True, exist_ok=True)

    args = [
        sys.executable, "-m",
        "nnunetv2.experiment_planning.plan_and_preprocess",
        "-d", str(config.dataset_id),
        "-c", config.configuration,
        "--verify_dataset_integrity",
    ]

    return _run_subprocess(args, env, "nnU-Net 전처리")


def run_train(config: TrainConfig, fold: int) -> bool:
    """단일 fold 학습 실행.

    Args:
        config: 학습 설정
        fold: fold 번호 (0~4)

    Returns:
        성공 여부
    """
    env = setup_environment(config)

    args = [
        sys.executable, "-m",
        "nnunetv2.run.run_training",
        str(config.dataset_id),
        config.configuration,
        str(fold),
        "-tr", config.trainer_class,
        "-device", config.device if config.device != "cpu" else "cpu",
    ]

    if config.epochs is not None:
        args.extend(["-num_epochs", str(config.epochs)])

    return _run_subprocess(args, env, f"nnU-Net 학습 (fold {fold})")


def run_full_training(config: TrainConfig) -> bool:
    """전체 학습 실행: 전처리 + 모든 fold 학습.

    Args:
        config: 학습 설정

    Returns:
        전체 성공 여부
    """
    logger.info(
        "전체 학습 시작: dataset=%d, config=%s, folds=%s, epochs=%s",
        config.dataset_id, config.configuration,
        config.folds, config.epochs or "기본값",
    )

    # 1. 전처리
    if not run_plan_and_preprocess(config):
        logger.error("전처리 실패, 학습 중단")
        return False

    # 2. fold별 학습
    all_success = True
    for fold in config.folds:
        if not run_train(config, fold):
            logger.error("fold %d 학습 실패", fold)
            all_success = False
            break

    if all_success:
        logger.info("전체 학습 완료")

    return all_success


def export_model(config: TrainConfig) -> Optional[Path]:
    """학습된 모델을 SpineUnifiedEngine 경로로 복사.

    Args:
        config: 학습 설정

    Returns:
        내보내기 경로 (실패 시 None)
    """
    # 학습 결과 디렉토리
    source_dir = (
        config.nnunet_results
        / config.dataset_name
        / f"{config.trainer_class}__{config.configuration}__nnUNetPlans"
    )

    if not source_dir.exists():
        logger.error("학습 결과 디렉토리 없음: %s", source_dir)
        return None

    # 내보내기 경로 설정
    if config.export_path:
        export_dir = config.export_path
    else:
        export_dir = Path.home() / ".spine_sim" / "models" / "spine_unified"

    export_dir.mkdir(parents=True, exist_ok=True)

    try:
        # fold별 결과 복사
        for fold in config.folds:
            fold_dir = source_dir / f"fold_{fold}"
            if fold_dir.exists():
                dest = export_dir / f"fold_{fold}"
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(str(fold_dir), str(dest))
                logger.info("fold_%d 내보내기 완료 → %s", fold, dest)

        # 계획 파일 복사
        for plan_file in ["plans.json", "dataset.json", "dataset_fingerprint.json"]:
            src = source_dir / plan_file
            if src.exists():
                shutil.copy2(str(src), str(export_dir / plan_file))

        logger.info("모델 내보내기 완료: %s", export_dir)
        return export_dir

    except Exception as e:
        logger.error("모델 내보내기 실패: %s", e)
        return None
