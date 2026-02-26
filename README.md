# Spine Surgery Planner

UBE/Biportal 내시경 척추 수술 계획 및 시뮬레이션 도구.

CT 영상으로부터 수술 전 계획을 수립합니다: 자동 세그멘테이션, 3D 시각화, 임플란트 배치, 구조 해석.

## 주요 기능

- **CT DICOM 자동 세그멘테이션** — TotalSpineSeg / TotalSegmentator 엔진
- **3D 척추 메쉬 시각화** — Three.js 기반 웹 뷰어
- **임플란트 배치 시뮬레이션** — Pedicle Screw, Interbody Cage, Rod
- **FEA 구조 해석** — FEM / Peridynamics / SPG 멀티솔버
- **수술 가이드라인 생성** — 삽입 경로, 안전 영역, 깊이 마커

## 빠른 시작

```bash
# 의존성 설치
uv sync
cd frontend && npm install && cd ..

# 서버 실행
./start_backend.bat    # 백엔드 (포트 8000)
./start_frontend.bat   # 프론트엔드 (포트 5174)
```

자세한 설치/실행 방법은 [Getting Started](docs/getting_started.md) 참조.

## 문서

| 문서 | 내용 |
|------|------|
| [Getting Started](docs/getting_started.md) | 설치, 실행, 프로젝트 구조 |
| [API Reference](docs/api_reference.md) | REST/WebSocket 엔드포인트, 요청/응답 스키마 |
| [FEA Framework](docs/fea_framework.md) | Domain, Material, Solver, Scene 통합 API |
| [FEM Solver](docs/fem_solver.md) | 솔버, 재료 모델, 메쉬 임포트, VTK 내보내기 |
| [Preprocessing](docs/preprocessing.md) | CT 라벨맵 → 자동 다물체 해석 파이프라인 |

## 기술 스택

- **프론트엔드**: Svelte 5 + TypeScript + Three.js + Vite
- **백엔드**: Python 3.13+ + FastAPI + WebSocket + Taichi GPU
- **세그멘테이션**: TotalSpineSeg / TotalSegmentator / nnU-Net v2
- **해석**: 자체 구현 FEM + NOSB-PD + SPG + FEM↔PD 적응적 커플링
- **재료 모델**: Linear Elastic, Neo-Hookean, Mooney-Rivlin, Ogden, J2 Plasticity, Transverse Isotropic

## 테스트

```bash
uv run pytest backend/ -v    # 679개 테스트
```
