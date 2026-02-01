# FEM (Finite Element Method) 구현 진행 상황

## 개요

척추 수술 시뮬레이션을 위한 FEM Taichi 구현. FEMcy(https://github.com/mo-hanxuan/FEMcy)를 참고하여 개선된 구조로 구현.

## 완료된 작업

### 1. 핵심 모듈 구현

| 파일 | 설명 | 상태 |
|------|------|------|
| `core/element.py` | 요소 타입 정의 (TET4, TRI3 등) | ✅ 완료 |
| `core/mesh.py` | FEMesh 데이터 구조 (SoA 레이아웃) | ✅ 완료 |
| `material/base.py` | 재료 모델 추상 인터페이스 | ✅ 완료 |
| `material/linear_elastic.py` | 선형 탄성 재료 | ✅ 완료 |
| `material/neo_hookean.py` | Neo-Hookean 초탄성 | ✅ 완료 |
| `solver/static_solver.py` | 정적 평형 솔버 | ✅ 완료 |

### 2. 지원 요소 타입

| 요소 | 노드 수 | 차원 | Gauss 점 | 상태 |
|------|---------|------|----------|------|
| TET4 (C3D4) | 4 | 3D | 1 | ✅ 구현 완료 |
| TRI3 (CPS3/CPE3) | 3 | 2D | 1 | ✅ 구현 완료 |
| HEX8 (C3D8) | 8 | 3D | 8 | ✅ 구현 완료 (2025-02) |
| QUAD4 (CPS4/CPE4) | 4 | 2D | 4 | ✅ 구현 완료 (2025-02) |
| TET10 (C3D10) | 10 | 3D | 4 | 🔲 정의만 |

### 3. 재료 모델

#### Linear Elastic (선형 탄성)
```python
# 응력-변형률 관계
σ = λ·tr(ε)·I + 2μ·ε

# Lamé 파라미터
μ = E / (2(1+ν))
λ = Eν / ((1+ν)(1-2ν))
```

#### Neo-Hookean (초탄성)
```python
# 변형에너지밀도
ψ = μ/2 * (I₁ - 3) - μ·ln(J) + λ/2 * ln²(J)

# Cauchy 응력
σ = J⁻¹ · (μ·(B - I) + λ·ln(J)·I)
```

### 4. HEX8/QUAD4 요소 구현 (2025-02)

#### 4.1 HEX8 (8노드 육면체)

**노드 배치:**
```
    7-------6
   /|      /|
  4-------5 |
  | |     | |
  | 3-----|-2
  |/      |/
  0-------1
```

**형상함수:**
```python
N_i(ξ,η,ζ) = (1/8)(1 + ξ_i·ξ)(1 + η_i·η)(1 + ζ_i·ζ)
```

**Gauss 적분:** 2×2×2 = 8점, ξ,η,ζ ∈ {-1/√3, +1/√3}

**추가된 함수 (`element.py`):**
- `get_gauss_points_hex8()`: Gauss점 및 가중치
- `get_shape_functions_hex8()`: 형상함수
- `get_shape_derivatives_hex8()`: 형상함수 미분

#### 4.2 QUAD4 (4노드 사각형)

**노드 배치:**
```
  3-------2
  |       |
  |       |
  0-------1
```

**형상함수:**
```python
N_i(ξ,η) = (1/4)(1 + ξ_i·ξ)(1 + η_i·η)
```

**Gauss 적분:** 2×2 = 4점, ξ,η ∈ {-1/√3, +1/√3}

**추가된 함수 (`element.py`):**
- `get_gauss_points_quad4()`: Gauss점 및 가중치
- `get_shape_functions_quad4()`: 형상함수
- `get_shape_derivatives_quad4()`: 형상함수 미분

### 5. 검증 결과

```
24 passed in 6.37s

test_fem.py (6개):
- test_element_types: 요소 정의 검증
- test_mesh_creation: 메쉬 생성 및 체적 계산
- test_linear_elastic_material: Lamé 파라미터 계산
- test_neo_hookean_material: 초탄성 재료 속성
- test_solver_linear_tet: 3D 인장 해석
- test_2d_triangle: 2D 삼각형 요소

test_hex8.py (9개):  # 새로 추가 (2025-02)
- test_shape_function_sum: ΣN = 1 검증
- test_shape_function_at_nodes: N_i(node_j) = δ_ij
- test_shape_derivatives_sum: ΣdN = 0
- test_gauss_points_count: 8개 Gauss점
- test_gauss_weights_sum: Σw = 8 (기준 육면체 부피)
- test_unit_cube_volume: 단위 정육면체 부피 = 1
- test_scaled_cube_volume: 2×3×4 직육면체 부피 = 24
- test_deformation_gradient_identity: 무변형시 F = I
- test_compression_direction: 압축 해석 변위 방향

test_quad4.py (9개):  # 새로 추가 (2025-02)
- test_shape_function_sum: ΣN = 1 검증
- test_shape_function_at_nodes: N_i(node_j) = δ_ij
- test_shape_derivatives_sum: ΣdN = 0
- test_gauss_points_count: 4개 Gauss점
- test_gauss_weights_sum: Σw = 4 (기준 사각형 면적)
- test_unit_square_area: 단위 정사각형 면적 = 1
- test_scaled_rectangle_area: 2×3 직사각형 면적 = 6
- test_deformation_gradient_identity: 무변형시 F = I
- test_2x2_mesh_creation: 2×2 메쉬 총 면적 = 4
```

## 사용 예시

```python
import taichi as ti
import numpy as np
ti.init(arch=ti.gpu)

from spine_sim.analysis.fem import FEMesh, ElementType, LinearElastic, StaticSolver

# 메쉬 생성
nodes = np.array([
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [0.5, 1.0, 0.0],
    [0.5, 0.5, 1.0]
], dtype=np.float32)

elements = np.array([[0, 1, 2, 3]], dtype=np.int32)

mesh = FEMesh(n_nodes=4, n_elements=1, element_type=ElementType.TET4)
mesh.initialize_from_numpy(nodes, elements)

# 경계조건 설정
mesh.set_fixed_nodes(np.array([0, 1, 2]))  # 바닥면 고정
mesh.set_nodal_forces(np.array([3]), np.array([[0, 0, 100]]))  # 상단 하중

# 재료 및 솔버
material = LinearElastic(youngs_modulus=1e6, poisson_ratio=0.3, dim=3)
solver = StaticSolver(mesh, material)

# 해석 실행
result = solver.solve(verbose=True)

# 결과 확인
displacements = mesh.get_displacements()
print(f"Max displacement: {np.max(np.abs(displacements)):.6f}")
```

## 핵심 수식

### Shape Function Derivatives (TET4)
```
dN/dξ = [-1, 1, 0, 0]
dN/dη = [-1, 0, 1, 0]
dN/dζ = [-1, 0, 0, 1]
```

### Jacobian
```
J = dX/dξ = Σ X_a ⊗ (dN_a/dξ)
```

### Deformation Gradient
```
F = I + ∂u/∂X = I + Σ u_a ⊗ (dN_a/dX)
```

### Internal Force
```
f_a = - Σ_gp P : (dN_a/dX) · det(J₀) · w
```

## 남은 과제

### 1. 고차 요소 (우선순위: 높음)
- [ ] TET10 완전 구현 (10-node quadratic tetrahedron)
- [x] QUAD4 구현 ✅ (2025-02)
- [x] HEX8 구현 ✅ (2025-02)
- [ ] QUAD8 구현
- [ ] HEX20 구현

### 2. 기하학적 비선형성 (우선순위: 높음)
- [ ] Tangent stiffness matrix에 geometric stiffness 추가
- [ ] Updated Lagrangian 정식화

### 3. 뼈 재료 모델 (우선순위: 중간)
- [ ] Cortical bone (피질골)
- [ ] Cancellous bone (해면골)
- [ ] Transversely isotropic 모델

### 4. 메쉬 입출력 (우선순위: 중간)
- [ ] Abaqus .inp 파일 읽기
- [ ] VTK 출력
- [ ] CT 메쉬 변환기

### 5. 솔버 최적화 (우선순위: 낮음)
- [ ] Preconditioned CG for large systems
- [ ] Matrix-free 방법

## 아키텍처

```
fem/
├── __init__.py
├── core/
│   ├── element.py      # 요소 타입 정의
│   └── mesh.py         # FEMesh 데이터 구조
├── material/
│   ├── base.py         # 추상 인터페이스
│   ├── linear_elastic.py
│   └── neo_hookean.py
├── solver/
│   └── static_solver.py
└── tests/
    └── test_fem.py
```

## 의존성

```toml
dependencies = [
    "taichi>=1.7.4",
    "numpy>=1.24",
    "scipy>=1.10",
]
```
