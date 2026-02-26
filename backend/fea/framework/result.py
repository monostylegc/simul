"""해석 결과 데이터 클래스."""

from dataclasses import dataclass


@dataclass
class SolveResult:
    """솔버 결과 데이터 클래스.

    Args:
        converged: 수렴 여부
        iterations: 반복 횟수
        residual: 최종 잔차
        relative_residual: 상대 잔차
        elapsed_time: 소요 시간 [초]
    """
    converged: bool
    iterations: int
    residual: float
    relative_residual: float
    elapsed_time: float
