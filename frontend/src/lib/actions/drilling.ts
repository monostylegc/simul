/**
 * 드릴링 액션
 * — 드릴 프리뷰, 실제 드릴, 복셀 메쉬 갱신
 */

import * as THREE from 'three';
import { sceneState } from '$lib/stores/scene.svelte';
import { toolsState } from '$lib/stores/tools.svelte';
import { historyState } from '$lib/stores/history.svelte';
import { uiState } from '$lib/stores/ui.svelte';
import { voxelGrids, voxelMeshes, initializeVoxels } from './loading';

// 드릴 하이라이트 (InstancedMesh)
let drillHighlight: THREE.InstancedMesh | null = null;
const MAX_HIGHLIGHT_INSTANCES = 5000;

/**
 * 드릴 모드 활성화
 */
export async function enableDrill(): Promise<void> {
  await initializeVoxels();
  // History에 복셀 그리드 참조 연결 (Undo/Redo 동작 보장)
  historyState.setVoxelGrids(voxelGrids);
  toolsState.setMode('drill');
  _ensureDrillHighlight();
  uiState.statusMessage = 'Drill mode: Click to drill';
}

/**
 * 드릴 모드 비활성화
 */
export function disableDrill(): void {
  toolsState.reset();
  if (drillHighlight) {
    drillHighlight.visible = false;
  }
}

/**
 * 드릴 프리뷰 업데이트 (마우스 이동 시)
 */
export function updateDrillPreview(worldPoint: THREE.Vector3): void {
  if (toolsState.mode !== 'drill') return;
  if (!drillHighlight) return;

  const radius = toolsState.drillRadius;
  let totalCount = 0;
  const matrix = new THREE.Matrix4();

  // 각 그리드에서 영향 받는 복셀 수집
  for (const grid of Object.values(voxelGrids)) {
    const affected = grid.previewDrill(worldPoint, radius);
    const cellSize = grid.cellSize;

    for (const pos of affected) {
      if (totalCount >= MAX_HIGHLIGHT_INSTANCES) break;
      const wp = grid.gridToWorld(pos.x, pos.y, pos.z);
      matrix.makeScale(cellSize * 0.98, cellSize * 0.98, cellSize * 0.98);
      matrix.setPosition(wp.x, wp.y, wp.z);
      drillHighlight.setMatrixAt(totalCount, matrix);
      totalCount++;
    }
  }

  drillHighlight.count = totalCount;
  drillHighlight.instanceMatrix.needsUpdate = true;
  drillHighlight.visible = totalCount > 0;
}

/**
 * 드릴 실행 (마우스 클릭 시)
 */
export function performDrill(worldPoint: THREE.Vector3): void {
  if (toolsState.mode !== 'drill') return;

  const radius = toolsState.drillRadius;
  const manager = sceneState.manager;
  if (!manager) return;

  // Undo용 스냅샷 저장
  historyState.push('drill');

  let drilled = false;

  for (const [name, grid] of Object.entries(voxelGrids)) {
    const removed = grid.drillWithSphere(worldPoint, radius);
    if (removed > 0) {
      drilled = true;

      // 메쉬 재생성
      const newGeometry = grid.toMesh();
      const oldMesh = voxelMeshes[name];
      if (oldMesh && newGeometry) {
        oldMesh.geometry.dispose();
        oldMesh.geometry = newGeometry;
      }
    }
  }

  if (drilled) {
    uiState.statusMessage = `Drilled at radius ${radius.toFixed(1)} mm`;
  }
}

/**
 * 드릴 하이라이트 인스턴스드 메쉬 생성
 */
function _ensureDrillHighlight(): void {
  const manager = sceneState.manager;
  if (!manager || drillHighlight) return;

  const boxGeom = new THREE.BoxGeometry(1, 1, 1);
  const mat = new THREE.MeshBasicMaterial({
    color: 0xff4444,
    transparent: true,
    opacity: 0.35,
    depthTest: false,
  });

  drillHighlight = new THREE.InstancedMesh(boxGeom, mat, MAX_HIGHLIGHT_INSTANCES);
  drillHighlight.count = 0;
  drillHighlight.visible = false;
  drillHighlight.renderOrder = 999;
  manager.scene.add(drillHighlight);
}

/**
 * 드릴 하이라이트 정리
 */
export function disposeDrillHighlight(): void {
  if (drillHighlight) {
    sceneState.manager?.scene.remove(drillHighlight);
    drillHighlight.geometry.dispose();
    (drillHighlight.material as THREE.Material).dispose();
    drillHighlight = null;
  }
}
