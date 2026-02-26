# FEA 통합 프레임워크 가이드

FEM, Peridynamics(PD), SPG 세 솔버를 동일한 API로 사용하는 통합 프레임워크.
`Method` enum만 변경하면 나머지 코드는 동일하게 유지됩니다.

---

## 임포트

```python
from backend.fea.framework import (
    init, Backend, Precision,
    create_domain, Domain, Method,
    Material, Solver, SolveResult,
    Scene, ContactType,
    RigidBody, PrescribedMotion, create_rigid_body,
)
```

---

## 1. 초기화: `init()`

Taichi 런타임을 초기화합니다. **프로세스당 1회만** 호출합니다.

```python
init()                                    # 자동 (CUDA → Vulkan → CPU)
init(backend=Backend.CUDA)                # CUDA 강제
init(backend=Backend.CPU)                 # CPU 강제
init(backend=Backend.AUTO, precision=Precision.F32)  # 단정밀도
```

| Backend | 설명 |
|---------|------|
| `AUTO` | CUDA → Vulkan → CPU 순 자동 선택 |
| `CUDA` | NVIDIA GPU (CUDA) |
| `VULKAN` | 크로스 플랫폼 GPU |
| `CPU` | CPU 폴백 |

---

## 2. 도메인 생성: `create_domain()`

해석 영역(노드/입자 집합)을 생성합니다.

### 정규 격자 도메인

```python
domain = create_domain(
    method=Method.FEM,       # FEM | PD | SPG | COUPLED
    dim=2,                   # 2D 또는 3D
    origin=(0.0, 0.0),       # 원점
    size=(1.0, 0.2),         # 크기
    n_divisions=(50, 10),    # 격자 분할 수
)
```

### 입자 기반 도메인 (복셀 메쉬용)

```python
from backend.fea.framework.domain import create_particle_domain

domain = create_particle_domain(
    positions=np.array([[0, 0, 0], [1, 0, 0], ...]),  # (n, dim) 좌표
    method=Method.PD,
    volumes=np.array([1.0, 1.0, ...]),                 # (n,) 체적
)
```

### Domain API

| 메서드 | 설명 |
|--------|------|
| `select(axis, value, tol=None)` | 특정 축/값에 위치한 노드 인덱스 반환 |
| `select_boundary(tol=None)` | 경계 노드 인덱스 반환 |
| `set_fixed(indices, values=None, dofs=None)` | 고정 경계조건 설정 |
| `set_force(indices, forces)` | 절점력 설정 |
| `get_positions()` | 노드/입자 좌표 (n, dim) 반환 |
| `n_points` | 총 노드/입자 수 (property) |

**경계조건 예시**:
```python
# 왼쪽 면 완전 고정
left = domain.select(axis=0, value=0.0)
domain.set_fixed(left)

# 오른쪽 면에 힘 적용
right = domain.select(axis=0, value=1.0)
domain.set_force(right, [100.0, 0.0])  # x 방향 100N/node

# Per-DOF: x축만 고정 (롤러 경계조건)
bottom = domain.select(axis=1, value=0.0)
domain.set_fixed(bottom, dofs=[0])     # x만 고정, y는 자유

# 규정 변위
top = domain.select(axis=1, value=1.0)
domain.set_fixed(top, values=np.array([[0.01, 0.0]] * len(top)))
```

---

## 3. 재료 정의: `Material`

```python
mat = Material(E=1e6, nu=0.3, density=1000, dim=2)
```

### 전체 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `E` | `float` | 필수 | 영률 [Pa] |
| `nu` | `float` | 필수 | 포아송비 |
| `density` | `float` | `1000.0` | 밀도 [kg/m³] |
| `dim` | `int` | `2` | 차원 (2D/3D) |
| `plane_stress` | `bool` | `False` | 평면응력 (2D FEM 전용) |
| `constitutive_model` | `str` | `"linear_elastic"` | 구성 모델 |

**초탄성 파라미터** (`constitutive_model` 지정 시):

| 파라미터 | 구성 모델 | 설명 |
|----------|-----------|------|
| `C10`, `C01` | `mooney_rivlin` | Mooney-Rivlin 상수 [Pa] |
| `D1` | `mooney_rivlin`, `ogden` | 비압축성 [1/Pa] |
| `mu_ogden`, `alpha_ogden` | `ogden` | Ogden 전단/지수 |

**소성/이방성 파라미터**:

| 파라미터 | 구성 모델 | 설명 |
|----------|-----------|------|
| `yield_stress` | `j2_plasticity` | 항복 응력 [Pa] |
| `hardening_modulus` | `j2_plasticity` | 경화 계수 [Pa] |
| `E1`, `E2` | `transverse_isotropic` | 종/횡 영률 [Pa] |
| `nu12`, `nu23` | `transverse_isotropic` | 포아송비 |
| `G12` | `transverse_isotropic` | 전단 계수 [Pa] |
| `fiber_direction` | `transverse_isotropic` | 섬유 방향 벡터 |

---

## 4. 단일 물체 해석: `Solver`

```python
solver = Solver(domain, mat)
result = solver.solve()     # SolveResult 반환

u = solver.get_displacements()  # (n_points, dim) 변위 배열
s = solver.get_stress()         # 응력 배열
d = solver.get_damage()         # 손상도 (PD/SPG만, FEM은 None)
```

### SolveResult

| 필드 | 타입 | 설명 |
|------|------|------|
| `converged` | `bool` | 수렴 여부 |
| `iterations` | `int` | 반복 수 |
| `residual` | `float` | 잔차 |
| `relative_residual` | `float` | 상대 잔차 |
| `elapsed_time` | `float` | 소요 시간 (초) |

---

## 5. 다물체 접촉 해석: `Scene`

여러 도메인을 하나의 Scene에 등록하고 접촉을 추가하여 연성(coupled) 해석을 수행합니다.

```python
scene = Scene()

# 물체 추가
scene.add(bone_domain, bone_material)
scene.add(screw_domain, screw_material)

# 접촉 추가
scene.add_contact(
    bone_domain, screw_domain,
    method=ContactType.PENALTY,
    penalty=1e8,
    gap_tolerance=0.01,
    static_friction=0.3,
    dynamic_friction=0.2,
)

# 해석 실행
result = scene.solve(
    mode="static",              # "static" | "quasi_static" | "explicit"
    max_contact_iters=30,
    contact_tol=1e-3,
)

# 결과 추출 (도메인별)
u_bone = scene.get_displacements(bone_domain)
u_screw = scene.get_displacements(screw_domain)
```

### Scene API

| 메서드 | 설명 |
|--------|------|
| `add(domain, material, **options)` | 물체 추가 → `Body` 반환 |
| `add_contact(dom_a, dom_b, method, ...)` | 접촉 정의 추가 |
| `solve(mode, ...)` | 전체 해석 실행 → `SolveResult` |
| `get_displacements(domain)` | 특정 물체 변위 |
| `get_stress(domain)` | 특정 물체 응력 |

### ContactType

| 타입 | 설명 | 용도 |
|------|------|------|
| `PENALTY` | 페널티법 접촉 (반발력 + 마찰) | 척추골 간 후관절 접촉 |
| `TIED` | 구속 접촉 (초기 상대위치 유지) | 척추골-디스크 접착 |

---

## 6. 강체: `RigidBody`

변형 없이 규정 운동만 하는 물체. 접촉 해석에서 공구(tool) 역할.

```python
positions = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)

motion = PrescribedMotion(
    motion_type="translation",   # "translation" 또는 "rotation"
    axis=np.array([0.0, -1.0]),  # 이동/회전 방향
    rate=0.01,                   # m/s 또는 rad/s
    total=0.1,                   # 총 이동/회전량
)

rb = create_rigid_body(positions, dim=2, motions=[motion])

# Scene에 추가
scene = Scene()
scene.add(deformable_domain, mat)
scene.add(rb)
scene.add_contact(deformable_domain, rb, method=ContactType.PENALTY, penalty=1e6)
```

---

## 7. Method enum

| Method | 설명 | 적합한 상황 |
|--------|------|------------|
| `FEM` | 유한요소법 | 탄성/소성 변형, 높은 정밀도 |
| `PD` | NOSB-Peridynamics | 균열/파괴 해석 |
| `SPG` | Smoothed Particle Galerkin | 대변형, 무격자법 |
| `COUPLED` | FEM↔PD/SPG 적응적 커플링 | 벌크(FEM) + 파괴 영역(PD) 동시 |
| `RIGID` | 강체 | 변형 없는 공구/지그 |

---

## 코드 예시: 2D 인장봉

```python
from backend.fea.framework import init, create_domain, Material, Solver, Method

init()

# 도메인 생성: 1.0 × 0.2 직사각형, 50×10 격자
L, H = 1.0, 0.2
domain = create_domain(Method.FEM, dim=2, origin=(0, 0), size=(L, H), n_divisions=(50, 10))

# 경계조건
left = domain.select(axis=0, value=0.0)    # x=0 고정
right = domain.select(axis=0, value=L)      # x=L 하중
domain.set_fixed(left)

P = 1000.0  # 총 하중 [N]
domain.set_force(right, [P / len(right), 0.0])

# 재료: E=1MPa, ν=0.3
mat = Material(E=1e6, nu=0.3, density=1000, dim=2, plane_stress=True)

# 해석
solver = Solver(domain, mat)
result = solver.solve()
print(f"수렴: {result.converged}, 반복: {result.iterations}")

# 변위 확인
u = solver.get_displacements()
u_tip = u[right].mean(axis=0)
print(f"끝단 x변위: {u_tip[0]:.6f} m")

# 이론값: δ = PL/(AE) = 1000 * 1.0 / (0.2 * 1e6) = 0.005
```

---

## 코드 예시: FEM/PD/SPG 비교

```python
for method in [Method.FEM, Method.PD, Method.SPG]:
    domain = create_domain(method, dim=2, origin=(0, 0), size=(1.0, 0.2), n_divisions=(40, 8))

    left = domain.select(axis=0, value=0.0)
    right = domain.select(axis=0, value=1.0)
    domain.set_fixed(left)
    domain.set_force(right, [100.0 / len(right), 0.0])

    mat = Material(E=1e6, nu=0.3, density=1000, dim=2)
    solver = Solver(domain, mat)
    result = solver.solve()

    u = solver.get_displacements()
    print(f"{method.value}: tip_x = {u[right, 0].mean():.6f}")
```

---

## 소스 파일

| 모듈 | 경로 |
|------|------|
| 패키지 초기화 | `backend/fea/framework/__init__.py` |
| 런타임 초기화 | `backend/fea/framework/runtime.py` |
| 도메인 관리 | `backend/fea/framework/domain.py` |
| 재료 정의 | `backend/fea/framework/material.py` |
| 솔버 디스패치 | `backend/fea/framework/solver.py` |
| 결과 데이터 | `backend/fea/framework/result.py` |
| 다물체 씬 | `backend/fea/framework/scene.py` |
| 접촉 알고리즘 | `backend/fea/framework/contact.py` |
| 강체 | `backend/fea/framework/rigid_body.py` |
| 커플링 엔진 | `backend/fea/framework/coupling/` |
