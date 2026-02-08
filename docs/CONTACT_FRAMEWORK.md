# 다중 물체 접촉 해석 프레임워크

> 최종 업데이트: 2026-02-08

## 개요

FEM, Peridynamics(PD), SPG 세 가지 이종 솔버 간 **접촉 해석**을 지원하는 프레임워크.
척추 수술 시뮬레이션의 핵심인 **뼈(SPG) + 임플란트(FEM)** 접촉 문제를 해결하기 위해 설계되었다.

### 핵심 도전과 해결

| 문제 | 해결 |
|------|------|
| FEM(암묵적) vs PD/SPG(명시적) 시간적분 이질성 | 3가지 해석 모드 (`quasi_static`, `static`, `explicit`) |
| FEM 요소 기반 vs PD/SPG 입자 기반 표면 표현 | 노드-노드 페널티: 모든 솔버가 점(point)으로 통일 |
| 접촉력 주입 방식이 솔버마다 다름 | AdapterBase ABC로 공통 인터페이스 강제 |

## 사용법

### 기본 예제: 두 블록 접촉

```python
from src.fea.framework import (
    init, create_domain, Material, Method, Scene, ContactType
)

init()

# 아래 블록 (SPG - 뼈)
bone = create_domain(Method.SPG, dim=2,
    origin=(0, 0), size=(1.0, 0.5), n_divisions=(21, 11))
bone_fix = bone.select(axis=1, value=0.0)
bone.set_fixed(bone_fix)
bone_mat = Material(E=17e9, nu=0.3, density=1900, dim=2)

# 위 블록 (FEM - 임플란트)
screw = create_domain(Method.FEM, dim=2,
    origin=(0.2, 0.6), size=(0.6, 0.3), n_divisions=(6, 3))
screw_top = screw.select(axis=1, value=0.9)
screw.set_force(screw_top, [0.0, -500.0 / len(screw_top)])
screw_mat = Material(E=110e9, nu=0.34, density=4500, dim=2, plane_stress=True)

# Scene 구성
scene = Scene()
scene.add(bone, bone_mat, stabilization=0.01, viscous_damping=0.05)
scene.add(screw, screw_mat)

# 접촉 조건
bone_top = bone.select(axis=1, value=0.5)
screw_bottom = screw.select(axis=1, value=0.6)
scene.add_contact(bone, screw,
    method=ContactType.PENALTY,
    penalty=1e8,
    gap_tolerance=0.05,
    surface_a=bone_top,
    surface_b=screw_bottom)

# 해석
result = scene.solve(mode="quasi_static", max_iterations=50000, tol=1e-3)

# 결과
u_bone = scene.get_displacements(bone)
u_screw = scene.get_displacements(screw)
stress_bone = scene.get_stress(bone)
```

### 접촉 매개변수 자동 추정

`penalty`와 `gap_tolerance`를 생략하면 자동 추정된다:

```python
scene.add_contact(bone, screw)  # penalty, gap_tolerance 자동
# penalty ≈ (E_a + E_b) / (2 × min_spacing)
# gap_tolerance ≈ 1.5 × max_spacing
```

### 경계면 자동 감지

`surface_a`, `surface_b`를 생략하면 도메인 외곽 전체를 접촉면으로 사용:

```python
scene.add_contact(bone, screw, penalty=1e8)  # 경계 자동 감지
```

수동 지정도 가능:

```python
bone_boundary = bone.select_boundary()        # 전체 경계
bone_top = bone.select(axis=1, value=0.5)     # 특정 면만
```

## 해석 모드

### `quasi_static` (기본, 권장)

모든 body가 매 스텝 동시에 1스텝 전진하면서 접촉력도 매 스텝 갱신.
전체 운동에너지(KE)가 수렴하면 종료.

```
for step in range(max_iterations):
    접촉력 계산 & 주입 (매 스텝)
    SPG/PD body → step(dt)
    FEM body → 주기적 re-solve (500 스텝마다)
    KE/E_ref < tol → 수렴 종료
```

- **적합**: SPG-SPG, PD-PD, FEM+SPG 혼합
- FEM만 있으면 자동으로 `static` 모드로 폴백
- FEM 재해석 주기: `fem_update_interval` (기본 500)

```python
result = scene.solve(mode="quasi_static", max_iterations=50000, tol=1e-3)
```

### `static` (Staggered)

매 접촉 반복마다 각 body가 독립적으로 완전 해석(converge).
FEM-FEM 접촉에 최적화.

```
for contact_iter in range(max_contact_iters):
    접촉력 계산 & 주입
    각 body 독립 solve (FEM: Newton-Raphson, SPG/PD: 준정적 수렴)
    접촉력 변화 < tol → 수렴
```

- **적합**: FEM-FEM 접촉
- **주의**: SPG/PD는 매 반복 시 속도 리셋으로 처음부터 수렴 → 비효율적

```python
result = scene.solve(mode="static", max_contact_iters=30, contact_tol=1e-2)
```

### `explicit` (동기화 명시적)

수렴 체크 없이 n_steps 진행. 동적 문제용.

```python
result = scene.solve(mode="explicit", n_steps=10000)
```

## 접촉 알고리즘

### 노드-노드 페널티 접촉

```
접촉력 = penalty × max(0, gap_tol - distance) × normal
normal = (pos_a - pos_b) / distance   (A를 B에서 밀어내는 방향)
```

1. **감지**: `scipy.spatial.cKDTree`로 B 표면에서 A 표면 최근접 탐색
2. **계산**: gap_tolerance 이내 쌍에 대해 페널티 반발력 계산
3. **주입**: 작용-반작용 (A ← +f, B ← -f)

## 아키텍처

### 파일 구조

```
src/fea/framework/
├── contact.py           # ContactType, NodeNodeContact 알고리즘
├── scene.py             # Scene, Body, quasi_static/static/explicit 솔버
├── domain.py            # (+) select_boundary() 추가
├── __init__.py          # (+) Scene, ContactType export
├── _adapters/
│   ├── base_adapter.py  # AdapterBase ABC (접촉 공통 인터페이스)
│   ├── fem_adapter.py   # (+) inject/clear_contact_forces, step, get_stable_dt
│   ├── pd_adapter.py    # (+) 동일
│   └── spg_adapter.py   # (+) 동일
└── tests/
    ├── test_framework.py  # 기존 19개
    └── test_contact.py    # 신규 19개
```

### AdapterBase 공통 인터페이스

기존 4개 메서드에 5개 접촉 메서드 추가:

| 메서드 | 기존 | 접촉 추가 |
|--------|------|----------|
| `solve()` | O | |
| `get_displacements()` | O | |
| `get_stress()` | O | |
| `get_damage()` | O | |
| `get_current_positions()` | | O |
| `get_reference_positions()` | | O |
| `inject_contact_forces()` | | O |
| `clear_contact_forces()` | | O |
| `step(dt)` | | O |
| `get_stable_dt()` | | O |

### 접촉력 주입 방식 (솔버별)

| 솔버 | 메커니즘 | 상세 |
|------|---------|------|
| **FEM** | `_contact_forces` + `_user_f_ext` → `mesh.f_ext` | 매 solve() 전 합산 |
| **PD** | `_contact_forces` → `_apply_forces()` 콜백에서 `ps.f`에 추가 | 매 step 콜백 |
| **SPG** | `_contact_forces` + `_user_f_ext` → `ps.f_ext` | 매 step 전 합산 |

## 테스트

```bash
# 접촉 테스트만
uv run pytest src/fea/framework/tests/test_contact.py -v

# 전체 테스트
uv run pytest src/ -v  # 163 passed
```

### 테스트 목록 (19개)

| 카테고리 | 테스트 | 수 |
|---------|--------|-----|
| 접촉 알고리즘 | 감지, 작용-반작용, 방향, 크기, 부분집합, 비접촉 | 6 |
| 경계 감지 | FEM 경계, SPG 경계 | 2 |
| Scene API | 물체 추가, 접촉 추가, 잘못된 도메인, enum 값 | 4 |
| FEM-FEM 통합 | 두 블록 압축, 독립 해석 | 2 |
| SPG 준정적 | 두 블록 접촉, 비접촉 수렴 | 2 |
| 모드 선택 | 기본 모드 확인, 잘못된 모드 오류 | 2 |
| 자동 추정 | gap_tolerance, penalty 추정 | 1 |

## 설계 교훈

### gap_tolerance 설정 주의

- `gap_tolerance > 실제 gap` → 초기부터 큰 반발력 → 블록 분리
- **올바른 설정**: `gap > gap_tolerance` (초기 분리) → 하중으로 접근 → 자연스러운 접촉 발생

### SPG/PD solve()의 속도 리셋

- `SPGExplicitSolver.solve()`와 `QuasiStaticSolver.solve()`는 호출 시 **속도를 리셋**
- 변위(u)는 유지되지만, 매번 kinetic damping 수렴을 처음부터 시작
- 따라서 Staggered(`static`)보다 **`quasi_static`** 모드가 효율적

### penalty 추정 경험칙

```
penalty = E_avg / char_length
```

- 너무 작으면: 관통 허용 (비물리적)
- 너무 크면: dt 감소 필요, 진동 발생
- 경험적으로 `E / spacing` ~ `10 × E / spacing` 범위가 적절

## 향후 확장

- **노드-표면 접촉**: FEM 요소면 투영 기반 (정밀도 향상)
- **마찰**: Coulomb friction (접선 방향 힘 추가)
- **명시적 FEM**: Mass matrix 기반 Velocity Verlet
- **적응형 dt**: 접촉 시 dt 자동 축소
- **GPU 가속**: Taichi 커널로 KDTree 대체
