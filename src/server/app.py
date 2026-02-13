"""FastAPI 앱 — 시뮬레이터 정적 파일 서빙 + WebSocket + REST API."""

import os
import uuid
import shutil
from pathlib import Path

from typing import List
from fastapi import FastAPI, WebSocket, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .ws_handler import handle_websocket

# 경로 설정
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # pysim/
SIMULATOR_DIR = BASE_DIR / "src" / "simulator"
UPLOAD_DIR = Path("/tmp/spine_sim")

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


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """파일 업로드 (NIfTI, STL 등).

    /tmp/spine_sim/{uuid}/{filename} 에 저장.
    반환: {"path": str, "filename": str, "size": int}
    """
    session_id = str(uuid.uuid4())[:8]
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    dest = session_dir / file.filename
    size = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):  # 1MB 청크
            f.write(chunk)
            size += len(chunk)

    return JSONResponse({
        "path": str(dest),
        "filename": file.filename,
        "size": size,
        "session_id": session_id,
    })


@app.post("/api/upload_dicom")
async def upload_dicom(files: List[UploadFile] = File(...)):
    """DICOM 다중 파일 업로드.

    webkitdirectory로 선택한 DICOM 폴더의 파일들을 flat하게 저장.
    반환: {dicom_dir, n_files, session_id, total_size}
    """
    session_id = str(uuid.uuid4())[:8]
    dicom_dir = UPLOAD_DIR / session_id / "dicom"
    dicom_dir.mkdir(parents=True, exist_ok=True)

    # DICOM 파일 필터링 확장자
    _EXCLUDE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".txt", ".xml",
                     ".html", ".pdf", ".csv", ".zip", ".tar", ".gz"}

    total_size = 0
    saved_count = 0
    for f in files:
        # 확장자 필터링
        name = f.filename or ""
        ext = os.path.splitext(name)[1].lower()
        if ext in _EXCLUDE_EXTS:
            continue

        # flat 저장 (하위 디렉토리 구조 무시, 파일명만 사용)
        safe_name = os.path.basename(name) or f"dcm_{saved_count:04d}"
        dest = dicom_dir / safe_name

        # 파일명 충돌 방지
        if dest.exists():
            safe_name = f"{saved_count:04d}_{safe_name}"
            dest = dicom_dir / safe_name

        size = 0
        with open(dest, "wb") as out:
            while chunk := await f.read(1024 * 1024):
                out.write(chunk)
                size += len(chunk)
        total_size += size
        saved_count += 1

    if saved_count == 0:
        raise HTTPException(status_code=400, detail="유효한 DICOM 파일이 없습니다.")

    return JSONResponse({
        "dicom_dir": str(dicom_dir),
        "n_files": saved_count,
        "session_id": session_id,
        "total_size": total_size,
    })


@app.post("/api/upload_plan")
async def upload_plan(file: UploadFile = File(...)):
    """수술 계획 JSON 업로드."""
    import json
    content = await file.read()
    try:
        plan_data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON 파싱 실패: {e}")
    return JSONResponse(plan_data)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 엔드포인트 — 해석/세그멘테이션/메쉬추출 요청."""
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
