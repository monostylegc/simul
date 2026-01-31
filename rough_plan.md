## Spine Surgery Planner - Claude Code 작업 브리핑

### 프로젝트 개요
**UBE/Biportal 내시경 척추 수술 계획 및 시뮬레이션 도구**

목적: 수술 전 계획 수립 - 나사/케이지 배치, 내시경 시야 시뮬레이션, 진입 경로 검증

---

### 기술 스택 (확정)

```
Python + Taichi (단일 스택, Windows 배포 필수)
├── MONAI          → CT 자동 세그멘테이션
├── FEMcy (포크)    → FEM 해석 (Hyperelastic 추가 필요)
├── NOSB-PD (신규)  → Peridynamics 파괴 해석
└── Taichi GGUI    → 렌더링 + UI
```

**기각된 기술들:**
- Julia: 체감 성능 향상 없음
- JAX/FEniCSx: Windows 미지원
- FEBio: 메쉬 품질에 과민, CT 메쉬에 부적합
- MPM: 파괴 예측 정확도 부족

---

### 핵심 기능 4가지

| 기능 | 설명 | 우선순위 |
|------|------|----------|
| **임플란트 배치** | 나사 각도/길이, 케이지 위치/사이즈 | Phase 2 |
| **내시경 시뮬레이션** | 포탈 위치, 시야/사각지대, 충돌 감지 | Phase 3 (핵심 차별점) |
| **가상 수술** | 뼈 제거, 복셀 편집 | Phase 3 |
| **구조 해석** | FEM + NOSB-PD (수술 후 안정성) | Phase 4 |

---

### 워크플로우

```
CT DICOM
   ↓
MONAI 세그멘테이션 (뼈/디스크/신경 분리)
   ↓
3D 모델
   ↓
수술 계획
├── 나사/케이지 배치
├── 내시경 시뮬레이션
│   ├── 포탈 위치 설정
│   ├── 시야 범위 확인
│   ├── 사각지대 표시
│   └── 진입 시 충돌 지점
└── 가상 수술 (뼈 제거)
   ↓
구조 해석 (오프라인)
   ↓
리포트
```

---

### 모듈 구조

```
spine_sim/
├── io/
│   └── dicom/
├── ai/
│   └── segmentation/        # MONAI
├── planning/
│   ├── implants/
│   │   ├── screw.py         # Pedicle screw
│   │   └── cage.py
│   └── collision/
├── endoscope/
│   ├── camera.py            # 내시경 뷰 렌더링
│   ├── portal.py            # 포탈 위치
│   ├── visibility.py        # 시야/사각지대
│   └── trajectory.py        # 진입 경로 충돌
├── surgery/
│   └── tools/
├── analysis/
│   ├── fem/                 # FEMcy 기반
│   └── peridynamics/        # NOSB-PD
├── render/
│   ├── volume/
│   └── endoscope_view/
└── app/
    └── main.py
```

---

### 개발 Phase

| Phase | 내용 |
|-------|------|
| **1** | CT → MONAI → 3D 뷰어 파이프라인 |
| **2** | 임플란트 배치 (나사, 케이지) |
| **3** | 내시경 시뮬레이션 + 가상 수술 |
| **4** | FEM + NOSB-PD 구조 해석 |
| **5** | 통합, Windows 배포 |

---

### FEMcy 수정 작업

**Repo:** https://github.com/mo-hanxuan/FEMcy (MIT)

**현재 지원:** Linear elasticity, Large deformation, Tet elements, Newton solver

**추가 필요:**
```python
# Hyperelastic (Neo-Hookean) - Taichi autodiff 활용
@ti.func
def neo_hookean_energy(F, mu, lam):
    J = F.determinant()
    C = F.transpose() @ F
    I1 = C.trace()
    return 0.5*mu*(I1-3) - mu*ti.log(J) + 0.5*lam*ti.log(J)**2
```

---

### 첫 작업 선택

**A.** FEMcy 포크 → Hyperelastic 추가

**B.** CT → MONAI → Taichi 3D 뷰어 프로토타입

---

### 제약 조건

- Windows 배포 필수 (병원 환경)
- CT 메쉬 품질 불규칙 → 메쉬 민감도 낮은 방법 필요
- 내시경 시뮬레이션이 핵심 차별점