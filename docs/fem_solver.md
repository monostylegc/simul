# FEM 솔버 가이드

FEM(유한요소법) 솔버, 재료 모델, 메쉬 입출력에 대한 상세 가이드.

> 상위 프레임워크 API는 [FEA Framework](fea_framework.md) 참조.

---

## 솔버 종류

### StaticSolver — 정적 해석

선형 및 비선형(Newton-Raphson) 정적 해석.

```python
from backend.fea.fem.solver import StaticSolver
from backend.fea.fem.material import LinearElastic
from backend.fea.fem.core import FEMesh, ElementType

mesh = FEMesh(n_nodes, n_elements, ElementType.HEX8)
mesh.initialize_from_numpy(nodes, elements)

mat = LinearElastic(E=1e6, nu=0.3, dim=3)
solver = StaticSolver(mesh, mat, use_newton=True, max_iterations=50, tol=1e-8)
result = solver.solve(verbose=True)
```

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `use_newton` | `True` | Newton-Raphson 비선형 해석 사용 |
| `max_iterations` | `50` | 최대 Newton 반복 수 |
| `tol` | `1e-8` | 수렴 허용 오차 |
| `linear_solver` | `"auto"` | 선형 솔버: `"auto"` / `"direct"` / `"cg"` |

> `linear_solver="auto"`: DOF > 50K이면 CG+ILU 전처리기 자동 선택, 아니면 직접 풀기(spsolve).

### DynamicSolver — 동적 해석

Newmark-beta (암시적) 또는 Central Difference (양시적) 시간 적분.

```python
from backend.fea.fem.solver import DynamicSolver

solver = DynamicSolver(
    mesh, mat,
    density=1000.0,
    method="newmark",     # "newmark" 또는 "central_difference"
    dt=1e-4,
    rayleigh_alpha=0.1,   # 질량 비례 감쇠
    rayleigh_beta=0.001,  # 강성 비례 감쇠
)

# 초기 속도 설정 (선택)
solver.set_initial_velocity(v0)

# 시간 전진
for step in range(1000):
    solver.advance(dt=1e-4)
    u, v, a = solver.get_state()  # 변위, 속도, 가속도
```

### ArcLengthSolver — 호장법 (불안정 경로 추적)

Crisfield 구면 호장법으로 snap-through, snap-back, 후좌굴 경로를 추적합니다.

```python
from backend.fea.fem.solver import ArcLengthSolver

solver = ArcLengthSolver(
    mesh, mat,
    arc_length=0.1,           # 초기 호장 길이
    max_steps=100,            # 최대 하중 스텝 수
    max_iterations=30,        # 스텝당 Newton 반복 수
    tol=1e-8,
    psi=1.0,                  # 하중/변위 가중치
    desired_iterations=5,     # 적응적 호장 목표 반복 수
    min_arc_length=1e-6,
    max_arc_length=10.0,
    max_load_factor=1.0,      # 하중 비율 상한
)

result = solver.solve(f_ref=external_force, verbose=True)

# 평형 경로 추출
load_factors = solver.load_history       # [λ₁, λ₂, ...]
displacements = solver.displacement_history  # [u₁, u₂, ...]
```

---

## 재료 모델

### LinearElastic — 선형 탄성

소변형 탄성체. 2D(평면응력/평면변형) 및 3D.

```python
mat = LinearElastic(E=210e9, nu=0.3, dim=3)
mat = LinearElastic(E=1e6, nu=0.3, dim=2, plane_stress=True)
```

### NeoHookean — Neo-Hookean 초탄성

대변형 압축성 초탄성.

```python
mat = NeoHookean(E=1e6, nu=0.45, dim=3)
```

### MooneyRivlin — Mooney-Rivlin 초탄성

2-파라미터 초탄성 모델. 고무, 생체 연조직 등.

```python
# 직접 파라미터 지정
mat = MooneyRivlin(C10=0.5e6, C01=0.1e6, D1=1e-7, dim=3)

# E, ν에서 자동 변환
mat = MooneyRivlin.from_engineering(E=1e6, nu=0.45, dim=3)
```

### Ogden — Ogden 초탄성

1-항 Ogden 모델. 큰 신축률의 고무/생체 조직.

```python
mat = Ogden(mu=0.5e6, alpha=2.0, D1=1e-7, dim=3)
mat = Ogden.from_engineering(E=1e6, nu=0.45, dim=3)
```

### J2Plasticity — J2 소성

Von Mises 항복 + 등방 경화. 금속, 임플란트 재료.

```python
mat = J2Plasticity(
    youngs_modulus=210e9,
    poisson_ratio=0.3,
    yield_stress=250e6,        # 항복 응력 [Pa]
    hardening_modulus=1e9,      # 경화 계수 [Pa]
    dim=3,
)
```

### TransverseIsotropic — 횡이방성

섬유 방향이 있는 이방성 재료. 피질골, 인대 등.

```python
mat = TransverseIsotropic(
    E1=17e9,                    # 종방향 영률 (섬유 방향) [Pa]
    E2=11.5e9,                  # 횡방향 영률 [Pa]
    nu12=0.32,                  # 주 포아송비
    nu23=0.4,                   # 횡 포아송비
    G12=3.3e9,                  # 전단 계수 [Pa]
    fiber_direction=(0, 0, 1),  # 섬유 방향 벡터
    dim=3,
)
```

### 재료 모델 요약

| 모델 | is_linear | 용도 |
|------|-----------|------|
| LinearElastic | ✅ | 소변형 탄성 |
| NeoHookean | ❌ | 대변형 초탄성 |
| MooneyRivlin | ❌ | 고무/연조직 |
| Ogden | ❌ | 큰 신축 |
| J2Plasticity | ❌ | 금속 항복 |
| TransverseIsotropic | ✅ | 이방성 뼈/인대 |

---

## Per-DOF 경계조건

자유도(DOF)별로 독립적인 경계조건을 설정합니다.

```python
# 2D: x만 고정, y는 자유 (롤러)
mesh.set_fixed_nodes(node_ids, dofs=[0])

# 3D: z만 고정 (대칭면)
mesh.set_fixed_nodes(node_ids, dofs=[2])

# 혼합: x고정 + y 규정변위
mesh.set_fixed_nodes(node_ids, values=disp_values, dofs=[0, 1])

# 프레임워크 API 사용
domain.set_fixed(indices, dofs=[0])  # x축 롤러
```

---

## 표면 하중

면 위의 균일 압력을 등가 절점력으로 변환합니다.

```python
from backend.fea.fem.solver import compute_pressure_load, find_surface_faces

# 특정 면에 압력 적용
nodes = mesh.X.to_numpy()[:, :mesh.dim]
faces = np.array([[0, 1, 2, 3]])  # HEX8 면 (4노드)
f_pressure = compute_pressure_load(nodes, faces, pressure=1e6)  # 1 MPa
mesh.f_ext.from_numpy(mesh.f_ext.to_numpy() + f_pressure)

# 좌표면 기반 자동 면 검색
elements = mesh.elements.to_numpy()[:, :mesh.nodes_per_elem]
top_faces = find_surface_faces(elements, dim=3)  # 외부 표면 면 자동 검색
```

---

## 에너지 균형 검증

해석 품질을 자동 검증합니다.

```python
from backend.fea.fem.solver import (
    compute_external_work,
    compute_internal_energy_from_forces,
    check_energy_balance,
    EnergyReport,
)

u = mesh.u.to_numpy()
f_ext = mesh.f_ext.to_numpy()
f_int = mesh.f.to_numpy()

W_ext = compute_external_work(u, f_ext)
U_int = compute_internal_energy_from_forces(u, f_int)

report = check_energy_balance(W_ext, U_int, tolerance=0.05)
print(f"에너지 균형: {report.balance_error:.2%}")
# 5% 이내면 정상
```

---

## VTK 내보내기

ParaView 호환 VTU 파일로 결과를 내보냅니다.

```python
from backend.fea.fem.io import export_vtk, export_vtk_series

# 단일 스텝
export_vtk("result.vtu", mesh, fields=["displacement", "stress", "mises"])

# 호장법/동적 해석 시계열
export_vtk_series(
    "results/step",
    mesh,
    displacement_history=solver.displacement_history,
    load_history=solver.load_history,
)
# → results/step_000.vtu, step_001.vtu, ..., step.pvd
```

---

## 메쉬 임포트

### Abaqus .inp

```python
from backend.fea.fem.io import read_abaqus_inp

mesh_data = read_abaqus_inp("model.inp")
# mesh_data.nodes: (n, 3) 좌표
# mesh_data.elements: (m, nodes_per_elem) 연결
# mesh_data.element_type: ElementType
# mesh_data.node_sets: {"SET_NAME": [indices]}
# mesh_data.boundary_conditions: [(node_id, dof, value), ...]
# mesh_data.concentrated_loads: [(node_id, dof, value), ...]
```

지원 키워드: `*NODE`, `*ELEMENT`, `*NSET` (+GENERATE), `*ELSET`, `*BOUNDARY`, `*CLOAD`

### GMSH .msh v4

```python
from backend.fea.fem.io import read_gmsh_msh

mesh_data = read_gmsh_msh("model.msh")
# 동일한 MeshData 구조 반환
# 체적 요소 자동 필터링 (면/선 요소 제외)
# $PhysicalNames → node_sets 매핑
```

지원: GMSH v4 ASCII 형식, 12종 요소 타입

### MeshData → FEMesh 변환

```python
from backend.fea.fem.core import FEMesh

mesh = FEMesh(len(mesh_data.nodes), len(mesh_data.elements), mesh_data.element_type)
mesh.initialize_from_numpy(mesh_data.nodes, mesh_data.elements)

# 노드셋 활용
fixed_nodes = mesh_data.node_sets.get("FIXED", [])
mesh.set_fixed_nodes(fixed_nodes)
```

---

## 벡터화 성능

내부적으로 모든 계산은 벡터화/배치 처리됩니다:

| 연산 | 방법 | 성능 |
|------|------|------|
| 강성 행렬 조립 | `np.einsum` 배치 | 50-200x 가속 |
| 선형 풀기 | CG + ILU (> 50K DOF) | 5-20x, 메모리 70% 절감 |
| 경계조건 적용 | 배열 인덱싱 벡터화 | Python 루프 제거 |
| 기하 강성 | 벡터화 조립 | Newton-Raphson 수렴 |

---

## 소스 파일

| 모듈 | 경로 |
|------|------|
| 정적 솔버 | `backend/fea/fem/solver/static_solver.py` |
| 동적 솔버 | `backend/fea/fem/solver/dynamic_solver.py` |
| 호장법 솔버 | `backend/fea/fem/solver/arclength_solver.py` |
| 벡터화 조립 | `backend/fea/fem/solver/assembly.py` |
| 표면 하중 | `backend/fea/fem/solver/surface_load.py` |
| 에너지 균형 | `backend/fea/fem/solver/energy_balance.py` |
| 입력 검증 | `backend/fea/fem/validation.py` |
| 메쉬 자료구조 | `backend/fea/fem/core/mesh.py` |
| 요소 정보 | `backend/fea/fem/core/element.py` |
| 재료 모델 | `backend/fea/fem/material/*.py` |
| Abaqus 읽기 | `backend/fea/fem/io/abaqus_reader.py` |
| GMSH 읽기 | `backend/fea/fem/io/gmsh_reader.py` |
| VTK 내보내기 | `backend/fea/fem/io/vtk_export.py` |
