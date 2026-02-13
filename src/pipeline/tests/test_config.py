"""파이프라인 설정 테스트."""

import tempfile
from pathlib import Path

import pytest

from src.pipeline.config import (
    CacheConfig,
    PipelineConfig,
    PostprocessConfig,
    SegmentConfig,
    SolveConfig,
    VoxelizeConfig,
)


class TestPipelineConfig:
    """PipelineConfig 테스트."""

    def test_default_config(self):
        """기본 설정 생성."""
        cfg = PipelineConfig.default()
        assert cfg.segment.engine == "totalseg"
        assert cfg.segment.device == "gpu"
        assert cfg.solve.method == "spg"
        assert cfg.cache.enabled is True
        assert cfg.on_error == "stop"

    def test_segment_config(self):
        """SegmentConfig 필드 검증."""
        cfg = SegmentConfig(engine="totalspineseg", device="cpu", fast=True)
        assert cfg.engine == "totalspineseg"
        assert cfg.device == "cpu"
        assert cfg.fast is True
        assert cfg.roi_subset is None

    def test_postprocess_config(self):
        """PostprocessConfig 필드 검증."""
        cfg = PostprocessConfig(min_volume_mm3=50.0, fill_holes=False)
        assert cfg.min_volume_mm3 == 50.0
        assert cfg.fill_holes is False
        assert cfg.smooth_sigma == 0.5

    def test_voxelize_config(self):
        """VoxelizeConfig 필드 검증."""
        cfg = VoxelizeConfig(resolution=128, spacing=0.5)
        assert cfg.resolution == 128
        assert cfg.spacing == 0.5

    def test_solve_config(self):
        """SolveConfig 필드 검증."""
        cfg = SolveConfig(method="fem", E=1e6, max_iterations=5000)
        assert cfg.method == "fem"
        assert cfg.E == 1e6
        assert cfg.max_iterations == 5000

    def test_cache_config(self):
        """CacheConfig 필드 검증."""
        cfg = CacheConfig(enabled=False, max_size_gb=5.0)
        assert cfg.enabled is False
        assert cfg.max_size_gb == 5.0

    def test_from_toml(self):
        """TOML 파일에서 설정 로드."""
        toml_content = """
on_error = "skip"

[segment]
engine = "totalspineseg"
device = "cpu"
fast = true

[solve]
method = "fem"
E = 1e6
nu = 0.25

[cache]
enabled = false
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write(toml_content)
            f.flush()
            cfg = PipelineConfig.from_toml(f.name)

        assert cfg.on_error == "skip"
        assert cfg.segment.engine == "totalspineseg"
        assert cfg.segment.device == "cpu"
        assert cfg.segment.fast is True
        assert cfg.solve.method == "fem"
        assert cfg.solve.E == 1e6
        assert cfg.solve.nu == 0.25
        assert cfg.cache.enabled is False

    def test_from_toml_file_not_found(self):
        """존재하지 않는 TOML 파일."""
        with pytest.raises(FileNotFoundError):
            PipelineConfig.from_toml("/nonexistent/path.toml")

    def test_from_toml_partial(self):
        """일부 섹션만 있는 TOML 파일 (나머지는 기본값)."""
        toml_content = """
[segment]
engine = "totalseg"
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write(toml_content)
            f.flush()
            cfg = PipelineConfig.from_toml(f.name)

        assert cfg.segment.engine == "totalseg"
        # 나머지는 기본값
        assert cfg.solve.method == "spg"
        assert cfg.cache.enabled is True

    def test_bundled_config_file(self):
        """번들 설정 파일(config/pipeline.toml) 로드."""
        config_path = Path(__file__).parents[3] / "config" / "pipeline.toml"
        if config_path.exists():
            cfg = PipelineConfig.from_toml(config_path)
            assert cfg.segment.engine == "totalseg"
            assert cfg.solve.method == "spg"
