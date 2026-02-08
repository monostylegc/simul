# Smoothed Particle Galerkin (SPG) Method

## 개요

SPG(Smoothed Particle Galerkin)는 극한 변형과 재료 파괴 해석을 위한 순수 무격자(meshfree) 방법이다.
Galerkin 약형식에 변위 스무딩(displacement smoothing)을 도입하여, 직접 절점 적분(Direct Nodal Integration, DNI)의
불안정성을 제거하면서도 2차 미분 계산을 회피한다.

### 기존 방법 대비 장점

| 특성 | FEM | SPH | NOSB-PD | **SPG** |
|------|-----|-----|---------|---------|
| 극한 변형 | 요소 왜곡 문제 | 인장 불안정 | 가능 | **우수** |
| 재료 파괴 | 요소 삭제 | 어려움 | 본드 파괴 | **본드 파괴** |
| 일관성(Consistency) | 높음 | 낮음 | 중간 | **높음** |
| 질량/운동량 보존 | 보존 | 보존 | 보존 | **보존** |
| 임의 Poisson비 | 가능 | 제한 | 가능 | **가능** |
| 안정화 필요 | 불필요 | hourglass | zero-energy | **strain gradient** |

## 수학적 정형화 (Mathematical Formulation)

### 1. 무격자 근사 (Meshfree Approximation)

변위 근사:
```
u^h(X) = Σ_{I=1}^{NP} Ψ_I(X) · ũ_I
```
여기서 `Ψ_I(X)`는 무격자 형상함수, `ũ_I`는 일반화 변위.

### 2. 스무딩된 변위장 (Smoothed Displacement Field)

SPG의 핵심: 변위장에 커널 스무딩 적용
```
ū(X) = ∫_Ω Ψ̃(Y; X) · û(Y) dΩ
```

이산형:
```
ū_I = Σ_{J=1}^{NP} Ψ̃_J(X_I) · û_J
```

스무딩된 형상함수 (smoothed meshfree shape function):
```
φ_K(X_I) := Σ_{J=1}^{NP} Ψ_K(X_J) · Ψ̃_J(X_I)
```

### 3. 형상함수 특성 (Shape Function Properties)

**다항식 재현 조건** (Polynomial Reproduction):
```
Σ_{J=1}^{NP} φ_J(X_I) = 1              (단위 분배, partition of unity)
Σ_{J=1}^{NP} φ_J(X_I) · X_J = X_I      (선형 재현)
```

**경계 Kronecker-delta 특성**:
```
φ_K(X_I) = δ_{KI}    (X_K ∈ Γ_g 경계)
```

### 4. 커널 함수 (Kernel/Weight Function)

**Cubic B-spline 커널** (권장):
```
W(r, h) = C_d · { 1 - 6r² + 6r³       (0 ≤ r ≤ 0.5)
                  { 2(1 - r)³            (0.5 < r ≤ 1)
                  { 0                    (r > 1)

여기서 r = |X - X_I| / h, h = 지지 반경 (support radius)
C_d = 정규화 상수 (2D: 10/(7πh²), 3D: 1/(πh³))
```

**지지 영역** (Support Domain):
- 일반적으로 h = (1.5 ~ 2.0) × 입자 간격
- 충분한 이웃 입자 확보가 중요 (2D: ~20개, 3D: ~40개)

### 5. 변형률 근사 (Strain Approximation)

```
ε(u^h) = Σ_{I=1}^{NP} B_I · ũ_I
```

여기서 변형률-변위 행렬 B:
```
       ⎡ Ψ_{I,X}    0     ⎤
B_I =  ⎢   0      Ψ_{I,Y} ⎥   (2D)
       ⎣ Ψ_{I,Y}  Ψ_{I,X} ⎦

       ⎡ Ψ_{I,X}    0        0     ⎤
       ⎢   0       Ψ_{I,Y}   0     ⎥
B_I =  ⎢   0        0      Ψ_{I,Z} ⎥   (3D)
       ⎢ Ψ_{I,Y}  Ψ_{I,X}   0     ⎥
       ⎢   0       Ψ_{I,Z}  Ψ_{I,Y}⎥
       ⎣ Ψ_{I,Z}   0       Ψ_{I,X} ⎦
```

### 6. Galerkin 약형식 (Weak Form)

안정화 포함 쌍선형 형식:
```
a_h(û, δû) = a_h^{stan} + a_h^{stab}
```

**표준항** (Standard term):
직접 절점 적분(DNI)에 의한 강성행렬:
```
K_{IJ} = Σ_{K=1}^{NP} B_I^T(X_K) · C · B_J(X_K) · V_K^0
```

**안정화항** (Stabilization term):
변위 스무딩에서 유도된 변형률 구배 안정화:
```
a_h^{stab} = η · Σ_{K=1}^{NP} (∇ε_smooth - ∇ε_standard)^T · C · (∇ε_smooth - ∇ε_standard) · V_K^0
```

여기서 `η`는 안정화 매개변수 (0.05 ~ 0.5 권장)

### 7. 외력 벡터 (External Force Vector)

```
f_I^{ext} = Σ_{K=1}^{NP} Ψ_I(X_K) · f(X_K) · V_K^0  +  Σ_{K=1}^{NB} Ψ_I(X_K) · t(X_K) · L_K
```

여기서 `V_K^0`은 초기 입자 부피, `L_K`는 경계 세그먼트 길이.

### 8. 좌표 변환 (Transformation to Smoothed Coordinates)

행렬 변환: `Ū = A · Ũ`
```
A_{IJ} = φ_J(X_I)   (변환 행렬)
```

최종 시스템:
```
A^{-T} · K · A^{-1} · Ū = A^{-T} · f^{ext}
```

### 9. 비선형 (Updated Lagrangian) 정형화

소성 해석을 위한 반복방정식:
```
δŨ^T · K_v^{n+1} · (ΔŨ)_{v+1}^{n+1} = δŨ^T · R_v^{n+1}
```

내부력 계산:
```
f_I^{int} = Σ_{N=1}^{NP} B_I^T(X_N) · G^T(X_N) · S(F(X_N)) · J_0(X_N) · V_N^0
```

여기서 `J_0 = det(F)`는 야코비안 행렬식, `G`는 역변형구배 성분.

### 10. 명시적 동역학 (Explicit Dynamics)

**질량행렬** (일관 형식):
```
M_{IJ} = Σ_{N=1}^{NP} ρ_0 · Ψ_I(X_N) · Ψ_J(X_N) · V_N^0
```

**집중 질량행렬** (lumped, 실용적):
```
M_{II} = ρ_0 · V_I^0
```

**운동방정식**:
```
M · ü = f^{ext} - f^{int}
```

### 11. 적응 라그랑지안 커널 업데이트

재료 형상함수 미분의 연쇄법칙:
```
Ψ_{I,i}(X) = ∂Ψ_I/∂X_j · F_{ji}^{-1}
```

### 12. 본드 기반 파괴 (Bond-Based Failure)

SPG에서 각 입자는 영향 영역(influence domain) 내 다른 입자와 본드로 연결된다.
본드 파괴 기준:

**유효 소성 변형률 기반**:
```
if ε_p^{eff}(X_I, X_J) > ε_p^{crit}:
    bond(I, J) = broken
```

여기서:
```
ε_p^{eff} = 0.5 · (ε_p(X_I) + ε_p(X_J))   (본드 양 끝의 평균 소성 변형률)
```

**본드 신장 기반** (stretch-based):
```
s_{IJ} = (|η_{IJ}| - |ξ_{IJ}|) / |ξ_{IJ}|

if s_{IJ} > s_crit:
    bond(I, J) = broken
```

본드가 파괴되면:
- 해당 이웃을 형상함수 계산에서 제외
- 질량, 운동량 보존 유지
- 파편화(fragmentation) 자연스럽게 발생

## 알고리즘 (Algorithm)

### 초기화
```
1. 입자 위치 X, 부피 V, 밀도 ρ 설정
2. 이웃 탐색 (support domain h 기반)
3. 본드 연결 구축
4. 형상함수 Ψ 및 미분 ∇Ψ 계산
5. 스무딩 행렬 A 구축
6. 안정 시간 간격 Δt 계산
```

### 시간 적분 루프 (Velocity Verlet)
```
for each time step n:
    1. 위치 업데이트: x^{n+1/2} = x^n + v^n · Δt + 0.5 · a^n · Δt²
    2. 변형 구배 F 계산
    3. 응력 σ (또는 P) 계산 (재료 모델)
    4. B 행렬 계산 (형상함수 미분)
    5. 내부력 계산: f^{int} = Σ B^T · σ · V
    6. 안정화력 추가
    7. 본드 파괴 검사
    8. 가속도: a = (f^{ext} - f^{int}) / m
    9. 속도 업데이트: v^{n+1} = v^n + 0.5 · (a^n + a^{n+1}) · Δt
```

## 구현 단순화 (Practical Implementation)

본 프로젝트에서는 아래와 같이 단순화하여 구현한다:

1. **형상함수**: RKPM(Reproducing Kernel Particle Method) 기반 1차 일관성
2. **적분**: 직접 절점 적분(DNI) - 입자 위치에서 직접 적분
3. **안정화**: 변형률 스무딩 기반 페널티 안정화
4. **시간 적분**: 명시적 Velocity Verlet
5. **파괴**: 본드 기반 유효 소성 변형률/본드 신장 기준

## 참고 문헌 (References)

1. Wu, C.T., Guo, Y., Askari, E. (2013). "Smoothed particle Galerkin method with a momentum-consistent smoothing algorithm for coupled thermal-structural analysis." *LS-DYNA Conference*.
   - [Google Patent: US20150112653A1](https://patents.google.com/patent/US20150112653A1/en)

2. Wu, C.T., Wu, Y., Hu, W. (2018). "Parametric and convergence studies of the smoothed particle Galerkin (SPG) method in semi-brittle and ductile material failure analyses." *15th International LS-DYNA Conference*.
   - [Paper](https://lsdyna.ansys.com/wp-content/uploads/2022/11/parametric-and-convergence-studies-of-the-smoothed-particle-galerkin-spg-method-in-semi-brittle-and-ductile-material-failure-analyses.pdf)

3. Wu, C.T., Wu, Y., Crawford, J.E., Magallanes, J.M. (2017). "Three-dimensional concrete impact and penetration simulations using the smoothed particle Galerkin method." *Int. J. Impact Engineering*, 106, 1-17.
   - [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0734743X16308430)

4. Wu, C.T., Park, C.K., Chen, J.S. (2011). "A displacement smoothing induced strain gradient stabilization for the meshfree Galerkin nodal integration method." *Comput. Mech.*, 56, 19-37.
   - [Springer](https://link.springer.com/article/10.1007/s00466-015-1153-2)

5. Huang, T.H., Wu, C.T. et al. (2019). "The momentum-consistent smoothed particle Galerkin (MC-SPG) method for simulating the extreme thread forming in the flow drill screw-driving process." *Comput. Part. Mech.*, 7, 177-191.
   - [Springer](https://link.springer.com/article/10.1007/s40571-019-00235-2)

6. Jimenez, S., Wu, C.T. (2024). "Numerical study of smoothed particle Galerkin method in orthogonal cutting simulations." *Comput. Part. Mech.*
   - [Springer](https://link.springer.com/article/10.1007/s40571-024-00843-7)

7. Chen, J.S., Wu, C.T., Yoon, S., You, Y. (2001). "A stabilized conforming nodal integration for Galerkin mesh-free methods." *Int. J. Numer. Methods Eng.*, 50(2), 435-466.
   - [Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1002/1097-0207(20010120)50:2%3C435::AID-NME32%3E3.0.CO;2-A)
