/**
 * 후처리기 타입/인터페이스 정의
 *
 * PostProcessor, ScalarMapper, UI 컴포넌트가 공통으로 사용한다.
 */

/** 시각화 모드 — 변위/응력/손상 */
export type PostProcessMode = 'displacement' | 'stress' | 'damage';

/** 벡터 컴포넌트 선택 */
export type VectorComponent = 'magnitude' | 'x' | 'y' | 'z';

/** 표현 타입 — 포인트/표면/혼합 */
export type RepresentationType = 'points' | 'surface' | 'points+surface';

/** 시각화 통계 (컬러바/UI 표시용) */
export interface PostProcessStats {
  maxDisp: number;
  maxStress: number;
  maxDamage: number;
  minDisp: number;
  minStress: number;
  minDamage: number;
  /** 현재 모드 스칼라 범위 */
  currentMin: number;
  currentMax: number;
}

/** 임계값 필터 설정 */
export interface ThresholdConfig {
  enabled: boolean;
  lower: number;
  upper: number;
}

/** 클리핑 평면 설정 */
export interface ClipPlaneConfig {
  enabled: boolean;
  axis: 'x' | 'y' | 'z';
  position: number; // -1 ~ 1 (정규화)
  invert: boolean;
}
