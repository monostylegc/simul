# Spine Surgery Planner — 프로젝트 목표 및 워크플로우

최종 업데이트: 2026-02-25 (CT/DICOM 파이프라인 End-to-End 검증 + 버그 수정)

---

## 프로젝트 목표

**UBE/Biportal 내시경 척추 수술 계획 및 시뮬레이션 도구**

환자의 CT/MRI 영상으로부터 수술 전 계획을 수립하고, 나사/케이지 등 임플란트 배치를 시뮬레이션하며, 구조해석을 통해 수술 안전성을 사전 검증하는 end-to-end 플랫폼.

### 핵심 가치
- **수술 전 계획 최적화**: 환자별 해부학적 구조에 맞춘 임플란트 위치/크기 결정
- **구조적 안전성 검증**: 유한요소 해석(FEM/PD/SPG)으로 뼈-임플란트 계면 응력 사전 평가
- **웹 기반 통합 플랫폼**: 별도 소프트웨어 설치 없이 브라우저에서 전체 워크플로우 수행
- **병원 배포 대응**: Windows 환경 호환, 직관적 CAE 스타일 UI

### 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Three.js 웹 시뮬레이터 (브라우저)                  │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐          │
│  │ main.js  │ pre.js   │ post.js  │implant.js│ voxel.js │          │
│  │ 씬/UI    │ 전처리   │ 후처리   │ 임플란트 │ 복셀화   │          │
│  └────┬─────┴────┬─────┴────┬─────┴──────────┴──────────┘          │
│       │          │          │                                       │
│       └──────────┼──────────┘                                       │
│                  │ ws.js (WebSocket)                                 │
└──────────────────┼──────────────────────────────────────────────────┘
                   │ JSON 양방향 통신
┌──────────────────┼──────────────────────────────────────────────────┐
│                  │ FastAPI 서버 (Python)                             │
│  ┌───────────────▼───────────────┐                                  │
│  │     ws_handler.py (라우팅)     │                                  │
│  └──┬────────┬────────┬────────┬─┘                                  │
│     │        │        │        │                                     │
│  ┌──▼──┐ ┌──▼──┐ ┌──▼───┐ ┌──▼──────────┐                         │
│  │세그멘│ │메쉬 │ │자동  │ │해석         │                         │
│  │테이션│ │추출 │ │재료  │ │파이프라인   │                         │
│  │파이프│ │파이프│ │매핑  │ │             │                         │
│  └──┬──┘ └──┬──┘ └──┬──┘ └──┬──────────┘                         │
│     │       │       │       │                                       │
│  ┌──▼───────▼───────▼───────▼──────────────────────────────┐       │
│  │           통합 FEA 프레임워크 (Taichi GPU)               │       │
│  │  ┌─────┐  ┌──────────────┐  ┌─────┐  ┌──────┐          │       │
│  │  │ FEM │  │ Peridynamics │  │ SPG │  │Scene │          │       │
│  │  │정적 │  │ NOSB-PD      │  │무격자│  │접촉  │          │       │
│  │  │동적 │  │ 파괴해석     │  │극한변│  │해석  │          │       │
│  │  └─────┘  └──────────────┘  └─────┘  └──────┘          │       │
│  └─────────────────────────────────────────────────────────┘       │
└────────────────────────────────────────────────────────────────────┘
```

---

## End-to-End 워크플로우 (7단계)

```
DICOM 폴더 ──→ [0] DICOM→NIfTI 변환 ──→ [1] 세그멘테이션 ──→ [2] 3D 모델 생성 ──→ [3] 수술 도구 배치
                                                                                            │
                                          [6] 후처리 시각화 ←── [5] 구조해석 ←── [4] 전처리  ←┘
```

> **원클릭 자동화**: 0단계~2단계는 DICOM 폴더 선택만으로 자동 연쇄 실행 가능

### 0단계: DICOM 원클릭 파이프라인 — ✅ 완료

병원에서 DICOM 폴더를 선택하면 변환→세그멘테이션→메쉬 추출→3D 표시까지 자동으로 처리한다.

| 항목 | 내용 |
|------|------|
| **입력** | DICOM 폴더 (webkitdirectory로 브라우저에서 폴더 선택) |
| **출력** | 3D 표면 메쉬 (Three.js 렌더링) |
| **자동화 단계** | DICOM 업로드 → NIfTI 변환 → 세그멘테이션 → 메쉬 추출 (4단계 연쇄) |
| **DICOM 변환** | SimpleITK `ImageSeriesReader` — 복수 시리즈 시 최대 슬라이스 자동 선택 |
| **Modality 감지** | DICOM 태그에서 CT/MR 자동 감지 → 엔진 자동 선택 (CT→TotalSeg, MR→TotalSpineSeg) |
| **GPU 폴백** | GPU 실패 시 CPU 자동 재시도 |
| **핵심 파일** | `src/server/dicom_converter.py`, `src/server/ws_handler.py` |

**프로토콜**: REST `POST /api/upload_dicom` (파일 업로드) → WS `run_dicom_pipeline` → `pipeline_step` (진행률) → `pipeline_result` (최종 메쉬)

---

### 1단계: 세그멘테이션 (CT/MRI → 라벨맵) — ✅ 완료

환자의 CT 또는 MRI 영상에서 척추골, 디스크, 연조직을 자동으로 분류한다.

| 항목 | 내용 |
|------|------|
| **입력** | CT/MRI NIfTI 파일 (`.nii.gz`) |
| **출력** | 라벨맵 NIfTI (각 복셀에 SpineLabel 값 할당) |
| **지원 엔진** | TotalSegmentator (CT), TotalSpineSeg (MRI), SpineUnified (CT+MRI 통합, nnU-Net v2) |
| **라벨 체계** | `SpineLabel` IntEnum — 척추골 C1~Sacrum (101~125), 디스크 C2C3~L5S1 (201~223), 연조직 (301~302) |
| **핵심 API** | `create_engine("totalseg"|"totalspineseg"|"spine_unified")` → `engine.segment(input, output)` |
| **핵심 파일** | `src/segmentation/{factory.py, base.py, labels.py, totalseg.py, totalspineseg.py, nnunet_spine.py}` |

**데이터 흐름**: NIfTI → 엔진별 추론 → 엔진 고유 라벨 → `convert_to_standard()` → SpineLabel 통합 라벨맵

---

### 2단계: 3D 모델 생성 (라벨맵 → 표면 메쉬) — ✅ 완료

라벨맵에서 각 해부학적 구조물의 3D 표면 메쉬를 추출하여 웹 뷰어에 표시한다.

| 항목 | 내용 |
|------|------|
| **입력** | 라벨맵 NIfTI + 추출할 라벨 목록 |
| **출력** | 라벨별 메쉬 `{vertices[][], faces[][], material_type, color}` |
| **알고리즘** | scikit-image `marching_cubes` (이진마스크 → 삼각형 표면) |
| **후처리** | 선택적 가우시안 평활화 (`sigma=0.8`) |
| **색상 구분** | bone `#e6d5c3`, disc `#6ba3d6`, soft_tissue `#f0a0b0` |
| **핵심 API** | `extract_meshes(request, progress_callback)` |
| **핵심 파일** | `src/server/mesh_extract_pipeline.py` |

**데이터 흐름**: 라벨맵 → 라벨별 이진 마스크 → Marching Cubes → 표면 메쉬 → WebSocket → Three.js BufferGeometry

---

### 3단계: 수술 도구 배치 (임플란트 모델링) — ✅ 완료

나사, 케이지, 로드 등 임플란트 STL 모델을 3D 환경에서 직접 배치하고 수술 계획을 저장한다.

| 항목 | 내용 |
|------|------|
| **입력** | 임플란트 STL 파일 + 재료 타입 선택 |
| **출력** | 수술 계획 JSON `{implants: [{name, position[3], rotation[3], scale[3], material}]}` |
| **인터랙션** | TransformControls — 이동(Translate) / 회전(Rotate) / 크기(Scale) 모드 전환 |
| **재료 프리셋** | titanium `#8899aa`, PEEK `#ccbb88`, cobalt-chrome `#99aacc`, stainless steel `#aaaaaa` |
| **저장/복원** | `exportPlan()` → JSON 다운로드, `importPlan(data)` → 복원 |
| **추가 기능** | 구체 드릴(복셀 제거)로 뼈 가공 시뮬레이션, Undo/Redo 지원 |
| **핵심 파일** | `src/simulator/src/implant.js`, `src/simulator/src/voxel.js` |

**데이터 흐름**: STL 로드 → Three.js Mesh 생성 → 사용자 배치(이동/회전) → 수술 계획 JSON 내보내기

---

### 4단계: 전처리 (경계조건 + 재료 설정) — ✅ 완료

해석을 위해 경계조건(고정/하중)과 재료 물성을 설정한다.

| 항목 | 내용 |
|------|------|
| **입력** | 3D 메쉬/복셀 모델 + 라벨맵 |
| **출력** | `AnalysisRequest {positions, volumes, boundary_conditions[], materials[], method}` |
| **경계조건 설정** | (a) 구체 브러쉬: 복셀 단위 페인팅 선택 <br/> (b) 면 선택: BFS 기반 연결면 확장 (법선 유사도 cos(30°) 기준) |
| **BC 타입** | Fixed BC (초록 시각화) — 변위 구속 <br/> Force BC (빨강 화살표) — 하중 적용 (Ctrl+드래그로 방향 조정) |
| **재료 할당** | 자동: SpineLabel → SPINE_MATERIAL_DB (8종) 자동 매핑 (제안값) <br/> 수동: E/ν/ρ 직접 편집 UI |
| **재료 DB** | bone(15GPa), cancellous(1GPa), disc(10MPa), soft_tissue(1MPa), titanium(110GPa), PEEK(4GPa), cobalt-chrome(230GPa), stainless steel(200GPa) |
| **핵심 파일** | `src/simulator/src/pre.js`, `src/server/auto_material.py` |

**데이터 흐름**: 복셀 선택 → BC 적용 → 재료 할당 → `buildAnalysisRequest(method)` → AnalysisRequest JSON 조립

---

### 5단계: 구조해석 (FEA) — ✅ 완료

통합 FEA 프레임워크로 3가지 해석 방법 중 하나를 선택하여 구조 응답을 계산한다.

| 항목 | 내용 |
|------|------|
| **입력** | `AnalysisRequest {positions, volumes, method, boundary_conditions, materials}` |
| **출력** | `{displacements[][], stress[], damage[], info{converged, iterations, elapsed_time}}` |
| **해석 방법** | **FEM** — 유한요소법 (정적/동적, Newton-Raphson, Newmark-beta) <br/> **PD** — Peridynamics (NOSB-PD, 준정적/명시적, 파괴 해석 가능) <br/> **SPG** — Smoothed Particle Galerkin (극한 변형, 무격자법) |
| **GPU 가속** | 자동 감지: CUDA → Vulkan → CPU 폴백 |
| **정밀도** | 전체 f64 (배정밀도) 통일 |
| **다중 물체** | Scene API: 이종 솔버 간 접촉 해석 (노드-노드 페널티, KDTree 기반) |
| **강체** | RigidBody + PrescribedMotion: 규정 운동(회전/병진) 강체, 나사/임플란트 시뮬레이션 |
| **마찰 접촉** | Coulomb 마찰: penalty-regularized stick/slip, 정적/동적 마찰 계수 |
| **진행률** | WebSocket 콜백: init → setup → bc → material → solving → postprocess → done |
| **핵심 API** | `init()` → `create_domain(Method.FEM|PD|SPG, ...)` → `Solver(domain, material).solve()` |
| **핵심 파일** | `src/server/analysis_pipeline.py`, `src/fea/framework/{runtime.py, domain.py, solver.py, scene.py}` |

**데이터 흐름**: AnalysisRequest → Taichi 초기화 → Domain 생성 → BC/재료 적용 → 솔버 수렴 → 변위/응력/손상 → WebSocket 전송

---

### 6단계: 후처리 시각화 — ✅ 완료

해석 결과를 3D 컬러맵으로 시각화하고 수술 전/후 비교 분석을 수행한다.

| 항목 | 내용 |
|------|------|
| **입력** | 해석 결과 `{displacements, stress, damage}` |
| **출력** | Three.js Points Cloud (Jet 컬러맵 적용) + 컬러바 |
| **시각화 모드** | Displacement (변위 크기) / Stress (von Mises 응력) / Damage (손상 지수 0~1) |
| **조절 파라미터** | 변위 확대배율 (기본 10×), 입자 크기, 컬러맵 범위 |
| **수술 전/후 비교** | 수술 전 결과 저장 → 수술 후 결과와 차이 시각화 |
| **영역 필터** | 임플란트 주변 반경 지정 → 해당 영역만 응력 분석 |
| **핵심 파일** | `src/simulator/src/post.js`, `src/simulator/src/colormap.js` |

**데이터 흐름**: 해석 결과 수신 → 모드별 스칼라 정규화 → Jet 컬러맵 변환 → Points Cloud 렌더링 + 컬러바

---

## 프로젝트 디렉토리 구조

```
src/
├── core/                          # 핵심 유틸리티
│   └── volume_io.py              # NIfTI/NPZ 볼륨 I/O
├── fea/                          # 유한요소/다중 물리 해석
│   ├── fem/                      # 유한요소법 (FEM)
│   │   ├── core/                # 메쉬, 적분, 기본 요소
│   │   ├── material/            # 선형 탄성, Neo-Hookean 재료
│   │   ├── solver/              # 정적/동적 솔버 (Newton-Raphson, Newmark-β, Central Diff)
│   │   └── tests/               # FEM 테스트 (39개)
│   ├── peridynamics/            # Peridynamics (PD)
│   │   ├── core/                # 입자, 결합, 손상, 이웃
│   │   ├── material/            # PD 선형 탄성
│   │   ├── solver/              # NOSB 명시적/준정적 솔버
│   │   └── tests/               # PD 테스트 (22개)
│   ├── spg/                     # Smoothed Particle Galerkin (SPG)
│   │   ├── core/                # RKPM 형상함수, 안정화력 커널
│   │   ├── material/            # SPG 재료
│   │   ├── solver/              # SPG 명시적 솔버
│   │   └── tests/               # SPG 테스트 (31개)
│   ├── framework/               # 통합 프레임워크 (핵심 인터페이스)
│   │   ├── runtime.py           # Taichi 런타임 관리 (GPU 자동 감지)
│   │   ├── domain.py            # 통합 Domain API (Method.FEM/PD/SPG)
│   │   ├── material.py          # 통합 Material 클래스
│   │   ├── solver.py            # 통합 Solver 인터페이스
│   │   ├── scene.py             # 다중 물체 접촉 장면 관리
│   │   ├── contact.py           # 노드-노드 페널티 접촉 (KDTree)
│   │   ├── result.py            # SolveResult 데이터 클래스
│   │   └── _adapters/           # FEM/PD/SPG 어댑터 (Adapter 패턴)
│   └── tests/                   # 통합 벤치마크 (L4+disc+L5 압축 등)
├── pipeline/                    # CLI 파이프라인 (Typer)
│   ├── cli.py                   # 7개 서브커맨드 (segment, solve, report, pipeline, server 등)
│   ├── config.py                # Pydantic 설정 + TOML 로드
│   ├── cache.py                 # SHA256 해시 기반 캐시
│   └── stages/                  # 단계별 처리 모듈 (segment, postprocess, voxelize, solve, report)
├── segmentation/                # AI 세그멘테이션 엔진
│   ├── labels.py                # SpineLabel IntEnum (100번대=척추, 200번대=디스크, 300번대=연조직)
│   ├── factory.py               # create_engine("totalseg"|"totalspineseg"|"spine_unified")
│   ├── totalseg.py              # TotalSegmentator 래퍼 (CT)
│   ├── totalspineseg.py         # TotalSpineSeg 래퍼 (MRI)
│   ├── nnunet_spine.py          # SpineUnified — nnU-Net v2 CT+MRI 통합
│   └── training/                # 학습 데이터 준비 파이프라인
├── server/                      # FastAPI 백엔드
│   ├── app.py                   # REST(업로드) + WebSocket 엔드포인트 + 정적 파일 서빙
│   ├── models.py                # Pydantic 모델 (AnalysisRequest, SurgicalPlan 등)
│   ├── ws_handler.py            # WebSocket 메시지 라우팅 (5종 파이프라인 호출)
│   ├── dicom_converter.py       # DICOM→NIfTI 변환 (SimpleITK, 복수 시리즈 자동 선택)
│   ├── analysis_pipeline.py     # FEA 프레임워크 호출 파이프라인
│   ├── segmentation_pipeline.py # 세그멘테이션 엔진 호출 (GPU→CPU 자동 폴백)
│   ├── mesh_extract_pipeline.py # Marching Cubes 메쉬 추출
│   ├── auto_material.py         # SpineLabel → 재료 자동 매핑 (8종 DB)
│   └── tests/                   # 서버 테스트 (44개)
└── simulator/                   # Three.js 웹 시뮬레이터
    ├── index.html               # 메인 HTML (탭 기반 CAE UI)
    └── src/
        ├── main.js              # Three.js 씬/UI/이벤트 핸들러 (메인 엔트리)
        ├── pre.js               # PreProcessor — BC 설정, 재료 할당, 해석 요청 조립
        ├── post.js              # PostProcessor — 컬러맵 시각화, 전/후 비교
        ├── implant.js           # ImplantManager — STL 배치, TransformControls
        ├── voxel.js             # VoxelGrid — 복셀화, 구체 드릴링
        ├── ws.js                # WSClient — WebSocket 통신
        ├── colormap.js          # Jet 컬러맵 유틸리티
        └── nrrd.js              # NRRD 로더 (3D Slicer 호환)
```

---

## WebSocket 통신 프로토콜

```
클라이언트 → 서버:
  {"type": "segment",             "data": SegmentationRequest}   # 세그멘테이션 실행
  {"type": "extract_meshes",      "data": MeshExtractRequest}    # 3D 메쉬 추출
  {"type": "auto_material",       "data": AutoMaterialRequest}   # 자동 재료 매핑
  {"type": "run_analysis",        "data": AnalysisRequest}       # FEA 해석 실행
  {"type": "run_dicom_pipeline",  "data": DicomPipelineRequest}  # DICOM 원클릭 자동화
  {"type": "ping"}                                               # 연결 확인

REST 엔드포인트:
  POST /api/upload_dicom   files: List[UploadFile]  # DICOM 다중 파일 업로드

서버 → 클라이언트:
  {"type": "progress",         "data": {"step": "init|setup|bc|solving|done", ...}}
  {"type": "segment_result",   "data": {labels_path, n_labels, label_info[]}}
  {"type": "meshes_result",    "data": {meshes: [{vertices, faces, color}]}}
  {"type": "material_result",  "data": {materials: [{name, E, nu, density}]}}
  {"type": "result",           "data": {displacements, stress, damage, info}}
  {"type": "pipeline_step",    "data": {step, message, phase}}   # DICOM 파이프라인 진행률
  {"type": "pipeline_result",  "data": {meshes, patient_info}}   # DICOM 파이프라인 최종 결과
  {"type": "error",            "data": {"message": "..."}}
```

---

## 기술 스택

| 카테고리 | 기술 |
|---------|------|
| **프론트엔드** | Three.js (3D 렌더링), ES Modules, TransformControls |
| **백엔드** | Python 3.13+, FastAPI, WebSocket, Pydantic |
| **해석 엔진** | Taichi (GPU 가속), NumPy, SciPy |
| **세그멘테이션** | TotalSegmentator, TotalSpineSeg, nnU-Net v2 |
| **메쉬 처리** | scikit-image (Marching Cubes), STL 로더 |
| **CLI** | Typer, Rich (콘솔 출력) |
| **패키지 관리** | uv (빌드: hatchling) |
| **테스트** | pytest (309 passed), Playwright (웹 UI) |

---

## 실행 모드

| 모드 | 명령어 | 설명 |
|------|--------|------|
| **웹 통합** | `uv run spine-sim server --port 8000` | 해석 서버 + 웹 시뮬레이터 통합 |
| **웹 단독** | `cd src/simulator && python -m http.server 8080` | 시뮬레이터만 (해석 불가) |
| **CLI 파이프라인** | `uv run spine-sim pipeline input.nii.gz -o output/` | CT → 해석 → 리포트 자동화 |
| **개별 스테이지** | `uv run spine-sim segment|solve|report ...` | 단계별 개별 실행 |

---

## 단계별 구현 상태 요약

| 단계 | 기능 | 상태 |
|------|------|------|
| 1. 세그멘테이션 | CT/MRI 자동 세그멘테이션 (3 엔진) | ✅ 완료 |
| 2. 3D 모델 생성 | Marching Cubes 메쉬 추출 | ✅ 완료 |
| 3. 수술 도구 배치 | 임플란트 STL 배치 + 드릴 | ✅ 완료 |
| 4. 전처리 | BC 설정 + 재료 할당 | ✅ 완료 |
| 5. 구조해석 | FEM/PD/SPG 통합 프레임워크 | ✅ 완료 |
| 6. 후처리 | 컬러맵 시각화 + 비교 분석 | ✅ 완료 |
| — | 내시경 시뮬레이션 (포탈 시야/사각지대) | 🔲 미구현 |

---

# 프로젝트 진행 상황

최종 업데이트: 2026-02-25

## 오늘 작업 내역 (2026-02-25)

### 완료

1. **구성 모델(Constitutive Model) 확장 — Mooney-Rivlin + Ogden FEM 구현**

   기존에 Linear Elastic + Neo-Hookean만 지원하던 FEM 재료 모델에
   **Mooney-Rivlin 2-파라미터 초탄성**과 **1-term Ogden 초탄성** 모델을 신규 구현.

   - **`src/fea/fem/material/mooney_rivlin.py`** (신규 290줄)
     - ψ = C10·(I₁-3) + C01·(I₂-3) + (1/D1)·(J-1)²
     - Taichi GPU 커널 (`@ti.data_oriented`) — compute_stress, compute_nodal_forces
     - `from_engineering(E, ν)` 자동 변환 유틸리티
   - **`src/fea/fem/material/ogden.py`** (신규 320줄)
     - ψ = (μ/α)·(λ₁^α + λ₂^α + λ₃^α - 3) + (1/D1)·(J-1)²
     - Cardano 공식 기반 3D 고유치 분해 (B 텐서 → 주연신비)
     - Rivlin-Ericksen 표현식으로 응력 텐서 재구성
   - **`src/fea/fem/material/__init__.py`** — MooneyRivlin, Ogden export 추가

2. **프레임워크 + 서버 구성 모델 디스패치 확장**

   - **`src/fea/framework/material.py`** — `constitutive_model` 필드 + `_create_fem_material()` 분기
     (linear_elastic / neo_hookean / mooney_rivlin / ogden)
   - **`src/server/models/analysis.py`** — MaterialRegion에 constitutive_model Literal + C10/C01/D1/mu_ogden/alpha_ogden 추가
   - **`src/server/services/analysis.py`** — FEM 재료 생성을 `FrameworkMaterial._create_fem_material()` 위임으로 변경

3. **프론트엔드 데이터 레이어 확장**

   - **`materials.svelte.ts`** — ConstitutiveModel 타입, CONSTITUTIVE_MODELS 메타정보,
     enuToMooneyRivlin/enuToOgden 변환 유틸리티, MaterialEntry 초탄성 파라미터 필드
   - **`PreProcessor.ts`** — ResolvedMaterial에 constitutiveModel + 초탄성 파라미터,
     buildAnalysisRequest에서 서버 전달 시 constitutive_model 포함

4. **MaterialLibraryPanel 구성 모델 선택기 추가**

   속성 편집기에 "구성 모델 (Constitutive Model)" 드롭다운 추가:
   - **Linear Elastic / Neo-Hookean**: E/ν/ρ 슬라이더 (기존)
   - **Mooney-Rivlin**: C₁₀/C₀₁/D₁ 직접 입력 + "E/ν→자동계산" 버튼
   - **Ogden**: μ/α/D₁ 직접 입력 + "E/ν→자동계산" 버튼
   - FEM 전용 경고 표시 ("⚠ FEM 전용 — PD/SPG에서는 Linear Elastic으로 대체")

5. **SolvePanel 재료 UI 통합 — 드롭다운 제거**

   Solve 탭의 모델별 재료 `<select>` 드롭다운을 읽기 전용 요약으로 교체.
   재료 변경은 Pre-process 탭에서만 가능하도록 단일화.
   - "※ 재료 변경은 Pre-process 탭에서" 안내 문구 추가
   - `handleMaterialChange`, `getModelMaterialKey`, materialLibrary import 제거
   - 재료 라벨 + 툴팁 (모델명/E/ν 표시)

   **수정 파일 총괄**:
   | 파일 | 변경 |
   |------|------|
   | `src/fea/fem/material/mooney_rivlin.py` | 신규 |
   | `src/fea/fem/material/ogden.py` | 신규 |
   | `src/fea/fem/material/__init__.py` | 수정 |
   | `src/fea/framework/material.py` | 수정 |
   | `src/server/models/analysis.py` | 수정 |
   | `src/server/services/analysis.py` | 수정 |
   | `src/frontend/src/lib/stores/materials.svelte.ts` | 수정 |
   | `src/frontend/src/lib/analysis/PreProcessor.ts` | 수정 |
   | `src/frontend/src/components/sidebar/MaterialLibraryPanel.svelte` | 수정 |
   | `src/frontend/src/components/sidebar/SolvePanel.svelte` | 수정 |

   **빌드**: 0 에러, 프론트엔드 빌드 정상 통과
   **UI 테스트**: 구성 모델 선택/전환, 파라미터 자동계산, Assign Material, Solve 탭 읽기 전용 표시 검증 완료

6. **Material 전용 사이드바 탭 신설**

   기존 Pre-process 탭에 끼워져 있던 재료 라이브러리를 독립 탭으로 분리.
   사이드바 전체 높이를 활용해 재료 리스트 + 편집기를 넉넉하게 표시.

   - **`MaterialPanel.svelte`** (신규 460줄) — 전용 재료 라이브러리 관리 탭
     - 카테고리 탭 (전체/뼈/디스크/임플란트/연조직/커스텀) + 검색
     - 재료 카드 리스트 (구성 모델 배지 표시)
     - 구성 모델 선택기 (Linear Elastic / Neo-Hookean / Mooney-Rivlin / Ogden)
     - 기본 물성 참조 섹션 (MR/Ogden 시 E/ν 표시)
     - 대상 모델 선택 + Assign Material 버튼
     - 커스텀 저장/초기화 기능
   - **`ui.svelte.ts`** — TabId: `'view'` → `'material'`로 변경
   - **`Menubar.svelte`** — 탭 배열에서 View→Material 교체
   - **`Sidebar.svelte`** — ViewPanel→MaterialPanel import/분기 교체
   - **탭 순서**: File / Modeling / Material / Pre-process / Solve / Post-process

7. **View 플로팅 메뉴 (3D 뷰포트 우상단)**

   사이드바에서 View 탭을 제거하고, 3D 뷰포트 우상단 플로팅 메뉴로 이동.
   접기/펼치기 토글 (기본: 접힘) + 반투명 글래스 UI.

   - **`ViewFloatingMenu.svelte`** (신규 310줄)
     - Camera preset (F/Bk/T/Bo/L/R + Reset)
     - 배경색 드롭다운, 렌더모드 (Solid/Wire/S+W)
     - Opacity/Light 슬라이더
     - Grid/Axes 토글 + Screenshot 버튼
     - `position: absolute; top: 8px; right: 8px;` + `backdrop-filter: blur(10px)`
   - **`Canvas3D.svelte`** — ViewFloatingMenu import + 컨테이너 내부에 삽입
   - **`ViewPanel.svelte`** — 삭제 (ViewFloatingMenu로 대체)

8. **PreProcessPanel 재료 UI 제거**

   MaterialLibraryPanel import/사용 제거, BC 관련 기능만 잔존.
   "💡 재료 설정은 Material 탭에서 관리합니다" 안내 + 링크 버튼 추가.
   - **`MaterialLibraryPanel.svelte`** — 삭제 (MaterialPanel로 대체)

9. **SolvePanel 힌트 텍스트 수정**

   "※ 재료 변경은 Pre-process 탭에서" → "※ 재료 변경은 Material 탭에서"

   **수정/신규/삭제 파일 총괄**:
   | 파일 | 변경 |
   |------|------|
   | `src/frontend/src/components/sidebar/MaterialPanel.svelte` | 신규 |
   | `src/frontend/src/components/floating/ViewFloatingMenu.svelte` | 신규 |
   | `src/frontend/src/lib/stores/ui.svelte.ts` | 수정 |
   | `src/frontend/src/components/Menubar.svelte` | 수정 |
   | `src/frontend/src/components/sidebar/Sidebar.svelte` | 수정 |
   | `src/frontend/src/components/Canvas3D.svelte` | 수정 |
   | `src/frontend/src/components/sidebar/PreProcessPanel.svelte` | 수정 |
   | `src/frontend/src/components/sidebar/SolvePanel.svelte` | 수정 |
   | `src/frontend/src/components/sidebar/ViewPanel.svelte` | 삭제 |
   | `src/frontend/src/components/sidebar/MaterialLibraryPanel.svelte` | 삭제 |

   **빌드**: 0 에러, 프론트엔드 빌드 정상 통과
   **UI 테스트**: Material 탭 재료 리스트/편집기/구성모델, View 플로팅 메뉴 접기/펼치기, Pre-process BC전용, Solve 힌트 텍스트 검증 완료

10. **CT/DICOM 파이프라인 End-to-End 검증 및 버그 수정**

    실제 CT DICOM 파일(L-spine, 129슬라이스)을 사용하여 전체 파이프라인 검증.
    3가지 핵심 버그를 발견 및 수정하여 파이프라인 정상 동작 확인.

    **발견 및 수정한 버그**:

    - **Bug #1: 프론트엔드-백엔드 메쉬 데이터 형식 불일치**
      - 백엔드: `vertices`/`faces` 인라인 배열 직접 반환
      - 프론트엔드: `mesh.path`로 STL URL 접근 시도 → 데이터 로드 실패
      - **수정**: `loadMeshFromInlineData()` 함수 신규 구현 — 인라인 vertices/faces에서 Three.js BufferGeometry 직접 생성
      - 수정 파일: `types.ts`, `loading.ts`, `pipeline.ts`, `pipeline.svelte.ts`

    - **Bug #2: 세그멘테이션 출력 경로 불일치**
      - `segmentation.py`가 엔진 반환 경로를 무시하고 고정 `labels.nii.gz` 파일에서 읽으려 함
      - TotalSpineSeg는 `step2_output/` 하위에 결과 저장 → FileNotFoundError
      - **수정**: `engine.segment()` 반환값(실제 경로) 사용 + fallback 탐색 로직 추가
      - 수정 파일: `segmentation.py`

    - **Bug #3: SpineLabel 값 매핑 오류 (테스트)**
      - 테스트에서 L4=120, L5=121로 잘못 사용 → 실제는 L4=123, L5=124
      - E2E 테스트 수정

    **실제 CT 파이프라인 실행 결과**:
    ```
    DICOM: 512x512x129, L-spine CT (spacing 0.29mm/2.0mm)
    세그멘테이션: TotalSpineSeg (CPU) → 8개 구조물, ~6분 30초
      ● L1, L2, L3, SACRUM (뼈 4개)
      ● L1L2, L2L3, L5S1 (디스크 3개)
      ● SPINAL_CANAL (연조직 1개)
    메쉬 추출: ~790K 정점, ~1.5M 면 (Marching Cubes + Gaussian smoothing)
    ```

    **테스트 현황**: 전체 52개 테스트 통과 (기존 44 + E2E 신규 8)

    **수정/신규 파일 총괄**:
    | 파일 | 변경 |
    |------|------|
    | `src/server/services/segmentation.py` | 수정 — 엔진 반환 경로 사용 + fallback |
    | `src/frontend/src/lib/ws/types.ts` | 수정 — PipelineMeshData 인터페이스 신규 |
    | `src/frontend/src/lib/actions/loading.ts` | 수정 — loadMeshFromInlineData() 신규, centerMeshesAtOrigin export |
    | `src/frontend/src/lib/actions/pipeline.ts` | 수정 — 인라인 데이터 로딩 방식으로 전환 |
    | `src/frontend/src/lib/stores/pipeline.svelte.ts` | 수정 — extractedMeshes 타입 변경 |
    | `src/server/tests/test_pipeline_e2e.py` | 신규 — E2E 테스트 8개 |

---

## 이전 작업 내역 (2026-02-24)

### 완료

1. **레거시 `src/simulator/` 정리 — 배포 경로 버그 수정 (개선 #1)**

   Svelte 5 + Vite 마이그레이션 완료 이후에도 구형 바닐라 JS 파일들이 잔존하고,
   `GET /`가 레거시 `index.html`을 반환하는 **프로덕션 라우팅 버그**가 존재했다.
   (`STATIC_DIR = src/simulator/` ↔ `outDir = ../simulator/dist` 경로 불일치)

   - **STL 보존**: `cantilever_beam.stl`, `cylinder.stl` → `src/frontend/public/stl/` 복사
     (Vite build 시 `public/` 자동 복사로 `src/simulator/stl/`에 포함됨)
   - **레거시 파일 삭제**:
     - `src/simulator/src/` — 구형 바닐라 JS 8개 (main.js, voxel.js, pre.js, post.js, implant.js, nrrd.js, colormap.js, ws.js) 전부 Svelte lib/로 포팅 완료
     - `src/simulator/index.html` — 레거시 HTML
     - `src/simulator/tests/` — 구형 JS 시뮬레이터 테스트 4개
     - `src/simulator/dist/` — 구 빌드 산출물
     - `src/simulator/stl/` — public/stl/로 이동 완료
   - **`vite.config.ts` 수정** (1줄): `outDir: '../simulator/dist'` → `'../simulator'`
     `emptyOutDir: true`가 이미 설정되어 있으므로 빌드 시 자동 정리
   - **결과**: `npm run build` 후 `src/simulator/` = `index.html` (Svelte) + `assets/` + `stl/` 5개

   **수정 파일**:
   - `src/frontend/vite.config.ts` (outDir 1줄 수정)
   - `src/frontend/public/stl/cantilever_beam.stl` (신규 복사)
   - `src/frontend/public/stl/cylinder.stl` (신규 복사)

   **삭제 파일**:
   - `src/simulator/src/` 전체 (8개 JS)
   - `src/simulator/index.html`, `src/simulator/tests/` 전체
   - `src/simulator/dist/` 전체, `src/simulator/stl/` 전체

   **검증**: `uv run python -X utf8 -c "from src.server.app import app; print(app.title)"` → 정상

---

2. **`asyncio.get_event_loop()` → `get_running_loop()` 수정 (개선 #2)**

   Python 3.10+에서 `async` 함수 내부에서 `asyncio.get_event_loop()`를 호출하면 DeprecationWarning 발생.
   이미 실행 중인 루프가 있을 때는 `asyncio.get_running_loop()`를 써야 한다.

   - `_run_in_thread()` (line 109): `get_event_loop()` → `get_running_loop()`
   - `_handle_dicom_pipeline()` (line 204): 동일 수정

   **수정 파일**: `src/server/ws_handler.py` (2줄)
   **검증**: 44/44 테스트 통과, DeprecationWarning 없음

---

3. **CORS `allow_origins=["*"]` → 환경변수 기반 화이트리스트 (개선 #3)**

   병원 배포 환경에서 `["*"]`는 보안 위험. `SPINE_SIM_CORS_ORIGINS` 환경변수로 제어.

   - **`config.py`**: `CORS_ORIGINS` 추가
     - 미설정 시 개발 기본값: `localhost:5174` (Vite dev) + `localhost:8000` (FastAPI)
     - 설정 시: 콤마 구분 파싱 (예: `https://hospital.example.com,https://www.hospital.example.com`)
   - **`app.py`**: `allow_origins=CORS_ORIGINS`, `allow_methods`/`allow_headers`도 최소 필요 항목으로 명시

   **수정 파일**: `src/server/config.py`, `src/server/app.py`
   **검증**: 44/44 테스트 통과

---

4. **PD/SPG 입자 좌표 버그 수정 (개선 #4)**

   복셀 기반 PD/SPG 해석 시 실제 복셀 좌표가 무시되고 균등 그리드로 대체되던 근본 버그 수정.

   **버그 원인 (3중 불일치)**:
   - `group_positions` (실제 복셀 중심 좌표, 불규칙) ← 클라이언트에서 전달
   - `create_domain` → `_positions` = 균등 그리드 (복셀 무시)
   - `PDAdapter/SPGAdapter` → `initialize_from_grid` → 또 다른 균등 그리드 생성 (domain._positions 완전 무시)
   - BC `global_to_local` → 그룹 내 순번(0..n-1) → 어댑터 그리드 인덱스와 **불일치**
   - 반환 `positions=group_positions` ↔ `displacements`(그리드 기준) → **완전 불일치**

   **수정 방식**: `domain._custom_positions` 신호 플래그
   - `_run_particle_region`: `create_domain` 직후 `domain._custom_positions = group_positions.copy()` 설정
   - `PDAdapter.__init__`: `_custom_positions` 감지 시 `ParticleSystem.initialize_from_arrays(custom_pos, volumes)` 사용
   - `SPGAdapter.__init__`: 동일 패턴
   - `global_to_local` 매핑: `_custom_positions` 사용 시 로컬 인덱스 = 그룹 내 순번 → **일관성 보장**

   **수정 파일 (3개)**:
   - `src/server/services/analysis.py` — `domain._custom_positions` 설정
   - `src/fea/framework/_adapters/pd_adapter.py` — `_custom_positions` 분기
   - `src/fea/framework/_adapters/spg_adapter.py` — `_custom_positions` 분기

   **검증**: 44/44 서버 테스트 통과, domain._custom_positions 단위 검증 통과

---

5. **`pipeline/solve.py` ↔ `services/analysis.py` 중복 제거 (개선 #5)**

   두 파일이 바운딩박스 + n_divisions 계산 + `create_domain` + `_custom_positions` 설정 패턴을 각각 구현.
   또한 `SolveStage`에 개선 #4 버그픽스(균등 그리드 → 실제 복셀 좌표)가 미적용된 상태였음.

   **`create_particle_domain()` 헬퍼 추출 — `src/fea/framework/domain.py` 추가**
   - 입자 좌표 배열 → 바운딩박스 → n_divisions 추정 → `create_domain` → `_custom_positions` 설정
   - `get_positions()` 수정: `_custom_positions` 우선 반환 (select() 등 도메인 API 전체 일관성)
   - 두 파일이 공통 헬퍼 사용 → 개선 #4 로직이 한 곳에만 존재

   **`services/analysis.py` (`_run_particle_region`)**:
   - 바운딩박스 계산 6줄 + `create_domain` 5줄 + `_custom_positions` 3줄 제거
   - `domain = create_particle_domain(group_positions, method=method_enum)` 1줄로 대체

   **`pipeline/stages/solve.py` (`SolveStage.run`)**:
   - 바운딩박스 계산 4줄 + n_divisions 추정 2줄 + `create_domain` 7줄 제거
   - `domain = create_particle_domain(positions, method=method)` 1줄로 대체
   - **개선 #4 버그픽스 동시 적용**: 균등 그리드 대신 실제 NPZ 입자 좌표 사용

   **수정 파일 (3개)**:
   - `src/fea/framework/domain.py` — `create_particle_domain()` 추가, `get_positions()` 수정
   - `src/server/services/analysis.py` — 25줄 → 3줄
   - `src/pipeline/stages/solve.py` — 18줄 → 4줄

   **검증**: 72/72 테스트 통과 (서버 44 + 파이프라인 28), `create_particle_domain` 단위 검증 통과

---

6. **`PostProcessor.ts` 1048줄 → 4개 모듈 분리 (개선 #6)**

   1048줄짜리 모놀리식 클래스를 역할별로 4개 파일로 분리.
   Three.js 없는 순수 함수는 별도 모듈로 추출하여 테스트 가능성 확보.

   | 파일 | 역할 | 줄 수 |
   |------|------|-------|
   | `PostProcessorTypes.ts` (신규) | 타입/인터페이스 전용 | 43줄 |
   | `HEX8Utils.ts` (신규) | HEX8 기하 유틸 (표면 삼각형 추출) | 60줄 |
   | `ScalarMapper.ts` (신규) | 순수 함수 — 스칼라 추출/통계/필터 | 260줄 |
   | `PostProcessor.ts` (재작성) | Three.js 렌더링 클래스 + re-export | 730줄 |

   **`ScalarMapper.ts` 순수 함수 (Three.js 의존 없음)**:
   - `extractComponent(vectors, component)` — 벡터 → 스칼라 컴포넌트 추출
   - `getFEMNodeScalars / getParticleScalars / getLegacyScalars / getAllScalars`
   - `computeStats(data, mode, component)` → `PostProcessStats`
   - `applyPointFilters(positions, scalars, threshold, clipConfig, bbox)` — PD/SPG 필터
   - `isTriangleVisible(tri, deformed, nodeScalars, threshold, clipConfig, bbox)` — FEM 필터

   **`PostProcessor.ts` 하위호환 re-export**:
   ```typescript
   export type { PostProcessMode, VectorComponent, ... } from './PostProcessorTypes';
   ```
   기존 import 경로 (`from './PostProcessor'`) 변경 없이 동작.

   **수정/신규 파일 (4개)**:
   - `src/frontend/src/lib/analysis/PostProcessorTypes.ts` (신규)
   - `src/frontend/src/lib/analysis/HEX8Utils.ts` (신규)
   - `src/frontend/src/lib/analysis/ScalarMapper.ts` (신규)
   - `src/frontend/src/lib/analysis/PostProcessor.ts` (재작성)

   **빌드 검증**: `npm run build` ✓ 151 모듈, 1.08s, 경고/에러 0

---

7. **`guideline.py` / `implants.py` → 프론트엔드 연결 (개선 #7)**

   `src/core/`에만 존재하던 임플란트 3D 메쉬 생성·수술 가이드라인 시각화 로직을
   WebSocket API로 프론트엔드에 연결하고 ModelingPanel에 UI를 추가했다.

   **백엔드 추가**:
   - **`models/surgical.py`**: `ScrewSpecModel`, `CageSpecModel`, `ImplantMeshRequest`, `GuidelineRequest` 추가
   - **`services/implants.py`** (신규): `generate_implant_mesh()` — 스크류/케이지/로드 메쉬 → JSON
   - **`services/guideline.py`** (신규): `generate_guideline_meshes()` — 양측 가이드라인 메쉬 목록 → JSON
   - **`ws_handler.py`**: `get_implant_mesh` / `get_guideline_meshes` 두 명령 핸들러 추가

   **프론트엔드 추가**:
   - **`ws/types.ts`**: `MeshData`, `ImplantMeshResult`, `GuidelineMeshResult` 인터페이스,
     `WSMessageType`·`WSRequestType` 확장 (implant_mesh_result / guideline_meshes_result)
   - **`ws/client.ts`**: `onImplantMeshResult()` / `onGuidelineMeshResult()` 콜백 등록 메서드 추가
   - **`actions/implants.ts`** (신규): `initImplantLayer()`, `requestScrew()`, `requestCage()`,
     `requestGuidelines()`, `clearImplants()`, `clearGuidelines()`, `getImplantCount()`
     — 수신 메쉬를 `THREE.BufferGeometry + MeshPhongMaterial`로 변환하여 씬에 추가
   - **`ModelingPanel.svelte`**: 3개 섹션 추가
     - Bone Drill: 기존 드릴 + 반경 슬라이더 (통합)
     - Implants: 스크류(M5~M7) / 케이지(S·M·L·XL) 규격 선택 + Add 버튼 + Clear
     - Pedicle Guidelines: 척추 레벨(L1~S1) + 내측각 + 삽입깊이 슬라이더 + Show/Clear

   **수정/신규 파일 (9개)**:
   - `src/server/models/surgical.py`, `models/__init__.py`
   - `src/server/services/implants.py`, `services/guideline.py` (신규)
   - `src/server/ws_handler.py`
   - `src/frontend/src/lib/ws/types.ts`, `ws/client.ts`
   - `src/frontend/src/lib/actions/implants.ts` (신규)
   - `src/frontend/src/components/sidebar/ModelingPanel.svelte`

   **검증**:
   - 백엔드: 스크류(322정점/640면), 케이지(8정점/12면), L4 가이드라인(6개 메쉬) 생성 확인
   - 서버 테스트: 44/44 통과
   - Vite 빌드: ✓ 152 모듈, 1.07s, 경고/에러 0

---

8. **E2E UI 테스트 — Claude Desktop 브라우저 도구 활용 (개선 #8)**

   Playwright MCP(`mcp__Claude_Preview__*`) 도구로 Svelte 프론트엔드 전 탭을 자동 검증했다.
   별도 테스트 바이너리 설치 없이 Claude Desktop 내장 브라우저 기능을 활용.

   **테스트 환경**:
   - 서버: Vite dev server (port 5174, `.claude/launch.json` "frontend")
   - 도구: `preview_start`, `preview_screenshot`, `preview_snapshot`, `preview_eval`, `preview_console_logs`

   **검증 항목 및 결과**:

   | 항목 | 결과 |
   |------|------|
   | 페이지 로드 | ✅ Spine Surgery Planner UI 정상 렌더링 |
   | JS 런타임 에러 | ✅ 없음 |
   | 탭 네비게이션 6개 | ✅ File / Modeling / Pre-process / Solve / Post-process / View |
   | **Modeling** — Bone Drill 섹션 | ✅ Drill ON/OFF 토글, 상태 바 "Drill mode: Click to drill" 반응 |
   | **Modeling** — Implants 섹션 | ✅ Screw(M5×40~M7×55), Cage(S/M/L/XL) 드롭다운 + Add/Clear 버튼 |
   | **Modeling** — Pedicle Guidelines 섹션 | ✅ 척추(L1~S1), 내측각, 삽입깊이 슬라이더 + Show/Clear 버튼 |
   | **Modeling** — History 섹션 | ✅ Undo(0)/Redo(0) 비활성 표시 |
   | **Pre-process** 패널 | ✅ Brush Selection, Fixed BC, Force BC(크기/방향) 모두 표시 |
   | **Solve** 패널 | ✅ Server Disconnected 상태, Checklist, FEM/PD/SPG 솔버 설명 |
   | **Post-process** 패널 | ✅ "해석 결과 없음" 빈 상태 정상 |
   | **View** 패널 | ✅ Camera Preset(7방향), Background, Grid/Axes 헬퍼 체크박스 |
   | FPS | ✅ 60+ 유지 |

   **수정 파일**: 없음 (테스트 전용)

---

6. **백엔드 체계적 재구성 — 프론트엔드와 동일한 계층 구조 적용**

   평면적으로 나열된 `src/server/` 파일들을 `config → models/ → services/` 계층으로 분리.
   `/tmp/spine_sim` Windows 비호환 경로 수정, 모델 중복 제거, DICOM 파이프라인 서비스 분리.

   - **config.py (신규)**: `UPLOAD_DIR` 환경변수 기반 (`~/.spine_sim` 기본값, Windows 호환)
   - **models/ 패키지 (신규)**: `analysis.py` / `surgical.py` / `imaging.py` 도메인별 분리
     - `BoundaryCondition`으로 `RegionBC` 중복 통합, `__init__.py`에서 전체 re-export
   - **services/ 패키지 (신규)**: 파이프라인 함수 6개 이동 + `dicom_pipeline.py` 신규 추출
     - `dicom_pipeline.py`: ws_handler 114줄 인라인 오케스트레이션 → 동기 서비스 함수
   - **ws_handler.py**: 순수 WS 디스패처로 정리 (services 위임)
   - **app.py**: config에서 경로 임포트, 불필요한 import 정리
   - **테스트 임포트 경로 업데이트**: test_auto_material, test_dicom_converter, test_mesh_extract

   **결과**: 44/44 테스트 통과, FastAPI 앱 임포트 정상

   **수정/신규 파일**:
   - `src/server/config.py` (신규)
   - `src/server/models/__init__.py`, `analysis.py`, `surgical.py`, `imaging.py` (신규)
   - `src/server/services/__init__.py`, `analysis.py`, `segmentation.py`, `mesh_extract.py`,
     `auto_material.py`, `dicom_convert.py`, `dicom_pipeline.py` (신규)
   - `src/server/app.py`, `ws_handler.py` (수정)
   - `src/server/tests/test_auto_material.py`, `test_dicom_converter.py`, `test_mesh_extract.py`,
     `test_segmentation_pipeline.py` (임포트 경로 수정)

   **삭제 파일** (services/로 이동):
   - `src/server/models.py`, `analysis_pipeline.py`, `segmentation_pipeline.py`,
     `mesh_extract_pipeline.py`, `auto_material.py`, `dicom_converter.py`

---

2. **FEM 볼륨 메쉬 파이프라인 구현 — 복셀 → HEX8 직접 변환**

   핵심 개선: FEM 해석 시 복셀 그리드에서 HEX8 볼륨 메쉬를 직접 생성하여 FEMesh에 전달.
   PD/SPG는 기존대로 포인트 클라우드 사용. 결과 시각화도 솔버 타입별로 분리.

   - **PreProcessor.ts**: `buildFEMMesh()` 메서드 추가
     - 채워진 복셀 1개 = HEX8 요소 1개
     - 인접 복셀 간 코너 노드 공유 (compact 번호 부여)
     - BC 매핑: FEM → 8개 코너 노드, PD/SPG → 입자 인덱스
   - **models.py**: `MaterialRegion`에 `nodes`, `elements`, `boundary_conditions` 필드 추가
   - **analysis_pipeline.py**: 완전 재작성
     - `_run_fem_region()`: FEMesh.initialize_from_numpy(nodes, elements) 직접 사용
     - `_run_particle_region()`: PD/SPG 입자 기반 도메인
     - 결과: `fem_regions[]`, `particle_regions[]` 구조화된 영역별 결과
   - **PostProcessor.ts**: FEM + 포인트 혼합 시각화
     - FEM: HEX8 표면 추출 → THREE.Mesh (vertex colors + Phong lighting)
     - PD/SPG: THREE.Points (포인트 클라우드)
     - extractSurfaceTriangles(): 내부 면 제거, 외부 면만 삼각형화
   - **ws/types.ts**: `FEMRegionResult`, `ParticleRegionResult` 타입 추가

   **수정 파일 (6개)**:
   - `src/frontend/src/lib/analysis/PreProcessor.ts` — HEX8 메쉬 생성 + 영역별 BC
   - `src/frontend/src/lib/analysis/PostProcessor.ts` — 메쉬 표면 + 포인트 시각화
   - `src/frontend/src/lib/ws/types.ts` — FEM/입자 영역 결과 타입
   - `src/frontend/src/lib/actions/analysis.ts` — FEM 전용 요청 처리
   - `src/server/models.py` — MaterialRegion FEM 필드
   - `src/server/analysis_pipeline.py` — 영역별 FEM/PD/SPG 분리 실행

---

## 이전 작업 내역 (2026-02-14)

### 완료

3. **GPU 자동 세그멘테이션 파이프라인 구축 + 실제 CT 검증** — 테스트 132개 전체 passed

   RTX 4070 Ti SUPER 16GB GPU 활용, TotalSpineSeg로 **척추골+디스크+척수+척추관** 자동 세그멘테이션.

   - **PyTorch CUDA 활성화**: CPU→CUDA 12.4 전환 (`torch 2.6.0+cu124`)
     - `pyproject.toml`에 `[[tool.uv.index]]` CUDA 인덱스 설정
     - AMD GPU 머신: `uv pip install torch torchvision --index-url .../rocm6.3`으로 오버라이드
   - **TotalSpineSeg 엔진 업그레이드** (`src/segmentation/totalspineseg.py`)
     - `supported_modalities`: MRI만 → **CT+MRI** 둘 다 지원
     - venv 내 스크립트 경로 자동 탐색 (Windows 호환)
     - GPU 메모리 격리 (subprocess 실행)
   - **기본 엔진 변경**: `totalseg`(척추골만) → `totalspineseg`(디스크 포함)
     - `models.py`: SegmentationRequest 기본 엔진 변경
     - `ws_handler.py`: DICOM 파이프라인 auto → totalspineseg (CT/MRI 무관)
     - `index.html`: 프론트엔드 엔진 선택 UI 업데이트
   - **TotalSpineSeg 확장 라벨 매핑 보완** (`labels.py`)
     - 천골 세부 분절 (41~49) → SACRUM, 천골 디스크 (91~95) → L5S1
     - 척추관 라벨 100 → SPINAL_CANAL
   - **실제 요추 CT 세그멘테이션 검증 완료** (512x512x151, L-spine 2.0mm)
     - GPU(RTX 4070 Ti Super) 159초 소요
     - 검출: L1, L2, L3, SACRUM + L1L2, L2L3, L5S1 디스크 + 척추관
     - 총 3,676,564 non-zero voxels, 8개 구조물 3D 메쉬 추출 완료

   **수정 파일 (6개)**:
   - `pyproject.toml` — CUDA 인덱스 + torch/torchvision/totalspineseg 의존성
   - `src/segmentation/totalspineseg.py` — CT+MRI 지원, venv 경로 탐색
   - `src/server/models.py` — 기본 엔진 totalspineseg
   - `src/server/ws_handler.py` — auto → totalspineseg
   - `src/simulator/index.html` — 엔진 선택 UI
   - `src/server/tests/` — 기본 엔진 테스트 업데이트

2. **nnU-Net v2 모델 학습 파이프라인 구현** — 테스트 44개 전체 passed

   원본 데이터셋(VerSe2020/CTSpine1K/SPIDER) → nnU-Net 형식 변환 → 학습 실행까지의 전체 파이프라인.

   - **원본 라벨 매핑 추가** (`src/segmentation/labels.py`)
     - `VERSE_TO_STANDARD`: VerSe2020 (1~28) → SpineLabel
     - `CTSPINE1K_TO_STANDARD`: CTSpine1K (1~25) → SpineLabel
     - `build_spider_mapping()`: SPIDER 상대 순번 → SpineLabel 동적 매핑

   - **데이터셋 케이스 탐색** (신규: `src/segmentation/training/dataset_crawl.py`)
     - `CaseInfo` dataclass: 케이스 ID, 영상/라벨 경로, 데이터셋, 모달리티
     - `crawl_verse2020/crawl_ctspine1k/crawl_spider/crawl_all`: 데이터셋별 파일 탐색

   - **데이터 준비 오케스트레이션** (신규: `src/segmentation/training/run_pipeline.py`)
     - CT: NIfTI→라벨변환→(pseudo-label)→merge→검증→전처리→nnU-Net 저장
     - MRI: NIfTI→SPIDER 동적매핑→검증→전처리→nnU-Net 저장
     - `skip_existing`, `continue_on_error` 지원 (중단 후 재시작 가능)

   - **nnU-Net 학습 실행** (신규: `src/segmentation/training/run_train.py`)
     - `TrainConfig`: dataset_id, configuration, folds, epochs, device, debug
     - `run_plan_and_preprocess()`: subprocess로 nnU-Net 전처리
     - `run_train()`: fold별 학습 실행
     - `run_full_training()`: 전처리 + 전체 fold 학습
     - `export_model()`: 학습 모델 내보내기

   - **CLI 연동** (`src/pipeline/cli.py`)
     - `prepare-training-data`: 데이터셋 변환 실행 (--pseudo-labels, --dry-run, --continue)
     - `train`: nnU-Net 학습 실행 (--dataset-id, --config, --folds, --debug, --export)

   - **테스트 추가** (20개 신규): 매핑 완전성, SPIDER 동적 매핑, 크롤 매칭, 스킵 확인

   **신규 파일 (3개)**:
   - `src/segmentation/training/dataset_crawl.py`
   - `src/segmentation/training/run_pipeline.py`
   - `src/segmentation/training/run_train.py`

   **수정 파일 (3개)**:
   - `src/segmentation/labels.py` — 원본 매핑 3종 추가
   - `src/pipeline/cli.py` — prepare-training-data 재구현 + train 추가
   - `src/segmentation/training/tests/test_training.py` — 20개 테스트 추가

1. **DICOM 입력 자동화 파이프라인 구현** — 서버 테스트 35→44개, 전체 44 passed

   DICOM 폴더를 선택하면 **변환 → 세그멘테이션 → 메쉬 추출 → 3D 표시까지 원클릭 자동 처리**.

   - **DICOM → NIfTI 변환 모듈 (신규)**: `src/server/dicom_converter.py`
     - SimpleITK `ImageSeriesReader` 기반 DICOM 시리즈 읽기
     - 복수 시리즈 존재 시 슬라이스 수 최대 시리즈 자동 선택
     - 환자 메타데이터 추출 (Modality, PatientID 등)
   - **DICOM 업로드 엔드포인트**: `POST /api/upload_dicom`
     - `webkitdirectory`로 선택한 폴더의 파일들을 flat 저장
     - 비-DICOM 파일 자동 필터링 (.jpg, .png, .txt 등 제외)
   - **WS 원클릭 파이프라인**: `run_dicom_pipeline` 메시지 타입
     - 3단계 연쇄: DICOM변환 → 세그멘테이션 → 메쉬추출
     - 각 단계마다 `pipeline_step` 중간 진행률 전송
     - 완료 시 `pipeline_result`로 메쉬 + 메타데이터 전송
   - **프론트엔드 UI**: DICOM 원클릭 버튼 + 4단계 진행률 표시
     - File 탭에 보라색 "DICOM 폴더 선택 → 자동 처리" 버튼
     - 업로드/변환/세그멘테이션/3D모델 4단계 진행 상태 표시
     - 기존 NIfTI 수동 워크플로우 그대로 유지
   - **테스트 (신규 9개)**: `src/server/tests/test_dicom_converter.py`
     - 단일/복수 시리즈, 빈 폴더, 에러 처리, 콜백, 메타데이터 추출

   **신규 파일 (2개)**:
   - `src/server/dicom_converter.py` — DICOM→NIfTI 변환 모듈
   - `src/server/tests/test_dicom_converter.py` — 변환 테스트

   **수정 파일 (5개)**:
   - `src/server/models.py` — DicomPipelineRequest 모델 추가
   - `src/server/app.py` — POST /api/upload_dicom 엔드포인트
   - `src/server/ws_handler.py` — run_dicom_pipeline 핸들러
   - `src/simulator/index.html` — DICOM 원클릭 UI + 진행률
   - `src/simulator/src/ws.js` — pipeline_step/pipeline_result 디스패치
   - `src/simulator/src/main.js` — runDicomPipeline() + 콜백

0. **FEA 솔버 종합 개선 (4단계)** — 테스트 275→309개, 전체 309 passed, 0 failed

   #### Phase 1: 정확도 및 안정성

   - **PD f32→f64 전환**: 모든 Peridynamics 필드를 ti.f64로 변환 (에너지 보존 133%→목표 <5%)
     - 수정: particles.py, bonds.py, nosb.py, nosb_solver.py, explicit.py, quasi_static.py, damage.py, neighbor.py, linear_elastic.py(PD), pd_adapter.py
     - 테스트: test_particles.py, test_3d.py, benchmark_analytical.py 모두 f64 전환

   - **PD dt 추정 개선**: 파동속도 기반(과대추정) → 스펙트럴 반경 방법으로 교체
     - `k_eff = (λ+2μ) · V_i · (|dpsi_sum|² + Σ|dpsi_k|²)` → `dt = 0.5 × 2/√(λ_max)`
     - 예상 ~10x dt 증가 → quasi-static 수렴 속도 대폭 개선

   - **SPG 경계 보정 강화**: 경계 입자의 안정화력을 이웃 수 비율로 스케일링
     - `support_ratio = n_neighbors_i / max_neighbors` → `G_s *= support_ratio`
     - 외팔보 오차 17.26% → 목표 <10%

   - **FEM f32→f64 통일**: 모든 FEM 필드/계산을 ti.f64로 변환
     - 수정: mesh.py, linear_elastic.py(FEM), neo_hookean.py, static_solver.py, fem_adapter.py
     - 테스트 파일(test_fem.py, test_hex8.py, test_quad4.py)도 f64 통일

   #### Phase 2: GPU 가속

   - **GPU 백엔드 자동 감지 확장**: CUDA→Vulkan→CPU 우선순위 (기존 Vulkan→CPU)
     - runtime.py에 Backend.METAL 추가, 로깅 강화

   - **접촉 감쇠력 추가**: 법선 방향 점성 감쇠 `f_damp = -2ξ√(k·m_eff) × v_rel_n × n`
     - contact.py: compute_forces()에 vel_a, vel_b, damping_ratio, mass_a, mass_b 파라미터 추가

   #### Phase 3: 새 기능 추가

   - **FEM 동적 솔버 (신규)**: `src/fea/fem/solver/dynamic_solver.py`
     - Newmark-beta implicit (γ=0.5, β=0.25): 무조건 안정
     - Central Difference explicit: 조건부 안정, 충격 문제용
     - 집중 질량 행렬 (row-sum lumping), Rayleigh 감쇠 (C = α·M + β·K)
     - 고유진동수 계산 (일반화 고유값 문제)
     - solver/__init__.py에 DynamicSolver export 추가

   - **NeoHookean 일반화**: TET4 전용(range(4)/range(3)) → 모든 요소 지원(nodes_per_elem/dim)

   #### Phase 4: 테스트 및 검증

   - **FEM 동적 솔버 테스트 (신규)**: `src/fea/fem/tests/test_dynamic.py` (15개)
     - 솔버 생성, 집중 질량 합, Newmark/Central Diff 스텝, 안정성, BC 강제
     - 2D 외팔보 1차 고유진동수 해석해 대비 <15% 오차 확인
     - Rayleigh 감쇠 에너지 감소 확인, 3D HEX8 지원 확인

   - **접촉 해석 Staggered 정적 솔버 버그 수정**: scene.py `_solve_static`
     - 첫 반복에서 고정 노드 없는 body 단독 해석 → 특이 행렬 발산 (f64 전환 후 표면화)
     - 수정: 구속 있는 body만 첫 독립 해석 수행

   - **전체 테스트**: 309 passed, 0 failed (FEM 39 + PD 22 + SPG 31 + Framework 19 + Contact 19 + Core 48 + Pipeline 28 + Segmentation 68 + Server 35)

   **신규 파일 (2개)**:
   - `src/fea/fem/solver/dynamic_solver.py` — FEM 동적 솔버
   - `src/fea/fem/tests/test_dynamic.py` — 동적 솔버 테스트

   **수정 파일 (21개)**:
   - PD: particles.py, bonds.py, nosb.py, nosb_solver.py, explicit.py, quasi_static.py, damage.py, neighbor.py, linear_elastic.py(PD), pd_adapter.py, test_particles.py, test_3d.py, benchmark_analytical.py
   - FEM: mesh.py, linear_elastic.py(FEM), neo_hookean.py, static_solver.py, solver/__init__.py, test_fem.py, test_hex8.py, test_quad4.py
   - SPG: spg_compute.py
   - Framework: runtime.py, contact.py, fem_adapter.py, scene.py

## 이전 작업 내역 (2026-02-13)

### 완료

0. **SpineUnified: CT+MRI 통합 척추 세그멘테이션 모델** — 세그멘테이션 테스트 25→68개, 전체 ~275 passed
   - **Phase 1: 기반 구조 (추론 엔진 + 라벨 매핑 + UI)**
     - `src/segmentation/labels.py`: `NNUNET_SPINE_TO_STANDARD` (0~50→SpineLabel) + `STANDARD_TO_NNUNET_SPINE` 역매핑 + `NNUNET_IGNORE_LABEL=51`
     - `src/segmentation/base.py`: `segment()` 시그니처에 `modality: Optional[str] = None` 추가
     - `src/segmentation/nnunet_spine.py` (신규): SpineUnifiedEngine — nnU-Net v2 기반 CT+MRI 통합 추론
       - `_detect_modality()`: HU 범위로 CT/MRI 자동 판별
       - `_prepare_input()`: 2채널 NIfTI 생성 (정규화 영상 + 도메인 채널 CT=1/MRI=0)
       - `_run_inference()`: nnUNetPredictor 호출
       - `download_model()`: GitHub Release 가중치 다운로드
     - `src/segmentation/factory.py`: `spine_unified` 엔진 등록
     - `src/pipeline/config.py`: `SegmentConfig.engine` Literal에 `spine_unified` 추가
     - `src/server/models.py`: `SegmentationRequest.modality` 필드 추가
     - `src/server/segmentation_pipeline.py`: spine_unified 매핑 분기 + modality 전달
     - `src/simulator/index.html`: 엔진 드롭다운에 "SpineUnified (CT+MRI)" + 모달리티 선택 UI
     - `src/simulator/src/main.js`: 엔진 변경 시 모달리티 UI 토글 + 요청에 modality 포함
     - `pyproject.toml`: `seg-unified = ["nnunetv2>=2.5"]`, `seg-train = [...]` 의존성
   - **Phase 2: 학습 데이터 준비 파이프라인** (`src/segmentation/training/`)
     - `config.py`: DatasetPaths, PseudoLabelConfig, PreprocessConfig, NnunetConfig, TrainingPipelineConfig
     - `download.py`: VerSe2020/CTSpine1K/SPIDER 데이터셋 검증 (validate_all, print_validation_report)
     - `pseudo_label.py`: TotalSpineSeg로 CT 디스크 pseudo-label 생성 + 신뢰도 필터 (min_voxels, 인접 척추 확인, 연결 성분)
     - `validate_labels.py`: 해부학적 일관성 검증 (척추골 순서, 디스크 위치, 구조물 크기)
     - `label_merge.py`: GT 척추골 + pseudo-label 디스크 병합 (GT 우선, 불확실=ignore)
     - `preprocess.py`: CT HU→0-1, MRI z-score→0-1, 도메인 채널 생성
     - `convert_nnunet.py`: SpineLabel→nnU-Net 연속 정수, 케이스 저장, dataset.json 생성
   - **Phase 4: CLI 확장**
     - `spine-sim download-model spine_unified`: 모델 가중치 다운로드
     - `spine-sim validate-data`: 학습 데이터셋 검증
     - `spine-sim prepare-training-data /data -o nnUNet_raw`: 학습 데이터 변환 가이드
     - `spine-sim segment` 에 `--modality` 옵션 추가
   - **테스트:** 43개 신규
     - test_nnunet_spine.py: 19개 (라벨 매핑 9 + 엔진 5 + 모달리티 감지 2 + 전처리 3)
     - test_training.py: 24개 (설정 2 + 전처리 6 + 병합 3 + 변환 5 + 검증 4 + 데이터셋 4)
   - **신규 파일 11개**: nnunet_spine.py, training/{__init__,config,download,pseudo_label,validate_labels,label_merge,preprocess,convert_nnunet}.py, tests/test_nnunet_spine.py, training/tests/test_training.py
   - **수정 파일 9개**: labels.py, base.py, totalseg.py, totalspineseg.py, factory.py, config.py, models.py, segmentation_pipeline.py, index.html, main.js, pyproject.toml, cli.py

1. **Phase 2-7: CT/MRI → 수술 시뮬레이션 전체 워크플로우 구현** — 신규 35개 서버 테스트, 전체 251 passed
   - **Phase 2: 서버-웹 통신 확장**
     - `src/server/app.py`: REST 파일 업로드 (`POST /api/upload`, `/api/upload_plan`)
     - `src/server/ws_handler.py`: 4개 새 WS 명령 (segment, extract_meshes, auto_material, run_analysis)
     - `src/server/models.py`: ImplantPlacement, SurgicalPlan, SegmentationRequest, MeshExtractRequest, AutoMaterialRequest 모델
     - `src/simulator/src/ws.js`: segment_result, meshes_result, material_result 디스패치 추가
   - **Phase 3: 세그멘테이션 서버 연동**
     - `src/server/segmentation_pipeline.py` (신규): NIfTI → TotalSeg/TotalSpineSeg → 표준 라벨맵
     - File 탭에 NIfTI 업로드 + 엔진 선택 + 진행률 UI 추가
   - **Phase 4: 3D 모델 생성 (라벨맵 → 메쉬)**
     - `src/server/mesh_extract_pipeline.py` (신규): 라벨별 Marching Cubes 메쉬 추출 (scikit-image)
     - JS 메쉬 수신 → BufferGeometry 생성 → 씬 표시 (bone/disc/soft_tissue 색상 구분)
   - **Phase 5: 수술 모델링 (웹 인터랙티브)**
     - `src/simulator/src/implant.js` (신규): ImplantManager 클래스 (TransformControls)
     - STL 임포트, 이동/회전/스케일, 수술 계획 JSON 저장/로드
   - **Phase 6: 전처리 + 해석 확장**
     - `src/server/auto_material.py` (신규): SPINE_MATERIAL_DB (8종 재료) + SpineLabel 자동 매핑
     - Pre-process 탭: 자동 재료 할당(제안) + 수동 E/nu/density 편집 UI
     - BC는 기존 브러쉬 UI 유지 (사용자 요청: 자동 BC 미구현)
     - 재료 상세 편집 가능 (사용자 요청: 환자별 뼈/디스크 물성치 다름)
     - Solve 탭: 단일 도메인/다중 물체 접촉 해석 모드 선택
   - **Phase 7: 후처리 시각화 확장**
     - `src/simulator/src/post.js`: 수술 전/후 비교 + 임플란트 주변 응력 필터
     - Post-process 탭: 수술 전 결과 저장, 전/후 비교 버튼, 필터 반경 슬라이더
   - **테스트 (35개 신규):**
     - test_models.py: 20개 (Pydantic 모델 + JSON 직렬화)
     - test_auto_material.py: 7개 (재료 DB + 자동 할당)
     - test_mesh_extract.py: 5개 (메쉬 추출 + 라벨 로드)
     - test_segmentation_pipeline.py: 3개 (파이프라인 에러 처리)
   - **신규 파일 10개**: segmentation_pipeline.py, mesh_extract_pipeline.py, auto_material.py, implant.js, 테스트 5개 + __init__.py
   - **수정 파일 7개**: app.py, ws_handler.py, models.py, ws.js, post.js, main.js, index.html
   - **의존성 추가**: scikit-image

1. **Phase 0+1: CLI 파이프라인 + 자동 세그멘테이션 모듈** — 신규 53개 테스트, 전체 216 passed
   - **CLI 파이프라인** (`src/pipeline/`)
     - `cli.py`: Typer CLI — 7개 서브커맨드 (segment, postprocess, voxelize, solve, report, pipeline, server)
     - `config.py`: Pydantic 설정 모델 + TOML 로드 (PipelineConfig, SegmentConfig 등)
     - `cache.py`: SHA256 해시 기반 파이프라인 캐시 (입력+스테이지+파라미터 → 결과 재사용)
     - `stages/base.py`: StageBase ABC + StageResult 데이터클래스
     - `stages/segment.py`: CT/MRI 자동 세그멘테이션 스테이지 (TotalSeg/TotalSpineSeg 엔진 호출)
     - `stages/postprocess.py`: SimpleITK 형태학적 후처리 (소 구성요소 제거, 구멍 채우기, 스무딩)
     - `stages/voxelize.py`: NIfTI → NPZ 복셀 모델 (VolumeLoader 재사용, SpineLabel 재료 매핑)
     - `stages/solve.py`: FEA 프레임워크 호출 (FEM/PD/SPG 솔버)
     - `stages/report.py`: JSON + HTML 리포트 생성
   - **자동 세그멘테이션** (`src/segmentation/`)
     - `labels.py`: SpineLabel IntEnum — 통합 라벨 체계 (100번대=척추, 200번대=디스크, 300번대=연조직)
     - `base.py`: SegmentationEngine ABC (is_available, segment, get_standard_label_mapping)
     - `totalseg.py`: TotalSegmentator Python API 래퍼 (CT, vertebrae C1~L5+sacrum)
     - `totalspineseg.py`: TotalSpineSeg CLI 래퍼 (MRI, 척추+디스크+척수)
     - `factory.py`: create_engine() 팩토리 + list_engines()
     - `labels.py`: TOTALSEG_TO_STANDARD, TOTALSPINESEG_TO_STANDARD 매핑 + convert_to_standard()
   - **기본 설정 파일**: `config/pipeline.toml`
   - **pyproject.toml 수정**: typer, nibabel, pydantic, rich 의존성 + build-system(hatchling) + project.scripts
   - **CLI 실행**: `uv run spine-sim --help` → 7개 서브커맨드 정상 출력
   - **테스트**:
     - Pipeline: 캐시 8 + 설정 10 + CLI 10 = 28개
     - Segmentation: 라벨 16 + 엔진 9 = 25개
     - 기존 163개 + 신규 53개 = **216 passed, 0 failed**

## 이전 작업 내역 (2026-02-12)

### 완료

0. **탭 기반 UI 전면 리팩토링** - `src/simulator/index.html`, `src/simulator/src/main.js`
   - **드롭다운 메뉴 → 탭 바 전환**: 4개 드롭다운(.menu-item+.dropdown) 전부 삭제 → 6개 탭(.tab-btn) 추가
   - **탭 구성 (워크플로우 순)**: File | Modeling | Pre-process | Solve | Post-process | View + Undo/Redo 아이콘
   - **사이드바 패널 재구성**: 기존 5개(default/drill/bc/analysis/nrrd) → 새 6개(file/modeling/preprocess/solve/postprocess/view)
     - File: 모델 목록 + Import 버튼 + 좌표설정 + NRRD 설정 (통합)
     - Modeling: Drill 토글 + 반경 + 해상도 + History
     - Pre-process: BC 타입(Fixed/Force) + 브러쉬 + Force 방향 + 재료
     - Solve: 서버상태 + 솔버선택 + 실행 + 진행률
     - Post-process: 시각화모드 + 스케일 + 컬러바 + 통계
     - View: 카메라 프리셋(6방향) + Up축(Y/Z) + 조명(Ambient/Directional) + 그림자 + 배경색 + Grid/Axes
   - **JS 핵심 변경**:
     - `switchTab()` 함수 추가: 탭 전환 + 패널 표시 + 도구 자동 활성화
     - `setTool(tool, force)`: force 파라미터 추가 (탭 전환 시 토글 방지)
     - `enterPostMode()`/`exitPostMode()`: 후처리 모드 진입/해제 분리
     - `setupViewListeners()`: 카메라 프리셋, Up축, 조명, 배경색, Grid/Axes 이벤트
     - `setCameraPreset(direction)`: 6방향 카메라 프리셋 (모델 바운딩박스 기반 거리 계산)
     - 조명 전역 참조(`ambientLight`, `dirLight`) 추가로 View 탭에서 실시간 조절
     - 드롭다운 관련 코드 전부 삭제 (`openDropdown`, `toggleDropdown`, `closeAllDropdowns`)
   - **CSS 변경**: 드롭다운 CSS 삭제, `.tab-btn`/`.tab-btn.active`/`.icon-btn`/`.menubar-sep` 추가
   - **해석 결과 수신 시 자동 Post-process 탭 전환** (`switchTab('postprocess')`)
   - **NRRD 로드 시 File 탭 + NRRD 설정 섹션 자동 표시**
   - **DOM ID 전부 보존** (기존 코드 호환)

0. **Force BC 화살표 동작 개선** - `src/simulator/src/main.js`, `src/simulator/src/pre.js`
   - **적용 후 표시**: Force BC 적용 버튼 클릭 시 적용면 중심에 빨간 확정 화살표 생성
   - **Ctrl+드래그 방향 조정**: 적용된 화살표의 방향을 카메라-facing 평면에서 실시간 회전, BC 데이터도 함께 갱신
   - **depthTest 비활성화**: 화살표가 물체에 가려지지 않고 항상 보이도록 설정
   - **Ctrl 키 시 브러쉬 비활성화**: Ctrl+클릭/드래그 시 복셀 선택이 되지 않도록 분리
   - **pre.js 중복 화살표 제거**: `_addBCVisual()`에서 자체 ArrowHelper 생성 제거 (main.js에서만 관리)
   - **적용 화살표 관리**: `appliedForceArrows` 배열로 추적, BC 제거 시 함께 정리

0. **Pre-process UI 개편** - `src/simulator/index.html`, `src/simulator/src/main.js`, `src/simulator/src/pre.js`
   - **메뉴 이름 변경**: "Boundary Cond." → "Pre-process" (data-menu, dropdown ID 포함)
   - **BC 타입별 색상 즉시 반영**:
     - Fixed: 호버=연초록(0x66ff88), 선택/확정=초록(0x00cc44)
     - Force: 호버=연빨강(0xff6666), 선택/확정=빨강(0xff2222)
     - `getCurrentBCColor()` 헬퍼로 라디오 값에 따라 동적 색상 반환
     - BC 타입 변경 시 하이라이트 색상 즉시 재생성
   - **Force 방향 3D 화살표**: ArrowHelper로 선택 영역 중심에서 방향 벡터 표시
     - 크기 슬라이더 (1~1000N, 기본 100N)
     - Ctrl+드래그로 카메라-facing 평면에서 3D 회전
     - 방향 텍스트 실시간 갱신: (x, y, z)
     - 기본 방향 리셋 버튼 (-Y)
     - 확정 BC에도 ArrowHelper 영구 표시
   - **재료 오브젝트 선택**: 대상 select (전체/L4/L5/disc...) 동적 생성
     - 모델 로드/복셀화 완료 시 자동 갱신
     - 선택된 오브젝트에만 재료 적용 가능
   - **패널 재구성**: BC 타입 라디오 상단 이동, Force X/Y/Z 슬라이더 제거 → 방향 드래그 + 크기 슬라이더
   - 기존 Force X/Y/Z 슬라이더 제거 → 방향은 3D 드래그, 크기는 단일 슬라이더
   - **BC 브러쉬 페인팅 버그 수정**: `pre.js`에서 `grid.size`(undefined) → `grid.gridSize.x/y/z` 변경 (6곳)
     - 원인: linearIdx 계산이 NaN → Set에 1개만 저장
     - 비정방(non-cubic) 그리드 (64x58x35 등) 올바르게 처리
   - **이중 복셀 초기화 수정**: `isDrillInitialized = true`를 setTimeout 전에 설정하여 중복 호출 방지

1. **BC 브러쉬 도구 구현** - `src/simulator/src/pre.js`, `src/simulator/src/main.js`, `src/simulator/index.html`
   - **드릴과 동일한 구체 브러쉬** 방식으로 경계조건 영역 선택 (기존 면 BFS 선택 → 브러쉬 페인팅)
   - **프리뷰**: 호버 시 시안색 InstancedMesh로 영향 복셀 하이라이트
   - **선택**: 클릭/드래그로 복셀 누적 선택 (노란색 하이라이트), 선택 카운트 실시간 표시
   - **BC 적용**: 선택된 복셀에 Fixed/Force BC 확정 (파랑/빨강 InstancedMesh 큐브 시각화)
   - **해석 연동**: `buildAnalysisRequest()`에서 voxelIndices → particle index 매핑으로 정확한 BC 전달
   - `pre.js`: `brushSelection` Map, `brushSelectSphere()`, `clearBrushSelection()`, `getBrushSelectionCount()`, `getBrushSelectionWorldPositions()` 추가
   - `main.js`: `bcBrushHighlight`, `bcSelectionHighlight` InstancedMesh, `bc_brush` 도구 핸들링 추가
   - `index.html`: BC 패널 브러쉬 UI (반경 슬라이더 1~15mm, 선택 카운트), 메뉴 텍스트 "Brush Select"
   - 기존 face 기반 BC와 호환 유지 (레거시 `bc_select` 도구 보존)

1. **데스크탑 CAE 스타일 UI 리팩토링** - `src/simulator/index.html`, `src/simulator/src/main.js`
   - **상단 메뉴바**: File / Modeling / Boundary Cond. / Analysis 드롭다운 메뉴
     - File: Load Sample, Load STL, Load NRRD, Clear All
     - Modeling: Drill, Re-voxelize, Undo/Redo (Ctrl+Z/Y)
     - Boundary Cond.: Select Faces, Apply Fixed/Force BC, Remove BC, Assign Material
     - Analysis: Run Analysis, Show Displacement/Stress/Damage
   - **우측 속성 패널** (260px): 활성 도구에 따라 컨텍스트 전환
     - 기본: 모델 목록 + 좌표 설정
     - Drill: 반경 슬라이더 + 복셀 해상도 + History(Undo/Redo)
     - BC: 면 선택 + Fixed/Force 설정 + 재료 프리셋
     - Analysis: 솔버 선택 + 실행 + 진행률 + 후처리(시각화/스케일/컬러바)
     - NRRD: 해상도 + Threshold + Apply
   - **하단 상태바**: Tool / FPS / Drill 정보 / WS 연결 상태
   - **View 버튼**: 메뉴바 우측에 Reset/Top/Front
   - **메뉴 호버 전환**: 드롭다운 열린 상태에서 다른 메뉴 호버 시 자동 전환
   - **캔버스 드래그 앤 드롭**: STL 파일을 뷰포트에 드롭하여 로드
   - **bc_select 도구**: 면 선택 전용 도구 분리 (기존 analysis 도구에서 분리)
   - 기존 모든 기능 호환 유지 (DOM ID 보존)

1. **Pre-process Step 워크플로우 검증 테스트 (30 항목, 29 PASS / 1 FAIL)**
   - Playwright (Chromium headless)로 http://localhost:8080 웹앱 자동화 테스트
   - **테스트 파일**: `test-preprocess-workflow.mjs`
   - **스크린샷**: `test-preprocess-workflow-screenshot.png`
   - **검증 항목 8가지**:
     1. 페이지 로드 후 JS 에러 없음 (PASS)
     2. Pre-process 탭 클릭 → panel-preprocess 표시 확인 (PASS)
     3. 워크플로우 요소 존재 + 순서 확인: 브러쉬 → Step1(Fixed) → Step2(Force) → BC관리 → Step3(재료) (PASS, 21항목 전부)
     4. input[name="bc-type"] 라디오 버튼 없음 확인 (PASS)
     5. Force 방향 표시 "(0.00, -1.00, 0.00)" 항상 보임 확인 (PASS)
     6. Step별 border-left 색상: 초록(Fixed #00cc44), 빨강(Force #ff2222), 파랑(재료 #1976d2) (PASS)
     7. 스크린샷 캡처 (PASS)
     8. 최종 JS 에러 확인: pageerror 없음(PASS), 콘솔 WebSocket 404만 존재(FAIL - 해석 서버 미실행으로 예상됨)

1. **탭 기반 UI 검증 테스트 실행 및 전체 통과 (55 passed, 0 failed)**
   - Playwright (Chromium headless)로 http://localhost:8080 웹앱 자동화 테스트
   - **테스트 파일**: `test-tab-ui.mjs`
   - **스크린샷 10장**: `test-screenshots/` 디렉토리
   - **검증 항목 8가지 전부 PASS**:
     1. 페이지 로드 시 JS 에러 없음 (WebSocket 관련 제외)
     2. 탭 바에 6개 탭 (File, Modeling, Pre-process, Solve, Post-process, View) 표시 확인
     3. Undo/Redo 아이콘 버튼 (#btn-undo-top, #btn-redo-top) 상단 우측 위치 확인
     4. File 탭 기본 활성 상태 (active 클래스) + Models/Import/좌표설정 섹션 확인
     5. 각 탭 클릭 → 패널 전환 확인:
        - Modeling: Drill 토글/반경/Voxel Resolution/History
        - Pre-process: BC 타입 라디오(Fixed/Force)/브러쉬 반경/재료 설정
        - Solve: 솔버 선택(FEM/PD/SPG)/해석 실행 버튼
        - Post-process: 시각화 모드(Displacement/Stress/Damage)/변위 스케일/입자 크기
        - View: 카메라 프리셋(6방향)/Up축/조명/배경색/Grid/Axes
     6. View 탭 배경색 "검정"(#1a1a1a)으로 변경 → 캔버스 배경 변경 확인 (스크린샷)
     7. Grid/Axes 체크박스 해제→재체크 토글 정상 동작 확인
     8. 전체 테스트 중 심각한 JS 에러 없음 확인

2. **이전: Playwright 웹 UI 테스트 실행 및 전체 통과**
   - Playwright (Chromium headless)로 http://localhost:8000 웹앱 자동화 테스트
   - **15개 항목 전부 PASS**:
     1. 페이지 접속 (http://localhost:8000)
     2. 타이틀 확인 ("Spine Surgery Simulator")
     3. STL 모델 자동 로드 (disc 8312 tris, L5 17620 tris, L4 34500 tris)
     4. 초기 상태 스크린샷
     5. Analysis 버튼 클릭
     6. Analysis 패널 표시
     7. Analysis 모드 스크린샷
     8. BC Force 변경 + Force 입력 UI 표시
     9. 재료 프리셋 드롭다운 (Bone/Disc/Ligament/Titanium)
     10. 솔버 드롭다운 (FEM/PD/SPG)
     11. Post-process 모드 전환
     12. Post-process 모드 스크린샷
     13. Pre-process 모드 복귀
     14. 최종 스크린샷
   - WebSocket 서버 연결 상태: **연결됨** (녹색)
   - 스크린샷 4장 저장: `src/fea/tests/screenshots/`
   - **테스트 파일**: `src/fea/tests/test_web_ui_playwright.mjs`

1. **Pre/Post Processor + GPU 지원 MVP 구현**
   - **FastAPI + WebSocket 서버** (`src/server/`)
     - `app.py`: FastAPI 앱 — 정적 파일 서빙 + WebSocket 엔드포인트
     - `models.py`: Pydantic 모델 (BoundaryCondition, MaterialRegion, AnalysisRequest)
     - `ws_handler.py`: WebSocket 핸들러 — 해석 실행 + 진행률 실시간 전송
     - `analysis_pipeline.py`: FEA framework 호출 파이프라인 — GPU 자동 선택 (Vulkan→CPU 폴백)
   - **프론트엔드 JS 모듈** (`src/simulator/src/`)
     - `ws.js`: WebSocket 클라이언트 — 자동 재연결, 콜백 레지스트리
     - `colormap.js`: Jet 컬러맵 유틸리티 — valuesToColors(), createColorbar()
     - `pre.js`: PreProcessor — 면 선택(BFS), 경계조건 설정, 재료 할당, 해석 요청 조립
     - `post.js`: PostProcessor — 컬러맵 시각화 (변위/응력/손상 모드), Points 렌더링
   - **UI 통합** (`index.html`, `main.js`)
     - Analysis 도구 버튼 + Analysis 패널 (Pre/Post 모드 토글)
     - 전처리: 면 선택, Fixed/Force BC, 재료 프리셋, 솔버 선택, 해석 실행
     - 후처리: 시각화 모드, 변위 스케일, 입자 크기, 컬러바
     - 진행률 바 + 통계 표시
   - **의존성 추가**: fastapi, uvicorn[standard], websockets
   - **서버 실행**: `uv run python -m src.server.app` → http://localhost:8000
   - **검증**: 서버 응답 200, 모든 정적 파일 정상 서빙, 모듈 임포트 정상

1. **PD/SPG 다중 재료(per-particle) 지원 추가**
   - PD: `ParticleSystem`에 `bulk_mod`, `shear_mod` per-particle 필드 추가
   - SPG: `SPGParticleSystem`에 `lam_param`, `mu_param` per-particle 필드 추가
   - 커널 수정: `nosb.compute_force_state_with_stabilization()` → 입자별 재료 상수 사용
   - 커널 수정: `spg_compute.compute_stress()` → 입자별 재료 상수 사용
   - 편의 메서드: `set_material_constants()` (단일), `set_material_constants_per_particle()` (다중)
   - 기존 테스트 전부 통과 (PD 벤치마크 5개, SPG 31개 테스트)
   - **수정 파일**: `peridynamics/core/particles.py`, `peridynamics/core/nosb.py`, `peridynamics/solver/nosb_solver.py`, `peridynamics/tests/benchmark_analytical.py`, `spg/core/particles.py`, `spg/core/spg_compute.py`, `spg/solver/explicit_solver.py`, `spg/tests/test_spg_validation.py`, `spg/tests/test_spg.py`, `tests/benchmark_spine_compression.py`

2. **L4+disc+L5 복셀화 → FEM/PD/SPG 압축 비교 벤치마크** - `src/fea/tests/benchmark_spine_compression.py`
   - STL 3개(L4, disc, L5)를 하나의 복셀 그리드로 합치는 파이프라인 구축
   - 레이캐스팅 복셀화 (Möller–Trumbore, numpy 벡터화, 3.5초/3개 STL)
   - 복셀 → HEX8 메쉬 변환 (노드 공유/중복 제거)
   - 복셀 → 입자 변환 (PD/SPG용)
   - **FEM 다중 재료 지원**: `StaticSolver`에 `materials` 딕셔너리 추가
     - 요소별 `material_id`에 따라 다른 탄성 텐서 사용
     - 뼈(15000 MPa) + 디스크(10 MPa) 동시 해석
   - **3-솔버 비교 결과** (2484 복셀, 4.16mm 간격) — **모두 다중 재료 지원**:

   | 솔버 | 다중재료 | z-변위 (mm) | 최대응력 (MPa) | 시간 |
   |------|---------|------------|--------------|------|
   | FEM (HEX8) | O | -1.35e-02 | 9.00 | 2.5초 |
   | NOSB-PD | O | -5.25e-03 | 2.13 | 0.5초 |
   | SPG | O | -5.27e-03 | 0.77 | 0.2초 |

   - FEM: 다중 재료로 디스크 영역에서 더 큰 응력 (뼈 0.16 vs 디스크 2.75 MPa)
   - PD/SPG: 다중 재료 적용, 동일 변위 적용 시 거의 같은 변위 (-5.25e-03 mm)
   - 세 솔버 변위 비율 max/min = 2.6 (같은 order of magnitude)
   - 실행: `uv run python src/fea/tests/benchmark_spine_compression.py`
   - **신규 파일**: `src/fea/tests/__init__.py`, `src/fea/tests/benchmark_spine_compression.py`
   - **수정 파일**: `src/fea/fem/solver/static_solver.py` (다중 재료 지원)

2. **드릴을 구체(Sphere) 방식으로 변경** - `src/simulator/src/voxel.js`, `src/simulator/src/main.js`
   - 기존 캡슐(원통+반구) 드릴 → 구체(Sphere) 드릴로 전환
   - `previewDrill(worldPos, radius)`: 구체 범위 내 영향 복셀 프리뷰
   - `drillWithSphere(worldPos, radius)`: 구체로 실제 복셀 제거
   - 드릴 프리뷰: 회색 반투명 구체 (`0xaaaaaa`, opacity 0.35)
   - Depth 파라미터/슬라이더 제거 (구체는 radius만 필요)

2. **CAD 스타일 네비게이션으로 변경** - `src/simulator/src/main.js`
   - Navigate 도구 제거 → 네비게이션은 항상 기본 탑재
   - 우클릭 드래그 = 회전 (항상), 중클릭 드래그 = 팬 (항상), 스크롤 = 줌 (항상)
   - 좌클릭 = 도구 없으면 회전, 도구 있으면 도구 사용
   - 도구 토글 방식 (같은 버튼 다시 클릭 시 해제)

3. **불필요한 UI 기능 제거** - `src/simulator/index.html`, `src/simulator/src/main.js`
   - Slice View (단면 뷰) 전체 제거: HTML 패널 + JS 함수 (~240줄)
   - Measure 버튼 제거 (미구현 상태였음)

4. **드릴 클릭 버그 수정** - `src/simulator/src/main.js`
   - 원인: OrbitControls가 `pointerdown`에서 `preventDefault()` 호출 → `mousedown` 이벤트 차단
   - 수정: 이벤트 리스너를 `mousedown/move/up` → `pointerdown/move/up`으로 변경

## 작업 내역 (2026-02-15)

### 완료

0. **강체(Rigid Body) + Coulomb 마찰 접촉 구현** - `src/fea/framework/`
   - Wu et al. (2026, JMBBM) 논문 기반 나사 삽입/pullout 시뮬레이션 준비
   - **신규 파일:**
     - `rigid_body.py`: RigidBody, PrescribedMotion, create_rigid_body
     - `_adapters/rigid_adapter.py`: RigidBodyAdapter (AdapterBase 구현, 리액션 힘 기록)
     - `tests/test_rigid_body.py`: 단위 24개 + 통합 2개 = 26개 테스트
     - `tests/test_friction.py`: 마찰 8개 테스트
   - **수정 파일:**
     - `domain.py`: Method.RIGID enum 추가
     - `contact.py`: ContactDefinition에 static_friction/dynamic_friction 필드, compute_forces_with_friction() (penalty-regularized Coulomb)
     - `scene.py`: add() material Optional, _build() RIGID 분기, quasi_static/explicit에서 rigid body 처리, 마찰 접촉 분기, _get_velocity() 헬퍼
     - `__init__.py`: RigidBody, PrescribedMotion, create_rigid_body export
   - **강체 기능:**
     - 규정 운동: 회전(Rodrigues) + 병진, 순차 적용
     - 2D/3D 지원, Duck typing으로 Scene 호환
     - 리액션 힘 기록 (pullout force 측정용)
   - **Coulomb 마찰:**
     - Penalty-regularized stick/slip 분류
     - |f_t| ≤ μ_s × |f_n| (stick), f_t = μ_d × |f_n| × dir (slip)
     - 작용-반작용 보존 확인됨
   - **테스트: 32개 신규, 70개 전체 프레임워크 통과**

---

## 이전 작업 내역 (2026-02-08)

### 완료

0. **다중 물체 접촉 해석 프레임워크** - `src/fea/framework/`
   - FEM-FEM, FEM-SPG, SPG-SPG 등 이종 솔버 간 접촉 해석 지원
   - 노드-노드 페널티 접촉 알고리즘 (KDTree 기반)
   - **3가지 해석 모드:**
     - `quasi_static` (기본, 권장): 모든 body 동시 step + 매 스텝 접촉력 갱신 + KE 수렴 판정
     - `static`: Staggered 정적 (FEM-FEM 전용)
     - `explicit`: 동기화 명시적 (수렴 체크 없이 n_steps 진행)
   - **Scene API:**
     ```python
     from src.fea.framework import init, create_domain, Material, Method, Scene, ContactType
     init()
     bone = create_domain(Method.SPG, dim=2, ...)
     screw = create_domain(Method.FEM, dim=2, ...)
     scene = Scene()
     scene.add(bone, bone_mat)
     scene.add(screw, screw_mat)
     scene.add_contact(bone, screw, method=ContactType.PENALTY, penalty=1e8)
     result = scene.solve(mode="quasi_static")  # 또는 "static", "explicit"
     u_bone = scene.get_displacements(bone)
     ```
   - **신규 파일:**
     - `contact.py`: ContactType enum, NodeNodeContact 알고리즘
     - `scene.py`: Scene 클래스, Body 관리, 정적/명시적 멀티바디 솔버
     - `_adapters/base_adapter.py`: AdapterBase ABC (접촉 인터페이스)
   - **수정 파일:**
     - `_adapters/fem_adapter.py`: AdapterBase 상속, 접촉력 inject/clear 추가
     - `_adapters/pd_adapter.py`: AdapterBase 상속, 접촉력 inject/clear 추가
     - `_adapters/spg_adapter.py`: AdapterBase 상속, 접촉력 inject/clear 추가
     - `domain.py`: `select_boundary()` 메서드 추가
     - `__init__.py`: Scene, ContactType export 추가
   - **접촉 매개변수 자동 추정:** penalty = E_avg/spacing, gap_tol = 1.5×max_spacing
   - **테스트: 19개 신규** (접촉 알고리즘 6 + 경계감지 2 + Scene API 4 + FEM-FEM 통합 2 + SPG 준정적 2 + 모드선택 2 + 자동추정 1)
   - **전체 테스트: 163 passed, 0 failed**

1. **통합 FEA 프레임워크 구현** - `src/fea/framework/`
   - FEM, Peridynamics, SPG 세 솔버를 동일한 API로 사용 가능
   - `Method.FEM` / `Method.PD` / `Method.SPG` 전환만으로 솔버 교체
   - GPU 자동 감지 (Vulkan → CPU 폴백), 정밀도(f32/f64) 설정
   - **통합 API 예시:**
     ```python
     from src.fea.framework import init, create_domain, Material, Solver, Method
     init()
     domain = create_domain(Method.FEM, dim=2, origin=(0,0), size=(1.0, 0.2), n_divisions=(50, 10))
     left = domain.select(axis=0, value=0.0)
     right = domain.select(axis=0, value=1.0)
     domain.set_fixed(left)
     domain.set_force(right, [100.0, 0.0])
     mat = Material(E=1e6, nu=0.3, density=1000, dim=2)
     solver = Solver(domain, mat)
     result = solver.solve()
     u = solver.get_displacements()
     ```
   - **파일 구조:**
     - `runtime.py`: Taichi 초기화 중앙 관리, GPU 감지, Backend/Precision enum
     - `domain.py`: create_domain() 팩토리 + Domain 클래스 (select, set_fixed, set_force)
     - `material.py`: Material 데이터 클래스 (E, nu, density → 솔버별 재료 지연 생성)
     - `solver.py`: Solver 통합 클래스 (어댑터 자동 선택)
     - `result.py`: SolveResult 데이터 클래스
     - `_adapters/`: FEM, PD, SPG 어댑터 (Adapter 패턴, 기존 코드 미수정)
   - **테스트: 19개 신규 (런타임 3 + 도메인 4 + 재료 2 + FEM 2 + SPG 1 + PD 2 + 교차검증 1 + API 4)**
   - **전체 테스트: 144 passed, 0 failed (기존 125 + 신규 19)**

2. **레거시 `spine_sim` import 일괄 수정**
   - 14개 Python 파일에서 `spine_sim.*` → `src.*` import 경로 변환
   - 불필요 코드 삭제 (spine_sim/, framework/, dead tests 등)
   - **전체 테스트: 125 passed, 0 skipped, 0 failed**

2. **SPG (Smoothed Particle Galerkin) 솔버 추가 및 검증** - `src/fea/spg/`
   - 극한 변형 및 재료 파괴 해석을 위한 무격자(meshfree) 방법
   - **검증 테스트 포함 31개 전부 통과**

3. **FEM 2D 호환성 버그 수정** - `src/fea/fem/material/linear_elastic.py`
   - `_compute_forces_kernel`에서 3D 하드코딩 (벡터 크기, 루프 범위) → 차원 일반화
   - `ti.static(self.dim)` 사용으로 2D/3D 모두 지원
   - `nodes_per_elem` 매개변수 추가 (TET4 4노드 하드코딩 제거)

4. **FEM 해석해 비교 벤치마크** - `src/fea/fem/tests/benchmark_analytical.py`
   - 5개 표준 문제로 FEM 솔버의 물리적 정확도 검증

   | 벤치마크 | 주요 오차 | 평가 |
   |---------|----------|------|
   | 균일 인장 봉 (2D QUAD4, 평면응력) | 0.28% | 양호 |
   | 균일 인장 봉 (3D HEX8) | 0.95% | 양호 |
   | 외팔보 (2D QUAD4, Timoshenko) | 1.23% | 양호 |
   | 3D 큐브 압축 (HEX8) | 3.44% | 양호 |
   | 격자 수렴율 (외팔보) | rate=1.33 | 보통 |

   - 실행: `uv run python src/fea/fem/tests/benchmark_analytical.py`

5. **Peridynamics 해석해 비교 벤치마크** - `src/fea/peridynamics/tests/benchmark_analytical.py`
   - 5개 표준 문제로 PD 솔버의 물리적 정확도 검증

   | 벤치마크 | 주요 오차 | 평가 |
   |---------|----------|------|
   | Bond-based 인장 (2D) | 0.00% | 양호 |
   | NOSB-PD 인장 (2D) | 0.00% | 양호 |
   | NOSB-PD 3D 압축 | 0.00% | 양호 |
   | 에너지 보존 (Explicit) | 133% 변동 | 미흡 |
   | 격자 수렴율 (F 정확도) | rate=1.26 | 양호 |

   - 에너지 보존 133% 변동: 명시적 솔버의 시간 적분 한계 (향후 개선)
   - 실행: `uv run python src/fea/peridynamics/tests/benchmark_analytical.py`

6. **SPG 해석해 비교 벤치마크** - `src/fea/spg/tests/benchmark_analytical.py`
   - 5개 표준 문제로 SPG 솔버의 물리적 정확도 검증

   | 벤치마크 | 주요 오차 | 평가 |
   |---------|----------|------|
   | 균일 인장 봉 | 6.8% | 양호 |
   | 외팔보 (Cantilever) | 17.3% | 보통 |
   | 양단 고정 보 (Clamped) | 14.1% | 보통 |
   | 3D 큐브 압축 | 13.2% | 보통 (범위 내) |
   | 격자 수렴율 | rate=1.02 | 양호 |

   - 실행: `uv run python src/fea/spg/tests/benchmark_analytical.py`

## 이전 작업 내역 (2026-02-06)

### 완료
1. **모델 좌표 시스템 개선** - `src/simulator/src/main.js`
   - STL 파일의 원본 좌표 유지 후 전체 모델을 원점 중심으로 자동 배치
   - geometry 정점 직접 이동 방식으로 변경 (mesh.position 대신 vertex 이동)
   - 복셀화/레이캐스트와의 좌표 정확도 보장
   - `centerToOrigin` 기본값 `true`로 변경

2. **동적 그리드/축 헬퍼**
   - 모델 크기에 비례하여 그리드 자동 조절 (2배 크기, 5~10mm 간격)
   - 축 헬퍼도 모델에 맞게 스케일링

3. **모델 정보 표시 UI**
   - 사이드바에 모델 크기/중심/min-max 좌표 실시간 표시
   - 복셀 모드와 원본 모드 모두 지원

4. **깊이 드릴링 구현** - `src/simulator/src/voxel.js`, `src/simulator/src/main.js`
   - `drillCylinder()` 메서드 추가: 캡슐(원통+반구) 형태로 깊이 방향 드릴링
   - 표면 법선 방향으로 지정된 깊이만큼 관통
   - 드릴 프리뷰: 구(sphere) → 원통+링+깊이디스크+축선으로 변경
   - 프리뷰가 표면 법선 방향에 맞춰 자동 회전
   - Depth 슬라이더 실제 적용 (기존엔 미사용)
   - 상태바에 실시간 드릴 반지름/깊이 표시

5. **드릴 프리뷰 하이라이트** - `src/simulator/src/voxel.js`, `src/simulator/src/main.js`
   - `previewDrill()` 메서드 추가: 제거될 복셀 좌표 목록 반환 (실제 제거 없음)
   - `drillCylinder()`가 `previewDrill()` 재사용하도록 리팩토링
   - InstancedMesh 기반 실시간 하이라이트 (빨간 복셀 오버레이)
   - hover=프리뷰, click=실제 드릴 방식으로 변경
   - 영향 복셀 수 상태바 표시 (예: D=10 (336))

## 이전 작업 내역 (2026-02-03)

### 완료
1. **NRRD 로딩 기능** - `src/simulator/src/nrrd.js`
   - 3D Slicer 볼륨/세그멘테이션 파일 로딩
   - Gzip 압축 지원 (pako 라이브러리)
   - 업샘플링/다운샘플링 지원

2. **해상도 조절 UI**
   - STL 복셀화: 32~192 슬라이더 + Re-voxelize 버튼
   - NRRD: Trilinear 보간 업샘플링

3. **파일 구조 정리**
   - `spine_sim/` → `src/`
   - `analysis/` → `fea/`
   - `web/` → `simulator/`
   - 진행상황 파일 → `docs/`
   - 테스트 파일 → `tests/` 폴더로 이동

4. **레거시 코드 삭제**
   - Taichi app 삭제
   - endoscope 모듈 삭제
   - api 폴더 삭제

5. **Playwright MCP 설치**
   - `@playwright/mcp` 글로벌 설치
   - `~/.claude/settings.json`에 MCP 서버 추가

6. **테스트 통과**
   - Solver (FEM + Peridynamics): 46개 통과
   - 웹 시뮬레이터: 정상 작동 확인

7. **STL 구조해석 파이프라인**
   - STL → 복셀화 → Peridynamics 입자 변환
   - L5 척추 압축 해석 테스트 완료

8. **FEA 시각화 웹 뷰어** - `src/fea/visualization/`
   - Three.js 기반 결과 시각화
   - Displacement/Strain/Damage 모드
   - NPZ → JSON 변환 도구

9. **Undo/Redo 기능** - `src/simulator/`
   - 복셀 스냅샷 저장/복원
   - Ctrl+Z/Y 키보드 단축키
   - 최대 30단계 히스토리

10. **단면 뷰 (Slice View)**
    - X(Sagittal)/Y(Coronal)/Z(Axial) 축 선택
    - 위치 슬라이더 (0~100%)
    - ClippingPlane + 반투명 헬퍼 평면

## 현재 구현 상태

### ✅ 완료된 모듈

#### 웹 시뮬레이터 (`src/simulator/`)
- STL 로딩 (L4, L5 척추)
- NRRD 로딩 (3D Slicer 호환)
- 복셀 기반 구체 드릴링 + Marching Cubes
- 해상도 조절 UI (32~192)
- **Undo/Redo** (Ctrl+Z/Y, 최대 30단계)
- **CAD 스타일 네비게이션** - 우클릭=회전, 중클릭=팬, 휠=줌 (항상 활성)
- **좌표 시스템 개선** - 원본 좌표 유지 + 자동 원점 중심 배치
- **동적 그리드** - 모델 크기에 맞게 자동 조절
- **모델 정보 UI** - 크기/중심/범위 실시간 표시
- **전처리기 (Pre-process)** - 구체 브러쉬 복셀 선택, 경계조건(Fixed/Force), 재료 프리셋 할당
- **후처리기 (Post-process)** - 변위/응력/손상 컬러맵 시각화, 변위 스케일, 입자 크기
- **탭 기반 CAE UI** - 상단 탭 바(File/Modeling/Pre-process/Solve/Post-process/View), 우측 컨텍스트 속성 패널, 하단 상태바
- **CT/MRI 파이프라인** - NIfTI 업로드 → 세그멘테이션 → 3D 모델 생성 (라벨별 메쉬)
- **임플란트 배치** - STL 임포트, TransformControls (이동/회전/스케일), 수술 계획 JSON 저장/로드
- **Material Library 시스템** - ANSYS/Abaqus 스타일 재료 라이브러리 (17종 빌트인 + 커스텀 저장)
  - 카테고리별 재료 DB: 골(5종), 디스크(4종), 임플란트(5종), 연조직(3종)
  - 병리학적 프리셋: 골다공증(피질골/해면골), 디스크 퇴행(Grade III~V), 경화골, 석회화 인대
  - 속성 편집기: E(대수 슬라이더, GPa/MPa 단위 전환), ν, ρ 미세 조정
  - 커스텀 재료 저장/로드 (localStorage)
  - SolvePanel `<optgroup>` 카테고리별 드롭다운
- **자동 재료 매핑** - SpineLabel 기반 자동 할당 + Material Library 연동
- **수술 전/후 비교** - 변위 차이 시각화 + 임플란트 주변 응력 필터 (반경 지정)
- **해석 검증** - 실행 전 BC/재료/전처리기 종합 검증, 오류 시 Run 버튼 비활성화 + 경고 표시
- **해석 타임아웃/취소** - 10분 자동 타임아웃 + Cancel 버튼, 서버 asyncio.Task 취소 지원
- **WS 지수 백오프** - 2s→4s→8s→16s→30s 자동 재연결 (최대 5회)
- **메모리 관리** - SceneManager dispose(): 전체 씬 리소스(geometry/material/texture) + GPU 컨텍스트 해제
- **렌더링 모드** - Solid / Wireframe / Solid+Wire 3종, 모델 투명도/조명 강도 조절
- **클리핑 평면** - X/Y/Z 축 선택 + 위치/반전 슬라이더 (PostProcessPanel)
- **결과 내보내기** - CSV 다운로드 (node, dx, dy, dz, von_mises_stress, damage)
- **스크린샷 캡처** - renderer.toDataURL → PNG 자동 다운로드
- **DICOM 자동 파이프라인 UI** - 폴더 선택 → 업로드 → 세그멘테이션 → 메쉬 추출 → Three.js 자동 로드
- 50+ FPS 성능

#### 서버 (`src/server/`)
- FastAPI + WebSocket 실시간 통신
- Python FEA framework 직접 호출 (GPU 자동 감지)
- 진행률 실시간 전송 (init → setup → bc → solving → done)
- 정적 파일 서빙 (시뮬레이터 + 해석 통합 단일 서버)
- **REST 업로드**: NIfTI/수술계획 파일 업로드 (`/api/upload`, `/api/upload_plan`)
- **세그멘테이션 파이프라인**: TotalSeg/TotalSpineSeg 서버 호출 → 표준 라벨맵
- **메쉬 추출 파이프라인**: 라벨맵 → Marching Cubes → vertices/faces (scikit-image)
- **자동 재료 매핑**: SpineLabel → 20종 재료 DB 자동 할당 (병리학적 변이 포함, 수동 편집 가능)
- **수술 계획 모델**: ImplantPlacement, SurgicalPlan (JSON 직렬화)
- **해석 취소 핸들러**: `cancel_analysis` WS 메시지 → asyncio.Task.cancel() + `cancelled` 응답
- **테스트: 35개** (모델 20 + 재료 7 + 메쉬 5 + 세그멘테이션 3)

#### 파이프라인 CLI (`src/pipeline/`)
- **Typer CLI**: `spine-sim` 명령어 — segment, postprocess, voxelize, solve, report, pipeline, server
- **Pydantic 설정**: TOML 기반 설정 (PipelineConfig, SegmentConfig 등)
- **SHA256 캐시**: 입력+스테이지+파라미터 해시로 결과 재사용, 자동 정리
- **5-스테이지 파이프라인**: segment → postprocess → voxelize → solve → report
- Rich 콘솔 출력 (진행률 스피너, 컬러)

#### 자동 세그멘테이션 (`src/segmentation/`)
- **SpineLabel 통합 라벨**: 100번대=척추(C1~SACRUM), 200번대=디스크, 300번대=연조직
- **TotalSegmentator (CT)**: Python API 래퍼, vertebrae C1~L5+sacrum
- **TotalSpineSeg (MRI)**: CLI 래퍼, 척추+디스크+척수
- **SpineUnified (CT+MRI)**: nnU-Net v2 기반 통합 모델, 51 클래스, 2채널 입력 (영상+도메인)
- **팩토리 패턴**: create_engine("totalseg"|"totalspineseg"|"spine_unified"), 미설치 시 힌트 포함 에러
- **라벨 변환**: convert_to_standard() — 엔진별 라벨 → SpineLabel 자동 변환
- **학습 파이프라인**: pseudo-label 생성, 라벨 병합, nnU-Net 형식 변환 (training/)

#### FEA (`src/fea/`)
- **통합 프레임워크**: Method.FEM/PD/SPG 전환만으로 솔버 교체, GPU 자동 감지 (CUDA→Vulkan→CPU)
- **FEM**: TET4, TRI3, HEX8, QUAD4 요소 (f64 정밀도)
  - **정적 솔버**: Newton-Raphson (비선형), 직접해법 (선형)
  - **동적 솔버** (신규): Newmark-beta (implicit) + Central Difference (explicit)
  - Rayleigh 감쇠, 집중 질량, 고유진동수 계산
- **Peridynamics**: NOSB-PD, 준정적 솔버 (f64 정밀도)
  - 스펙트럴 반경 기반 dt 추정 (개선)
- **SPG**: Smoothed Particle Galerkin (극한 변형/파괴 해석)
  - 경계 입자 적응형 안정화 (개선)
- **접촉**: 노드-노드 페널티 + 법선 감쇠력, 정적/준정적/명시적 모드
- **STL 구조해석**: STL → 복셀화 → Peridynamics 파이프라인
- 테스트: 309 passed, 0 failed (FEM 39 + PD 22 + SPG 31 + Framework 19 + Contact 19 + Core 48 + Pipeline 28 + Segmentation 68 + Server 35)
- 벤치마크: FEM 5개 + PD 5개 + SPG 5개 = 15개 해석해 비교

#### FEA 시각화 (`src/fea/visualization/`)
- Three.js 기반 웹 뷰어
- 시각화 모드: Displacement, von Mises Strain, Damage, Original
- Jet 컬러맵 + 컬러바
- 파티클 크기/변위 스케일/컬러 범위 조절
- 뷰 전환 (Top/Front/Side)
- 스크린샷 내보내기
- NPZ → JSON 변환 도구

#### Core (`src/core/`)
- mesh.py: 삼각형 메쉬, STL/OBJ 로딩
- volume.py: 복셀 볼륨, 드릴링
- collision.py: Ray casting 충돌 감지

### 🔲 미구현
- 내시경 시뮬레이션 (웹 버전으로 새로 구현 예정)

## 모듈 구조

```
src/
├── simulator/                 # Three.js 웹 시뮬레이터 (메인)
│   ├── index.html            # UI 레이아웃 (Analysis 패널 포함)
│   ├── src/
│   │   ├── main.js           # Three.js 메인 + Analysis 통합
│   │   ├── voxel.js          # 복셀 + Marching Cubes
│   │   ├── nrrd.js           # NRRD 파서
│   │   ├── ws.js             # WebSocket 클라이언트
│   │   ├── colormap.js       # Jet 컬러맵
│   │   ├── pre.js            # 전처리기 (면 선택, BC, 재료)
│   │   ├── post.js           # 후처리기 (컬러맵 시각화, 전/후 비교)
│   │   └── implant.js        # 임플란트 매니저 (TransformControls)
│   ├── stl/                  # 샘플 STL 파일
│   └── tests/                # 웹 테스트
├── pipeline/                  # CLI 파이프라인 (Phase 0)
│   ├── cli.py                # Typer CLI 진입점 (7 서브커맨드)
│   ├── config.py             # Pydantic 설정 + TOML 로드
│   ├── cache.py              # SHA256 해시 기반 캐시
│   ├── stages/               # 5-스테이지 (segment→postprocess→voxelize→solve→report)
│   └── tests/                # 테스트 (28개)
├── segmentation/              # 자동 세그멘테이션 (Phase 1)
│   ├── labels.py             # SpineLabel 통합 라벨 + nnU-Net 매핑
│   ├── base.py               # SegmentationEngine ABC
│   ├── totalseg.py           # TotalSegmentator (CT)
│   ├── totalspineseg.py      # TotalSpineSeg (MRI)
│   ├── nnunet_spine.py       # SpineUnified (CT+MRI, nnU-Net v2)
│   ├── factory.py            # create_engine() 팩토리
│   ├── training/             # 학습 데이터 준비 파이프라인
│   │   ├── config.py         # 데이터셋 경로 + 전처리 설정
│   │   ├── download.py       # 데이터셋 검증
│   │   ├── pseudo_label.py   # CT 디스크 pseudo-label 생성
│   │   ├── validate_labels.py # 해부학적 일관성 검증
│   │   ├── label_merge.py    # GT + pseudo-label 병합
│   │   ├── preprocess.py     # CT/MRI 정규화 + 도메인 채널
│   │   ├── convert_nnunet.py # nnU-Net 형식 변환
│   │   └── tests/            # 테스트 (24개)
│   └── tests/                # 테스트 (44개)
├── server/                    # FastAPI + WebSocket 서버
│   ├── app.py                # 메인 앱 + REST 업로드 + 정적 파일 서빙
│   ├── models.py             # Pydantic 데이터 모델 (BC, 재료, 임플란트, 수술계획)
│   ├── ws_handler.py         # WebSocket 핸들러 (해석, 세그멘테이션, 메쉬, 재료)
│   ├── analysis_pipeline.py  # FEA framework 호출
│   ├── segmentation_pipeline.py  # 세그멘테이션 서버 파이프라인
│   ├── mesh_extract_pipeline.py  # 라벨맵 → Marching Cubes 메쉬
│   ├── auto_material.py      # SpineLabel 자동 재료 매핑 (8종 DB)
│   └── tests/                # 서버 테스트 (35개)
├── core/                      # 핵심 데이터 구조 (Python)
└── fea/                       # 유한요소 해석 (Python)
    ├── framework/             # 통합 API (FEM/PD/SPG 전환, GPU 감지, 접촉 해석)
    │   ├── _adapters/        # FEM, PD, SPG, Rigid 어댑터 + base_adapter.py
    │   ├── rigid_body.py     # 강체(RigidBody) + 규정 운동(PrescribedMotion)
    │   ├── contact.py        # 접촉 알고리즘 (노드-노드 페널티 + Coulomb 마찰)
    │   ├── scene.py          # 다중 물체 Scene + 접촉 솔버
    │   └── tests/            # 통합 테스트 (19개) + 접촉 테스트 (15개) + 강체/마찰 (32개)
    ├── fem/                   # FEM 모듈
    ├── peridynamics/          # NOSB-PD 모듈
    ├── spg/                   # SPG 모듈 (극한 변형/파괴)
    │   ├── core/             # 입자, 커널, 본드, 핵심 계산
    │   ├── solver/           # 명시적 동적/준정적 솔버
    │   ├── material/         # 재료 모델
    │   └── tests/            # 테스트 (31개) + 벤치마크
    └── visualization/         # FEA 결과 웹 시각화
        ├── index.html        # FEA Viewer UI
        ├── src/main.js       # Three.js 시각화
        └── convert_npz.py    # NPZ→JSON 변환
```

## 상세 진행 문서

- `docs/SIMULATOR_PROGRESS.md` - 웹 시뮬레이터 진행 상황
- `docs/FEM_PROGRESS.md` - FEM 구현 상세
- `docs/NOSB_PD_PROGRESS.md` - NOSB-PD 구현 상세
- `docs/SPG_METHOD.md` - SPG 방법 기술 문서

## 실행 방법

```bash
# CLI 파이프라인 도움말
uv run spine-sim --help

# 전체 파이프라인 실행 (CT → 세그멘테이션 → 후처리 → 복셀화 → 해석 → 리포트)
uv run spine-sim pipeline input.nii.gz -o output/ --config config/pipeline.toml

# 개별 스테이지 실행
uv run spine-sim segment input.nii.gz -o output/segment --engine spine_unified --modality CT
uv run spine-sim postprocess labels.nii.gz -o output/postprocess
uv run spine-sim voxelize labels.nii.gz -o output/voxelize --resolution 64
uv run spine-sim solve voxel_model.npz -o output/solve --method spg
uv run spine-sim report result.npz -o output/report

# SpineUnified 모델 관련
uv run spine-sim download-model spine_unified          # 가중치 다운로드
uv run spine-sim validate-data --verse data/VerSe2020  # 데이터셋 검증
uv run spine-sim prepare-training-data /data -o nnUNet_raw  # 학습 데이터 변환

# 웹 시뮬레이터 + 해석 서버 (권장, 해석 기능 포함)
uv run spine-sim server --port 8000
# 또는: uv run python -m src.server.app
# 브라우저: http://localhost:8000

# 웹 시뮬레이터만 (해석 기능 없음)
cd src/simulator && python -m http.server 8080
# 브라우저: http://localhost:8080

# FEA 시각화
cd src/fea/visualization && python -m http.server 8081
# 브라우저: http://localhost:8081

# STL 구조해석 테스트
uv run python test_stl_fea.py

# Svelte 5 프론트엔드 개발 서버
cd src/frontend && npm run dev
# 브라우저: http://localhost:5174

# Svelte 프론트엔드 빌드 (→ src/simulator/dist/)
cd src/frontend && npm run build
```

---

## 프론트엔드 마이그레이션 (Svelte 5 + Vite + TypeScript) — ✅ 완료

기존 vanilla HTML/JS + Three.js r128 (CDN) 프론트엔드를 **Svelte 5 + Vite + Three.js r170+ + TypeScript** SPA로 전면 마이그레이션 완료.

### 마이그레이션 범위

| Phase | 내용 | 상태 |
|-------|------|------|
| **Phase 1** | 프로젝트 스캐폴딩 (Svelte 5 + Vite + Three.js r170) | ✅ |
| **Phase 2** | 핵심 로직 마이그레이션 (VoxelGrid, NRRDLoader, colormap) | ✅ |
| **Phase 3** | WS/해석 로직 (WSClient, PreProcessor, PostProcessor, ImplantManager) | ✅ |
| **Phase 4** | Svelte 5 runes 스토어 7개 + 액션 모듈 4개 | ✅ |
| **Phase 5** | UI 컴포넌트 (공통 5개 + Colorbar + 사이드바 패널 6개) | ✅ |
| **Phase 6** | 이벤트 핸들러 (포인터, 키보드 Ctrl+Z/Y, 드래그앤드롭) | ✅ |
| **Phase 7** | 프로덕션 빌드 + 통합 테스트 | ✅ |

### 신규 기술 스택

- **Svelte 5**: `$state`, `$derived`, `$bindable` runes 기반 반응형 상태
- **Vite 6**: HMR, `$lib` alias, proxy (`/ws` → 8000, `/api` → 8000)
- **Three.js r170+**: ES module import (`three/addons/...`), `SRGBColorSpace`
- **TypeScript strict**: 전체 코드 타입 안전성 보장

### 파일 구조 (`src/frontend/`)

```
src/frontend/
├── src/
│   ├── main.ts                    # Svelte 5 mount
│   ├── App.svelte                 # 루트 레이아웃
│   ├── app.css                    # CSS 변수, 전역 스타일
│   ├── components/
│   │   ├── Canvas3D.svelte        # Three.js + 포인터/키보드 이벤트
│   │   ├── Menubar.svelte         # 탭 바 + Undo/Redo
│   │   ├── Statusbar.svelte       # 상태바 (FPS, 모델 수, 정점/면)
│   │   ├── Colorbar.svelte        # Jet 컬러맵 시각화
│   │   ├── common/                # 공통 컴포넌트 (Slider, ToolButton 등)
│   │   └── sidebar/
│   │       ├── Sidebar.svelte     # 탭 기반 패널 전환
│   │       ├── FilePanel.svelte   # 모델 목록, STL/NRRD 로드
│   │       ├── ModelingPanel.svelte # 드릴, Undo/Redo
│   │       ├── PreProcessPanel.svelte # BC, 재료 할당
│   │       ├── SolvePanel.svelte  # 솔버 선택, 해석 실행
│   │       ├── PostProcessPanel.svelte # 결과 시각화
│   │       └── ViewPanel.svelte   # 카메라, 배경, 헬퍼
│   └── lib/
│       ├── three/
│       │   ├── SceneManager.ts    # Three.js 씬 관리
│       │   ├── VoxelGrid.ts       # 복셀 시스템 + Marching Cubes
│       │   ├── NRRDLoader.ts      # NRRD 파서
│       │   └── ImplantManager.ts  # 임플란트 TransformControls
│       ├── analysis/
│       │   ├── colormap.ts        # Jet 컬러맵
│       │   ├── PreProcessor.ts    # 면선택, BC, 재료, 해석 요청 조립
│       │   └── PostProcessor.ts   # 결과 시각화 (변위/응력/손상)
│       ├── ws/
│       │   ├── types.ts           # WS 메시지 타입 정의
│       │   └── client.ts          # WebSocket 클라이언트
│       ├── stores/                # Svelte 5 runes 스토어
│       │   ├── scene.svelte.ts    # 씬/모델 상태
│       │   ├── ui.svelte.ts       # 탭/상태바
│       │   ├── tools.svelte.ts    # 도구 상태 (드릴/브러쉬)
│       │   ├── analysis.svelte.ts # 해석 상태
│       │   ├── websocket.svelte.ts # WS 연결 상태
│       │   ├── history.svelte.ts  # Undo/Redo
│       │   └── pipeline.svelte.ts # DICOM 파이프라인
│       └── actions/               # 비즈니스 로직 액션
│           ├── loading.ts         # STL/NRRD 로드, 복셀 초기화
│           ├── drilling.ts        # 드릴 프리뷰/실행
│           ├── analysis.ts        # 해석 실행/결과 처리
│           └── pipeline.ts        # DICOM 파이프라인
├── public/stl/                    # 샘플 STL (L4, L5, disc)
├── package.json
├── vite.config.ts
├── tsconfig.json
└── svelte.config.js
```

### 빌드 결과

- **app JS**: 182 KB (gzip 60 KB)
- **Three.js**: 482 KB (gzip 122 KB) — 별도 청크 분리
- **CSS**: 13.3 KB (gzip 2.7 KB)
- **출력 경로**: `src/simulator/dist/` (FastAPI 정적 서빙 대응)
- **경고/에러**: 0개

### UX/워크플로우 개선 (2026-02-23)

| 항목 | 내용 |
|------|------|
| **빌드 청크 분리** | Three.js를 별도 청크로 분리 (661KB 단일 → 182KB + 482KB) |
| **a11y 라벨** | 모든 form input에 `for`/`id` 연결 (빌드 경고 0개) |
| **토스트 알림** | 로드/삭제/BC 적용 등 비동기 결과를 토스트로 표시 |
| **확인 다이얼로그** | Clear All, Clear All BC 등 파괴적 액션에 확인 필수 |
| **유효성 체크리스트** | Solve 탭에 Models/BC/Material 체크리스트 표시 |
| **솔버 설명** | FEM/PD/SPG 선택 시 한글 설명 표시 |
| **로딩 상태** | FilePanel 로드 중 버튼 비활성화 + "Loading..." 표시 |
| **에러 피드백** | 로드 실패 시 토스트 에러 알림 |
| **History 연결** | voxelGrids ↔ historyState 자동 연결 |
| **상태바 넘침 방지** | 긴 메시지 text-overflow: ellipsis 처리 |
| **Force BC 방향 UI** | X/Y/Z 개별 입력 + 프리셋 버튼 (↓-Y, ↑+Y, →+X, ⊙+Z) |
| **PostProcess 빈 상태** | 결과 없을 때 아이콘 + 안내 메시지 (기존 텍스트만 → 시각적 개선) |
| **버튼 disabled** | 모델 없을 때 Brush/Apply BC/Assign Material 등 비활성화 |
| **환경변수 지원** | `VITE_BACKEND_URL` 환경변수로 백엔드 URL 설정 가능 |
| **Magnitude 범위** | Force BC 최대값 1000N → 2000N 확장 |
| **Remove Last BC** | 마지막 BC만 제거하는 버튼 추가 |

### 후처리 시각화 + 전처리 UI 대폭 개선 (2026-02-23)

| 항목 | 내용 |
|------|------|
| **다중 컬러맵** | 6종 지원: Jet, Cool-to-Warm, Viridis, Grayscale, Rainbow, Turbo |
| **컬러맵 선택 UI** | 그라디언트 칩 그리드로 시각적 선택 (클릭 한 번) |
| **벡터 컴포넌트** | Magnitude / X / Y / Z 성분 별도 시각화 가능 |
| **CSS 그라디언트** | `colormapToCSS()` — 컬러맵 프리뷰용 동적 CSS 생성 |
| **데이터 범위 표시** | 현재 스칼라 필드의 min~max + 단위 표시 |
| **불투명도 제어** | 결과 포인트의 투명도 조절 (0.1~1.0) |
| **워프 범위 확장** | Warp by Vector 스케일 0~200 범위 |
| **PostProcessor 확장** | 컴포넌트 추출, 커스텀 범위, 임계값 필터, 클리핑 평면 내부 지원 |
| **통계 개선** | 입자 수, max 변위/응력/손상, 해석 방법 표시 |
| **스토어 동기화** | `syncFromPostProcessor()` — PostProcessor ↔ Svelte 스토어 자동 동기화 |
| **힘 크기 프리셋** | 50, 100, 200, 500, 1000 N 원클릭 버튼 |
| **크기 직접 입력** | 슬라이더 + 숫자 입력 필드 동시 지원 (최대 10000N) |
| **방향 6종 프리셋** | 압축/인장/측방/전방/굴곡/신전 (해부학적 한글 라벨) |
| **X/Y/Z 색상 코딩** | 축별 색상 배지 (빨강=X, 초록=Y, 파랑=Z) |
| **힘 벡터 미리보기** | `F = (0, -100, 0) N` 실시간 계산 표시 |
| **방향 정규화** | 비정규 방향 벡터도 자동 정규화 처리 |

### 모델별 멀티솔버 지정 (2026-02-24)

| 항목 | 내용 |
|------|------|
| **모델별 솔버 지정** | 각 모델(L4/L5/disc)에 독립적으로 FEM/PD/SPG 할당 가능 |
| **SolvePanel 테이블** | 모델명 + 솔버 + 재료를 한눈에 보는 그리드 UI |
| **솔버 색상 코딩** | FEM=파랑, PD=빨강, SPG=주황 점/테두리로 시각 구분 |
| **일괄 적용** | All FEM / All PD / All SPG 원클릭 버튼 |
| **요약 표시** | Run Analysis 버튼에 `(FEM×2, PD×1)` 형태로 솔버 구성 표시 |
| **solverAssignments** | `analysisState.solverAssignments` Record로 모델별 솔버 추적 |
| **PreProcessor 연동** | `buildAnalysisRequest()` → 각 material에 `method` 필드 포함 |
| **백엔드 멀티솔버** | `analysis_pipeline.py` — 영역별 그룹 분리 실행 후 결과 합성 |
| **MaterialRegion.method** | Pydantic 모델에 `method` 필드 추가 (기본값 "fem") |
| **솔버 설명** | FEM/PD/SPG 각각 한글 설명 + 색상 배지로 표시 |

# NPZ → JSON 변환
uv run python src/fea/visualization/convert_npz.py fea_result.npz output.json

# 테스트
uv run pytest src/ -v
```

### 임플란트 카탈로그 배치 + 3D 하중 편집기 (2026-02-24)

#### 임플란트 카탈로그 배치 시스템

| 항목 | 내용 |
|------|------|
| **더미 STL 생성** | `scripts/gen_implant_stls.py` — Python stdlib만으로 9개 STL 생성 |
| **스크류 5종** | M5×40, M6×45, M6×50, M7×50, M7×55 (원기둥 형태, 각 80 삼각형) |
| **케이지 4종** | cage_S(22×8mm), cage_M(26×10mm), cage_L(26×12mm), cage_XL(32×14mm) |
| **STL 위치** | `public/stl/implants/screws/` + `cages/` |
| **ImplantManager** | STL URL 기반 로드, 표면 법선 정렬 배치, TransformControls 이동/회전 |
| **표면 스냅** | 뼈 클릭 → 법선 방향으로 임플란트 +Y 정렬 (`Quaternion.setFromUnitVectors`) |
| **자유 이동/회전** | TransformControls (translate/rotate) — 드래그 중 OrbitControls 자동 비활성화 |
| **케이지 충돌 감지** | 실시간 AABB(Box3) 교차 검사 — 충돌 시 빨간색 반투명으로 경고 |
| **implantCatalog.ts** | 카탈로그 데이터 + selectImplantForPlacement / placeImplantAtClick / deleteSelectedImplant |
| **$state 반응성** | `implantCount = $state(0)` → Svelte `$derived`로 목록 갱신 |
| **연속 배치** | 배치 후 모드 유지 → 같은 임플란트 여러 개 연속 배치 가능 (Esc로 종료) |
| **Delete 키** | 선택된 임플란트 삭제 |
| **ModelingPanel** | 카탈로그 탭(Screw/Cage/Rod), 배치 목록, Move/Rotate/Del 컨트롤 |

#### 3D 하중 벡터 편집기

| 항목 | 내용 |
|------|------|
| **ForceArrowHandle** | ArrowHelper(빨강) + 구형 드래그 핸들(주황) |
| **화살표 길이** | `30 + ||F|| / 10` (힘 크기에 비례) |
| **드래그 평면** | 카메라 -Z 방향 평면 (Plane + Ray 교차) |
| **방향/크기 계산** | 드래그 히트점 → 새 방향 벡터 + 초기 크기 유지 |
| **toolsState.forceVector** | 3D 핸들 ↔ PreProcessPanel X/Y/Z 입력 양방향 실시간 동기화 |
| **3D 편집 버튼** | PreProcessPanel Force BC 섹션 상단에 토글 버튼 추가 |
| **$effect 동기화** | forceVector 변화 → 패널 dirX/Y/Z + forceMagnitude 자동 업데이트 |
| **패널→화살표 즉시 반영** | 방향 프리셋/슬라이더 변경 시 화살표도 즉시 업데이트 |

#### 아키텍처 변경

| 항목 | 내용 |
|------|------|
| **implants.ts 정리** | requestScrew/Cage 제거, 가이드라인 전용으로 축소 |
| **initGuidelineLayer** | (구 initImplantLayer) 가이드라인 씬 그룹만 담당 |
| **WebSocket 임플란트 제거** | ImplantManager + STL 파일 방식으로 완전 대체 |
| **빌드 검증** | `npm run build` → 0 오류, 0 경고 ✅ |

#### 케이지 디스트랙션 (Cage Distraction) — 구현 완료 (2026-02-24)

> **사용자 피드백**: "케이지 넣는 거 설계 잘해야 해. 실제처럼 높은 거 넣으면 디스크 스페이스 높이가 올라가는 거"

| 항목 | 내용 |
|------|------|
| **알고리즘** | 케이지 Y 중심 기준으로 상위/하위 척추 자동 탐색, `deltaH = cageHeight − originalGap` |
| **케이지 높이 소스** | 카탈로그 `heightMm` 우선 사용 (기울어진 배치 시 AABB 오차 방지) |
| **상위 척추 이동** | `superiorMesh.position.y += deltaH` — 추간판 공간 교정 |
| **케이지 위치 조정** | `cage.position.y += deltaH * 0.5` — 디스크 공간 중앙 유지 |
| **결과 피드백** | 토스트: "디스트랙션 적용: {gap}mm → {cage}mm (상위 척추 +{delta}mm)" |
| **CatalogItem.heightMm** | cage_S=8, cage_M=10, cage_L=12, cage_XL=14 (mm) |
| **toolsState.pendingImplantHeightMm** | 배치 모드 진입 시 heightMm 전달 체인 구축 |
| **undo 지원** | `undoDistraction(cageName, result)` — 원위치 복원 |
| **UI** | ModelingPanel 케이지 선택 시 보라색 Distraction 바 표시 |
| **E2E 검증** | Cage M 배치 → Apply → "+10.0mm" 정확 적용 ✅ |

#### 버그 수정 및 호환성 (2026-02-24)

| 항목 | 내용 |
|------|------|
| **rune_outside_svelte 수정** | `ImplantManager.ts` → `ImplantManager.svelte.ts` 파일명 변경 (`$state` 룬 사용 가능 확보) |
| **Three.js r170 호환성** | TransformControls가 더 이상 Object3D 미상속 → `getHelper()` 패턴으로 씬 추가 수정 |
| **Canvas3D.svelte 정리** | 디버그 코드 제거 (window.__app, console.log, try-catch) — HMR 재로드 문제 해결 |
| **ForceArrow 가시성 개선** | `setOrigin()` — 모델 bbox 상단으로 화살표 이동, `setScale()` — bbox 크기에 비례 스케일 |
| **일러스트 스타일 드래그** | 3D 편집 모드 시 뷰포트 어디서든 클릭-드래그 → 화살표 방향/크기 변경 (구 핸들 클릭 불필요) |
| **updateFromDrag 좌표 수정** | 그룹 이동 후 `this.group.position` 기준으로 방향 계산 (하드코딩 원점 버그 수정) |
| **꼬리 마커** | 화살표 시작점에 주황 구 표시 (시각적 기준점) |
| **빌드 검증** | `npm run build` → 0 오류, 0 경고 ✅ |

#### Force BC 화살표 기준점 정확화 (2026-02-25)

| 항목 | 내용 |
|------|------|
| **getBrushSelectionCentroid() 추가** | `PreProcessor.ts`: 브러쉬 선택 복셀의 월드 좌표 무게 중심 계산 메서드 신규 추가 |
| **forceBCOrigin 상태** | `analysis.svelte.ts`: Force BC 적용 영역 중심 좌표 `[x, y, z]` 저장 상태 추가 |
| **addForceBC() 중심점 저장** | `analysis.ts`: Force BC 적용 전 브러쉬 선택 중심점을 `forceBCOrigin`에 저장 (brushSelection 초기화 전) |
| **화살표 기준점 우선순위** | `PreProcessPanel.svelte toggle3DEdit()`: (1) 라이브 브러쉬 중심 → (2) 저장된 forceBCOrigin → (3) 폴백: bbox 상단 |
| **안내 토스트 메시지** | 각 케이스별 toast 메시지로 사용자에게 화살표 기준점 정보 안내 |
| **빌드 검증** | `npm run build` → 0 오류, 0 경고 ✅ |

#### STL 자동 오리엔테이션 + 로드 즉시 복셀화 + Force Arrow 개선 (2026-02-25)

| 항목 | 내용 |
|------|------|
| **autoOrientGeometry() 추가** | `SceneManager.ts`: 모든 STL 로드 시 최장 축 자동 감지 → Y축(상하) 정렬 회전 적용 |
| **오리엔테이션 로직 (1차)** | Z 최장 → X축 -90° 회전 (Z→Y); X 최장 → Z축 -90° 회전; Y 최장 → 무변환 |
| **focusOnAllMeshes() 추가** | `SceneManager.ts`: 복수 메쉬 AABB 합산 후 3/4 사선 뷰 카메라 포커스 (Y-up 보장) |
| **로드 즉시 복셀화** | `loading.ts`: `loadSampleModels()` / `loadSTLFiles()` 완료 즉시 `initializeVoxels()` 자동 호출 |
| **드래그 방향 전용** | `ForceArrowHandle.ts updateFromDrag()`: drag는 방향만 변경, 크기(initialMagnitude)는 불변 유지 |
| **PreProcessor 자동 초기화** | `PreProcessPanel.svelte onMount` + `toggleBrush()` 에서 미초기화 시 자동 `initAnalysis()` 호출 |
| **빌드 검증 (1차)** | `npm run build` → 0 오류, 0 경고 ✅ |

#### 척추 오리엔테이션 정확화 + 원점 중심화 + Force BC 구 위치 개선 (2026-02-25)

**문제 발견**: 요추 개별 STL의 최장축 = X (좌우 폭, ~90mm) ≠ 상하 축 (Z, ~50mm).
1차 최장축 탐지 로직은 X→Y 정렬해 좌우 폭을 수직으로 만드는 오류 발생.

| 항목 | 내용 |
|------|------|
| **오리엔테이션 로직 수정** | `SceneManager.ts autoOrientGeometry()`: 최장축 탐지 제거. CT Z(상하, scanner축)→Y 항상 적용. `makeRotationX(-PI/2)` |
| **해부학적 근거** | L4 Z center=-1134 > L5 Z center=-1167 → Z→Y 후 L4 Y > L5 Y → L4 위(머리)/L5 아래(발) ✓ |
| **원점 중심화** | `loading.ts centerMeshesAtOrigin()`: 모든 모델 로드+회전 후 combined bbox 중심(-1149)을 (0,0,0)으로 평행이동 |
| **상대 위치 보존** | 모든 geometry에 동일한 -center 이동 적용 → L4/disc/L5 간격(32mm) 유지 |
| **중심화 결과** | L4 Y center≈+15, disc Y≈-4, L5 Y center≈-18 → 그리드(Y=0)가 disc 위에 위치 ✓ |
| **Force 구 위치** | `PreProcessPanel toggle3DEdit()` 폴백: `box.max.y`(top face) → `box.getCenter()`(모델 중심) + 경고 토스트 |
| **Force 구 우선순위** | (1) 라이브 브러쉬 centroid → (2) forceBCOrigin(Apply Force BC 후) → (3) 모델 center + 경고 |
| **스케일 계산 수정** | voxelMeshes 기준으로 bbox 계산 (원본 STL은 복셀화 후 숨겨짐) |
| **voxelMeshes import** | `PreProcessPanel.svelte`: `$lib/actions/loading` 에서 voxelMeshes import 추가 |
| **E2E 검증** | 로드 → L4 위/L5 아래/disc 중간 확인 ✓ · Apply Force BC 버튼 확인 ✓ · 원점 중심화 확인 ✓ |
| **빌드 검증** | `npm run build` → 0 오류, 0 경고 ✅ |

#### Force BC 워크플로우 개선 — Apply 먼저, 방향 편집 나중에 (2026-02-25)

| 항목 | 내용 |
|------|------|
| **UI 재배치** | Step 2 Force BC 섹션: Apply 버튼을 최상단으로 이동, 방향/크기 편집은 Apply 후에만 표시 |
| **워크플로우 가이드** | 힌트: "1) 브러쉬로 영역 선택 → 2) Apply → 3) 방향/크기 편집" |
| **Apply 후 자동 3D 편집** | `handleApplyForce()`: centroid 저장 후 자동으로 `toggle3DEdit()` 호출 → 화살표 즉시 표시 |
| **브러쉬 미선택 가드** | Apply 클릭 시 brush count = 0이면 "⚠ 먼저 Brush로 Force 영역을 선택하세요" 경고 |
| **조건부 편집 섹션** | `hasForceBC = $derived(forceBCOrigin !== null)` → Apply 전에는 방향/크기 편집 완전 숨김 |
| **Force BC 업데이트** | `handleUpdateForce()`: 마지막 BC 삭제 → 새 방향/크기로 재적용 (방향 변경 반영) |
| **빌드 검증** | `npm run build` → 0 오류, 0 경고 ✅ |

#### 스크류 2클릭 배치 UX 개선 (2026-02-25)

> **배경**: 이전 드래그 방식은 pointerdown~pointerup 사이 카메라 회전 불가, async STL 로드 경쟁 조건 등 UX 문제가 있었음.
> **개선**: 2클릭(진입점→카메라 자유 회전→끝점) 방식으로 전환하여 사용성 대폭 향상.

| 항목 | 내용 |
|------|------|
| **스크류 2클릭 배치** | 1단계: 뼈 표면 클릭 → 진입점 설정 (노란 구체 마커 표시), 카메라 자유 회전 가능. 2단계: 끝점 클릭 → 진입점→끝점 방향으로 스크류 배치 |
| **ImplantManager 마커/프리뷰** | `showEntryMarker(pos)`: 노란 구체(r=1.5) 표시, `updatePreviewLine(target)`: 진입점→커서 빨간 프리뷰 라인, `hideEntryMarker()`: 마커+라인 제거+GPU 리소스 해제 |
| **implantCatalog 2클릭 API** | `setEntryPoint()`: 1단계 진입점 저장, `placeAtDirection()`: 2단계 방향 배치, `updateDirectionPreview()`: 프리뷰 라인 업데이트, `cancelScrewEntry()`: 취소, `hasEntryPoint()`/`getEntryPoint()`: 단계 판별 |
| **Canvas3D 이벤트 플로우** | implantPlace + screw: 1st click → `setEntryPoint()`, 2nd click → `placeAtDirection()`. pointermove: 진입점 설정 후 프리뷰 라인 업데이트 (뼈 밖이면 카메라 평면 투영). 케이지: 기존 단일 클릭 배치 유지 |
| **카메라 자유 회전** | 2클릭 모드에서 OrbitControls 비활성화 없음 — 진입점 설정 후 자유롭게 시야를 돌려 방향 확인 가능 |
| **레이캐스터 복셀 대응** | `getIntersection()`에 `voxelMeshes` 추가. 복셀화 후 원본 STL 메쉬가 `visible=false`이므로 복셀 메쉬도 대상에 포함 |
| **ModelingPanel 힌트** | 스크류: "🔩 1. 진입점 클릭 → 카메라 회전 → 2. 끝점 클릭", 케이지: "🦴 뼈 표면을 클릭해 배치" |
| **E2E 검증** | 스크류 2클릭 배치 ✓ · 진입점 마커 표시 ✓ · 카메라 자유 회전 ✓ · 케이지 클릭 배치 ✓ · TransformControls ✓ · 카탈로그 탭 전환 ✓ · Placed Implants 목록 ✓ |
| **빌드 검증** | `npm run build` → 0 오류, 0 경고 ✅ |

**수정 파일**:
- `src/frontend/src/lib/three/ImplantManager.svelte.ts` — 드래그 API 제거, 진입점 마커+프리뷰 라인 API 3개 추가
- `src/frontend/src/lib/actions/implantCatalog.ts` — 드래그 함수 제거, 2클릭 배치 함수 6개 추가
- `src/frontend/src/components/Canvas3D.svelte` — 2클릭 이벤트 플로우 + 카메라 평면 투영 + `getEntryPoint` import 수정
- `src/frontend/src/components/sidebar/ModelingPanel.svelte` — 스크류 배치 힌트 2클릭 방식으로 변경

#### 연결 로드(Rod) 카탈로그 추가 (2026-02-25)

| 항목 | 내용 |
|------|------|
| **Rod STL 생성** | `gen_implant_stls.py`에 ROD_SPECS 추가 — 5종 (40/50/60/80/100mm), Ø5.5mm 원기둥, 16 segments |
| **카탈로그 항목** | `implantCatalog.ts`에 rod 5개 항목 추가 — titanium 재질, `/stl/implants/rods/` 경로 |
| **2클릭 배치** | Canvas3D에서 rod도 screw와 동일한 2클릭(진입점→끝점) 배치 적용 |
| **ModelingPanel UI** | Rod 탭에 5개 항목 표시, 🔗 아이콘 힌트, 파란색 [R] 배지 추가 |
| **E2E 검증** | Rod 탭 표시 ✓ · Rod 60 2클릭 배치 ✓ · TransformControls ✓ · Placed Implants 목록 ✓ |
| **빌드 검증** | `npm run build` → 0 오류, 0 경고 ✅ |

**수정/신규 파일**:
- `scripts/gen_implant_stls.py` — ROD_SPECS 5종 + 로드 STL 생성 로직 추가
- `src/frontend/public/stl/implants/rods/` — rod_40~rod_100.stl 5개 파일 신규
- `src/frontend/src/lib/actions/implantCatalog.ts` — rod 카탈로그 항목 5개 추가
- `src/frontend/src/components/Canvas3D.svelte` — rod 카테고리 2클릭 배치 적용
- `src/frontend/src/components/sidebar/ModelingPanel.svelte` — rod 힌트/배지 추가

#### Material Library 시스템 (2026-02-25)

> **배경**: 기존 재료 시스템은 4개 하드코딩 프리셋(bone/disc/ligament/titanium)으로만 구성.
> 골다공증(T-score ≤ -2.5), 디스크 퇴행(Pfirrmann Grade III~V), 경화골, 다양한 임플란트 재질
> (PEEK, CoCr, 316L, UHMWPE) 등 환자별 물성 변이를 반영할 수 없었음.
> ANSYS/Abaqus 스타일 Material Library를 구현하여 해결.

**신규 파일**:
- `src/frontend/src/lib/stores/materials.svelte.ts` — Material Library 스토어 (17종 빌트인 + 커스텀 CRUD + localStorage)
- `src/frontend/src/components/sidebar/MaterialLibraryPanel.svelte` — 카테고리 탭 + 검색 + 속성 편집기 (대수 E 슬라이더)

**수정 파일**:
- `src/frontend/src/lib/analysis/PreProcessor.ts` — ResolvedMaterial 인터페이스 추가, materialAssignments 타입 변경 (string → ResolvedMaterial)
- `src/frontend/src/lib/actions/analysis.ts` — assignMaterial 시그니처 변경
- `src/frontend/src/components/sidebar/PreProcessPanel.svelte` — Step 3 → MaterialLibraryPanel 임베드
- `src/frontend/src/components/sidebar/SolvePanel.svelte` — 카테고리별 optgroup 드롭다운
- `src/server/services/auto_material.py` — SPINE_MATERIAL_DB 병리학적 재료 12종 추가 (총 20종)

**재료 카테고리 (17종)**:
| 카테고리 | 재료 |
|----------|------|
| Bone (5) | 피질골, 해면골, 골다공증 피질골, 골다공증 해면골, 경화골 |
| Disc (4) | 정상 디스크, 퇴행 III, 퇴행 IV, 퇴행 V |
| Implant (5) | Ti-6Al-4V, PEEK, CoCr, 316L, UHMWPE |
| Soft Tissue (3) | 인대, 석회화 인대, 연조직 |

#### 해석 파이프라인 안정성 9-Step 개선 (2026-02-25)

> **배경**: 백엔드 솔버(FEM/PD/SPG)는 잘 구현되어 있지만, 프론트엔드→백엔드 연결부에서
> 검증 부재, 타임아웃/취소 없음, WS 에러 복구 불안정, 메모리 누수, DICOM UI 부재 등의
> 안정성 문제를 9개 Step으로 일괄 개선.

##### Step 1 (P0): 해석 실행 전 종합 검증

| 항목 | 내용 |
|------|------|
| **canRun 게터** | `analysis.svelte.ts`: BC > 0, 미실행, preProcessor 초기화 확인 → false면 Run 버튼 비활성화 |
| **validationErrors 게터** | 전처리기 미초기화, BC 미설정, Fixed BC 없음 등 검증 실패 목록 반환 |
| **lastError / elapsedMs** | 마지막 에러 메시지 + 소요 시간 상태 추가 |
| **runAnalysis() 강화** | `analysis.ts`: 서버 전송 전 `validationErrors` 확인, 100ms 타이머로 소요 시간 추적 |
| **SolvePanel 검증 UI** | 검증 에러 주황색 경고 박스 + 비활성화 Run 버튼 + 완료 후 소요 시간 표시 |

##### Step 5 (P0): Force BC 입력 검증 강화

| 항목 | 내용 |
|------|------|
| **buildAnalysisRequest → null** | `PreProcessor.ts`: 반환 타입 `AnalysisRequest \| null`, 검증 실패 시 null |
| **검증 항목** | 빈 복셀 그리드, BC 0개, Fixed BC 없음, Force 벡터 차원≠3, 크기 < 1e-6 |
| **toast 피드백** | 각 검증 실패 시 한글 경고 메시지 토스트 표시 |
| **호출자 수정** | `runAnalysis()`: null 반환 시 중단 처리 |

##### Step 2 (P1): 해석 타임아웃 + 취소 기능

| 항목 | 내용 |
|------|------|
| **sendAnalysis()** | `client.ts`: `crypto.randomUUID()` 요청 ID 생성 + 10분 타임아웃 자동 설정 |
| **cancelAnalysis()** | 클라이언트: `cancel_analysis` WS 메시지 전송 + 타임아웃 정리 |
| **서버 핸들러** | `ws_handler.py`: `_running_tasks` 딕셔너리로 asyncio.Task 추적, `task.cancel()` 호출 |
| **cancelled 메시지** | 서버 → 클라이언트: `CancelledError` 발생 시 `cancelled` 응답 전송 |
| **Cancel 버튼** | SolvePanel: 해석 중일 때 "⏹ Cancel" 버튼 표시 |
| **타임아웃 에러** | 10분 초과 시 자동 취소 + "메쉬를 단순화하거나 서버 확인" 안내 |

##### Step 3 (P1): WS 에러 복구 강화

| 항목 | 내용 |
|------|------|
| **지수 백오프 재연결** | `client.ts`: 2s → 4s → 8s → 16s → 30s (최대), 5회까지 시도 |
| **WSStatus 확장** | `websocket.svelte.ts`: `'disconnected' \| 'connecting' \| 'connected' \| 'failed'` |
| **reconnectAttempt 추적** | 연결 성공 시 카운터 리셋, 최대 초과 시 `setFailed()` |
| **resetReconnect()** | 수동 재연결 시 카운터 초기화 메서드 |

##### Step 4 (P1): SceneManager 메모리 관리

| 항목 | 내용 |
|------|------|
| **dispose() 강화** | `SceneManager.ts`: 애니메이션 루프 중단 + 이벤트 리스너 제거 + OrbitControls dispose |
| **씬 리소스 정리** | traverse: Mesh/InstancedMesh/Line/Points geometry + material 전부 dispose |
| **텍스처 정리** | `_disposeMaterial()`: map, normalMap, roughnessMap, emissiveMap 등 텍스처 해제 |
| **GPU 컨텍스트** | `renderer.dispose()` + `renderer.forceContextLoss()` + 캔버스 DOM 제거 |

##### Step 6 (P2): 클리핑 평면 UI

| 항목 | 내용 |
|------|------|
| **PostProcessPanel 섹션** | Clip Plane: 활성화 토글, 축(X/Y/Z) 선택, 위치 슬라이더(-1~1), 반전 토글 |
| **PostProcessor 연동** | `setClipPlane({ enabled, axis, position, invert })` 호출 |
| **analysisState 동기화** | `clipEnabled, clipAxis, clipPosition, clipInvert` 상태 관리 |

##### Step 7 (P2): 결과 내보내기

| 항목 | 내용 |
|------|------|
| **exportResultsCSV()** | `analysis.ts`: node, dx, dy, dz, von_mises_stress, damage 열로 CSV 생성 |
| **_downloadBlob()** | Blob → URL.createObjectURL → a 태그 클릭 → URL 해제 |
| **Export 버튼** | PostProcessPanel: "📄 Export CSV" 버튼 |

##### Step 8 (P3): ViewPanel 강화

| 항목 | 내용 |
|------|------|
| **렌더링 모드** | Solid / Wire / Solid+Wire 3종 토글 (`_addWireOverlay` / `_clearWireOverlay`) |
| **와이어프레임 오버레이** | MeshBasicMaterial(wireframe, opacity=0.15) 클론 메쉬 추가 |
| **투명도 슬라이더** | 모델별 opacity 0.1~1.0 (depthWrite 자동 관리) |
| **조명 강도 슬라이더** | directional light intensity 0.0~2.0 |
| **스크린샷 캡처** | `renderer.domElement.toDataURL('image/png')` → 자동 다운로드 |

##### Step 9 (P1): CT DICOM 자동 파이프라인 UI

| 항목 | 내용 |
|------|------|
| **FilePanel DICOM 버튼** | "🏥 Load DICOM (CT/MRI)" — webkitdirectory 폴더 선택 |
| **파이프라인 진행 UI** | 단계별 진행률 바 + 한글 단계 설명 (업로드/세그멘테이션/메쉬추출) |
| **자동 메쉬 로드** | `pipeline.ts _loadPipelineMeshes()`: 결과 STL 경로 → Three.js 자동 로드 + 복셀화 |
| **loadSTLFromURL()** | `loading.ts`: 서버 경로 fetch → STLLoader.parse → CT 좌표 회전(-PI/2) → 씬 추가 |
| **_autoColor()** | 구조명 기반 자동 색상: disc→주황, L*→베이지, C*→청록, T*→회청 |
| **워크플로우** | DICOM 선택 → REST 업로드 → WS 3단계 자동 실행 → 메쉬 자동 로드 → 바로 작업 가능 |

##### 수정 파일 총괄 (9 Step)

| 파일 | Step | 변경 내용 |
|------|------|----------|
| `lib/stores/analysis.svelte.ts` | 1 | `canRun`, `validationErrors`, `lastError`, `elapsedMs` |
| `lib/actions/analysis.ts` | 1, 2, 7 | `runAnalysis()` 검증 + `cancelAnalysis()` + `exportResultsCSV()` |
| `components/sidebar/SolvePanel.svelte` | 1, 2 | 검증 UI + Cancel 버튼 + 소요 시간 |
| `lib/ws/client.ts` | 2, 3 | 타임아웃/취소 + 지수 백오프 재연결 |
| `lib/ws/types.ts` | 2 | `cancelled` 메시지 타입 + `CancelledCallback` |
| `lib/stores/websocket.svelte.ts` | 3 | WSStatus 확장 + reconnectAttempt |
| `server/ws_handler.py` | 2 | `cancel_analysis` 핸들러 + asyncio.Task 추적 |
| `lib/three/SceneManager.ts` | 4 | `dispose()` 전면 강화 |
| `lib/analysis/PreProcessor.ts` | 5 | `buildAnalysisRequest()` → null 반환 검증 |
| `components/sidebar/PostProcessPanel.svelte` | 6, 7 | 클리핑 평면 UI + Export CSV 버튼 |
| `components/sidebar/ViewPanel.svelte` | 8 | 렌더링 모드 + 투명도 + 조명 + 스크린샷 |
| `components/sidebar/FilePanel.svelte` | 9 | DICOM 업로드 + 파이프라인 진행 UI |
| `lib/actions/pipeline.ts` | 9 | 결과 메쉬 자동 로드 콜백 |
| `lib/actions/loading.ts` | 9 | `loadSTLFromURL()` + `_autoColor()` |
| **빌드 검증** | 전체 | `npm run build` → 0 오류, 0 경고 ✅ |

