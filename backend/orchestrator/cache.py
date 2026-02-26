"""해시 기반 파이프라인 캐시.

입력 파일 + 스테이지 + 파라미터 조합으로 SHA256 키를 생성하고,
이전 결과를 재사용한다.
"""

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Optional


class PipelineCache:
    """SHA256 해시 기반 캐시 관리자."""

    # 해시 계산에 사용할 파일 읽기 크기 (1MB)
    HASH_READ_SIZE = 1024 * 1024

    def __init__(self, cache_dir: str | Path, enabled: bool = True):
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_key(
        self,
        input_path: str | Path,
        stage: str,
        params: Optional[dict] = None,
    ) -> str:
        """캐시 키 생성.

        SHA256(파일 첫 1MB + stage + param_hash)

        Args:
            input_path: 입력 파일 경로
            stage: 스테이지 이름
            params: 스테이지 파라미터 딕셔너리

        Returns:
            SHA256 해시 문자열
        """
        h = hashlib.sha256()

        # 파일 첫 1MB 해시
        input_path = Path(input_path)
        if input_path.exists():
            with open(input_path, "rb") as f:
                h.update(f.read(self.HASH_READ_SIZE))

        # 스테이지 이름
        h.update(stage.encode())

        # 파라미터 해시
        if params:
            param_str = json.dumps(params, sort_keys=True, default=str)
            h.update(param_str.encode())

        return h.hexdigest()

    def has(self, key: str) -> bool:
        """캐시 존재 여부 확인."""
        if not self.enabled:
            return False
        cache_path = self.cache_dir / key
        metadata_path = cache_path / "metadata.json"
        return cache_path.exists() and metadata_path.exists()

    def get_path(self, key: str) -> Path:
        """캐시 디렉토리 경로 반환."""
        return self.cache_dir / key

    def store(
        self,
        key: str,
        files: list[Path],
        elapsed: float,
        params: Optional[dict] = None,
    ) -> Path:
        """결과를 캐시에 저장.

        Args:
            key: 캐시 키
            files: 저장할 파일 목록
            elapsed: 소요 시간 (초)
            params: 스테이지 파라미터

        Returns:
            캐시 디렉토리 경로
        """
        if not self.enabled:
            return self.cache_dir / key

        cache_path = self.cache_dir / key
        cache_path.mkdir(parents=True, exist_ok=True)

        # 파일 복사
        stored_files = []
        for f in files:
            f = Path(f)
            if f.exists():
                dest = cache_path / f.name
                shutil.copy2(f, dest)
                stored_files.append(f.name)

        # 메타데이터 저장
        metadata = {
            "created_at": time.time(),
            "elapsed_time": elapsed,
            "files": stored_files,
            "params": params or {},
        }
        with open(cache_path / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2, default=str)

        return cache_path

    def cleanup(self, max_size_gb: float) -> int:
        """캐시 크기 제한 (오래된 항목 삭제).

        Args:
            max_size_gb: 최대 캐시 크기 (GB)

        Returns:
            삭제된 항목 수
        """
        if not self.enabled or not self.cache_dir.exists():
            return 0

        max_size_bytes = max_size_gb * 1024 ** 3

        # 캐시 항목 수집 (생성 시간순 정렬)
        entries = []
        for entry_dir in self.cache_dir.iterdir():
            if not entry_dir.is_dir():
                continue
            meta_path = entry_dir / "metadata.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = json.load(f)
                size = sum(p.stat().st_size for p in entry_dir.iterdir() if p.is_file())
                entries.append((entry_dir, meta.get("created_at", 0), size))

        # 생성 시간 오름차순 정렬 (오래된 것 먼저)
        entries.sort(key=lambda x: x[1])

        # 전체 크기 계산
        total_size = sum(e[2] for e in entries)
        removed = 0

        # 오래된 항목부터 삭제
        while total_size > max_size_bytes and entries:
            entry_dir, _, size = entries.pop(0)
            shutil.rmtree(entry_dir)
            total_size -= size
            removed += 1

        return removed
