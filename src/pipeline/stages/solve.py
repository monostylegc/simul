"""FEA 해석 스테이지 — 기존 프레임워크 호출."""

import time
from pathlib import Path
from typing import Callable, Optional

from .base import StageBase, StageResult


class SolveStage(StageBase):
    """FEA 해석 스테이지.

    NPZ 복셀 모델을 입력받아 FEM/PD/SPG 솔버로 해석한다.
    src.fea.framework API를 사용한다.
    """

    name = "solve"

    def __init__(
        self,
        method: str = "spg",
        E: float = 12e9,
        nu: float = 0.3,
        density: float = 1850.0,
        max_iterations: int = 10000,
        tolerance: float = 1e-6,
    ):
        self.method = method
        self.E = E
        self.nu = nu
        self.density = density
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def validate_input(self, input_path: str | Path) -> bool:
        """NPZ 입력 유효성 검증."""
        input_path = Path(input_path)
        if not input_path.exists():
            return False
        return input_path.suffix == ".npz"

    def run(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> StageResult:
        """FEA 해석 실행."""
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
            progress_callback("solve", {"message": f"{self.method.upper()} 해석 시작..."})

        start = time.time()

        try:
            import numpy as np

            # NPZ 로드
            data = np.load(input_path)
            positions = data["positions"]
            n_particles = len(positions)

            if progress_callback:
                progress_callback("solve", {"message": f"입자 {n_particles}개 설정 중..."})

            # 프레임워크 초기화
            from src.fea.framework import init, Material, Solver, Method
            from src.fea.framework.domain import create_particle_domain

            init()

            method_map = {"fem": Method.FEM, "pd": Method.PD, "spg": Method.SPG}
            method = method_map[self.method]

            # create_particle_domain: 바운딩박스·n_divisions 계산 + 실제 좌표(_custom_positions) 설정
            # get_positions() / select() 가 실제 복셀 좌표를 기준으로 동작한다
            domain = create_particle_domain(positions, method=method)

            # 하단 고정 (실제 복셀 좌표 기준 select)
            bottom = domain.select(axis=2, value=positions.min(axis=0)[2])
            domain.set_fixed(bottom)

            # 재료 설정
            material = Material(E=self.E, nu=self.nu, density=self.density, dim=3)

            # 솔버 실행
            solver = Solver(
                domain, material,
                max_iterations=self.max_iterations,
                tolerance=self.tolerance,
            )

            if progress_callback:
                progress_callback("solve", {"message": "해석 실행 중..."})

            result = solver.solve()

            # 결과 추출
            displacements = solver.get_displacements()
            stress = solver.get_stress()
            damage = solver.get_damage()

            # NPZ로 저장
            output_path = output_dir / "result.npz"
            save_dict = {
                "positions": positions,
                "displacements": displacements if displacements is not None else np.array([]),
                "converged": np.array([result.converged]),
                "iterations": np.array([result.iterations]),
                "residual": np.array([result.residual]),
            }
            if stress is not None:
                save_dict["stress"] = stress
            if damage is not None:
                save_dict["damage"] = damage

            np.savez_compressed(output_path, **save_dict)

            elapsed = time.time() - start

            if progress_callback:
                progress_callback("solve", {
                    "message": f"완료: 수렴={result.converged}, 반복={result.iterations} ({elapsed:.1f}초)"
                })

            return StageResult(
                success=True,
                output_path=output_path,
                elapsed_time=elapsed,
                message=f"수렴={result.converged}, 반복={result.iterations}",
            )

        except Exception as e:
            elapsed = time.time() - start
            return StageResult(
                success=False,
                output_path=output_dir,
                elapsed_time=elapsed,
                message=f"해석 실패: {e}",
            )
