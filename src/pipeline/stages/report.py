"""리포트 생성 스테이지 — JSON/HTML 결과 요약."""

import json
import time
from pathlib import Path
from typing import Callable, Optional

from .base import StageBase, StageResult


class ReportStage(StageBase):
    """해석 결과 리포트 생성 스테이지.

    NPZ 해석 결과에서 변위/응력 통계를 추출하여
    JSON 요약 + HTML 리포트를 생성한다.
    """

    name = "report"

    def validate_input(self, input_path: str | Path) -> bool:
        """NPZ 결과 유효성 검증."""
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
        """리포트 생성."""
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
            progress_callback("report", {"message": "리포트 생성 시작..."})

        start = time.time()

        try:
            import numpy as np

            data = np.load(input_path, allow_pickle=True)

            # 기본 정보
            report = {
                "input_file": str(input_path),
                "n_particles": len(data["positions"]) if "positions" in data else 0,
                "converged": bool(data["converged"][0]) if "converged" in data else None,
                "iterations": int(data["iterations"][0]) if "iterations" in data else None,
                "residual": float(data["residual"][0]) if "residual" in data else None,
            }

            # 변위 통계
            if "displacements" in data and len(data["displacements"]) > 0:
                disp = data["displacements"]
                disp_mag = np.linalg.norm(disp, axis=1) if disp.ndim == 2 else np.abs(disp)
                report["displacement"] = {
                    "max_magnitude": float(np.max(disp_mag)),
                    "mean_magnitude": float(np.mean(disp_mag)),
                    "max_component": disp.max(axis=0).tolist() if disp.ndim == 2 else [float(disp.max())],
                    "min_component": disp.min(axis=0).tolist() if disp.ndim == 2 else [float(disp.min())],
                }

            # 응력 통계
            if "stress" in data and len(data["stress"]) > 0:
                stress = data["stress"]
                report["stress"] = {
                    "max": float(np.max(stress)),
                    "min": float(np.min(stress)),
                    "mean": float(np.mean(stress)),
                }

            # 손상 통계
            if "damage" in data and len(data["damage"]) > 0:
                damage = data["damage"]
                report["damage"] = {
                    "max": float(np.max(damage)),
                    "mean": float(np.mean(damage)),
                    "damaged_ratio": float(np.mean(damage > 0.5)),
                }

            # JSON 저장
            json_path = output_dir / "report.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            # HTML 리포트 생성
            html_path = output_dir / "report.html"
            self._write_html(report, html_path)

            elapsed = time.time() - start

            if progress_callback:
                progress_callback("report", {"message": f"리포트 생성 완료 ({elapsed:.1f}초)"})

            return StageResult(
                success=True,
                output_path=json_path,
                elapsed_time=elapsed,
                message="JSON + HTML 리포트 생성 완료",
            )

        except Exception as e:
            elapsed = time.time() - start
            return StageResult(
                success=False,
                output_path=output_dir,
                elapsed_time=elapsed,
                message=f"리포트 생성 실패: {e}",
            )

    @staticmethod
    def _write_html(report: dict, output_path: Path):
        """HTML 리포트 생성."""
        html = [
            "<!DOCTYPE html>",
            "<html><head><meta charset='utf-8'>",
            "<title>척추 해석 리포트</title>",
            "<style>",
            "  body { font-family: sans-serif; max-width: 800px; margin: 40px auto; }",
            "  table { border-collapse: collapse; width: 100%; margin: 16px 0; }",
            "  th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
            "  th { background-color: #f5f5f5; }",
            "  .ok { color: green; } .fail { color: red; }",
            "</style></head><body>",
            "<h1>척추 해석 리포트</h1>",
        ]

        # 기본 정보 테이블
        html.append("<h2>해석 정보</h2><table>")
        converged = report.get("converged")
        conv_class = "ok" if converged else "fail"
        conv_text = "수렴" if converged else "미수렴"
        html.append(f"<tr><th>입자 수</th><td>{report.get('n_particles', '-')}</td></tr>")
        html.append(f"<tr><th>수렴 여부</th><td class='{conv_class}'>{conv_text}</td></tr>")
        html.append(f"<tr><th>반복 횟수</th><td>{report.get('iterations', '-')}</td></tr>")
        html.append(f"<tr><th>잔차</th><td>{report.get('residual', '-'):.2e}</td></tr>")
        html.append("</table>")

        # 변위
        if "displacement" in report:
            d = report["displacement"]
            html.append("<h2>변위</h2><table>")
            html.append(f"<tr><th>최대 크기</th><td>{d['max_magnitude']:.6e}</td></tr>")
            html.append(f"<tr><th>평균 크기</th><td>{d['mean_magnitude']:.6e}</td></tr>")
            html.append("</table>")

        # 응력
        if "stress" in report:
            s = report["stress"]
            html.append("<h2>응력</h2><table>")
            html.append(f"<tr><th>최대</th><td>{s['max']:.6e}</td></tr>")
            html.append(f"<tr><th>최소</th><td>{s['min']:.6e}</td></tr>")
            html.append(f"<tr><th>평균</th><td>{s['mean']:.6e}</td></tr>")
            html.append("</table>")

        html.append("</body></html>")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(html))
