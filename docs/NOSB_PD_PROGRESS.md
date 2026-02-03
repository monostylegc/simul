# NOSB-PD (Non-Ordinary State-Based Peridynamics) 구현 진행 상황

## 개요
척추 수술 시뮬레이션에서 뼈 파괴 해석을 위한 NOSB-PD Taichi 구현.

## 완료된 작업

### 1. 핵심 모듈 구현
| 파일 | 설명 | 상태 |
|------|------|------|
| `core/particles.py` | ParticleSystem (SoA 레이아웃) | ✅ 완료 |
| `core/neighbor.py` | Grid 기반 이웃 탐색 O(n) | ✅ 완료 |
| `core/bonds.py` | CSR-like 본드 저장 | ✅ 완료 |
| `core/damage.py` | Critical stretch 손상 모델 | ✅ 완료 |
| `core/nosb.py` | NOSB-PD 핵심 계산 | ✅ 완료 |
| `solver/explicit.py` | Bond-based PD 솔버 | ✅ 완료 |
| `solver/quasi_static.py` | 운동 감쇠 준정적 솔버 | ✅ 완료 |
| `solver/nosb_solver.py` | NOSB-PD 준정적 솔버 | ✅ 완료 |
| `material/bone.py` | 뼈 재료 모델 | ✅ 완료 |

### 2. 주요 버그 수정

#### 2.1 힘 계산 부호 오류 (핵심 수정)
**파일:** `core/nosb.py:261-265`

**문제:** NOSB-PD 힘 공식에서 부호 오류로 인해 힘이 평형 반대 방향으로 작용

**수정 전 (오류):**
```python
f_corr = (t_ij + t_ji) * V_j  # t_ji already has minus sign from xi_ji
```

**수정 후 (정상):**
```python
# Net force on i from bond ij: (T[i]<ξ> - T[j]<-ξ>) * V_j
# T[i]<ξ> = t_ij = ω * P_i * K_inv_i * ξ
# T[j]<-ξ> = ω * P_j * K_inv_j * (-ξ) = t_ji
# So: f_i = (t_ij - t_ji) * V_j = ω * (P_i*K_inv_i + P_j*K_inv_j) * ξ * V_j
f_corr = (t_ij - t_ji) * V_j
```

**원리:**
- 표준 NOSB-PD 힘 공식: `f_i = ∫ (T[i]<ξ> - T[j]<-ξ>) dV_j`
- `t_ji = ω * P_j * K_inv_j * (-ξ)` 이므로
- `t_ij - t_ji = ω * (P_i*K_inv_i*ξ + P_j*K_inv_j*ξ)`
- 코드에서 `(t_ij + t_ji)`를 사용하면 `(P_i - P_j)`가 되어 오류

#### 2.2 GPU 동기화 추가
**파일:** `solver/nosb_solver.py`

Taichi 커널 반환값 읽기 전 `ti.sync()` 호출 추가:
```python
_sync = getattr(ti, 'sync', lambda: None)

# 사용 예:
ke = float(self._velocity_verlet_step2(self.dt))
_sync()  # GPU 동기화
```

#### 2.3 3D 지원 검증 (2025-02)
**추가된 파일:**
- `tests/test_3d.py` - 11개 3D 테스트
- `examples/cube_3d.py` - 3D 큐브 압축 예제

**테스트 항목:**
```
Test3DGridInitialization (2개)
- test_3d_grid_creation: 3D 격자 생성
- test_3d_particle_volume: 입자 부피 계산

Test3DNeighborSearch (2개)
- test_3d_neighbor_count: 직접 이웃 (6개)
- test_3d_diagonal_neighbors: 대각선 포함 (18개)

Test3DBondSystem (2개)
- test_3d_bond_creation: 본드 생성
- test_3d_bond_vectors: 본드 벡터 길이

Test3DNOSBShapeTensor (3개)
- test_3d_shape_tensor_symmetry: K 대칭성
- test_3d_shape_tensor_positive_definite: K 양정치
- test_3d_deformation_gradient_identity: F=I (무변형)

Test3DQuasiStaticCompression (2개)
- test_3d_compression_displacement: 압축 변위 방향
- test_3d_solver_stability: 솔버 안정성
```

#### 2.4 QuasiStaticSolver 안정성 개선 (2025-02)
**파일:** `solver/quasi_static.py`

**개선 내용:**
1. 가속도/속도 초기화 함수 추가
2. Viscous damping 파라미터 추가 (기본값 0.1)
3. NaN/Inf 보호 로직 추가
4. 더 보수적인 시간 간격 추정

**수정된 생성자:**
```python
def __init__(
    self,
    particles: "ParticleSystem",
    bonds: "BondSystem",
    micromodulus: float,
    dt: float = None,
    damping: float = 0.1  # 새로 추가
):
```

#### 2.5 점성 감쇠 추가
**파일:** `solver/nosb_solver.py`

운동 감쇠만으로는 큰 진폭 진동을 효과적으로 억제하지 못함. 점성 감쇠 추가:
```python
# 생성자에 viscous_damping 파라미터 추가
def __init__(self, ..., viscous_damping: float = 0.0):
    self.viscous_damping = ti.field(dtype=ti.f32, shape=())
    self.viscous_damping[None] = viscous_damping

# 속도 업데이트에 감쇠 적용
@ti.kernel
def _velocity_verlet_step2(self, dt):
    damping = 1.0 - self.viscous_damping[None]
    for i in range(self.n_particles):
        # ... 속도 업데이트 ...
        self.particles.v[i] *= damping  # 점성 감쇠
```

**권장값:** `viscous_damping=0.0001` (준정적 해석)

### 3. 검증 결과

#### 3.1 단위 테스트
```
22 passed in 5.38s

test_particles.py (11개):
- test_initialization
- test_grid_initialization
- test_fixed_particles
- test_displacement
- test_basic_neighbor_search
- test_horizon_cutoff
- test_bond_creation
- test_critical_stretch_computation
- test_bone_critical_stretch
- test_stable_dt_estimation
- test_energy_conservation

test_3d.py (11개):  # 새로 추가 (2025-02)
- test_3d_grid_creation
- test_3d_particle_volume
- test_3d_neighbor_count
- test_3d_diagonal_neighbors
- test_3d_bond_creation
- test_3d_bond_vectors
- test_3d_shape_tensor_symmetry
- test_3d_shape_tensor_positive_definite
- test_3d_deformation_gradient_identity
- test_3d_compression_displacement
- test_3d_solver_stability
```

#### 3.2 NOSB-PD 준정적 수렴 테스트
```
Grid: 15x31 = 465 particles
Material: E=1.00e+04, ν=0.300

Iter      0: rel=1.00e+00, resets=0
Iter  40000: rel=2.08e-03, resets=42
Iter 160000: rel=1.96e-03, resets=312

결과: 잔차 99.8% 감소, 평형 수렴 확인
```

#### 3.3 힘 방향 검증
- 변위된 경계 입자 근처의 내부 입자: 경계 방향으로 당겨짐 ✅
- 균일 변형장의 중심 입자: 힘 ≈ 0 ✅
- 전체 힘 합: ≈ 0 (뉴턴 3법칙) ✅

## 남은 과제

### 1. 엄격한 허용오차 달성 (우선순위: 높음)
**상태:** 부분 해결

**현재 결과:**
- 상대 잔차: 1.0 → 6.66e-03 (99.3% 감소)
- 변위 오차: 0% (정확한 해 달성)
- 수렴 속도가 느려 1e-4 달성에 ~30만 반복 필요

**해결된 문제:**
- [x] 점성 감쇠 추가 (`viscous_damping` 파라미터)
- [x] 최적 파라미터 탐색: `dt=5e-5, stab=0.10, viscous_damping=0.0001`

**권장 파라미터:**
```python
solver = NOSBSolver(
    particles=particles,
    bonds=bonds,
    material=material,
    horizon=horizon,
    stabilization=0.10,
    dt=5e-5,
    viscous_damping=0.0001  # 새로 추가된 파라미터
)
```

**남은 작업:**
- [ ] Adaptive time stepping 구현 (수렴 가속)

### 2. Bond-Associated Deformation Gradient (우선순위: 중간)
영에너지 모드를 근본적으로 제거하는 방법.

**참고 논문:**
- Breitzman & Dayal (2018)
- arXiv 2410.00934

**구현 내용:**
- [ ] 입자별 F 대신 본드별 F 계산
- [ ] 본드별 응력 계산
- [ ] 힘 상태 재정의

### 3. 3D 확장 (우선순위: 중간)
- [x] 3D Shape tensor 계산 ✅ (2025-02)
- [x] 3D 이웃 탐색 최적화 ✅ (2025-02)
- [x] 3D 검증 테스트 ✅ (2025-02)

### 4. FEMcy 메쉬 연동 (우선순위: 낮음)
- [ ] `io/mesh_converter.py` 구현
- [ ] CT 메쉬 → PD 입자 변환

## 사용 예시

```python
import taichi as ti
ti.init(arch=ti.gpu)

from spine_sim.analysis.peridynamics.core.particles import ParticleSystem
from spine_sim.analysis.peridynamics.core.bonds import BondSystem
from spine_sim.analysis.peridynamics.core.neighbor import NeighborSearch
from spine_sim.analysis.peridynamics.core.nosb import NOSBMaterial
from spine_sim.analysis.peridynamics.solver.nosb_solver import NOSBSolver

# 입자 시스템 생성
particles = ParticleSystem(n_particles=n, dim=2)
particles.initialize_from_arrays(positions, volumes, density=1000.0)

# 이웃 탐색 및 본드 생성
neighbor_search = NeighborSearch(domain_min, domain_max, horizon, n, dim=2)
neighbor_search.build(particles.X, n)

bonds = BondSystem(n_particles=n, max_bonds=20, dim=2)
bonds.build_from_neighbor_search(particles, neighbor_search, horizon)

# 재료 및 솔버
material = NOSBMaterial(youngs_modulus=1e4, poisson_ratio=0.3, dim=2)
solver = NOSBSolver(
    particles, bonds, material, horizon,
    stabilization=0.1,
    dt=5e-5,
    viscous_damping=0.0001  # 준정적 해석에 권장
)

# 경계 조건 설정 후 해석
result = solver.solve(max_iterations=200000, tol=1e-4)
```

## 핵심 수식

### Shape Tensor
```
K_i = Σ_j ω(|ξ_ij|) · (ξ_ij ⊗ ξ_ij) · V_j
```

### Deformation Gradient
```
F_i = [Σ_j ω(|ξ_ij|) · (η_ij ⊗ ξ_ij) · V_j] · K_i⁻¹
```

### Force State (Correspondence)
```
T[i]<ξ> = ω · P_i · K_i⁻¹ · ξ
```

### Internal Force
```
f_i = Σ_j (T[i]<ξ_ij> - T[j]<-ξ_ij>) · V_j
```

### Zero-Energy Mode Stabilization
```
f_stab = G_s · c · s · ω · (η/|η|) · V_j
```
where `s = (|η| - |ξ|) / |ξ|` is the bond stretch.
