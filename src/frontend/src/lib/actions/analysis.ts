/**
 * 해석 실행 액션
 * — PreProcessor/PostProcessor 초기화, 해석 요청, 결과 처리
 * — ParaView 스타일 후처리 제어
 */

import * as THREE from 'three';
import { sceneState } from '$lib/stores/scene.svelte';
import { analysisState } from '$lib/stores/analysis.svelte';
import { wsState } from '$lib/stores/websocket.svelte';
import { uiState } from '$lib/stores/ui.svelte';
import { PreProcessor } from '$lib/analysis/PreProcessor';
import type { ResolvedMaterial } from '$lib/analysis/PreProcessor';
import { PostProcessor } from '$lib/analysis/PostProcessor';
import type { PostProcessMode, VectorComponent } from '$lib/analysis/PostProcessor';
import type { ColormapName } from '$lib/analysis/colormap';
import { WSClient } from '$lib/ws/client';
import { voxelGrids, initializeVoxels } from './loading';
import type { AnalysisResultData, ProgressData, ErrorData } from '$lib/ws/types';

/**
 * 해석 환경 초기화 (PreProcessor, PostProcessor, WebSocket)
 */
export async function initAnalysis(): Promise<void> {
  const manager = sceneState.manager;
  if (!manager) return;

  // 복셀 초기화
  await initializeVoxels();

  // 메쉬 참조 구축
  const meshes: Record<string, THREE.Mesh> = {};
  sceneState.models.forEach(m => { meshes[m.name] = m.mesh; });

  // PreProcessor
  if (!analysisState.preProcessor) {
    analysisState.preProcessor = new PreProcessor(manager.scene, meshes, voxelGrids);
  }

  // PostProcessor
  if (!analysisState.postProcessor) {
    analysisState.postProcessor = new PostProcessor(manager.scene);
  }

  // WebSocket
  if (!wsState.client) {
    const client = new WSClient();
    wsState.client = client;

    client.onConnect(() => wsState.setConnected(true));
    client.onDisconnect(() => {
      wsState.setConnected(false);
      wsState.reconnectAttempt++;
    });
    client.onProgress(_onProgress);
    client.onResult(_onResult);
    client.onError(_onError);
    client.onCancelled(_onCancelled);

    client.connect();
  }
}

/**
 * 해석 실행
 *
 * 1. 종합 검증 (canRun, validationErrors)
 * 2. buildAnalysisRequest 조립 (null 반환 시 중단)
 * 3. 서버 전송 + 타이머 시작
 */
export async function runAnalysis(): Promise<void> {
  const pre = analysisState.preProcessor;
  const client = wsState.client;

  // ── 연결 검증 ──
  if (!pre || !client?.connected) {
    uiState.toast('서버에 연결되지 않았거나 전처리기가 초기화되지 않았습니다', 'error');
    return;
  }

  // ── 종합 검증 ──
  const errors = analysisState.validationErrors;
  if (errors.length > 0) {
    uiState.toast(`해석 불가: ${errors.join(', ')}`, 'error');
    return;
  }

  // 상태 초기화
  analysisState.lastError = null;
  analysisState.elapsedMs = 0;
  const startTime = Date.now();

  // 요청 조립 (검증 실패 시 null 반환)
  const request = pre.buildAnalysisRequest(analysisState.method);
  if (!request) {
    // buildAnalysisRequest 내부에서 toast를 표시함
    return;
  }

  // FEM은 materials에 nodes가 있으므로 positions가 빈 배열일 수 있음
  const hasFEM = request.materials.some(m => m.method === 'fem' && m.nodes && m.nodes.length > 0);
  const hasParticles = request.positions.length > 0;

  if (!hasFEM && !hasParticles) {
    uiState.toast('해석할 메쉬 데이터 또는 입자가 없습니다', 'error');
    return;
  }

  // 원본 좌표 캐시 (레거시 변형 좌표 계산용)
  if (hasParticles) {
    analysisState.postProcessor?.cachePositions(request.positions);
  }

  // 해석 시작
  analysisState.isRunning = true;
  analysisState.progress = 0;
  analysisState.progressMessage = 'Submitting analysis...';
  uiState.statusMessage = `Running ${analysisState.method.toUpperCase()} analysis...`;

  // 타이머 업데이트 (100ms 간격)
  const timer = setInterval(() => {
    if (analysisState.isRunning) {
      analysisState.elapsedMs = Date.now() - startTime;
    } else {
      clearInterval(timer);
    }
  }, 100);

  client.sendAnalysis(request);
}

/**
 * 진행 중인 해석 취소
 */
export function cancelAnalysis(): void {
  const client = wsState.client;
  if (!client) return;
  client.cancelAnalysis();
  analysisState.isRunning = false;
  analysisState.progressMessage = '';
  uiState.toast('해석 취소 요청을 전송했습니다', 'info');
}

// ── BC 관리 ──

/** 고정 BC 추가 */
export function addFixedBC(): void {
  analysisState.preProcessor?.addFixedBC();
  analysisState.updateBCCount();
}

/** 하중 BC 추가 */
export function addForceBC(force: number[]): void {
  const pre = analysisState.preProcessor;
  if (!pre) return;

  // Force BC 적용 전, 브러쉬 선택 영역 중심점을 먼저 저장한다.
  // (addForceBC 내부에서 brushSelection이 초기화되므로 반드시 먼저 계산)
  const centroid = pre.getBrushSelectionCentroid();
  if (centroid) {
    analysisState.forceBCOrigin = [centroid.x, centroid.y, centroid.z];
  }

  pre.addForceBC(force);
  analysisState.updateBCCount();
}

/** 마지막 BC 제거 */
export function removeLastBC(): void {
  analysisState.preProcessor?.removeLastBC();
  analysisState.updateBCCount();
}

/** 모든 BC 제거 */
export function clearAllBC(): void {
  analysisState.preProcessor?.clearAllBC();
  analysisState.updateBCCount();
}

/** 재료 할당 (확정된 물성치) */
export function assignMaterial(meshName: string, material: ResolvedMaterial): void {
  analysisState.preProcessor?.assignMaterial(meshName, material);
  analysisState.updateMaterialCount();
}

/** 모델별 솔버 할당 */
export function assignSolver(meshName: string, method: 'fem' | 'pd' | 'spg'): void {
  analysisState.solverAssignments = {
    ...analysisState.solverAssignments,
    [meshName]: method,
  };
  // PreProcessor에도 동기화
  if (analysisState.preProcessor) {
    analysisState.preProcessor.solverAssignments[meshName] = method;
  }
}

/** 기본 솔버 변경 (할당되지 않은 모델에 적용) */
export function setDefaultMethod(method: 'fem' | 'pd' | 'spg'): void {
  analysisState.method = method;
}

// ── ParaView 스타일 후처리 제어 ──

/** 후처리 모드 변경 */
export function setPostMode(mode: PostProcessMode): void {
  analysisState.postMode = mode;
  const pp = analysisState.postProcessor;
  if (pp) {
    pp.setMode(mode);
    analysisState.syncFromPostProcessor();
    // 모드 변경 시 범위 리셋
    analysisState.rangeMin = pp.stats.currentMin;
    analysisState.rangeMax = pp.stats.currentMax;
    analysisState.thresholdLower = pp.stats.currentMin;
    analysisState.thresholdUpper = pp.stats.currentMax;
    analysisState.useCustomRange = false;
  }
}

/** 벡터 컴포넌트 변경 */
export function setComponent(comp: VectorComponent): void {
  analysisState.component = comp;
  const pp = analysisState.postProcessor;
  if (pp) {
    pp.setComponent(comp);
    analysisState.syncFromPostProcessor();
    analysisState.rangeMin = pp.stats.currentMin;
    analysisState.rangeMax = pp.stats.currentMax;
    analysisState.thresholdLower = pp.stats.currentMin;
    analysisState.thresholdUpper = pp.stats.currentMax;
    analysisState.useCustomRange = false;
  }
}

/** 컬러맵 변경 */
export function setColormap(name: ColormapName): void {
  analysisState.colormap = name;
  const pp = analysisState.postProcessor;
  if (pp) {
    pp.setColormap(name);
    analysisState.syncFromPostProcessor();
  }
}

/** 변위 스케일 변경 (Warp by Vector) */
export function setDispScale(scale: number): void {
  analysisState.dispScale = scale;
  analysisState.postProcessor?.setDisplacementScale(scale);
  analysisState.syncFromPostProcessor();
}

/** 입자 크기 변경 */
export function setParticleSize(size: number): void {
  analysisState.particleSize = size;
  analysisState.postProcessor?.setParticleSize(size);
}

/** 불투명도 변경 */
export function setOpacity(val: number): void {
  analysisState.opacity = val;
  analysisState.postProcessor?.setOpacity(val);
}

/** 커스텀 범위 설정 */
export function setCustomRange(enabled: boolean, min?: number, max?: number): void {
  analysisState.useCustomRange = enabled;
  if (min !== undefined) analysisState.rangeMin = min;
  if (max !== undefined) analysisState.rangeMax = max;

  const pp = analysisState.postProcessor;
  if (pp) {
    pp.setCustomRange(
      enabled ? analysisState.rangeMin : null,
      enabled ? analysisState.rangeMax : null,
    );
    analysisState.syncFromPostProcessor();
  }
}

/** 범위 값 업데이트 (슬라이더 드래그 중) */
export function updateRangeValues(min: number, max: number): void {
  analysisState.rangeMin = min;
  analysisState.rangeMax = max;

  if (analysisState.useCustomRange) {
    const pp = analysisState.postProcessor;
    if (pp) {
      pp.setCustomRange(min, max);
      analysisState.syncFromPostProcessor();
    }
  }
}

/** 범위 자동 리셋 */
export function resetRange(): void {
  const pp = analysisState.postProcessor;
  if (pp) {
    const range = pp.getDataRange();
    analysisState.rangeMin = range.min;
    analysisState.rangeMax = range.max;
    analysisState.useCustomRange = false;
    pp.setCustomRange(null, null);
    analysisState.syncFromPostProcessor();
  }
}

/** 임계값 필터 설정 */
export function setThreshold(enabled: boolean, lower?: number, upper?: number): void {
  analysisState.thresholdEnabled = enabled;
  if (lower !== undefined) analysisState.thresholdLower = lower;
  if (upper !== undefined) analysisState.thresholdUpper = upper;

  analysisState.postProcessor?.setThreshold(
    enabled,
    analysisState.thresholdLower,
    analysisState.thresholdUpper,
  );
  analysisState.syncFromPostProcessor();
}

/** 클리핑 평면 설정 */
export function setClipPlane(
  enabled: boolean,
  axis?: 'x' | 'y' | 'z',
  position?: number,
  invert?: boolean,
): void {
  analysisState.clipEnabled = enabled;
  if (axis !== undefined) analysisState.clipAxis = axis;
  if (position !== undefined) analysisState.clipPosition = position;
  if (invert !== undefined) analysisState.clipInvert = invert;

  analysisState.postProcessor?.setClipPlane({
    enabled,
    axis: analysisState.clipAxis,
    position: analysisState.clipPosition,
    invert: analysisState.clipInvert,
  });
  analysisState.syncFromPostProcessor();
}

/** 수술 전 결과 저장 */
export function savePreOpResults(): void {
  const result = analysisState.postProcessor?.savePreOpResults();
  if (result) {
    analysisState.hasPreOpResult = true;
    _preOpData = result;
  }
}

let _preOpData: AnalysisResultData | null = null;

/** 수술 전/후 비교 */
export function showComparison(): void {
  if (_preOpData) {
    analysisState.postProcessor?.showComparison(_preOpData);
  }
}

// ── 결과 내보내기 (Step 7) ──

/**
 * 해석 결과를 CSV 파일로 다운로드.
 *
 * 열: node, dx, dy, dz, von_mises_stress, damage
 */
export function exportResultsCSV(): void {
  const pp = analysisState.postProcessor;
  if (!pp || !pp.data) {
    uiState.toast('내보낼 결과가 없습니다', 'warn');
    return;
  }

  const { displacements, stress, damage, info } = pp.data;
  const rows: string[] = ['node,dx,dy,dz,von_mises_stress,damage'];

  const nParticles = displacements?.length ?? 0;
  for (let i = 0; i < nParticles; i++) {
    const d = displacements?.[i] ?? [0, 0, 0];
    // stress는 1D(von Mises) 또는 2D(텐서) 형태 가능
    let s = 0;
    if (Array.isArray(stress)) {
      const sv = stress[i];
      s = typeof sv === 'number' ? sv : (Array.isArray(sv) ? sv[0] : 0);
    }
    const dmg = damage?.[i] ?? 0;
    rows.push(`${i},${d[0]},${d[1]},${d[2]},${s},${dmg}`);
  }

  const csv = rows.join('\n');
  const method = info?.method ?? 'unknown';
  const filename = `analysis_${method}_${nParticles}pts.csv`;
  _downloadBlob(csv, filename, 'text/csv');
  uiState.toast(`CSV 내보내기 완료: ${filename}`, 'success');
}

/** Blob → 브라우저 다운로드 */
function _downloadBlob(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── 내부 콜백 ──

function _onProgress(data: ProgressData): void {
  analysisState.progress = data.progress;
  analysisState.progressMessage = data.message ?? data.step;
}

function _onResult(data: AnalysisResultData): void {
  analysisState.isRunning = false;
  analysisState.hasResult = true;
  analysisState.lastError = null;
  analysisState.postProcessor?.loadResults(data);

  // 결과 로드 후 스토어 동기화
  analysisState.syncFromPostProcessor();
  const pp = analysisState.postProcessor;
  if (pp) {
    analysisState.rangeMin = pp.stats.currentMin;
    analysisState.rangeMax = pp.stats.currentMax;
    analysisState.thresholdLower = pp.stats.currentMin;
    analysisState.thresholdUpper = pp.stats.currentMax;
  }

  const elapsed = (analysisState.elapsedMs / 1000).toFixed(1);
  uiState.statusMessage = `Analysis complete (${data.info?.method}) — ${elapsed}s`;
  uiState.toast(`해석 완료 (${elapsed}초)`, 'success');
  uiState.activeTab = 'postprocess';
}

function _onCancelled(_data: { request_id: string }): void {
  analysisState.isRunning = false;
  analysisState.progressMessage = '';
  analysisState.lastError = '사용자가 해석을 취소했습니다';
  uiState.statusMessage = 'Analysis cancelled';
  uiState.toast('해석이 취소되었습니다', 'warn');
}

function _onError(data: ErrorData): void {
  analysisState.isRunning = false;
  analysisState.progressMessage = '';
  analysisState.lastError = data.message;
  uiState.statusMessage = `Analysis error: ${data.message}`;
  uiState.toast(`해석 실패: ${data.message}`, 'error');
  console.error('해석 에러:', data.message);
}
