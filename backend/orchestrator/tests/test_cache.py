"""파이프라인 캐시 테스트."""

import tempfile
from pathlib import Path

import pytest

from backend.orchestrator.cache import PipelineCache


class TestPipelineCache:
    """PipelineCache 테스트."""

    def test_disabled_cache(self):
        """비활성화된 캐시는 항상 miss."""
        cache = PipelineCache("/tmp/test_cache_disabled", enabled=False)
        key = cache.get_key("/tmp/test.nii", "segment")
        assert cache.has(key) is False

    def test_get_key_deterministic(self):
        """동일 입력에 대해 동일 키 반환."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PipelineCache(tmpdir)

            # 테스트 파일 생성
            test_file = Path(tmpdir) / "test.bin"
            test_file.write_bytes(b"hello world")

            key1 = cache.get_key(test_file, "segment", {"fast": True})
            key2 = cache.get_key(test_file, "segment", {"fast": True})
            assert key1 == key2

    def test_get_key_different_stage(self):
        """다른 스테이지는 다른 키."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PipelineCache(tmpdir)
            test_file = Path(tmpdir) / "test.bin"
            test_file.write_bytes(b"data")

            key1 = cache.get_key(test_file, "segment")
            key2 = cache.get_key(test_file, "postprocess")
            assert key1 != key2

    def test_get_key_different_params(self):
        """다른 파라미터는 다른 키."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PipelineCache(tmpdir)
            test_file = Path(tmpdir) / "test.bin"
            test_file.write_bytes(b"data")

            key1 = cache.get_key(test_file, "segment", {"fast": True})
            key2 = cache.get_key(test_file, "segment", {"fast": False})
            assert key1 != key2

    def test_store_and_retrieve(self):
        """저장 후 조회."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PipelineCache(Path(tmpdir) / "cache")

            # 테스트 파일 생성
            src_file = Path(tmpdir) / "result.npz"
            src_file.write_bytes(b"fake npz data")

            key = "test_key_abc123"
            cache.store(key, [src_file], elapsed=1.5, params={"method": "spg"})

            assert cache.has(key)

            cached_dir = cache.get_path(key)
            assert (cached_dir / "result.npz").exists()
            assert (cached_dir / "metadata.json").exists()

    def test_store_no_file(self):
        """존재하지 않는 파일 저장 시도."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PipelineCache(Path(tmpdir) / "cache")
            key = "test_key_missing"
            cache.store(key, [Path("/nonexistent/file.npz")], elapsed=0.1)
            # 메타데이터만 존재
            assert cache.has(key)

    def test_cleanup(self):
        """캐시 크기 제한 정리."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PipelineCache(Path(tmpdir) / "cache")

            # 여러 캐시 항목 생성
            for i in range(5):
                data_file = Path(tmpdir) / f"data_{i}.bin"
                data_file.write_bytes(b"x" * 1000)  # 1KB
                cache.store(f"key_{i}", [data_file], elapsed=0.1)

            # 매우 작은 한도로 정리 → 일부 삭제
            removed = cache.cleanup(max_size_gb=0)
            assert removed > 0

    def test_has_without_metadata(self):
        """metadata.json 없으면 캐시 미스."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PipelineCache(tmpdir)
            key_dir = Path(tmpdir) / "fake_key"
            key_dir.mkdir()
            # metadata.json 없음
            assert cache.has("fake_key") is False
