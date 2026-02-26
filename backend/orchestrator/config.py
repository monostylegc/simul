"""파이프라인 설정 — Pydantic 모델 + TOML 로드."""

import tomllib
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SegmentConfig(BaseModel):
    """세그멘테이션 스테이지 설정."""

    engine: Literal["totalseg", "totalspineseg", "spine_unified"] = "totalseg"
    device: Literal["gpu", "cpu"] = "gpu"
    fast: bool = False
    roi_subset: Optional[list[str]] = None


class PostprocessConfig(BaseModel):
    """라벨 후처리 설정."""

    min_volume_mm3: float = 100.0
    fill_holes: bool = True
    smooth_sigma: float = 0.5


class VoxelizeConfig(BaseModel):
    """복셀화 설정."""

    resolution: int = 64
    spacing: Optional[float] = None


class SolveConfig(BaseModel):
    """FEA 솔버 설정."""

    method: Literal["fem", "pd", "spg"] = "spg"
    E: float = 12e9
    nu: float = 0.3
    density: float = 1850.0
    max_iterations: int = 10000
    tolerance: float = 1e-6


class CacheConfig(BaseModel):
    """캐시 설정."""

    enabled: bool = True
    cache_dir: str = ".cache/pipeline"
    max_size_gb: float = 10.0


class PipelineConfig(BaseModel):
    """최상위 파이프라인 설정."""

    segment: SegmentConfig = Field(default_factory=SegmentConfig)
    postprocess: PostprocessConfig = Field(default_factory=PostprocessConfig)
    voxelize: VoxelizeConfig = Field(default_factory=VoxelizeConfig)
    solve: SolveConfig = Field(default_factory=SolveConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    on_error: Literal["stop", "skip", "warn"] = "stop"

    @classmethod
    def from_toml(cls, path: str | Path) -> "PipelineConfig":
        """TOML 파일에서 설정 로드.

        Args:
            path: TOML 파일 경로

        Returns:
            PipelineConfig 인스턴스
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {path}")

        with open(path, "rb") as f:
            data = tomllib.load(f)

        return cls(**data)

    @classmethod
    def default(cls) -> "PipelineConfig":
        """기본 설정 반환."""
        return cls()
