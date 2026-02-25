# Spine Surgery Planner — 프로젝트 현황

최종 업데이트: 2026-02-25 (5차)

> 이전 상세 작업 내역은 `PROJECT_STATUS_OLD.md` 참조

---

## 프로젝트 개요

**UBE/Biportal 내시경 척추 수술 계획 및 시뮬레이션 도구**

환자 CT/MRI → 자동 세그멘테이션 → 3D 모델 생성 → 임플란트 배치 → 구조해석 → 안전성 검증

### 기술 스택
- **프론트엔드**: Svelte 5 + TypeScript + Three.js + Vite
- **백엔드**: FastAPI + WebSocket + Taichi GPU
- **세그멘테이션**: TotalSpineSeg / TotalSegmentator / nnU-Net v2
- **해석**: FEM (정적/동적) + NOSB-PD (파괴) + SPG (무격자)
- **재료 모델**: Linear Elastic, Neo-Hookean, Mooney-Rivlin, Ogden

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

- **서버 전체**: 64개 통과
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
uv run uvicorn src.server.app:app --host 0.0.0.0 --port 8000 --reload

# 개발 모드 (프론트엔드 HMR)
cd src/frontend && npm run dev

# 테스트
uv run pytest src/ -v

# 프론트엔드 빌드
cd src/frontend && npm run build
```

---

## 주요 디렉토리 구조

```
src/
├── frontend/           # Svelte 5 + TypeScript 프론트엔드
│   └── src/
│       ├── components/ # UI 컴포넌트 (sidebar/, floating/)
│       ├── lib/        # 스토어, 액션, WebSocket, Three.js 래퍼
│       └── ...
├── server/             # FastAPI 백엔드
│   ├── services/       # DICOM변환, 세그멘테이션, 메쉬추출, 자동재료, 해석
│   ├── models/         # Pydantic 요청/응답 모델
│   ├── ws_handler.py   # WebSocket 라우터
│   └── tests/          # 64개 테스트
├── fea/                # 통합 FEA 프레임워크 (Taichi GPU)
│   ├── fem/            # FEM 솔버 + 재료 모델 (4종)
│   ├── peridynamics/   # NOSB-PD 파괴해석
│   ├── spg/            # SPG 무격자법
│   └── framework/      # 멀티솔버 디스패치
├── segmentation/       # 자동 세그멘테이션 엔진
│   ├── labels.py       # SpineLabel 통합 라벨 체계
│   ├── totalspineseg.py
│   ├── totalseg.py
│   └── nnunet_spine.py
├── core/               # 볼륨 I/O, 공통 유틸
└── simulator/          # 빌드 결과 + 정적 에셋 (STL)
```

---

## 오늘 작업 내역 (2026-02-25)

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
