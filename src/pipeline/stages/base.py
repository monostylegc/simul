"""파이프라인 스테이지 기본 클래스."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class StageResult:
    """스테이지 실행 결과."""

    success: bool
    output_path: Path
    elapsed_time: float
    message: str = ""
    cached: bool = False


class StageBase(ABC):
    """파이프라인 스테이지 추상 클래스.

    모든 스테이지는 이 클래스를 상속하고
    run()과 validate_input()을 구현해야 한다.
    """

    name: str = "base"

    @abstractmethod
    def run(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> StageResult:
        """스테이지 실행.

        Args:
            input_path: 입력 파일 경로
            output_dir: 출력 디렉토리 경로
            progress_callback: 진행률 콜백 (message, details)

        Returns:
            StageResult 객체
        """
        ...

    @abstractmethod
    def validate_input(self, input_path: str | Path) -> bool:
        """입력 파일 유효성 검증.

        Args:
            input_path: 입력 파일 경로

        Returns:
            유효하면 True
        """
        ...
