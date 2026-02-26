/**
 * 스칼라 매퍼 — Three.js 없는 순수 함수 집합
 *
 * PostProcessor 클래스의 private 데이터 처리 로직을 순수 함수로 추출.
 * 테스트 가능하고 Three.js 의존 없이 재사용 가능하다.
 *
 * 포함:
 *  - extractComponent     : 벡터 배열 → 스칼라 (컴포넌트 선택)
 *  - getFEMNodeScalars    : FEM 영역 노드별 스칼라
 *  - getParticleScalars   : PD/SPG 영역 입자별 스칼라
 *  - getAllScalars         : 전체 영역 스칼라 통합
 *  - computeStats         : 통계 계산 (min/max)
 *  - applyPointFilters    : 임계값 + 클리핑 평면 필터 (포인트용)
 *  - isTriangleVisible    : 임계값 + 클리핑 평면 필터 (삼각형용)
 */

import * as THREE from 'three';
import type {
  PostProcessMode,
  VectorComponent,
  PostProcessStats,
  ThresholdConfig,
  ClipPlaneConfig,
} from './PostProcessorTypes';
import type { AnalysisResultData, FEMRegionResult, ParticleRegionResult } from '$lib/ws/types';

// ── 컴포넌트 추출 ──

/**
 * 벡터 배열에서 지정한 컴포넌트를 추출한다.
 *
 * @param vectors 벡터 배열 (n × 2 또는 n × 3)
 * @param component 추출할 컴포넌트
 * @returns 스칼라 배열
 */
export function extractComponent(vectors: number[][], component: VectorComponent): number[] {
  switch (component) {
    case 'x':
      return vectors.map(v => v[0] || 0);
    case 'y':
      return vectors.map(v => v[1] || 0);
    case 'z':
      return vectors.map(v => v[2] || 0);
    case 'magnitude':
    default:
      return vectors.map(v =>
        Math.sqrt((v[0] || 0) ** 2 + (v[1] || 0) ** 2 + (v[2] || 0) ** 2),
      );
  }
}

// ── 영역별 스칼라 추출 ──

/**
 * FEM 영역의 노드별 스칼라 값 (모드 + 컴포넌트 적용)
 */
export function getFEMNodeScalars(
  region: FEMRegionResult,
  mode: PostProcessMode,
  component: VectorComponent,
): number[] {
  switch (mode) {
    case 'displacement':
      return extractComponent(region.displacements, component);
    case 'stress':
      return region.stress || [];
    case 'damage':
      return new Array(region.nodes.length).fill(0);
    default:
      return [];
  }
}

/**
 * PD/SPG 영역의 입자별 스칼라 값 (모드 + 컴포넌트 적용)
 */
export function getParticleScalars(
  region: ParticleRegionResult,
  mode: PostProcessMode,
  component: VectorComponent,
): number[] {
  switch (mode) {
    case 'displacement':
      return extractComponent(region.displacements || [], component);
    case 'stress':
      return region.stress || [];
    case 'damage':
      return region.damage || [];
    default:
      return [];
  }
}

/**
 * 레거시 플랫 결과 데이터의 스칼라 배열 반환
 */
export function getLegacyScalars(
  data: AnalysisResultData,
  mode: PostProcessMode,
  component: VectorComponent,
): number[] {
  switch (mode) {
    case 'displacement':
      return extractComponent(data.displacements ?? [], component);
    case 'stress': {
      const stress = data.stress;
      if (!stress || stress.length === 0) return [];
      if (typeof stress[0] === 'number') return stress as number[];
      return extractComponent(stress as number[][], component);
    }
    case 'damage':
      return data.damage || [];
    default:
      return [];
  }
}

/**
 * 모든 영역의 스칼라 값을 통합 반환 (범위 계산용)
 */
export function getAllScalars(
  data: AnalysisResultData,
  mode: PostProcessMode,
  component: VectorComponent,
): number[] {
  const all: number[] = [];

  if (data.fem_regions) {
    for (const r of data.fem_regions) {
      all.push(...getFEMNodeScalars(r, mode, component));
    }
  }

  if (data.particle_regions) {
    for (const r of data.particle_regions) {
      all.push(...getParticleScalars(r, mode, component));
    }
  }

  // 레거시 폴백 (fem_regions/particle_regions 없을 때)
  if (!data.fem_regions && !data.particle_regions) {
    all.push(...getLegacyScalars(data, mode, component));
  }

  return all;
}

// ── 통계 계산 ──

/**
 * 결과 데이터의 통계를 계산한다.
 *
 * @returns PostProcessStats 객체
 */
export function computeStats(
  data: AnalysisResultData,
  mode: PostProcessMode,
  component: VectorComponent,
): PostProcessStats {
  const stats: PostProcessStats = {
    maxDisp: 0, minDisp: Infinity,
    maxStress: 0, minStress: 0,
    maxDamage: 0, minDamage: 0,
    currentMin: 0, currentMax: 0,
  };

  // 변위 통계 — 모든 영역 통합
  const updateDispStats = (disps: number[][]) => {
    for (const d of disps) {
      const mag = Math.sqrt((d[0] || 0) ** 2 + (d[1] || 0) ** 2 + (d[2] || 0) ** 2);
      if (mag > stats.maxDisp) stats.maxDisp = mag;
      if (mag < stats.minDisp) stats.minDisp = mag;
    }
  };

  if (data.fem_regions) {
    for (const r of data.fem_regions) updateDispStats(r.displacements);
  }
  if (data.particle_regions) {
    for (const r of data.particle_regions) updateDispStats(r.displacements || []);
  }
  // 레거시 폴백
  if (!data.fem_regions && !data.particle_regions && data.displacements?.length > 0) {
    updateDispStats(data.displacements);
  }
  if (stats.minDisp === Infinity) stats.minDisp = 0;

  // 현재 모드 스칼라 범위
  const allScalars = getAllScalars(data, mode, component);
  if (allScalars.length > 0) {
    stats.currentMin = Math.min(...allScalars);
    stats.currentMax = Math.max(...allScalars);

    if (mode === 'stress') {
      stats.maxStress = stats.currentMax;
      stats.minStress = stats.currentMin;
    }
    if (mode === 'damage') {
      stats.maxDamage = stats.currentMax;
      stats.minDamage = stats.currentMin;
    }
  }

  return stats;
}

// ── 필터 ──

/**
 * 임계값 + 클리핑 평면 필터 적용 (포인트 클라우드용)
 *
 * @param positions 입자 좌표 배열
 * @param scalars   입자별 스칼라 값
 * @param threshold 임계값 필터 설정
 * @param clipConfig 클리핑 평면 설정
 * @param bbox      도메인 바운딩 박스 (클리핑 정규화용)
 * @returns 필터 통과한 positions + scalars 쌍
 */
export function applyPointFilters(
  positions: number[][],
  scalars: number[],
  threshold: ThresholdConfig,
  clipConfig: ClipPlaneConfig,
  bbox: THREE.Box3,
): { positions: number[][]; scalars: number[] } {
  const n = Math.min(positions.length, scalars.length);
  const filteredPos: number[][] = [];
  const filteredScl: number[] = [];

  for (let i = 0; i < n; i++) {
    const val = scalars[i];

    // 임계값 필터
    if (threshold.enabled) {
      if (val < threshold.lower || val > threshold.upper) continue;
    }

    // 클리핑 평면 필터
    if (clipConfig.enabled) {
      const pos = positions[i];
      const axisIdx = clipConfig.axis === 'x' ? 0 : clipConfig.axis === 'y' ? 1 : 2;
      const bboxMin = bbox.min.getComponent(axisIdx);
      const bboxMax = bbox.max.getComponent(axisIdx);
      const range = bboxMax - bboxMin || 1;
      const clipPos = bboxMin + (clipConfig.position + 1) / 2 * range;
      const pass = clipConfig.invert ? pos[axisIdx] < clipPos : pos[axisIdx] > clipPos;
      if (!pass) continue;
    }

    filteredPos.push(positions[i]);
    filteredScl.push(val);
  }

  return { positions: filteredPos, scalars: filteredScl };
}

/**
 * 삼각형(FEM 표면)에 임계값 + 클리핑 평면 필터를 적용한다.
 *
 * @param tri       삼각형 노드 인덱스 [ni0, ni1, ni2]
 * @param deformed  변형된 노드 좌표 배열
 * @param nodeScalars 노드별 스칼라 값
 * @param threshold 임계값 설정
 * @param clipConfig 클리핑 평면 설정
 * @param bbox      바운딩 박스
 * @returns true이면 삼각형 표시, false이면 제거
 */
export function isTriangleVisible(
  tri: number[],
  deformed: number[][],
  nodeScalars: number[],
  threshold: ThresholdConfig,
  clipConfig: ClipPlaneConfig,
  bbox: THREE.Box3,
): boolean {
  const [ni0, ni1, ni2] = tri;
  const p0 = deformed[ni0];
  const p1 = deformed[ni1];
  const p2 = deformed[ni2];

  if (!p0 || !p1 || !p2) return false;

  // 임계값 필터 (세 노드 평균)
  if (threshold.enabled) {
    const avg = (nodeScalars[ni0] + nodeScalars[ni1] + nodeScalars[ni2]) / 3;
    if (avg < threshold.lower || avg > threshold.upper) return false;
  }

  // 클리핑 평면 필터 (삼각형 중심)
  if (clipConfig.enabled) {
    const axisIdx = clipConfig.axis === 'x' ? 0 : clipConfig.axis === 'y' ? 1 : 2;
    const center = [(p0[0] + p1[0] + p2[0]) / 3, (p0[1] + p1[1] + p2[1]) / 3, (p0[2] + p1[2] + p2[2]) / 3];
    const bboxMin = bbox.min.getComponent(axisIdx);
    const bboxMax = bbox.max.getComponent(axisIdx);
    const range = bboxMax - bboxMin || 1;
    const clipPos = bboxMin + (clipConfig.position + 1) / 2 * range;
    const pass = clipConfig.invert ? center[axisIdx] < clipPos : center[axisIdx] > clipPos;
    if (!pass) return false;
  }

  return true;
}
