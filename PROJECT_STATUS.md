# 프로젝트 진행 상황

최종 업데이트: 2026-02-03

## 오늘 작업 내역 (2026-02-03)

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

### 재부팅 후 수동 삭제 필요
- `spine_sim/` 폴더 (잠김)
- `web/` 폴더 (잠김)

## 현재 구현 상태

### ✅ 완료된 모듈

#### 웹 시뮬레이터 (`src/simulator/`)
- STL 로딩 (L4, L5 척추)
- NRRD 로딩 (3D Slicer 호환)
- 복셀 기반 드릴링 + Marching Cubes
- 해상도 조절 UI (32~192)
- **Undo/Redo** (Ctrl+Z/Y, 최대 30단계)
- **단면 뷰 (Slice View)** - X/Y/Z 축 단면 + 위치 조절
- 50+ FPS 성능

#### FEA (`src/fea/`)
- **FEM**: TET4, TRI3, HEX8, QUAD4 요소
- **Peridynamics**: NOSB-PD, 준정적 솔버
- **STL 구조해석**: STL → 복셀화 → Peridynamics 파이프라인
- 테스트: 46개 통과

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
- 드릴 깊이 (현재 표면만 깎임)
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
    ├── fem/                   # FEM 모듈
    ├── peridynamics/          # NOSB-PD 모듈
    └── visualization/         # FEA 결과 웹 시각화
        ├── index.html        # FEA Viewer UI
        ├── src/main.js       # Three.js 시각화
        └── convert_npz.py    # NPZ→JSON 변환
```

## 상세 진행 문서

- `docs/SIMULATOR_PROGRESS.md` - 웹 시뮬레이터 진행 상황
- `docs/FEM_PROGRESS.md` - FEM 구현 상세
- `docs/NOSB_PD_PROGRESS.md` - NOSB-PD 구현 상세
- `rough_plan.md` - 전체 프로젝트 계획

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
