"""FastAPI 앱 — 시뮬레이터 정적 파일 서빙 + WebSocket 엔드포인트."""

import os
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .ws_handler import handle_websocket

# 경로 설정
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # pysim/
SIMULATOR_DIR = BASE_DIR / "src" / "simulator"

app = FastAPI(title="Spine Surgery Simulator")

# CORS 미들웨어 (개발용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def index():
    """시뮬레이터 메인 페이지 서빙."""
    return FileResponse(SIMULATOR_DIR / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 엔드포인트 — 해석 요청/결과 통신."""
    await handle_websocket(ws)


# 정적 파일 마운트 (index.html 이외의 파일: js, stl, css 등)
app.mount("/", StaticFiles(directory=str(SIMULATOR_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.server.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(BASE_DIR / "src")],
    )
