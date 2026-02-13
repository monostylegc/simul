"""CLI 테스트."""

import pytest
from typer.testing import CliRunner

from src.pipeline.cli import app

runner = CliRunner()


class TestCLI:
    """CLI 기본 테스트."""

    def test_help(self):
        """--help 옵션."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "spine-sim" in result.output or "파이프라인" in result.output

    def test_segment_help(self):
        """segment --help."""
        result = runner.invoke(app, ["segment", "--help"])
        assert result.exit_code == 0
        assert "engine" in result.output

    def test_postprocess_help(self):
        """postprocess --help."""
        result = runner.invoke(app, ["postprocess", "--help"])
        assert result.exit_code == 0
        assert "min-volume" in result.output

    def test_voxelize_help(self):
        """voxelize --help."""
        result = runner.invoke(app, ["voxelize", "--help"])
        assert result.exit_code == 0
        assert "resolution" in result.output

    def test_solve_help(self):
        """solve --help."""
        result = runner.invoke(app, ["solve", "--help"])
        assert result.exit_code == 0
        assert "method" in result.output

    def test_report_help(self):
        """report --help."""
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0

    def test_pipeline_help(self):
        """pipeline --help."""
        result = runner.invoke(app, ["pipeline", "--help"])
        assert result.exit_code == 0
        assert "config" in result.output

    def test_server_help(self):
        """server --help."""
        result = runner.invoke(app, ["server", "--help"])
        assert result.exit_code == 0
        assert "host" in result.output
        assert "port" in result.output

    def test_segment_missing_input(self):
        """존재하지 않는 입력 파일로 segment 실행."""
        result = runner.invoke(app, ["segment", "/nonexistent/file.nii.gz"])
        assert result.exit_code != 0

    def test_report_missing_input(self):
        """존재하지 않는 입력 파일로 report 실행."""
        result = runner.invoke(app, ["report", "/nonexistent/result.npz"])
        assert result.exit_code != 0
