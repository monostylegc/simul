# 전처리 및 자동 조립 가이드

CT 라벨맵(NPZ)에서 다물체 FEA Scene을 자동 생성하는 파이프라인.

---

## 개요

```
CT 라벨맵 NPZ
  → assemble(npz_path, SpineProfile())
    → 라벨별 복셀 추출
    → FEM/COUPLED 도메인 자동 생성 (voxel_to_hex HEX8)
    → 인접 쌍 탐색 → TIED 접촉 자동 추가 (척추골-디스크)
    → 후관절 탐지 → PENALTY+마찰 접촉 자동 추가 (척추골-척추골)
  → AssemblyResult
    → scene.solve() → 다물체 접촉 해석
```

아키텍처는 **범용 전처리**(`preprocessing/`)와 **부위 특화**(`anatomy/`)로 분리됩니다:

- `preprocessing/`: 부위에 무관한 범용 알고리즘 (인접 쌍, HEX8 변환, 조립)
- `anatomy/`: 부위별 해부학 지식 (재료, 접촉 규칙, 후관절 탐지)

---

## 임포트

```python
from backend.preprocessing import (
    find_adjacent_pairs, AdjacencyPair,
    voxels_to_hex_mesh,
    assemble, AssemblyResult,
)
from backend.anatomy import (
    AnatomyProfile, MaterialProps,
    SpineProfile, FacetJoint,
)
```

---

## 1. 인접 쌍 탐색: `find_adjacent_pairs()`

3D 라벨 볼륨에서 6-connected 이웃을 스캔하여 인접한 라벨 쌍을 찾습니다.

```python
import numpy as np

# 라벨 볼륨 (예: L4=123, L4L5=222, L5=124)
label_volume = np.zeros((10, 10, 20), dtype=np.int32)
label_volume[:, :, :7] = 123   # L4
label_volume[:, :, 7:13] = 222  # L4L5 디스크
label_volume[:, :, 13:] = 124   # L5

pairs = find_adjacent_pairs(label_volume, ignore_labels={0})
for pair in pairs:
    print(f"{pair.label_a} ↔ {pair.label_b}: 경계 복셀 {pair.interface_voxels}개")
# 123 ↔ 222: ...
# 222 ↔ 124: ...
```

### AdjacencyPair

| 필드 | 타입 | 설명 |
|------|------|------|
| `label_a` | `int` | 라벨 A |
| `label_b` | `int` | 라벨 B |
| `interface_voxels` | `int` | 접촉 경계 복셀 수 |

---

## 2. 복셀 → HEX8 메쉬: `voxels_to_hex_mesh()`

복셀 중심 좌표를 HEX8(8절점 육면체) 유한요소 메쉬로 변환합니다.
좌표 해싱으로 인접 복셀 간 노드를 자동 합병합니다.

```python
# 복셀 중심 좌표
centers = np.array([
    [0.5, 0.5, 0.5],
    [1.5, 0.5, 0.5],
    [0.5, 1.5, 0.5],
])
spacing = np.array([1.0, 1.0, 1.0])

nodes, elements = voxels_to_hex_mesh(centers, spacing)
# nodes: (n_nodes, 3) — HEX8 절점 좌표
# elements: (n_elements, 8) — 요소-절점 연결 (0-based)
```

| 입력 | 형상 | 설명 |
|------|------|------|
| `voxel_centers` | `(n, 3)` | 복셀 중심 좌표 |
| `voxel_spacing` | `(3,)` | 복셀 간격 (dx, dy, dz) |

| 출력 | 형상 | 설명 |
|------|------|------|
| `nodes` | `(n_nodes, 3)` | HEX8 절점 좌표 |
| `elements` | `(n_elem, 8)` | 요소-절점 연결 |

---

## 3. 자동 조립: `assemble()`

NPZ 파일과 AnatomyProfile을 받아 다물체 Scene을 자동 생성합니다.

```python
from backend.fea.framework import init

init()

result = assemble("spine_labels.npz", SpineProfile(), min_voxels=10)
# result.scene: Scene 객체 (solve 가능)
# result.body_map: {123: "L4", 222: "L4L5_disc", 124: "L5"}
# result.contact_pairs: [(123, 222, ContactType.TIED), ...]
# result.label_domains: {123: Domain, 222: Domain, 124: Domain}
```

### NPZ 파일 형식

```python
# NPZ 생성 예시
np.savez(
    "spine_labels.npz",
    label_volume=label_volume,  # (I, J, K) int32 — 라벨맵
    spacing=np.array([1.0, 1.0, 1.0]),  # (3,) — 복셀 간격 [mm]
    origin=np.array([0.0, 0.0, 0.0]),   # (3,) — 원점 좌표 [mm]
)
```

### 처리 절차

1. NPZ 로드 → `label_volume`, `spacing`, `origin`
2. 라벨별 복셀 추출 (`min_voxels` 이하 라벨 무시)
3. `AnatomyProfile.get_material(label)` → 재료 물성 + 해석 방법
4. 복셀 → 도메인 생성:
   - `FEM`: `voxels_to_hex_mesh()` → HEX8 메쉬
   - `COUPLED`: HEX8 메쉬 + CouplingConfig
   - `PD`/`SPG`: `create_particle_domain()` → 입자 기반
5. `find_adjacent_pairs()` → 인접 쌍 탐색
6. `profile.get_contact_type()` → 접촉 유형 결정 + Scene에 추가
7. `profile.detect_facet_joints()` → 후관절 PENALTY 접촉 추가 (SpineProfile)

### AssemblyResult

| 필드 | 타입 | 설명 |
|------|------|------|
| `scene` | `Scene` | 다물체 Scene (solve 가능) |
| `body_map` | `dict[int, str]` | 라벨 → 물체 이름 |
| `contact_pairs` | `list[tuple]` | (label_a, label_b, ContactType) |
| `label_domains` | `dict[int, Domain]` | 라벨 → Domain 객체 |

---

## 4. AnatomyProfile 인터페이스

부위별 해부학 지식을 추상화하는 인터페이스.

```python
from backend.anatomy.base import AnatomyProfile, MaterialProps

class MyProfile(AnatomyProfile):
    def get_material(self, label: int) -> MaterialProps:
        """라벨에 해당하는 재료 물성 반환."""
        ...

    def get_contact_type(self, label_a: int, label_b: int):
        """두 라벨 간 접촉 유형 반환 (None이면 접촉 없음)."""
        ...

    def get_contact_params(self, label_a: int, label_b: int) -> dict:
        """접촉 파라미터 반환 (penalty, gap_tolerance 등)."""
        ...
```

### MaterialProps

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `E` | `float` | 필수 | 영률 [Pa] |
| `nu` | `float` | 필수 | 포아송비 |
| `density` | `float` | `1000.0` | 밀도 [kg/m³] |
| `method` | `Method` | `Method.FEM` | 해석 방법 |

---

## 5. SpineProfile — 척추 특화 프로파일

척추 해석에 필요한 재료, 접촉, 후관절 규칙을 캡슐화합니다.

```python
profile = SpineProfile(
    bone_E=12e9,          # 척추골 영률 [Pa]
    bone_nu=0.3,
    bone_density=1800.0,
    disc_E=4e6,           # 추간판 영률 [Pa]
    disc_nu=0.45,
    disc_density=1060.0,
    ligament_E=10e6,      # 인대 영률 [Pa]
    ligament_nu=0.4,
    ligament_density=1100.0,
    tied_penalty=1e6,     # TIED 접촉 페널티
    facet_penalty=1e5,    # 후관절 접촉 페널티
    facet_friction=0.1,   # 후관절 마찰 계수
)
```

### 재료 규칙

SpineLabel에 따라 자동 분류:

| 라벨 범위 | 분류 | 재료 기본값 |
|-----------|------|------------|
| 100-199 (T1~SACRUM) | 척추골 (뼈) | 12 GPa, ν=0.3 |
| 200-299 (T1T2~L5S1) | 추간판 | 4 MPa, ν=0.45 |
| 300+ (SPINAL_CANAL) | 연조직 (인대) | 10 MPa, ν=0.4 |

### 접촉 규칙

| 쌍 | 접촉 유형 | 설명 |
|----|-----------|------|
| 척추골 ↔ 디스크 | `TIED` | 접착 (초기 상대위치 유지) |
| 척추골 ↔ 척추골 | `PENALTY` | 후관절 접촉 (마찰 포함) |
| 기타 | `None` | 접촉 없음 |

### 후관절 자동 탐지

```python
facet_joints = profile.detect_facet_joints(
    label_volume=label_volume,
    spacing=spacing,
    origin=origin,
    vertebra_labels=[123, 124],   # 인접 척추골 라벨
    gap_tol=5.0,                  # 최대 간격 [mm]
    posterior_fraction=0.4,       # 후방 영역 비율
)

for fj in facet_joints:
    print(f"{fj.superior} ↔ {fj.inferior}: 간격 {fj.gap:.1f}mm")
```

탐지 과정:
1. 척추관(SPINAL_CANAL) 위치로 AP(전후방) 방향 결정
2. 각 척추골에서 후방 영역 복셀 필터링 (percentile 기반)
3. KDTree로 인접 척추골 후방 근접 쌍 탐색
4. `gap_tol` 이내의 쌍을 후관절로 판정

---

## E2E 워크플로우 예시

CT 라벨맵에서 다물체 해석까지의 전체 흐름:

```python
import numpy as np
from backend.fea.framework import init
from backend.preprocessing import assemble
from backend.anatomy import SpineProfile
from backend.segmentation.labels import SpineLabel

init()

# 1. NPZ 생성 (세그멘테이션 출력으로부터)
label_volume = np.zeros((10, 10, 30), dtype=np.int32)
label_volume[:, :, :10] = SpineLabel.L4       # 123
label_volume[:, :, 10:20] = SpineLabel.L4L5   # 222
label_volume[:, :, 20:] = SpineLabel.L5        # 124

np.savez("/tmp/spine.npz",
    label_volume=label_volume,
    spacing=np.array([1.0, 1.0, 1.0]),
    origin=np.array([0.0, 0.0, 0.0]),
)

# 2. 자동 조립
profile = SpineProfile(bone_E=1000.0, disc_E=100.0, tied_penalty=500.0)
result = assemble("/tmp/spine.npz", profile, min_voxels=1)

print(f"물체 수: {len(result.body_map)}")
print(f"접촉 쌍: {len(result.contact_pairs)}")

# 3. 경계조건 설정 (각 물체 독립적으로 풀 수 있어야 함)
dom_l4 = result.label_domains[SpineLabel.L4]
pos_l4 = dom_l4.get_positions()

# L4: z=0 면 고정, z=1 면에 하향 힘
fixed_l4 = dom_l4.select(axis=2, value=pos_l4[:, 2].min())
dom_l4.set_fixed(fixed_l4)

force_l4 = dom_l4.select(axis=2, value=pos_l4[:, 2].min() + 1.0, tol=0.5)
dom_l4.set_force(force_l4, [0.0, 0.0, -10.0])

# 디스크/L5도 각각 고정 BC 설정 (staggered 솔버 요구사항)
dom_disc = result.label_domains[SpineLabel.L4L5]
pos_disc = dom_disc.get_positions()
fixed_disc = dom_disc.select(axis=2, value=pos_disc[:, 2].max())
dom_disc.set_fixed(fixed_disc)

dom_l5 = result.label_domains[SpineLabel.L5]
pos_l5 = dom_l5.get_positions()
fixed_l5 = dom_l5.select(axis=2, value=pos_l5[:, 2].max())
dom_l5.set_fixed(fixed_l5)

# 4. 해석 실행
solve_result = result.scene.solve(
    mode="static",
    max_contact_iters=30,
    contact_tol=1e-2,
)

# 5. 결과 추출
u_l4 = result.scene.get_displacements(dom_l4)
print(f"L4 최대 변위: {np.abs(u_l4).max():.6f}")
```

> **주의**: Staggered 정적 솔버에서는 각 물체가 독립적으로 풀릴 수 있도록
> 반드시 각 물체에 충분한 Dirichlet BC(고정 경계조건)를 설정해야 합니다.

---

## 확장: 새 부위 프로파일 추가

새로운 해부학 부위(예: 무릎)를 추가하려면 `AnatomyProfile`을 구현합니다:

```python
# backend/anatomy/knee.py
from backend.anatomy.base import AnatomyProfile, MaterialProps
from backend.fea.framework import Method, ContactType

class KneeProfile(AnatomyProfile):
    def get_material(self, label: int) -> MaterialProps:
        if label in FEMUR_LABELS:
            return MaterialProps(E=17e9, nu=0.3, density=1850.0)
        elif label in CARTILAGE_LABELS:
            return MaterialProps(E=10e6, nu=0.45, density=1100.0)
        ...

    def get_contact_type(self, label_a, label_b):
        if is_bone(label_a) and is_cartilage(label_b):
            return ContactType.TIED
        ...

    def get_contact_params(self, label_a, label_b):
        return {"penalty": 1e6}
```

사용:
```python
result = assemble("knee_labels.npz", KneeProfile())
```

---

## 소스 파일

| 모듈 | 경로 |
|------|------|
| 인접 쌍 탐색 | `backend/preprocessing/adjacency.py` |
| 복셀→HEX8 변환 | `backend/preprocessing/voxel_to_hex.py` |
| 자동 조립 | `backend/preprocessing/assembly.py` |
| 추상 프로파일 | `backend/anatomy/base.py` |
| 척추 프로파일 | `backend/anatomy/spine.py` |
| 라벨 정의 | `backend/segmentation/labels.py` |
| E2E 테스트 | `backend/anatomy/tests/test_assembly_with_spine.py` |
