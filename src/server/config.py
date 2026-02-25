"""서버 설정 — 경로 및 환경변수 중앙 관리."""

import os
from pathlib import Path

# 프로젝트 루트 (pysim/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ── 업로드 디렉토리 ──
# 환경변수 SPINE_SIM_DATA_DIR 우선, 없으면 홈 디렉토리 하위 (~/.spine_sim)
# Windows: C:\Users\{user}\.spine_sim
# Linux/Mac: /home/{user}/.spine_sim
UPLOAD_DIR = Path(os.environ.get(
    "SPINE_SIM_DATA_DIR",
    str(Path.home() / ".spine_sim"),
))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── 정적 파일 디렉토리 ──
# Svelte 빌드 출력 디렉토리 (npm run build → src/simulator/)
STATIC_DIR = BASE_DIR / "src" / "simulator"

# ── CORS 허용 오리진 ──
# 환경변수 SPINE_SIM_CORS_ORIGINS: 콤마로 구분된 오리진 목록
#   예) SPINE_SIM_CORS_ORIGINS=https://hospital.example.com,https://www.hospital.example.com
# 미설정 시 개발용 localhost 기본값 사용 (["*"] 금지 — 프로덕션 보안)
_cors_env = os.environ.get("SPINE_SIM_CORS_ORIGINS", "")
if _cors_env.strip():
    CORS_ORIGINS: list[str] = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    # 개발 기본값: Vite dev 서버(5174) + FastAPI 자체(8000) 포트
    CORS_ORIGINS = [
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
