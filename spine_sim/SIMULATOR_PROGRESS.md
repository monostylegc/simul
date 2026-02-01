# 수술 시뮬레이터 구현 진행 상황

## 개요

척추 수술 시뮬레이션을 위한 Taichi 기반 3D 애플리케이션.

## 완료된 작업

### 1. 핵심 모듈

| 파일 | 설명 | 상태 |
|------|------|------|
| `core/mesh.py` | 삼각형 메쉬, STL/OBJ 로딩 | ✅ 완료 |
| `core/transform.py` | 3D 변환 (위치, 회전) | ✅ 완료 |
| `core/volume.py` | 복셀 볼륨, 드릴링 기능 | ✅ 완료 |
| `core/collision.py` | Ray casting 충돌 감지 | ✅ 완료 |
| `endoscope/camera.py` | 내시경 카메라 | ✅ 완료 |
| `endoscope/instrument.py` | 내시경 도구 | ✅ 완료 |
| `app/simulator.py` | 메인 시뮬레이터 GUI | ✅ 완료 |

### 2. 구현된 기능

#### 3D 모델 로딩
```python
from spine_sim.core.mesh import TriangleMesh

# STL 파일 로딩
mesh = TriangleMesh.load_stl("vertebra.stl")

# OBJ 파일 로딩
mesh = TriangleMesh.load_obj("model.obj")

# 기본 도형 생성
box = TriangleMesh.create_box(size=(30, 25, 20))
cylinder = TriangleMesh.create_cylinder(radius=5, height=20)
```

#### 복셀 편집 (드릴링)
```python
from spine_sim.core.volume import VoxelVolume

volume = VoxelVolume(resolution=(64, 64, 64), spacing=0.5)
volume.fill_sphere(cx, cy, cz, radius=10, value=1.0, mat_type=1)  # 뼈 채우기
volume.drill(tip_x, tip_y, tip_z, dir_x, dir_y, dir_z, radius=2, depth=10)  # 드릴링
```

#### 충돌 감지
```python
from spine_sim.core.collision import CollisionDetector

detector = CollisionDetector(max_triangles=100000)
detector.load_mesh(vertices, faces)

hit = detector.ray_cast(origin, direction, max_distance=100)
if hit.hit:
    print(f"Collision at {hit.position}, distance {hit.distance}")
```

#### 내시경 시뮬레이션
```python
from spine_sim.endoscope import Endoscope

endoscope = Endoscope(diameter=7.0, length=150.0)
endoscope.set_position([50, 30, 50])
endoscope.set_direction([-1, 0, -1])

# 카메라 뷰 파라미터
cam_params = endoscope.get_camera_params()

# 충돌 체크
hits = endoscope.check_collision(detector)
```

### 3. GUI 기능

| 기능 | 조작 | 상태 |
|------|------|------|
| 카메라 회전 | 마우스 드래그 | ✅ |
| 줌 인/아웃 | +/- 키 | ✅ |
| 내시경 전진/후진 | W/S | ✅ |
| 내시경 회전 | A/D/Q/E | ✅ |
| 객체 추가 | GUI 버튼 | ✅ |
| 도구 모드 전환 | GUI 버튼 | ✅ |

## 사용 방법

```python
import taichi as ti
ti.init(arch=ti.gpu)

from spine_sim.app.simulator import SpineSimulator

sim = SpineSimulator(width=1400, height=900)

# 척추 모델 로딩
sim.load_model("L5.stl", name="L5", color=(0.9, 0.85, 0.75))
sim.set_object_position("L5", (0, 0, 0))

# 또는 샘플 척추 추가
sim.add_sample_vertebra("L4", position=(0, 30, 0))

# 시뮬레이터 실행
sim.run()
```

## 실행

```bash
uv run python -m spine_sim.app.simulator
```

## 아키텍처

```
spine_sim/
├── core/
│   ├── mesh.py          # 메쉬 로딩 및 처리
│   ├── transform.py     # 3D 변환
│   ├── volume.py        # 복셀 볼륨
│   └── collision.py     # 충돌 감지
├── endoscope/
│   ├── camera.py        # 내시경 카메라
│   └── instrument.py    # 내시경 도구
├── app/
│   └── simulator.py     # 메인 GUI
└── analysis/
    ├── fem/             # FEM 해석 (완료)
    └── peridynamics/    # NOSB-PD (완료)
```

## 남은 과제

### 1. 내시경 뷰 렌더링 (우선순위: 높음)
- [x] 뷰 모드 전환 (V 키) ✅ 완료
- [x] 내시경 시점 카메라 ✅ 완료
- [x] 내시경 조명 효과 (팁에서 발광) ✅ 완료
- [ ] 진정한 PIP (동시 렌더링) - Taichi GGUI 제한으로 추후

### 2. 3D Slicer 연동 (우선순위: 높음)
- [ ] NRRD/NIFTI 볼륨 로딩
- [ ] 세그멘테이션 마스크 지원
- [ ] 메쉬 내보내기

### 3. 향상된 드릴링 (우선순위: 중간)
- [x] 실시간 복셀 → 메쉬 변환 (Marching Cubes) ✅ 완료
- [ ] 햅틱 피드백 시뮬레이션
- [ ] 드릴 소리/진동 효과

### 4. 임플란트 배치 (우선순위: 중간)
- [ ] Pedicle screw 모델
- [ ] Cage 모델
- [ ] 배치 가이드라인

### 5. UI 개선 (우선순위: 낮음)
- [ ] 더 나은 객체 선택
- [ ] 변환 Gizmo
- [ ] 측정 도구

---

## 최근 업데이트 (2024-01)

### GUI 체계화

GUI를 별도 모듈로 분리하여 구조화:

```
spine_sim/app/gui/
├── __init__.py      # 모듈 익스포트
├── state.py         # 상태 관리 (GUIState, ToolMode, CameraState 등)
├── panels.py        # 패널 컴포넌트 (ToolPanel, DrillPanel 등)
└── manager.py       # GUI 매니저 (입력 처리, 렌더링 조율)
```

**구성 요소:**
- `GUIState`: 전체 UI 상태 (도구 모드, 카메라, 드릴 설정 등)
- `Panel`: 패널 베이스 클래스
  - `ToolPanel`: 도구 선택
  - `EndoscopePanel`: 내시경 정보
  - `DrillPanel`: 드릴링 설정
  - `ObjectPanel`: 씬 객체 목록
  - `HelpPanel`: 도움말
  - `StatsPanel`: 통계 (디버그)
  - `SelectedObjectPanel`: 선택된 객체 상세
- `GUIManager`: 패널 관리, 입력 처리, 콜백 시스템

**장점:**
- 패널별 독립적 개발/테스트 가능
- 콜백 기반으로 시뮬레이터와 느슨한 결합
- 새 패널 추가가 쉬움

---

### 내시경 뷰 렌더링 구현

내시경 시점에서 씬을 볼 수 있는 기능 추가:

**새 파일:**
- `app/gui/endoscope_view.py`: 내시경 뷰 렌더링 모듈

**뷰 모드:**
- `MAIN_ONLY`: 메인 카메라 뷰 (기본)
- `ENDOSCOPE_ONLY`: 내시경 시점 뷰
- `PIP_BOTTOM_RIGHT`: 메인 + 우하단 PIP (향후)
- `SPLIT_HORIZONTAL`: 좌우 분할 (향후)

**조작:**
- `V` 키: 뷰 모드 순환
- 내시경 뷰에서는 내시경 팁에서 조명 발광

**구조:**
```python
class DualViewRenderer:
    """이중 뷰 렌더러"""
    endoscope_view: EndoscopeViewRenderer

    def toggle_view(self)           # 뷰 전환
    def setup_camera(...)           # 뷰 모드에 따라 카메라 설정
    def setup_lighting(...)         # 뷰 모드에 따라 조명 설정
```

---

### Marching Cubes 드릴링 구현

복셀 볼륨에서 실시간으로 표면 메쉬를 추출하는 Marching Cubes 알고리즘 구현.

**새 파일:**
- `core/marching_cubes.py`: Taichi 기반 Marching Cubes 등치면 추출
- `core/tests/test_marching_cubes.py`: 7개 테스트

**기능:**
- 복셀 볼륨에서 등치면(isosurface) 메쉬 추출
- 드릴링 후 실시간 메쉬 업데이트
- 내시경 팁 위치에서 Space 키로 드릴링

**사용법:**
```python
# 시뮬레이터에서
sim.init_drilling_volume(resolution=(64, 64, 64), center=(0, 15, 0), size=80.0)
# Drill 모드에서 Space 키로 드릴링

# 직접 사용
from spine_sim.core.volume import VoxelVolume
from spine_sim.core.marching_cubes import MarchingCubes

volume = VoxelVolume(resolution=(32, 32, 32), spacing=1.0)
volume.fill_sphere(0, 0, 0, 10, 1.0, 1)

mc = MarchingCubes()
vertices, normals, faces = mc.extract(volume, isovalue=0.5)
```
