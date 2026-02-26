# CLAUDE.md

Claude Code 작업 지시 사항

## Project Overview

**Spine Surgery Planner** - UBE/Biportal 내시경 척추 수술 계획 및 시뮬레이션 도구

CT 영상으로부터 수술 전 계획 수립: 나사/케이지 배치, 내시경 시야 시뮬레이션, 진입 경로 검증

## Build & Run Commands

```bash
# 의존성 설치 (uv 사용)
uv sync

# 백엔드 실행
uv run uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --reload

# 프론트엔드 개발
cd frontend && npm run dev

# 프론트엔드 빌드
cd frontend && npm run build

# 테스트 실행
uv run pytest backend/ -v
```

## Project Structure

```
pysim/
├── frontend/          # Svelte 프론트엔드
│   ├── src/
│   ├── public/stl/    # STL 에셋
│   └── dist/          # 빌드 출력
├── backend/           # Python 백엔드
│   ├── utils/         # 유틸리티 (L0)
│   ├── segmentation/  # CT 세그멘테이션 (L1)
│   ├── fea/           # 유한요소/PD/SPG 해석 (L2)
│   ├── preprocessing/ # 범용 전처리 (L2.5a)
│   ├── anatomy/       # 부위별 특화 로직 (L2.5b)
│   ├── orchestrator/  # 워크플로우 오케스트레이션 (L3)
│   └── api/           # FastAPI 서버 (L4)
└── pyproject.toml
```

## Tech Stack

- **Three.js** - 웹 기반 3D 시뮬레이터 (메인)
- **Python 3.13+** - 백엔드/분석
- **FEM** - 유한요소법 해석 (자체 구현)
- **NOSB-PD** - Peridynamics 파괴 해석 (자체 구현)

## Key Constraints

- **Windows 배포 필수** (병원 환경)
- CT 메쉬 품질이 불규칙하므로 메쉬 민감도 낮은 방법 사용
- 내시경 시뮬레이션이 핵심 차별점 - 포탈 위치, 시야 범위, 사각지대, 진입 충돌 지점

## Important Rules

1. 주석은 반드시 한글로 달아라
2. 변수명은 절대 한글로 작성하지 마라
3. 사용자에게 설명은 반드시 한글로 해라
4. 한 작업이 끝날 때 마다 `PROJECT_STATUS.md` 파일을 업데이트 해라
5. 웹 UI 테스트는 반드시 **Playwright MCP** (`@playwright/mcp`)를 사용해라. 직접 Python 스크립트를 작성하지 말고 MCP 도구를 활용할 것.
