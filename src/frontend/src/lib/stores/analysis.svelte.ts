/**
 * 해석 상태 관리 (Svelte 5 runes).
 *
 * 경계조건, 재료 할당, 해석 결과, 진행률,
 * ParaView 스타일 후처리 설정 등.
 */

import type { PostProcessMode, VectorComponent, RepresentationType } from '$lib/analysis/PostProcessor';
import type { PostProcessor } from '$lib/analysis/PostProcessor';
import type { PreProcessor } from '$lib/analysis/PreProcessor';
import type { ColormapName } from '$lib/analysis/colormap';

class AnalysisState {
  /** PreProcessor 인스턴스 */
  preProcessor = $state<PreProcessor | null>(null);

  /** PostProcessor 인스턴스 */
  postProcessor = $state<PostProcessor | null>(null);

  /** 기본 해석 방법 (전체 모델 기본값) */
  method = $state<'fem' | 'pd' | 'spg'>('fem');

  /** 모델별 솔버 할당 (meshName → method) */
  solverAssignments = $state<Record<string, 'fem' | 'pd' | 'spg'>>({});

  /** 경계조건 수 */
  bcCount = $state(0);

  /** 재료 할당 수 */
  materialCount = $state(0);

  /** 해석 진행 상태 */
  isRunning = $state(false);

  /** 진행률 (0~1) */
  progress = $state(0);

  /** 진행 메시지 */
  progressMessage = $state('');

  /** 결과 있음 여부 */
  hasResult = $state(false);

  // ── ParaView 스타일 후처리 설정 ──

  /** 시각화 모드 */
  postMode = $state<PostProcessMode>('displacement');

  /** 벡터 컴포넌트 (Magnitude, X, Y, Z) */
  component = $state<VectorComponent>('magnitude');

  /** 컬러맵 */
  colormap = $state<ColormapName>('jet');

  /** 변위 스케일 (Warp by Vector) */
  dispScale = $state(10.0);

  /** 입자 크기 */
  particleSize = $state(3.0);

  /** 불투명도 */
  opacity = $state(1.0);

  /** 표현 타입 */
  representation = $state<RepresentationType>('points');

  /** 커스텀 범위 사용 여부 */
  useCustomRange = $state(false);

  /** 커스텀 범위 min */
  rangeMin = $state(0);

  /** 커스텀 범위 max */
  rangeMax = $state(1);

  /** 임계값 필터 ON/OFF */
  thresholdEnabled = $state(false);

  /** 임계값 하한 */
  thresholdLower = $state(0);

  /** 임계값 상한 */
  thresholdUpper = $state(1);

  /** 클리핑 평면 ON/OFF */
  clipEnabled = $state(false);

  /** 클리핑 축 */
  clipAxis = $state<'x' | 'y' | 'z'>('x');

  /** 클리핑 위치 (-1 ~ 1) */
  clipPosition = $state(0);

  /** 클리핑 반전 */
  clipInvert = $state(false);

  /** 수술 전 결과 저장 여부 */
  hasPreOpResult = $state(false);

  /** 보이는 입자 수 */
  visibleCount = $state(0);

  /** 전체 입자 수 */
  totalCount = $state(0);

  /** 현재 데이터 범위 */
  dataMin = $state(0);
  dataMax = $state(1);

  /** BC 수 업데이트 */
  updateBCCount(): void {
    this.bcCount = this.preProcessor?.boundaryConditions.length ?? 0;
  }

  /** 재료 할당 수 업데이트 */
  updateMaterialCount(): void {
    this.materialCount = Object.keys(this.preProcessor?.materialAssignments ?? {}).length;
  }

  /** PostProcessor 동기화 후 스토어 업데이트 */
  syncFromPostProcessor(): void {
    const pp = this.postProcessor;
    if (!pp) return;

    this.visibleCount = pp.visibleCount;
    this.totalCount = pp.data?.displacements?.length ?? 0;
    this.dataMin = pp.stats.currentMin;
    this.dataMax = pp.stats.currentMax;
  }
}

export const analysisState = new AnalysisState();
