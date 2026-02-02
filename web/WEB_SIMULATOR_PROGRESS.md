# Web Simulator 진행 상황

## 개요

Three.js 기반 웹 시뮬레이터. Taichi GGUI 버전의 드릴 기능 디버깅이 어려워서 웹 버전으로 전환함.
웹 버전은 Playwright로 자동 테스트하면서 스크린샷으로 결과 확인 가능.

## 현재 상태 (2026-02-02)

### ✅ 완료된 기능

1. **STL 로딩**
   - L4, L5 척추 STL 파일 로드
   - 각 척추가 Y축으로 분리 배치됨 (겹침 해결)
   - 삼각형 수: L5 (17,620), L4 (34,500)

2. **복셀(Voxel) 기반 드릴링**
   - 메쉬 → 복셀 변환 (Ray casting 방식)
   - 구 형태로 복셀 제거
   - Marching Cubes로 실시간 메쉬 재생성
   - 해상도: 48 (조절 가능)

3. **UI**
   - Navigate/Drill/Measure 도구 버튼
   - Drill 반경/깊이 슬라이더
   - 모델 목록 (삼각형 수, 복셀 수 표시)
   - Top/Front/Reset View 버튼
   - FPS 표시

4. **성능**
   - 50+ FPS 유지
   - Marching Cubes: 2-3ms

### 🔲 미구현/개선 필요

1. **Measure 도구** - 거리/각도 측정 (버튼만 있음)
2. **해상도 조절** - UI에서 복셀 해상도 변경
3. **NRRD 파일 로드** - 현재 STL만 지원
4. **Undo/Redo** - 드릴링 취소
5. **드릴 깊이** - 현재는 표면만 깎임, 깊이 방향 드릴링 필요

## 파일 구조

```
web/
├── index.html          # HTML + CSS UI
├── src/
│   ├── main.js         # Three.js 메인 코드
│   └── voxel.js        # 복셀 시스템 + Marching Cubes
├── stl/
│   ├── L4.stl          # 척추 L4
│   ├── L5.stl          # 척추 L5
│   └── disc.stl        # 디스크 (미사용)
└── .gitignore          # 테스트 파일 제외
```

## 핵심 코드 설명

### 1. 복셀화 (voxel.js - VoxelGrid.fromMesh)

```javascript
// 메쉬를 복셀 그리드로 변환
// Ray casting 방식: X 방향으로 레이를 쏴서 교차점 개수로 내부/외부 판단
_voxelizeMesh(mesh) {
    // 각 Y-Z 좌표에서 X 방향으로 레이 발사
    // 홀수 번 교차 = 내부, 짝수 번 교차 = 외부
}
```

### 2. 드릴링 (voxel.js - VoxelGrid.drillSphere)

```javascript
// 월드 좌표에서 반경 내 복셀 제거
drillSphere(worldPos, radius) {
    const gridPos = this.worldToGrid(worldPos);
    // 반경 내 모든 복셀을 0으로 설정
}
```

### 3. Marching Cubes (voxel.js - VoxelGrid.toMesh)

```javascript
// 복셀 → 삼각형 메쉬 변환
// 256가지 큐브 패턴에 대한 룩업 테이블 사용
toMesh() {
    // EDGE_TABLE, TRI_TABLE 사용
    // 각 큐브의 8개 코너 값으로 삼각형 생성
}
```

### 4. 메쉬 배치 (main.js - arrangeVertebrae)

```javascript
// L4와 L5를 Y축으로 분리 배치
// L5: 원점 기준
// L4: L5 위에 gap(5mm) 간격으로 배치
```

## 실행 방법

```bash
cd web
python -m http.server 8080
# 브라우저에서 http://localhost:8080
```

## 테스트 방법

```bash
cd web
uv run python test_voxel.py
# 스크린샷이 web/ 폴더에 저장됨
```

## 다음 작업 제안

1. **드릴 깊이 구현**: 현재 표면만 깎이므로, 드릴 방향(normal)으로 깊이만큼 복셀 제거
2. **해상도 높이기**: 48 → 64 또는 80으로 올리면 더 부드러운 표면
3. **Measure 도구 구현**: 두 점 사이 거리, 세 점 각도 측정
4. **Taichi 버전과 통합**: 웹에서 테스트한 로직을 Taichi로 포팅

## 참고

- Taichi GGUI 버전: `spine_sim/app/simulator.py`
- 복셀 드릴링 원본: `spine_sim/core/volume.py`
- 이전 드릴 시도 (삼각형 제거 방식)는 표면만 깎여서 내부가 빈 것처럼 보임 → 복셀 방식으로 해결
