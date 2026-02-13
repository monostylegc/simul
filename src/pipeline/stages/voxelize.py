"""복셀화 스테이지 — NIfTI → NPZ 복셀 모델 변환."""

import time
from pathlib import Path
from typing import Callable, Optional

from .base import StageBase, StageResult


class VoxelizeStage(StageBase):
    """NIfTI 라벨맵 → NPZ 복셀 모델 변환 스테이지.

    라벨맵에서 비영 복셀의 좌표, 볼륨, 재료 ID를 추출하여
    FEA 솔버 입력 형식(NPZ)으로 저장한다.
    """

    name = "voxelize"

    def __init__(self, resolution: int = 64, spacing: Optional[float] = None):
        self.resolution = resolution
        self.spacing = spacing

    def validate_input(self, input_path: str | Path) -> bool:
        """NIfTI 라벨맵 유효성 검증."""
        input_path = Path(input_path)
        if not input_path.exists():
            return False
        suffixes = "".join(input_path.suffixes).lower()
        return suffixes in (".nii", ".nii.gz")

    def run(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> StageResult:
        """복셀화 실행."""
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not self.validate_input(input_path):
            return StageResult(
                success=False,
                output_path=output_dir,
                elapsed_time=0.0,
                message=f"입력 파일이 유효하지 않습니다: {input_path}",
            )

        if progress_callback:
            progress_callback("voxelize", {"message": "복셀 모델 생성 시작..."})

        start = time.time()

        try:
            import numpy as np
            from src.segmentation.labels import SpineLabel

            # VolumeLoader로 라벨맵 로드
            from src.core.volume_io import VolumeLoader

            data, metadata = VolumeLoader.load(input_path, max_resolution=self.resolution)
            labels = data.astype(np.int32)

            # 비영 복셀 추출
            nonzero = np.argwhere(labels > 0)
            if len(nonzero) == 0:
                return StageResult(
                    success=False,
                    output_path=output_dir,
                    elapsed_time=time.time() - start,
                    message="라벨맵에 비영 복셀이 없습니다",
                )

            # 복셀 좌표 계산 (물리 좌표)
            spacing = self.spacing or metadata.min_spacing
            origin = np.array(metadata.origin)
            spacing_arr = np.array(metadata.spacing)

            positions = nonzero.astype(np.float64) * spacing_arr + origin
            volumes = np.full(len(positions), np.prod(spacing_arr), dtype=np.float64)

            # 라벨 → 재료 ID 변환
            label_values = labels[nonzero[:, 0], nonzero[:, 1], nonzero[:, 2]]
            material_ids = np.array(
                [SpineLabel.to_material_type(lv) for lv in label_values],
                dtype=np.int32,
            )

            # NPZ 저장
            output_path = output_dir / "voxel_model.npz"
            np.savez_compressed(
                output_path,
                positions=positions,
                volumes=volumes,
                material_ids=material_ids,
                label_values=label_values,
                spacing=spacing_arr,
                origin=origin,
            )

            elapsed = time.time() - start
            n_particles = len(positions)

            if progress_callback:
                progress_callback("voxelize", {
                    "message": f"완료: {n_particles}개 입자 ({elapsed:.1f}초)"
                })

            return StageResult(
                success=True,
                output_path=output_path,
                elapsed_time=elapsed,
                message=f"{n_particles}개 입자 복셀 모델 생성",
            )

        except Exception as e:
            elapsed = time.time() - start
            return StageResult(
                success=False,
                output_path=output_dir,
                elapsed_time=elapsed,
                message=f"복셀화 실패: {e}",
            )
