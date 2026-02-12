# 프로젝트 진행 상황

최종 업데이트: 2026-02-12

## 오늘 작업 내역 (2026-02-12)

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
- 50+ FPS 성능

#### 서버 (`src/server/`)
- FastAPI + WebSocket 실시간 통신
- Python FEA framework 직접 호출 (GPU 자동 감지)
- 진행률 실시간 전송 (init → setup → bc → solving → done)
- 정적 파일 서빙 (시뮬레이터 + 해석 통합 단일 서버)

#### FEA (`src/fea/`)
- **통합 프레임워크**: Method.FEM/PD/SPG 전환만으로 솔버 교체, GPU 자동 감지
- **FEM**: TET4, TRI3, HEX8, QUAD4 요소
- **Peridynamics**: NOSB-PD, 준정적 솔버
- **SPG**: Smoothed Particle Galerkin (극한 변형/파괴 해석)
- **STL 구조해석**: STL → 복셀화 → Peridynamics 파이프라인
- **다중 물체 접촉 해석**: Scene API, 노드-노드 페널티, 정적/명시적 모드
- 테스트: 163 passed, 0 failed (FEM 24 + PD 22 + SPG 31 + Framework 19 + Contact 19 + Core 48)
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
- 임플란트 배치 (나사/케이지)

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
│   │   └── post.js           # 후처리기 (컬러맵 시각화)
│   ├── stl/                  # 샘플 STL 파일
│   └── tests/                # 웹 테스트
├── server/                    # FastAPI + WebSocket 서버
│   ├── app.py                # 메인 앱 + 정적 파일 서빙
│   ├── models.py             # Pydantic 데이터 모델
│   ├── ws_handler.py         # WebSocket 핸들러
│   └── analysis_pipeline.py  # FEA framework 호출
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
# 웹 시뮬레이터 + 해석 서버 (권장, 해석 기능 포함)
uv run python -m src.server.app
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
