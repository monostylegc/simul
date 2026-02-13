# Spine Surgery Planner — 프로젝트 목표 및 워크플로우

최종 업데이트: 2026-02-14

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

## End-to-End 워크플로우 (6단계)

```
CT/MRI NIfTI ──→ [1] 세그멘테이션 ──→ [2] 3D 모델 생성 ──→ [3] 수술 도구 배치
                                                                     │
                    [6] 후처리 시각화 ←── [5] 구조해석 ←── [4] 전처리  ←┘
```

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
│   ├── ws_handler.py            # WebSocket 메시지 라우팅 (4종 파이프라인 호출)
│   ├── analysis_pipeline.py     # FEA 프레임워크 호출 파이프라인
│   ├── segmentation_pipeline.py # 세그멘테이션 엔진 호출
│   ├── mesh_extract_pipeline.py # Marching Cubes 메쉬 추출
│   ├── auto_material.py         # SpineLabel → 재료 자동 매핑 (8종 DB)
│   └── tests/                   # 서버 테스트 (35개)
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
  {"type": "segment",        "data": SegmentationRequest}   # 세그멘테이션 실행
  {"type": "extract_meshes", "data": MeshExtractRequest}    # 3D 메쉬 추출
  {"type": "auto_material",  "data": AutoMaterialRequest}   # 자동 재료 매핑
  {"type": "run_analysis",   "data": AnalysisRequest}       # FEA 해석 실행
  {"type": "ping"}                                          # 연결 확인

서버 → 클라이언트:
  {"type": "progress",         "data": {"step": "init|setup|bc|solving|done", ...}}
  {"type": "segment_result",   "data": {labels_path, n_labels, label_info[]}}
  {"type": "meshes_result",    "data": {meshes: [{vertices, faces, color}]}}
  {"type": "material_result",  "data": {materials: [{name, E, nu, density}]}}
  {"type": "result",           "data": {displacements, stress, damage, info}}
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

최종 업데이트: 2026-02-14

## 오늘 작업 내역 (2026-02-14)

### 완료

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
- **자동 재료 할당** - SpineLabel 기반 8종 프리셋 + 수동 E/nu/density 편집
- **수술 전/후 비교** - 변위 차이 시각화 + 임플란트 주변 응력 필터 (반경 지정)
- 50+ FPS 성능

#### 서버 (`src/server/`)
- FastAPI + WebSocket 실시간 통신
- Python FEA framework 직접 호출 (GPU 자동 감지)
- 진행률 실시간 전송 (init → setup → bc → solving → done)
- 정적 파일 서빙 (시뮬레이터 + 해석 통합 단일 서버)
- **REST 업로드**: NIfTI/수술계획 파일 업로드 (`/api/upload`, `/api/upload_plan`)
- **세그멘테이션 파이프라인**: TotalSeg/TotalSpineSeg 서버 호출 → 표준 라벨맵
- **메쉬 추출 파이프라인**: 라벨맵 → Marching Cubes → vertices/faces (scikit-image)
- **자동 재료 매핑**: SpineLabel → 8종 재료 DB 자동 할당 (제안값, 수동 편집 가능)
- **수술 계획 모델**: ImplantPlacement, SurgicalPlan (JSON 직렬화)
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
    │   ├── _adapters/        # FEM, PD, SPG 어댑터 + base_adapter.py
    │   ├── contact.py        # 접촉 알고리즘 (노드-노드 페널티)
    │   ├── scene.py          # 다중 물체 Scene + 접촉 솔버
    │   └── tests/            # 통합 테스트 (19개) + 접촉 테스트 (15개)
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

# NPZ → JSON 변환
uv run python src/fea/visualization/convert_npz.py fea_result.npz output.json

# 테스트
uv run pytest src/ -v
```
