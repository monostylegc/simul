# 프로젝트 진행 상황

최종 업데이트: 2026-02-08

## 오늘 작업 내역 (2026-02-08)

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
- 복셀 기반 드릴링 + Marching Cubes
- 해상도 조절 UI (32~192)
- **Undo/Redo** (Ctrl+Z/Y, 최대 30단계)
- **단면 뷰 (Slice View)** - X/Y/Z 축 단면 + 위치 조절
- **좌표 시스템 개선** - 원본 좌표 유지 + 자동 원점 중심 배치
- **동적 그리드** - 모델 크기에 맞게 자동 조절
- **모델 정보 UI** - 크기/중심/범위 실시간 표시
- 50+ FPS 성능

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
- Measure 도구 (웹)
- 임플란트 배치 (나사/케이지)

## 모듈 구조

```
src/
├── simulator/                 # Three.js 웹 시뮬레이터 (메인)
│   ├── index.html            # UI 레이아웃
│   ├── src/
│   │   ├── main.js           # Three.js 메인
│   │   ├── voxel.js          # 복셀 + Marching Cubes
│   │   └── nrrd.js           # NRRD 파서
│   ├── stl/                  # 샘플 STL 파일
│   └── tests/                # 웹 테스트
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
# 웹 시뮬레이터
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
