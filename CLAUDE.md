# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Spine Surgery Planner** - UBE/Biportal 내시경 척추 수술 계획 및 시뮬레이션 도구

CT 영상으로부터 수술 전 계획 수립: 나사/케이지 배치, 내시경 시야 시뮬레이션, 진입 경로 검증

## Build & Run Commands

```bash
# 의존성 설치 (uv 사용)
uv sync

# 시뮬레이터 실행
uv run python -m spine_sim.app.simulator

# 테스트 실행
uv run pytest spine_sim/ -v
```

## Tech Stack

- **Python 3.13+** with **Taichi** (GPU 가속 컴퓨팅)
- **Three.js** - 웹 기반 3D 시뮬레이터 (신규 추가, 2026-02)
- **MONAI** - CT 자동 세그멘테이션 (아직 미구현)
- **FEM** - 유한요소법 해석 (자체 구현 완료)
- **NOSB-PD** - Peridynamics 파괴 해석 (자체 구현 완료)
- **Taichi GGUI** - 렌더링 및 UI

## 현재 구현 상태 (2026-01)

### ✅ 완료된 모듈

#### 1. 구조 해석 (spine_sim/analysis/)

**NOSB-PD (Peridynamics)** - `analysis/peridynamics/`
- 입자 시스템, 이웃 탐색, 본드 시스템
- NOSB-PD 힘 계산 (correspondence material)
- 준정적 솔버 (kinetic damping + viscous damping)
- 뼈 재료 모델
- 테스트: 11개 통과

**FEM** - `analysis/fem/`
- TET4, TRI3 요소
- Linear Elastic, Neo-Hookean 재료
- Static solver (Newton-Raphson)
- 테스트: 6개 통과

#### 2. 수술 시뮬레이터 (spine_sim/core/, endoscope/, app/)

**Core** - `core/`
- `mesh.py`: 삼각형 메쉬, STL/OBJ 로딩
- `volume.py`: 복셀 볼륨, 드릴링 기능
- `collision.py`: Ray casting 충돌 감지
- `transform.py`: 3D 변환

**Endoscope** - `endoscope/`
- `camera.py`: 내시경 카메라 (FOV, 투영)
- `instrument.py`: 내시경 도구 (위치, 충돌)

**App** - `app/`
- `simulator.py`: Taichi GGUI 기반 메인 시뮬레이터

#### 3. 웹 시뮬레이터 (web/) - 신규 2026-02

**Three.js 기반 웹 버전** - `web/`
- `index.html`: UI 레이아웃
- `src/main.js`: Three.js 메인 코드, STL 로딩, 이벤트 처리
- `src/voxel.js`: 복셀 시스템, Marching Cubes
- 복셀 기반 드릴링 구현 완료
- L4/L5 척추 분리 배치
- 50+ FPS 성능

### 🔲 미구현

- MONAI 세그멘테이션
- 임플란트 배치 (screw, cage)
- 내시경 뷰 별도 렌더링 (PIP)
- 3D Slicer 연동

## 모듈 구조

```
spine_sim/
├── core/                      # 핵심 데이터 구조
│   ├── mesh.py               # TriangleMesh - STL/OBJ 로딩
│   ├── volume.py             # VoxelVolume - 복셀 편집/드릴링
│   ├── collision.py          # CollisionDetector - Ray casting
│   └── transform.py          # Transform - 3D 변환
├── endoscope/                 # 내시경 시뮬레이션
│   ├── camera.py             # EndoscopeCamera
│   └── instrument.py         # Endoscope
├── app/                       # GUI 애플리케이션
│   └── simulator.py          # SpineSimulator (Taichi GGUI)
└── analysis/                  # 구조 해석
    ├── fem/                   # FEM 모듈
    │   ├── core/mesh.py      # FEMesh
    │   ├── material/         # LinearElastic, NeoHookean
    │   └── solver/           # StaticSolver
    └── peridynamics/          # NOSB-PD 모듈
        ├── core/             # particles, bonds, neighbor, nosb
        ├── material/         # bone material
        └── solver/           # NOSBSolver

web/                           # Three.js 웹 시뮬레이터 (신규)
├── index.html                 # UI 레이아웃
├── src/
│   ├── main.js               # Three.js 메인
│   └── voxel.js              # 복셀 + Marching Cubes
└── stl/                       # 샘플 STL 파일
```

## Key Constraints

- **Windows 배포 필수** (병원 환경)
- CT 메쉬 품질이 불규칙하므로 메쉬 민감도 낮은 방법 사용
- 내시경 시뮬레이션이 핵심 차별점 - 포탈 위치, 시야 범위, 사각지대, 진입 충돌 지점

## 주요 사용법

### 웹 시뮬레이터 실행 (권장)
```bash
cd web
python -m http.server 8080
# 브라우저에서 http://localhost:8080 접속
```

### Taichi 시뮬레이터 실행
```python
import taichi as ti
ti.init(arch=ti.gpu)

from spine_sim.app.simulator import SpineSimulator

sim = SpineSimulator(width=1400, height=900)
sim.load_model("vertebra.stl", name="L5")  # 3D Slicer에서 만든 모델
sim.add_sample_vertebra("L4", position=(0, 30, 0))
sim.run()
```

### 복셀 드릴링
```python
from spine_sim.core.volume import VoxelVolume

vol = VoxelVolume(resolution=(64, 64, 64), spacing=0.5)
vol.fill_sphere(0, 0, 0, 10, 1.0, 1)  # 뼈 채우기
vol.drill(0, 0, -20, 0, 0, 1, 2, 30)  # 드릴링
```

### 충돌 감지
```python
from spine_sim.core.collision import CollisionDetector

detector = CollisionDetector()
detector.load_mesh(vertices, faces)
hit = detector.ray_cast([0,0,-10], [0,0,1])
```

## GUI 조작법

| 조작 | 키/마우스 |
|------|-----------|
| 카메라 회전 | 마우스 드래그 |
| 줌 | +/- 키 |
| 내시경 전진/후진 | W/S |
| 내시경 좌우 회전 | A/D |
| 내시경 상하 회전 | Q/E |

## 테스트

```bash
# 전체 테스트 (17개)
uv run pytest spine_sim/ -v

# FEM만
uv run pytest spine_sim/analysis/fem/ -v

# Peridynamics만
uv run pytest spine_sim/analysis/peridynamics/ -v
```

## Important Rules

1. 주석은 반드시 한글로 달아라
2. 변수명은 절대 한글로 작성하지 마라
3. 사용자에게 설명은 반드시 한글로 해라
4. 한 작업이 끝날 때 마다 진행 상황을 마크다운 파일로 업데이트 해라.

## 참고 문서

- `spine_sim/analysis/peridynamics/NOSB_PD_PROGRESS.md` - NOSB-PD 구현 상세
- `spine_sim/analysis/fem/FEM_PROGRESS.md` - FEM 구현 상세
- `spine_sim/SIMULATOR_PROGRESS.md` - 시뮬레이터 구현 상세
- `web/WEB_SIMULATOR_PROGRESS.md` - **웹 시뮬레이터 진행 상황 (최신)**
- `rough_plan.md` - 전체 프로젝트 계획
