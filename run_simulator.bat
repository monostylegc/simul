@echo off
echo Starting Spine Surgery Planner Simulator...
echo http://localhost:8080 에서 실행됩니다.
echo 종료하려면 Ctrl+C를 누르세요.
echo.
cd /d "%~dp0src\simulator"
uv run python -m http.server 8080
