# Getting Started

Spine Surgery Planner 설치 및 실행 가이드.

---

## 시스템 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| OS | Windows 10 64-bit | Windows 11 |
| Python | 3.13+ | 3.13+ |
| Node.js | 18+ | 20+ |
| 패키지 매니저 | uv | uv |
| GPU | - | NVIDIA CUDA 지원 GPU |
| RAM | 8 GB | 16 GB+ |

> **참고**: GPU가 없으면 세그멘테이션/FEA가 CPU 모드로 자동 전환됩니다.

---

## 설치

### 백엔드 (Python)

```bash
# uv 패키지 매니저로 의존성 설치
uv sync
```

주요 의존성: FastAPI, Uvicorn, Taichi, PyTorch, SimpleITK, scipy, numpy

### 프론트엔드 (Node.js)

```bash
cd frontend
npm install
```

주요 의존성: Svelte 5, Three.js, TypeScript, Vite

---

## 실행

### 방법 1: 시작 스크립트 (권장)

```bash
# 백엔드 서버 (포트 8000)
./start_backend.bat    # Windows
./start_backend.sh     # Linux/Mac

# 프론트엔드 개발 서버 (포트 5174)
./start_frontend.bat   # Windows
./start_frontend.sh    # Linux/Mac
```

### 방법 2: 직접 실행

```bash
# 백엔드
uv run uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --reload

# 프론트엔드 (별도 터미널)
cd frontend && npm run dev
```

### 방법 3: 프로덕션 빌드

```bash
# 프론트엔드 빌드 → frontend/dist/
cd frontend && npm run build

# 백엔드만 실행 (빌드된 프론트엔드를 정적 파일로 서빙)
uv run uvicorn backend.api.app:app --host 0.0.0.0 --port 8000
```

브라우저에서 `http://localhost:5174` (개발) 또는 `http://localhost:8000` (프로덕션)에 접속합니다.

---

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `SPINE_SIM_DATA_DIR` | 업로드 파일 저장 디렉토리 | `~/.spine_sim` |
| `SPINE_SIM_CORS_ORIGINS` | CORS 허용 오리진 (콤마 구분) | `localhost:5174,8000` |
| `VITE_BACKEND_URL` | 프론트엔드→백엔드 URL | `http://localhost:8000` |

---

## 테스트

```bash
# 전체 테스트 실행
uv run pytest backend/ -v

# 특정 모듈만
uv run pytest backend/fea/ -v          # FEA 프레임워크
uv run pytest backend/preprocessing/ -v # 전처리
uv run pytest backend/anatomy/ -v       # 해부학 모듈
uv run pytest backend/api/ -v           # API 서버
```

---

## 프로젝트 구조

```
pysim/
├── frontend/               # Svelte 5 + TypeScript 프론트엔드
│   ├── src/                # 소스 (components/, lib/)
│   ├── public/stl/         # 정적 에셋 (STL)
│   └── dist/               # 빌드 출력
│
├── backend/                # Python 백엔드
│   ├── api/                # FastAPI 서버 + WebSocket (L4)
│   ├── orchestrator/       # 파이프라인 오케스트레이터 (L3)
│   ├── anatomy/            # 부위별 해부학 특화 로직 (L2.5b)
│   ├── preprocessing/      # 범용 전처리 (L2.5a)
│   ├── fea/                # FEA 프레임워크 (L2)
│   │   ├── framework/      # 통합 API (Domain, Solver, Scene)
│   │   ├── fem/            # FEM 솔버 + 재료 모델
│   │   ├── peridynamics/   # NOSB-PD 파괴 해석
│   │   └── spg/            # SPG 무격자법
│   ├── segmentation/       # CT 세그멘테이션 엔진 (L1)
│   ├── utils/              # 볼륨 I/O, 공통 유틸 (L0)
│   ├── config/             # 파이프라인 설정 (pipeline.toml)
│   └── scripts/            # 유틸리티 스크립트
│
├── docs/                   # 문서
│   └── archive/            # 이전 진행 기록
│
├── start_backend.bat/sh    # 시작 스크립트
├── start_frontend.bat/sh
├── pyproject.toml          # Python 프로젝트 설정
└── PROJECT_STATUS.md       # 프로젝트 현황
```

### 의존성 레이어

```
L0: utils/          ← 외부 의존성 없음
L1: segmentation/   ← utils 참조
L2: fea/            ← 자체 완결
L2.5a: preprocessing/ ← fea + segmentation 참조
L2.5b: anatomy/     ← preprocessing + segmentation 참조
L3: orchestrator/   ← 전체 참조
L4: api/            ← 전체 참조 (최상위)
```

---

## 문서 목차

- **[API Reference](api_reference.md)** — REST/WebSocket 엔드포인트, 요청/응답 스키마
- **[FEA Framework](fea_framework.md)** — Domain, Material, Solver, Scene 통합 API
- **[FEM Solver](fem_solver.md)** — 솔버, 재료 모델, 메쉬 임포트, VTK 내보내기
- **[Preprocessing](preprocessing.md)** — CT 라벨맵 → 자동 다물체 해석 파이프라인
