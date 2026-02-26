# Spine Surgery Planner — 프로젝트 현황

최종 업데이트: 2026-02-26 (14차)

> 이전 상세 작업 내역은 `docs/archive/PROJECT_STATUS_OLD.md` 참조

---

## 프로젝트 개요

**UBE/Biportal 내시경 척추 수술 계획 및 시뮬레이션 도구**

환자 CT/MRI → 자동 세그멘테이션 → 3D 모델 생성 → 임플란트 배치 → 구조해석 → 안전성 검증

### 기술 스택
- **프론트엔드**: Svelte 5 + TypeScript + Three.js + Vite
- **백엔드**: FastAPI + WebSocket + Taichi GPU
- **세그멘테이션**: TotalSpineSeg / TotalSegmentator / nnU-Net v2
- **해석**: FEM (정적/동적/호장법) + NOSB-PD (파괴) + SPG (무격자) + **FEM↔PD/SPG 적응적 커플링**
- **재료 모델**: Linear Elastic, Neo-Hookean, Mooney-Rivlin, Ogden, J2 Plasticity, Transverse Isotropic
- **전처리**: Abaqus .inp / GMSH .msh v4 메쉬 임포트 + Per-DOF 경계조건 + 표면 압력 하중
- **후처리**: VTK 내보내기 + 에너지 균형 검증

---

## End-to-End 워크플로우 (7단계) — 전체 ✅ 완료

```
[0] DICOM 파이프라인   ✅  CT/MRI → NIfTI → 세그멘테이션 → 메쉬 → 자동 로드
[1] 세그멘테이션       ✅  TotalSpineSeg/TotalSeg/nnU-Net → 표준 SpineLabel
[2] 3D 모델 생성       ✅  라벨맵 → Marching Cubes → 표면 메쉬 (scikit-image)
[3] 임플란트 배치      ✅  스크류 2클릭/케이지 1클릭, 카탈로그 라이브러리
[4] 전처리             ✅  경계조건(Fixed/Force) + 재료 라이브러리(17종+커스텀)
[5] 구조해석           ✅  FEM/PD/SPG 멀티솔버, GPU 자동 감지
[6] 후처리             ✅  변위/응력/손상 컬러맵, 클리핑, CSV 내보내기
```

---

## 사이드바 탭 구조

```
File        — STL/NRRD/DICOM 로드, 카테고리별 모델 목록, per-model 제어(체크박스/색상/삭제)
Modeling    — 드릴/브러쉬 도구
Material    — 재료 라이브러리 (카테고리별 17종, 구성 모델 4종, 커스텀)
Pre-process — 경계조건 (Fixed/Force), 브러쉬 영역 선택, 자동 BC 추천
Solve       — 모델별 솔버/재료 읽기 전용 요약, 해석 실행/취소
Post-process — 결과 시각화, 컬러맵, 클리핑, 내보내기
```

**View**: 사이드바에서 분리 → 3D 뷰포트 우상단 플로팅 메뉴 (접기/펼치기)

---

## 테스트 현황

- **전체 테스트**: 679개 통과 (FEA 387개 + 전처리/해부학 53개 + Tied Contact 11개 + 후관절 14개 + COUPLED 8개 + Spine E2E 7개 + 기존 서버/파이프라인 등)
  - 모델/재료/BC: 20개
  - DICOM 변환: 7개
  - 메쉬 추출: 7개
  - 세그멘테이션: 3개
  - 자동 재료: 7개
  - E2E 파이프라인: 8개 (합성 DICOM + mock 세그멘테이션)
  - GPU 감지: 12개 (PyTorch mock, nvidia-smi mock, REST API)

- **실제 CT 검증**: L-spine 129슬라이스 → **16개 구조물** 추출 성공
  - CPU 모드: 4분 30초 / **GPU 모드: 4분 43초** (RTX 4070 Ti SUPER)
  - 척추골 8: T11, T12, L1, L2, L3, L4, L5, SACRUM
  - 디스크 7: T11T12, T12L1, L1L2, L2L3, L3L4, L4L5, L5S1
  - 연조직 1: SPINAL_CANAL
  - 194,148 정점, 317,014 면 → 카테고리별 3D 뷰, per-model 색상/불투명도 제어

- **UI E2E 검증**: LoadingOverlay + GPU 배지 + 카테고리 뷰 실제 동작 확인 ✅

---

## 실행 방법

```bash
# 의존성 설치
uv sync

# 서버 실행 (API + 프론트엔드 통합)
./start_backend.bat   # 또는 ./start_backend.sh

# 개발 모드 (프론트엔드 HMR)
./start_frontend.bat  # 또는 ./start_frontend.sh

# 테스트
uv run pytest backend/ -v

# 프론트엔드 빌드
cd frontend && npm run build
```

---

## 주요 디렉토리 구조

```
pysim/
├── frontend/               # Svelte 5 + TypeScript 프론트엔드
│   ├── src/
│   │   ├── components/     # UI 컴포넌트 (sidebar/, floating/)
│   │   └── lib/            # 스토어, 액션, WebSocket, Three.js 래퍼
│   ├── public/stl/         # 정적 에셋 (STL)
│   └── dist/               # 빌드 출력
│
├── backend/                # Python 백엔드
│   ├── api/                # FastAPI 서버 (was: server/)
│   │   ├── services/       # DICOM변환, 세그멘테이션, 메쉬추출, 자동재료, 해석
│   │   └── models/         # Pydantic 요청/응답 모델
│   ├── fea/                # 통합 FEA 프레임워크 (Taichi GPU)
│   │   ├── fem/            # FEM 솔버 + 재료 모델 (6종)
│   │   ├── peridynamics/   # NOSB-PD 파괴해석
│   │   ├── spg/            # SPG 무격자법
│   │   └── framework/      # 멀티솔버 디스패치 + 커플링 + 접촉
│   │       ├── coupling/   # FEM↔PD/SPG 적응적 커플링 엔진
│   │       └── contact.py  # PENALTY + TIED 접촉 알고리즘
│   ├── preprocessing/      # 범용 전처리 (부위 무관)
│   │   ├── adjacency.py    # 라벨 인접 쌍 탐색 (6-connected)
│   │   ├── voxel_to_hex.py # 복셀 → HEX8 메쉬 변환
│   │   └── assembly.py     # NPZ + AnatomyProfile → Scene 자동 생성
│   ├── anatomy/            # 부위별 해부학 특화
│   │   ├── base.py         # AnatomyProfile 추상 인터페이스
│   │   └── spine.py        # SpineProfile (재료/접촉/후관절)
│   ├── segmentation/       # 자동 세그멘테이션 엔진
│   ├── orchestrator/       # 파이프라인 오케스트레이터 (was: pipeline/)
│   ├── utils/              # 볼륨 I/O, 공통 유틸 (was: core/)
│   ├── config/             # 파이프라인 설정 (pipeline.toml)
│   └── scripts/            # 유틸리티 스크립트
│
├── docs/                   # 기술 문서
│   ├── getting_started.md  # 시작 가이드
│   ├── api_reference.md    # REST/WebSocket API
│   ├── fea_framework.md    # FEA 통합 프레임워크
│   ├── fem_solver.md       # FEM 솔버/재료/IO
│   ├── preprocessing.md    # 전처리/자동 조립
│   └── archive/            # 이전 진행 기록
│
├── start_backend.bat/sh    # 백엔드 시작 스크립트
├── start_frontend.bat/sh   # 프론트엔드 시작 스크립트
├── README.md               # 프로젝트 소개
└── pyproject.toml
```

### 의존성 레이어
```
Layer 0: utils/             ← 외부 의존성 없음 (numpy, SimpleITK)
Layer 1: segmentation/      ← utils/volume_io만 참조
Layer 2: fea/               ← 자체 완결 (framework, fem, pd, spg, coupling)
Layer 2.5a: preprocessing/  ← fea + segmentation 참조 (범용 전처리)
Layer 2.5b: anatomy/        ← preprocessing + segmentation 참조 (부위 특화)
Layer 3: orchestrator/      ← 전체 참조
Layer 4: api/               ← 전체 참조 (최상위 진입점)
```

---

## 오늘 작업 내역 (2026-02-26)

### 기술 문서 작성 + 루트 디렉토리 정리 (14차)

5개 기술 문서 작성 + 루트 디렉토리 정리. **679개 테스트 전체 통과.**

**Part A: 루트 디렉토리 정리**:

1. `.gitignore` 보강: `output/`, `segmentation/`, `CT-dicom/`, `*.dcm`, `.pytest_cache/` 추가
2. 기존 docs 아카이브: 5개 진행 문서 + `PROJECT_STATUS_OLD.md` → `docs/archive/` 이동
3. `config/pipeline.toml` → `backend/config/pipeline.toml` 이동 + 경로 수정 (test_config.py)
4. `scripts/gen_implant_stls.py` → `backend/scripts/` 이동 + BASE_DIR 경로 수정
5. 루트 `package.json`/`package-lock.json` 삭제 (중복 Playwright 의존성)
6. `CT-dicom/`, `output/`, `segmentation/` git 추적 해제 (DICOM 129개 + 세그멘테이션 출력)
7. `README.md` 작성 (프로젝트 소개 + 문서 링크)

**Part B: 기술 문서 5개 작성**:

1. **`docs/getting_started.md`** (~150줄) — 설치, 실행, 프로젝트 구조, 환경변수, 테스트
2. **`docs/api_reference.md`** (~350줄) — REST 5개 엔드포인트, WebSocket 9+11 메시지, Pydantic 모델 13종 스키마
3. **`docs/fea_framework.md`** (~400줄) — init, Domain, Material, Solver, Scene, RigidBody, ContactType + 코드 예시
4. **`docs/fem_solver.md`** (~350줄) — StaticSolver, DynamicSolver, ArcLengthSolver, 재료 6종, 표면 하중, 에너지 균형, VTK, 메쉬 임포트
5. **`docs/preprocessing.md`** (~280줄) — adjacency, voxel_to_hex, assemble, AnatomyProfile, SpineProfile, E2E 워크플로우

**수정/생성 파일** (13개):
- 신규 6: `docs/getting_started.md`, `api_reference.md`, `fea_framework.md`, `fem_solver.md`, `preprocessing.md`, `README.md`
- 수정 3: `.gitignore`, `backend/orchestrator/tests/test_config.py`, `backend/scripts/gen_implant_stls.py`
- 이동 8: `docs/` 5개 → `archive/`, `PROJECT_STATUS_OLD.md` → `archive/`, `config/` → `backend/config/`, `scripts/` → `backend/scripts/`
- 삭제 2: `package.json`, `package-lock.json`

---

### Spine E2E 해석 검증 + 버그 수정 (13차)

assembly → scene.solve() E2E 테스트 추가. 2건 버그 수정. **679개 테스트 전체 통과 (신규 7개).**

**버그 수정 (2건)**:

1. **FEMAdapter 커스텀 메쉬 미지원 (Critical)**
   - assembly 파이프라인이 `_hex_nodes`/`_hex_elements`에 복셀 기반 HEX8 메쉬를 저장하지만, FEMAdapter가 이를 무시하고 regular grid 메쉬를 생성
   - 노드 인덱싱 불일치 → 경계조건이 잘못된 노드에 적용
   - 수정: FEMAdapter에 CoupledAdapter와 동일한 커스텀 메쉬 감지 로직 추가

2. **assembly.py Material dim=2 기본값 (Critical)**
   - 3D HEX8 메쉬에 `Material(E=..., nu=...)` 생성 시 `dim=3` 미전달
   - 강성 행렬 C 텐서가 3×3(2D)으로 생성 → einsum 차원 불일치 오류
   - 수정: `Material(E=mat_props.E, nu=mat_props.nu, dim=3)`

**E2E 테스트 (7개 신규)** — `test_assembly_with_spine.py`:
- `test_assembly_creates_correct_bodies`: L4+L4L5+L5 → 3 Body + TIED 접촉
- `test_domains_have_valid_mesh`: HEX8 노드/요소 데이터 유효성
- `test_solve_with_bcs`: 3물체 경계조건 → 정적 해석 → L4 비영 변위
- `test_tied_contact_transfers_force`: Tied 접촉으로 디스크에 힘 전달
- `test_downward_force_produces_negative_z_displacement`: 하향 힘 → z 음수 변위
- `test_assembly_spine_labels`: SpineLabel 분류 + Method.FEM 검증
- `test_material_properties_applied`: body_map 이름 검증

**수정 파일** (3개):
- `backend/fea/framework/_adapters/fem_adapter.py`: 커스텀 메쉬 지원
- `backend/preprocessing/assembly.py`: Material dim=3
- `backend/anatomy/tests/test_assembly_with_spine.py` (신규): 7개 E2E 테스트

---

### 프로젝트 구조 개편 + CT 자동 다물체 해석 파이프라인 (12차)

프로젝트 구조를 `src/` → `backend/` + `frontend/` 분리로 개편하고, CT 라벨맵 → 자동 다물체 Scene 생성 파이프라인을 구축. **670개 테스트 통과 (신규 55개).**

**Phase 0: 프로젝트 구조 개편**
- `src/` → `backend/` 리네임
- `src/frontend/` → 루트 `frontend/` 이동
- `src/core/` → `backend/utils/`, `src/server/` → `backend/api/`, `src/pipeline/` → `backend/orchestrator/` 리네임
- `src/simulator/` 삭제 (Vite 빌드 → `frontend/dist/`)
- STL 에셋 → `frontend/public/stl/`
- 전체 임포트 경로 `from src.` → `from backend.` 일괄 치환 (~500줄)
- 설정 파일 업데이트: `pyproject.toml`, `vite.config.ts`, `.claude/CLAUDE.md`
- 루트 시작 스크립트 4개: `start_backend.bat/sh`, `start_frontend.bat/sh`
- 615개 기존 테스트 전체 통과

**Phase 1: Tied Contact (구속 접촉) 구현** — 11개 신규 테스트
- `NodeNodeContact.detect_tied_pairs()`: KDTree 기반 초기 쌍/오프셋 계산
- `NodeNodeContact.compute_tied_forces()`: 양방향 페널티 스프링 (인장+압축 저항)
- `Scene._build()`: Tied 쌍 사전 계산
- `Scene._compute_and_inject_contact()`: TIED 분기 추가
- E2E: 2물체 정적 해석에서 Tied 접촉으로 힘 전달 + 인터페이스 변위 연속성 검증

**Phase 2: 범용 전처리 + 부위별 해부학 모듈** — 23개 신규 테스트
- **`backend/preprocessing/`** (범용, 부위 무관):
  - `adjacency.py`: 6-connected 이웃 스캔으로 라벨 경계 탐색
  - `voxel_to_hex.py`: 복셀 중심 → HEX8 메쉬 변환 (좌표 해싱 노드 합병)
  - `assembly.py`: NPZ + AnatomyProfile → Scene 자동 생성 (핵심 함수)
- **`backend/anatomy/`** (부위별 특화):
  - `base.py`: `AnatomyProfile` 추상 인터페이스 + `MaterialProps` 데이터클래스
  - `spine.py`: `SpineProfile` (척추골 12GPa, 디스크 4MPa, 인대 10MPa)
- 확장 가능 설계: 향후 `anatomy/cervical.py`, `anatomy/knee.py` 등 추가 가능

**Phase 3: 후관절(Facet Joint) 자동 인식** — 14개 신규 테스트
- `FacetJoint` 데이터클래스: 상위/하위 척추골 라벨 + 접촉점 좌표 + 간격
- `SpineProfile.detect_facet_joints()`:
  - AP(전후방) 방향 결정 (척추관 위치 이용)
  - 후방 영역 필터링 (percentile 기반)
  - KDTree로 인접 척추골 후방 근접 쌍 탐색
- `assembly.py`: 후관절 탐지 → PENALTY + 마찰 접촉 자동 추가
- `get_contact_type(vert, vert)` → `ContactType.PENALTY` 반환

**Phase 4: Scene FEM↔PD 통합** — 8개 신규 테스트 (총 1개 신규 파일)
- `assembly.py`: `Method.COUPLED` 바디 올바르게 생성 (`_create_coupled_body()`)
  - HEX8 메쉬 생성 + `CouplingConfig` (auto 모드: 응력 기반 PD 전환) 부착
- `CoupledAdapter`: 복셀 기반 커스텀 메쉬(`_hex_nodes`/`_hex_elements`) 지원
  - 기존 regular grid 메쉬 생성과 하위호환 유지
- `CoupledTestProfile`: FEM + COUPLED 혼합 테스트 프로파일

**CT → 자동 해석 E2E 워크플로우** (구현 완료):
```
CT 라벨맵 NPZ
  → assemble(npz, SpineProfile())
    → 라벨별 복셀 추출
    → FEM/COUPLED 도메인 자동 생성 (voxel_to_hex HEX8)
    → 인접 쌍 탐색 → TIED 접촉 자동 추가 (척추골-디스크)
    → 후관절 탐지 → PENALTY+마찰 접촉 자동 추가 (척추골-척추골)
  → AssemblyResult (Scene + body_map + contact_pairs)
    → scene.solve() → 다물체 접촉 해석
```

**신규/수정 파일 요약** (25개):
- 신규 12: `adjacency.py`, `voxel_to_hex.py`, `assembly.py`, `base.py`, `spine.py`, 시작 스크립트 4개, 테스트 파일 5개
- 수정 6: `contact.py`, `scene.py`, `coupled_adapter.py`, `pyproject.toml`, `vite.config.ts`, `.claude/CLAUDE.md`
- 이동/리네임 6: `src/` → `backend/`, `src/frontend/` → `frontend/` 등

---

## 이전 작업 내역 (2026-02-25)

### CT/DICOM 파이프라인 E2E 검증 + 버그 수정

실제 CT DICOM(L-spine 129슬라이스)으로 전체 파이프라인 검증. 3가지 핵심 버그 수정.

**수정한 버그**:

1. **프론트엔드-백엔드 메쉬 데이터 형식 불일치**
   - 백엔드: vertices/faces 인라인 배열 반환
   - 프론트엔드: STL URL path 기대 → 로드 실패
   - 수정: `loadMeshFromInlineData()` 신규 구현 (BufferGeometry 직접 생성)

2. **세그멘테이션 출력 경로 불일치**
   - `segmentation.py`가 엔진 반환 경로 무시 → FileNotFoundError
   - 수정: 엔진 반환값 사용 + fallback 탐색 로직

3. **SpineLabel 값 오류 (테스트)**
   - L4=120 (잘못) → L4=123 (정확)

**실제 CT 결과 (1차)**:
- 8개 구조물: L1, L2, L3, SACRUM, L1L2, L2L3, L5S1, SPINAL_CANAL
- ~790K 정점, ~1.5M 면
- CPU 약 6분 30초

**수정 파일**: `segmentation.py`, `types.ts`, `loading.ts`, `pipeline.ts`, `pipeline.svelte.ts`, `test_pipeline_e2e.py`(신규)

### TotalSpineSeg 레벨 식별 보정 (2차)

TotalSpineSeg가 **L4/L5를 천골(SACRUM)로 잘못 분류**하는 문제 해결.

**근본 원인**: TotalSpineSeg step2 출력이 척추골 형태는 정확히 분할하지만, 레벨 식별(L1? L4? 천골?)이 부정확. Raw 41/42가 L4/L5인데 SACRUM으로 매핑되고, 디스크 Raw 91-95가 모두 L5S1로 매핑됨.

**해결 방법**: `step1_levels` (레벨 마커)를 이용한 동적 매핑
1. `labels.py`: `LEVEL_TO_VERTEBRA` 매핑 + `build_dynamic_totalspineseg_mapping()` 함수 추가
   - step1_levels의 레벨 마커(Z위치)와 step2 raw 라벨의 centroid를 순서 기반 1:1 매칭
   - 디스크도 순서 기반 매칭으로 올바른 간극에 배정
2. `segmentation.py`: step1_levels 존재 시 동적 매핑 자동 사용, 없으면 정적 매핑 fallback
3. `mesh_extract.py`: step_size=2 + 면 수 제한(50K) + 플랫 배열 전송 (JSON 크기 절감)
4. 프론트엔드: `types.ts`, `loading.ts` 플랫 배열 형식 대응

**보정 후 결과**: 16개 구조물 (T11~SACRUM 8 + 디스크 7 + 척수관 1)
- 194K 정점, 317K 면, 메시지 14.7MB
- CPU 약 4분 30초

### Material 전용 탭 + View 플로팅 메뉴

- Material 탭 신설 (사이드바 전체 높이, 재료 리스트+편집기 동시 표시)
- View → 3D 뷰포트 우상단 플로팅 메뉴로 이동
- PreProcess에서 재료 UI 제거 (BC만 잔존)
- 구성 모델 4종: Linear Elastic, Neo-Hookean, Mooney-Rivlin, Ogden

### Mooney-Rivlin + Ogden FEM 구현

- `mooney_rivlin.py` (290줄), `ogden.py` (320줄)
- Taichi GPU 커널, E/ν → 파라미터 자동 변환

### 메쉬 전송 최적화 + UI 개선 + FEM 연동 (3차)

**Phase 1: 메쉬 전송 base64 인코딩**
- `mesh_extract.py`: vertices/faces 플랫 배열 → base64 인코딩 (float32/int32 → base64 문자열)
- `types.ts`: `PipelineMeshData` 필드 `vertices_b64`/`faces_b64`로 변경
- `loading.ts`: `loadMeshFromInlineData()` base64 디코딩 → Float32Array/Uint32Array
- `pipeline.ts`: base64 필드 전달
- 예상 효과: 메시지 크기 14.7MB → ~5MB (base64 = raw × 1.33, raw는 플랫배열 대비 ~60% 절감)

**Phase 2: UI 모델 목록 카테고리화**
- `scene.svelte.ts`: `ModelInfo`에 `opacity`, `materialType`, `color` 추가
  - `setOpacity()`, `setColor()`, `setCategoryVisibility()` 메서드 추가
- `FilePanel.svelte`: 파이프라인 모델 → 카테고리별 그룹핑 (Bone/Disc/Soft Tissue)
  - per-model: 색상 피커, 가시성 토글, 개별 삭제(✕ 호버 표시)
  - 카테고리: 접기/펼치기, 일괄 가시성 토글, 카테고리 일괄 삭제(🗑)
  - 불투명도 슬라이더: FilePanel에서 제거 (setOpacity() 메서드는 Modeling 탭용으로 보존)
- STL/샘플 모델은 기존 플랫 목록 유지

**Phase 3: FEM 해석 자동 연동**
- `pipeline.ts`: 파이프라인 완료 후 자동 실행:
  1. `_autoAssignMaterials()`: material_type → 기본 물성치 (bone=피질골 15GPa, disc=추간판 10MPa, soft_tissue=인대 50MPa)
  2. `_suggestBoundaryConditions()`: SACRUM→Fixed BC, 최상위 척추→Force BC 500N 자동 추천
- `analysis.svelte.ts`: `suggestedBCs` 배열 추가
- `PreProcessPanel.svelte`: "자동 추천 BC" 섹션 (적용 버튼 + 가이드 메시지)

**수정 파일** (12개):
- 백엔드: `mesh_extract.py`, `test_mesh_extract.py`, `test_pipeline_e2e.py`
- 프론트엔드: `types.ts`, `loading.ts`, `pipeline.ts`, `scene.svelte.ts`, `analysis.svelte.ts`, `FilePanel.svelte`, `PreProcessPanel.svelte`

### 로딩 오버레이 + GPU 자동 감지 (4차)

**LoadingOverlay 컴포넌트 (파이프라인 + 해석 공용)**
- `LoadingOverlay.svelte`: 3D 뷰포트 위 반투명 오버레이
  - 파이프라인: 4단계 스텝 인디케이터 (✓/●/○) + 진행 바 + 경과 시간 + GPU 정보 배지
  - 해석: 진행률 바 + 메시지 + 스피너
  - `App.svelte`에 `.main-container` 내부에 배치 (`position: relative` + `absolute` 오버레이)

**GPU 자동 감지 시스템**
- `gpu_detect.py` (신규): GPU 탐지 유틸리티
  - PyTorch `torch.cuda.is_available()` 우선 → nvidia-smi CLI 폴백 → CPU 모드
  - `GpuInfo` 데이터클래스: available, name, memory_mb, cuda_version, driver_version
  - `resolve_device("gpu")`: GPU 없으면 자동 "cpu" 폴백
  - 결과 캐싱 (프로세스당 1회 탐지)
- `segmentation.py`: 세그멘테이션 실행 전 `resolve_device()` 사전 호출
  - GPU 불가 시 자동 CPU 전환 + 진행 메시지 발송
  - GPU 감지 시 GPU 이름/메모리 정보 표시
- `app.py`: `GET /api/gpu-info` REST 엔드포인트 추가
- `pipeline.svelte.ts`: `GpuInfo` 인터페이스 + `fetchGpuInfo()` + `autoDevice` getter
- `pipeline.ts`: 파이프라인 시작 전 GPU 정보 자동 조회 → `autoDevice` 사용

**FEA 프레임워크 (기존)**
- `runtime.py`: `Backend.AUTO` → CUDA → Vulkan → CPU 순서 자동 폴백 (기존 구현)

**검증 결과**:
- GPU 감지: NVIDIA GeForce RTX 4070 Ti SUPER (16,376MB, 드라이버 581.57)
- REST API 정상 응답
- 테스트: 12개 신규 (mock PyTorch/nvidia-smi + API) → 전체 64개 통과

**수정/생성 파일** (7개):
- 백엔드: `gpu_detect.py`(신규), `test_gpu_detect.py`(신규), `segmentation.py`, `app.py`
- 프론트엔드: `LoadingOverlay.svelte`(신규), `App.svelte`, `pipeline.svelte.ts`, `pipeline.ts`

**실제 UI E2E 검증** (GPU 모드):
- DICOM 129슬라이스 → 전체 파이프라인 → 3D 로드 (4분 43초, GPU)
- LoadingOverlay: GPU 배지(RTX 4070 Ti SUPER 16,376MB) ✅ / 4단계 스텝 인디케이터 ✅ / 경과 시간 타이머 ✅ / 진행 바 ✅
- 카테고리 뷰: Bone(8) / Disc(7) / Soft Tissue(1) ✅
- per-model 제어: 색상 피커 / 가시성 토글 / 개별 삭제(✕) / 카테고리 일괄 삭제(🗑) ✅
- 불투명도 슬라이더: FilePanel에서 제거 (추후 Modeling 탭에서 활용 예정)
- 자동 복셀화 + 카메라 포커스 ✅
- 총 194,148 정점, 317,014 면, 60 FPS ✅

### FilePanel UI 정리 (5차)

모델 목록 패널의 사용성 개선. 불필요한 요소 제거, 실용적 제어에 집중.

**변경 내역**:

1. **가시성 토글: ●/○ 버튼 → 체크박스**
   - `<input type="checkbox">` 교체 (카테고리 뷰 + 플랫 목록 뷰 모두)
   - 체크 해제 → 3D 뷰에서 모델 숨김, 체크 → 표시
   - 직관적 UX: "사용할 모델을 선택" 개념

2. **불투명도 슬라이더 제거**
   - FilePanel에서 per-model 불투명도 슬라이더(`<input type="range">`) 제거
   - `scene.svelte.ts`의 `setOpacity()` 메서드는 보존 (Modeling 탭에서 활용 예정)

3. **샘플 모델 로드 버튼 제거**
   - `Load Sample (L4+L5+Disc)` 버튼 제거
   - `handleLoadSample()` 함수 + `loadSampleModels` import 제거
   - `loading.ts`의 `loadSampleModels()` 원본 함수는 보존 (디버그/개발용)

**현재 FilePanel per-model 제어**:
```
☑ [🎨] MODEL_NAME   1,234v  [✕]
│   │      │           │      └─ 삭제 (호버 시 표시)
│   │      │           └─ 정점 수
│   │      └─ 모델 이름
│   └─ 색상 피커
└─ 가시성 체크박스
```

**수정 파일**: `FilePanel.svelte`

### FEA 솔버 아키텍처 최적화 (6차)

CT 메쉬(194K vertices, 317K faces, 16 구조물) 규모의 척추 구조 해석을 위한 3종 솔버(FEM, NOSB-PD, SPG) 성능 병목 해결. **390개 테스트 전체 통과.**

**Phase 1A: FEM 강성 행렬 벡터화 조립** — 50~200배 가속
- `assembly.py` (신규 290줄): numpy 배치 `np.einsum`으로 전체 요소 동시 처리
  - `assemble_stiffness_matrix()` — 벡터화 전역 강성 조립 + 청크 메모리 관리
  - `_build_B_matrices_batch()` — 전체 가우스점 B 행렬 일괄 구성
  - `assemble_geometric_stiffness()` — 벡터화 기하 강성 조립
  - 다중 재료: `material_id`별 그룹핑으로 다른 C 텐서 적용
  - 메모리 관리: 10K 요소 단위 청크 처리 (HEX8 기준 청크당 ~100-200MB)
- `static_solver.py`: Python for 루프 6중 중첩 제거 → `assembly.py` 호출로 교체

**Phase 1B: 반복 솔버 PCG 추가** — 대규모 5~20배 가속, 메모리 70% 절감
- `static_solver.py` + `dynamic_solver.py`: `_solve_linear_system()` 메서드 추가
  - `linear_solver: "auto"|"direct"|"cg"` 파라미터
  - auto: 50K DOF 초과 시 CG + ILU 전처리기 자동 선택
  - CG 실패 시 spsolve 자동 폴백
- `dynamic_solver.py`: 집중 질량/경계조건 벡터화 (`np.add.at`, `np.repeat`)

**Phase 2A: 본드 적응적 할당** — 3D 안정성 확보 + 메모리 ~30% 절감
- `neighbor.py`: `count_neighbors_only()` 경량 사전 카운트 커널 추가
  - max_neighbors 제한 없이 실제 이웃 수만 카운트
- `bonds.py` (PD/SPG): `from_neighbor_counts()` 클래스 메서드 추가
  - `max_bonds = max(counts) + margin`으로 자동 설정
- `kernel.py` (SPG): `from_neighbor_counts()` 클래스 메서드 추가
- `pd_adapter.py`, `spg_adapter.py`: 사전 카운트 워크플로우로 교체

**Phase 2B: SPG scatter → gather 변환** — GPU 2~5배 속도 향상
- `kernel.py`: 역방향 이웃 맵 필드 추가 (`reverse_i`, `reverse_k`, `n_reverse`)
  - `build_reverse_map()`: CPU에서 역방향 인덱스 구축 (1회성 전처리)
- `spg_compute.py`: `compute_internal_force_gather()` 커널 추가
  - 각 입자가 자신의 역이웃에서 기여분 수집 (atomic_add 제거)
  - 역방향 맵 존재 시 자동 사용, 없으면 scatter 폴백
- `spg_adapter.py`: 이웃 목록 구축 후 `build_reverse_map()` 자동 호출

**Phase 2C: FEM 기하 강성 구현** — 대변형 Newton-Raphson 수렴 복원
- `assembly.py`: `assemble_geometric_stiffness()` 벡터화 구현
  - K_geo[a*dim+d, b*dim+d] = dN_a^T · σ · dN_b · vol (delta_ij 구조)
- `static_solver.py`: `_assemble_tangent_stiffness()` = K_material + K_geometric

**수정/생성 파일** (10개):
- 신규: `src/fea/fem/solver/assembly.py`
- FEM: `static_solver.py`, `dynamic_solver.py`
- PD: `neighbor.py`, `bonds.py`
- SPG: `kernel.py`, `bonds.py`, `spg_compute.py`
- 어댑터: `pd_adapter.py`, `spg_adapter.py`

**성능 기대 효과 요약**:
| 항목 | Before | After | 개선 |
|------|--------|-------|------|
| FEM 강성 조립 (100K HEX8) | 수분 | ~1초 | 50-200배 |
| 선형 풀기 (300K DOF) | 30초+ | 2-5초 | 5-20배 |
| 메모리 (300K DOF) | ~2GB | ~600MB | -70% |
| PD/SPG 본드 (3D, 100K) | 부족/오류 | 자동 적응 | 안정성+절감 |
| SPG 내부력 (GPU, 100K) | atomic_add 경합 | gather 방식 | 2-5배 |

### FEA 솔버 프로덕션 리뷰 + 버그 수정 (7차)

6차에서 구현한 최적화 코드에 대한 프로덕션급 전수 리뷰 수행. **Critical 3건 + Important 3건** 수정. **162개 테스트 전체 통과.**

**Critical 버그 수정 (3건)**:

1. **C1: SPG verbose AttributeError 크래시**
   - `explicit_solver.py:306`: `self.spg_compute.eta[None]` → 실제 필드명 `G_s`
   - verbose=True로 solve() 호출 시 즉시 크래시
   - 수정: `self.spg_compute.G_s[None]`으로 교체

2. **C2: FEM 경계조건 적용 Python for 루프 병목**
   - `static_solver.py` 4곳에서 `for i in range(n_nodes)` 순수 Python 루프
   - 100K 노드에서 BC 적용만 수십초 소요 (벡터화 조립 효과 상쇄)
   - 수정:
     - `_get_fixed_dofs()` 헬퍼 추가 (벡터화 DOF 인덱스 생성)
     - Newton-Raphson 잔차 초기화: `residual[fixed_dofs] = 0.0` (배열 인덱싱)
     - `_apply_bc_to_system()`: `K.diagonal()` + `setdiag()` 벡터화 (Python for 루프 제거)
   - `dynamic_solver.py` `_apply_bc()`: 동일 벡터화 적용

3. **C3: assembly.py 다중 재료 Dead Code**
   - `assembly.py:136`: BtC einsum 계산 후 즉시 덮어쓰기 (불필요 연산 + 메모리 낭비)
   - 수정: 중복 einsum 제거

**Important 이슈 수정 (3건)**:

4. **I1: ILU 전처리기 메모리 폭발 방지**
   - `fill_factor=10` 고정 → 적응적 설정 (200K+ → 3, 100K+ → 5, 이하 → 10)
   - `except MemoryError` 명시적 핸들링 → spsolve 폴백
   - `static_solver.py`, `dynamic_solver.py` 양쪽 적용

5. **I2: SPG 이웃 카운트 O(n²) 메모리 개선**
   - `spg_adapter.py`: `KDTree.query_ball_tree()` (전체 쌍 리스트 반환) →
     `cKDTree.query_ball_point(return_length=True)` (카운트만 반환, O(n) 메모리)
   - 100K 입자에서 ~400MB Python 오버헤드 제거

6. **I3: Newton-Raphson 접선 강성 이중 Taichi→NumPy 추출 제거**
   - `_assemble_tangent_stiffness()`: dNdX/gauss_vol/elements 1회만 추출 → K_mat + K_geo 모두 재사용
   - Newton 반복당 수십MB 이중 복사 제거

**프로덕션 리뷰 결과 — 잔존 이슈 (Moderate)**:
- M1: CG 솔버 파라미터(tol/maxiter) 하드코딩 → 사용자 조정 불가
- M2: Newton-Raphson 라인서치 단순 (Armijo 미적용, 5회 backtracking만)
- M3: PD quasi-static dt 추정 과도 보수적 (safety=0.01, cap=1e-6)
- M4: 입력 검증 부재 (E<0, ν≥0.5, 퇴화 요소 미감지)
- M5: 진행 콜백/취소 API 부재 (수술 계획 도구 UX에 필요)

**수정 파일** (5개):
- `src/fea/spg/solver/explicit_solver.py` — C1 수정
- `src/fea/fem/solver/static_solver.py` — C2+I1+I3 수정
- `src/fea/fem/solver/dynamic_solver.py` — C2+I1 수정
- `src/fea/fem/solver/assembly.py` — C3 수정
- `src/fea/framework/_adapters/spg_adapter.py` — I2 수정

### FEM↔PD/SPG 적응적 커플링 엔진 구현 (8차)

하나의 메쉬 내에서 FEM(탄성 벌크) + PD/SPG(파괴 영역)를 동시에 사용하는 Dirichlet-Neumann 교대 커플링 구현. **수동 모드**(사용자 지정 PD 영역) + **자동 모드**(응력 기준 자동 전환) 모두 지원. **403개 테스트 전체 통과.**

**커플링 방식**: Shared-boundary Dirichlet-Neumann 교대법
- FEM 인터페이스 변위 → PD 고스트 입자 Dirichlet BC
- PD 인터페이스 반력 → FEM 인터페이스 노드 Neumann BC
- PD 입자를 FEM 노드 위치에 배치 → 인터페이스 보간 불필요
- 수렴까지 교대 반복 (tol 기반)

**Phase 1: 백엔드 커플링 엔진 (6개 신규 파일)**

1. **`coupling/zone_splitter.py`** (90줄) — 메쉬 분할기
   - `split_mesh(nodes, elements, pd_mask)` → `ZoneSplit` 데이터클래스
   - FEM/PD 노드 분리 + 요소 재번호 + 인터페이스 노드 감지
   - PD 입자 부피: 요소 체적 → 노드별 기여 합산

2. **`coupling/interface_manager.py`** (60줄) — 경계 DOF 전달
   - `fem_to_pd_displacements()`: FEM→PD 변위 전달
   - `pd_to_fem_forces()`: PD→FEM 반력 전달 (부호 반전)
   - `check_convergence()`: 인터페이스 변위 변화 수렴 판정

3. **`coupling/criteria.py`** (90줄) — 자동 전환 기준
   - Von Mises 응력 임계값 + 최대 변형률 임계값
   - 버퍼 레이어 확장 (인접 요소 자동 포함)
   - 2D/3D Von Mises 공식 지원

4. **`coupling/coupled_solver.py`** (250줄) — 핵심 오케스트레이터
   - `solve()`: Dirichlet-Neumann 교대 루프
   - `solve_automatic()`: FEM 1차 → 기준 판별 → 영역 분할 → 커플링 해석
   - `get_displacements()/get_stress()/get_damage()`: FEM+PD 결과 병합

5. **`_adapters/coupled_adapter.py`** (170줄) — AdapterBase 구현
   - Scene/Solver 호환 인터페이스
   - CouplingConfig → CoupledSolver 변환
   - 접촉 해석 메서드 포함

6. **`coupling/__init__.py`** — 패키지 초기화

**기존 코드 수정 (3개)**:
- `domain.py`: `Method.COUPLED` enum + `CouplingConfig` 데이터클래스
- `solver.py` + `scene.py`: COUPLED 분기 → CoupledAdapter 생성

**Phase 2: 서버 API 확장 (2개 수정)**:
- `models/analysis.py`: `CouplingConfig` Pydantic 모델, method에 "coupled" 추가
- `services/analysis.py`: `_run_coupled_region()` 함수 (수동/자동 모드 해석)

**Phase 3: 프론트엔드 UI (1개 수정)**:
- `SolvePanel.svelte`: 솔버 드롭다운에 "Coupled" 옵션 (보라색 #7b1fa2)

**테스트 (13개 신규)**:
- `TestZoneSplitter` (5): 기본 분할, 인터페이스 좌표 일치, 빈 PD/전체 PD, 입자 부피 양수
- `TestInterfaceManager` (3): FEM→PD 변위, PD→FEM 반력(부호 반전), 수렴 판정
- `TestSwitchingCriteria` (2): Von Mises 임계값, 버퍼 레이어 확장
- `TestDomainCoupled` (3): COUPLED enum, CouplingConfig, Domain 통합

**신규/수정 파일 요약** (12개):
- 신규 7: `zone_splitter.py`, `interface_manager.py`, `criteria.py`, `coupled_solver.py`, `__init__.py`, `coupled_adapter.py`, `test_coupling.py`
- 수정 5: `domain.py`, `solver.py`, `scene.py`, `models/analysis.py`, `services/analysis.py`, `SolvePanel.svelte`

### 커플링 E2E 검증 + 버그 수정 (9차)

E2E 통합 테스트로 실제 FEM+PD 커플링 워크플로우를 검증. **Critical 4건** 발견 및 수정.

**E2E 테스트 (11개 신규)** — `test_coupling_e2e.py`:
- `TestCoupledSolverInit` (4): PD 영역 초기화, 빈 PD 초기화, BC 전달, 고정 BC 병합
- `TestPureFEMReference` (2): 순수 FEM 캔틸레버, 빈 PD 커플링 = 순수 FEM 일치
- `TestCoupledManualE2E` (3): 커플링 실행, 비영 변위, 응력/손상도 접근
- `TestCoupledAutomaticE2E` (2): 전환 없음(높은 임계), 전환 발생(낮은 임계)

**Critical 버그 수정 (4건)**:

1. **빈 PD 영역 크래시** — `_build_particle_solver()`
   - `create_particle_domain(empty_array)` → `positions.min()` 크래시
   - 수정: PD 노드 0개이면 `pd_adapter = None` 설정 + `solve()`에서 순수 FEM 폴백

2. **인터페이스 고정 BC 덮어쓰기** — `_build_particle_solver()`
   - `pd_domain.set_fixed(interface_pd)`가 사용자 고정 BC 제거
   - 수정: 사용자 BC + 인터페이스 BC를 `set()` 병합 후 한 번에 설정

3. **존재하지 않는 `ps.u` 필드 참조** — `_update_pd_interface_bc()`
   - ParticleSystem에는 `u` 필드 없음 (변위 = `x - X`)
   - 수정: `x[p_idx] = X[p_idx] + displacement` 로 현재 좌표 직접 갱신

4. **전체 PD 전환 시 빈 FEM 크래시** — `_build_fem_solver()` + `solve_automatic()`
   - 자동 모드에서 전체 요소 전환 → FEMesh(0, 0) → Taichi 크래시
   - 수정: `_build_fem_solver()`에서 빈 FEM 스킵 + `solve()`에서 순수 PD 폴백

**기능 개선 (1건)**:
- `pd_solver_options` 파라미터 추가: CoupledSolver에 PD 솔버 옵션(max_iterations, tol) 전달 가능
  - 커플링 반복마다 PD 50K 기본 반복 → 사용자 제어 가능
  - 테스트 실행 시간 89초 → 2초로 단축

**수정 파일** (2개):
- `coupled_solver.py`: 4건 버그 수정 + pd_solver_options 기능
- `test_coupling_e2e.py` (신규): 11개 E2E 테스트

### FEM 솔버 프로덕션 성숙도 개선 (10차)

FEM 솔버의 프로덕션 성숙도를 60% → ~80%로 끌어올리는 6개 Phase 개선. **330개 FEA 테스트 전체 통과.**

**Phase 0-A: 입력 검증 인프라** — 런타임 크래시 방지
- `src/fea/fem/validation.py` (신규 350줄): 재료/메쉬/솔버 파라미터 통합 검증
  - `validate_material_properties()`: E>0, 0≤ν<0.5, yield_stress>0 등
  - `validate_mesh_quality()`: Jacobian 양정치, 퇴화 요소 감지
  - `validate_solver_parameters()`: CG tol/maxiter 범위, dt>0 등
  - `@validated` 데코레이터: 솔버 진입점 자동 검증
  - `FEAValidationError` / `FEAWarning` 예외 체계
- 기존 `static_solver.py`, `dynamic_solver.py`: `@validated` 데코레이터 적용
- `test_validation.py` (신규): 45개 테스트

**Phase 0-B: J2 소성 모델** — 금속 항복/경화
- `src/fea/fem/material/j2_plasticity.py` (신규 370줄): J2 소성 모델 (Taichi GPU)
  - 등방 경화 (선형 H + 지수 saturation)
  - Radial return 알고리즘 (von Mises 항복면)
  - 변형 이력 관리 (`reset_history()`)
  - 일관적 접선 모듈러스 (Newton-Raphson 2차 수렴)
- `material/__init__.py`: J2Plasticity export 추가
- `test_j2_plasticity.py` (신규): 20개 테스트

**Phase 1-A: 횡이방성 재료 모델** — 뼈/인대 이방성
- `src/fea/fem/material/transverse_isotropic.py` (신규 250줄): 횡이방성 탄성 (Taichi GPU)
  - 5개 독립 탄성 상수: E_L, E_T, ν_LT, ν_TT, G_LT
  - 임의 섬유 방향 (회전 변환 텐서)
  - 2D/3D 지원, 열역학적 안정성 자동 검증
  - framework `Material` 클래스: `is_bone` → TransverseIsotropic 자동 디스패치
- `test_transverse_isotropic.py` (신규): 23개 테스트

**Phase 1-C: VTK 내보내기** — 상용 후처리기 호환
- `src/fea/fem/io/vtk_export.py` (신규 240줄): VTU(Unstructured Grid) 내보내기
  - 노드 변위, 응력 텐서 (6 Voigt + von Mises), 주응력, 가우스→노드 보간
  - 요소별 소성 변수(ep), 손상도(damage) 필드
  - 시계열 PVD 파일 (호장법/동적 해석 다단계 결과)
  - ASCII/Binary 모드, ParaView 즉시 호환
- `test_vtk_export.py` (신규): 15개 테스트

**Phase 2-A: 호장법(Arc-Length) 솔버** — 불안정 경로 추적
- `src/fea/fem/solver/arclength_solver.py` (신규 330줄): Crisfield 구면 호장법
  - 구면 구속조건: ‖Δu‖² + (Δλ·ψ)² = Δl²
  - Ritto-Corrêa 선형화 업데이트 (2차 방정식 풀이)
  - 적응적 호장 길이: Bergan & Mollestad 기법 (Δl_new = Δl·√(n_des/n_act))
  - 하중 비율 상한 제한 (max_load_factor)
  - 진행 콜백 + 취소 지원
  - `get_equilibrium_path()`: 노드/자유도별 하중-변위 경로 추출
- **내부력 부호 규약 수정** (CRITICAL):
  - 모든 재료 모델이 `mesh.f = -∫ B^T σ dV` (음수 내부력) 규약 사용 확인
  - `static_solver.py` Newton-Raphson: `residual = f_ext - mesh.f` → `f_ext + mesh.f` (3곳 수정)
  - 이 수정으로 NeoHookean/Mooney-Rivlin Newton-Raphson도 정상 동작
- `solver/__init__.py`: ArcLengthSolver export 추가
- `test_arclength.py` (신규): 19개 테스트

**Phase 2-B: 에너지 균형 검증** — 해석 품질 자동 검증
- `src/fea/fem/solver/energy_balance.py` (신규 260줄): 에너지 기반 해석 품질 검증
  - `compute_external_work()`: W = ½ u^T · f_ext (선형 비례 하중)
  - `compute_internal_energy()`: U = ½ ∫ σ:ε dV (가우스 적분)
  - `compute_internal_energy_from_forces()`: U = -½ u^T · mesh.f (내부력 기반)
  - `check_energy_balance()` → `EnergyReport` (W_ext ≈ U_int 자동 판정)
  - `check_incremental_energy()`: 호장법 경로 증분 에너지 사다리꼴 적분
- `solver/__init__.py`: 에너지 함수 6개 export 추가
- `test_energy_balance.py` (신규): 12개 테스트

**내부력 부호 규약 정리** (전 솔버 영향):
```
모든 재료 모델: mesh.f = -∫ B^T σ dV  (음수 내부력)
잔차 계산:      R = f_ext + mesh.f = f_ext - f_int
에너지 계산:    U = -½ u^T · mesh.f = ½ u^T · f_int
```

**신규/수정 파일 요약** (16개):
- 신규 8: `validation.py`, `j2_plasticity.py`, `transverse_isotropic.py`, `vtk_export.py`, `arclength_solver.py`, `energy_balance.py` + 테스트 6개
- 수정 4: `static_solver.py` (부호 규약+검증), `dynamic_solver.py` (검증), `material/__init__.py`, `solver/__init__.py`

**성숙도 개선 요약**:
| 항목 | Before | After |
|------|--------|-------|
| 입력 검증 | 없음 | 통합 검증 프레임워크 |
| 재료 모델 | 4종 (탄성+초탄성) | 6종 (+J2소성, 횡이방성) |
| 비선형 솔버 | Newton-Raphson만 | +호장법 (불안정 경로) |
| 해석 검증 | 없음 | 에너지 균형 자동 검증 |
| 결과 내보내기 | CSV만 | +VTK/VTU (ParaView) |
| 테스트 | 299개 | 330개 (+31) |

### FEM 솔버 고도화 Phase 3 — 전처리 인프라 (11차)

FEM 솔버 성숙도 ~80% → ~90%로 향상. 척추 수술 시뮬레이션 핵심 전처리 기능 3종 구현. **387개 FEA 테스트 전체 통과.**

**Phase 3-A: Per-DOF 경계조건** — 롤러/대칭 BC 지원
- `mesh.py`: `fixed` 필드 `(n_nodes,)` → `(n_nodes, dim)` 형상 변경
  - `set_fixed_nodes(node_ids, values, dofs)`: `dofs` 파라미터 추가 (예: `[0]`=x만 고정)
  - `set_fixed_dofs(dof_indices, values)`: DOF 인덱스 직접 지정 API 추가
  - `apply_boundary_conditions` 커널: per-DOF 조건부 적용
- `static_solver.py`, `arclength_solver.py`: `_get_fixed_dofs()` 벡터화 (reshape→where)
- `dynamic_solver.py`: `_apply_bc()`, `_enforce_bc()`, `get_natural_frequencies()` per-DOF 대응
- `domain.py`: `set_fixed(dofs)` 파라미터 추가
- `fem_adapter.py`: `dofs` 전달
- `test_per_dof_bc.py` (신규): 13개 테스트 (하위호환, 롤러, 대칭, 혼합, 규정변위, 3솔버 검증)

**Phase 3-B: 메쉬 임포트 (.inp + .msh)** — 외부 도구 메쉬 사용
- `io/abaqus_reader.py` (신규 320줄): Abaqus .inp 파서
  - `MeshData` 공통 반환 구조 (노드/요소/집합/BC/하중)
  - 지원: *NODE, *ELEMENT, *NSET(+GENERATE), *ELSET, *BOUNDARY, *CLOAD
  - 1-based → 0-based 인덱스 자동 변환
  - NSET 참조 경계조건/하중 지원
- `io/gmsh_reader.py` (신규 300줄): GMSH .msh v4 ASCII 파서
  - 엔터티 블록 형식 $Nodes/$Elements 파싱
  - $PhysicalNames, $Entities 지원
  - 체적 요소 자동 필터링 + 2D z=0 축소
  - GMSH 요소 코드 → ElementType 매핑 (12종)
- `io/__init__.py`: `read_abaqus_inp`, `read_gmsh_msh`, `MeshData` export
- `test_mesh_import.py` (신규): 17개 테스트 (인라인 fixture, 왕복 해석 검증)

**Phase 3-C: 표면 압력 하중** — 추간판 내압 해석
- `core/element.py`: `ELEMENT_FACES` 딕셔너리 추가 (TET4/HEX8/TRI3/QUAD4 면 정의)
  - `get_face_nodes()` 헬퍼 함수
- `solver/surface_load.py` (신규 330줄): 표면 Gauss 적분
  - 면 형상함수: 선분(2노드), 삼각형(3노드), 사각형(4노드)
  - 면 법선/야코비안: 접선 외적(3D), 90° 회전(2D)
  - `compute_pressure_load()`: 등가 절점력 변환
  - `find_surface_faces()`: 좌표면 기반 면 자동 검색
- `core/mesh.py`: `add_pressure_load()`, `find_surface_faces()` 메서드 추가
- `solver/__init__.py`: `compute_pressure_load`, `find_surface_faces` export
- `test_surface_load.py` (신규): 27개 테스트 (형상함수, 법선, 2D/3D 압력, 면 검색, 왕복 해석)

**신규/수정 파일 요약** (15개):
- 신규 6: `abaqus_reader.py`, `gmsh_reader.py`, `surface_load.py`, `test_per_dof_bc.py`, `test_mesh_import.py`, `test_surface_load.py`
- 수정 9: `mesh.py`, `element.py`, `static_solver.py`, `arclength_solver.py`, `dynamic_solver.py`, `domain.py`, `fem_adapter.py`, `io/__init__.py`, `solver/__init__.py`

**성숙도 개선 요약**:
| 항목 | Before | After |
|------|--------|-------|
| 경계조건 | 노드별 전체 고정만 | Per-DOF (롤러/대칭/혼합) |
| 메쉬 소스 | 내부 생성만 | +Abaqus .inp, GMSH .msh v4 |
| 하중 타입 | 집중 절점력만 | +표면 압력 (2D/3D) |
| 테스트 | 330개 | 387개 (+57) |
