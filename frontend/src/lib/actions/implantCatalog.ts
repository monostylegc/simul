/**
 * 임플란트 카탈로그 및 배치 액션
 *
 * - 카탈로그 데이터 정의 (스크류/케이지/로드)
 * - 배치 모드 진입: selectImplantForPlacement()
 * - 스크류 2클릭 배치:
 *     1) setEntryPoint() — 진입점 클릭 (노란 마커 표시, 카메라 자유)
 *     2) placeAtDirection() — 끝점 클릭 (진입점→끝점 방향으로 배치)
 * - 케이지 즉시 배치: placeImplantAtClick()
 * - 임플란트 삭제: deleteSelectedImplant(), clearAllImplants()
 *
 * WebSocket 의존 없음. ImplantManager + toolsState + sceneState 활용.
 */

import * as THREE from 'three';
import { sceneState } from '$lib/stores/scene.svelte';
import { toolsState } from '$lib/stores/tools.svelte';
import { uiState } from '$lib/stores/ui.svelte';

// ── 카탈로그 타입 ──

export type ImplantCategory = 'screw' | 'cage' | 'rod';

export interface CatalogItem {
  id: string;                 // 고유 식별자 (예: 'M6x45')
  label: string;              // 표시 이름
  category: ImplantCategory;
  url: string;                // public STL 경로
  material: string;           // 기본 재료 타입
  description: string;        // 규격 설명
  /** 케이지 높이 (mm) — 디스트랙션 계산 참조용 */
  heightMm?: number;
}

// ── 카탈로그 데이터 ──

export const IMPLANT_CATALOG: CatalogItem[] = [
  // ── 척추경 나사 (Pedicle Screw) ──
  {
    id: 'M5x40', label: 'M5×40', category: 'screw',
    url: '/stl/implants/screws/M5x40.stl', material: 'titanium',
    description: 'Ø5mm · L40mm',
  },
  {
    id: 'M6x45', label: 'M6×45', category: 'screw',
    url: '/stl/implants/screws/M6x45.stl', material: 'titanium',
    description: 'Ø6mm · L45mm',
  },
  {
    id: 'M6x50', label: 'M6×50', category: 'screw',
    url: '/stl/implants/screws/M6x50.stl', material: 'titanium',
    description: 'Ø6mm · L50mm',
  },
  {
    id: 'M7x50', label: 'M7×50', category: 'screw',
    url: '/stl/implants/screws/M7x50.stl', material: 'titanium',
    description: 'Ø7mm · L50mm',
  },
  {
    id: 'M7x55', label: 'M7×55', category: 'screw',
    url: '/stl/implants/screws/M7x55.stl', material: 'titanium',
    description: 'Ø7mm · L55mm',
  },
  // ── TLIF 케이지 ──
  {
    id: 'cage_S', label: 'Cage S', category: 'cage',
    url: '/stl/implants/cages/cage_S.stl', material: 'peek',
    description: '22×8mm', heightMm: 8,
  },
  {
    id: 'cage_M', label: 'Cage M', category: 'cage',
    url: '/stl/implants/cages/cage_M.stl', material: 'peek',
    description: '26×10mm', heightMm: 10,
  },
  {
    id: 'cage_L', label: 'Cage L', category: 'cage',
    url: '/stl/implants/cages/cage_L.stl', material: 'peek',
    description: '26×12mm', heightMm: 12,
  },
  {
    id: 'cage_XL', label: 'Cage XL', category: 'cage',
    url: '/stl/implants/cages/cage_XL.stl', material: 'peek',
    description: '32×14mm', heightMm: 14,
  },
  // ── 연결 로드 (Connecting Rod) ──
  {
    id: 'rod_40', label: 'Rod 40', category: 'rod',
    url: '/stl/implants/rods/rod_40.stl', material: 'titanium',
    description: 'Ø5.5mm · L40mm',
  },
  {
    id: 'rod_50', label: 'Rod 50', category: 'rod',
    url: '/stl/implants/rods/rod_50.stl', material: 'titanium',
    description: 'Ø5.5mm · L50mm',
  },
  {
    id: 'rod_60', label: 'Rod 60', category: 'rod',
    url: '/stl/implants/rods/rod_60.stl', material: 'titanium',
    description: 'Ø5.5mm · L60mm',
  },
  {
    id: 'rod_80', label: 'Rod 80', category: 'rod',
    url: '/stl/implants/rods/rod_80.stl', material: 'titanium',
    description: 'Ø5.5mm · L80mm',
  },
  {
    id: 'rod_100', label: 'Rod 100', category: 'rod',
    url: '/stl/implants/rods/rod_100.stl', material: 'titanium',
    description: 'Ø5.5mm · L100mm',
  },
];

/** 카테고리별 분류 */
export const CATALOG_BY_CATEGORY: Record<ImplantCategory, CatalogItem[]> = {
  screw: IMPLANT_CATALOG.filter(i => i.category === 'screw'),
  cage:  IMPLANT_CATALOG.filter(i => i.category === 'cage'),
  rod:   IMPLANT_CATALOG.filter(i => i.category === 'rod'),
};

// ── 배치 액션 ──

/**
 * 카탈로그 항목 선택 → 배치 모드 진입.
 * 뷰포트에서 뼈 표면을 클릭하면 해당 위치에 임플란트가 배치된다.
 *
 * @param item 카탈로그 항목
 */
export function selectImplantForPlacement(item: CatalogItem): void {
  // 이전 진입점 마커가 있으면 정리
  cancelScrewEntry();
  toolsState.enterImplantPlaceMode(item.url, item.id, item.material, item.category, item.heightMm);
  uiState.statusMessage = `배치 모드: ${item.label} — 뼈 표면을 클릭하세요 (Esc 취소)`;
  uiState.toast(`${item.label} 선택됨. 뷰포트의 뼈 표면을 클릭해 배치하세요.`, 'info');
}

/**
 * 뼈 표면 클릭 시 즉시 배치 (케이지 등 비-스크류 임플란트).
 * Canvas3D.svelte의 handlePointerDown (implantPlace 모드)에서 호출.
 *
 * @param position  레이캐스터 교차점 위치 (월드 좌표)
 * @param normal    교차면 법선 벡터 (월드 좌표)
 */
export async function placeImplantAtClick(
  position: THREE.Vector3,
  normal: THREE.Vector3,
): Promise<void> {
  const manager = sceneState.implantManager;
  if (!manager) return;

  const url      = toolsState.pendingImplantUrl;
  const baseName = toolsState.pendingImplantName;
  const mat      = toolsState.pendingImplantMat;
  const category = toolsState.pendingImplantCategory;
  const heightMm = toolsState.pendingImplantHeightMm;

  if (!url || !baseName) return;

  try {
    manager.boneMeshes = sceneState.models
      .filter(m => m.visible)
      .map(m => m.mesh);

    const placedName = await manager.loadImplantFromURL(url, baseName, mat, category, heightMm);
    manager.placeImplantAtSurface(placedName, position, normal);

    uiState.statusMessage = `${baseName} 배치 완료 — 핸들로 이동/회전 가능`;
    uiState.toast(`${baseName} 배치됨`, 'success');
  } catch (e) {
    console.error('임플란트 배치 실패:', e);
    uiState.toast('임플란트 STL 로드 실패', 'error');
  }
}

// ── 스크류 2클릭 배치 ──

/** 1단계에서 설정된 진입점 좌표 (null = 아직 미설정) */
let _entryPoint: THREE.Vector3 | null = null;
/** 진입점의 표면 법선 */
let _entryNormal: THREE.Vector3 | null = null;

/**
 * 스크류 2클릭 배치 1단계: 진입점 설정.
 *
 * 뼈 표면 클릭 위치에 노란 마커를 표시한다.
 * 카메라 회전이 자유로운 상태이므로 사용자가 시야를 돌려
 * 삽입 방향을 확인한 후 두 번째 클릭을 할 수 있다.
 *
 * @param position 진입점 월드 좌표
 * @param normal   표면 법선 벡터
 */
export function setEntryPoint(position: THREE.Vector3, normal: THREE.Vector3): void {
  const manager = sceneState.implantManager;
  if (!manager) return;

  _entryPoint  = position.clone();
  _entryNormal = normal.clone();

  manager.showEntryMarker(position);

  const baseName = toolsState.pendingImplantName ?? 'screw';
  uiState.statusMessage = `${baseName} 진입점 설정 — 카메라를 돌려 방향을 확인한 후 끝점을 클릭하세요`;
}

/**
 * 스크류 2클릭 배치 2단계: 끝점 클릭 → STL 로드 + 배치.
 *
 * 진입점 → 끝점 방향으로 스크류를 배치한다.
 *
 * @param targetPoint 끝점 월드 좌표 (두 번째 클릭 위치)
 */
export async function placeAtDirection(targetPoint: THREE.Vector3): Promise<void> {
  if (!_entryPoint || !_entryNormal) return;
  const manager = sceneState.implantManager;
  if (!manager) return;

  // 방향 계산: 진입점 → 끝점
  const direction = targetPoint.clone().sub(_entryPoint);
  if (direction.length() < 0.5) {
    // 너무 가까운 클릭 → 표면 법선 방향 사용
    direction.copy(_entryNormal);
  }
  direction.normalize();

  const url      = toolsState.pendingImplantUrl;
  const baseName = toolsState.pendingImplantName;
  const mat      = toolsState.pendingImplantMat;
  const category = toolsState.pendingImplantCategory;
  const heightMm = toolsState.pendingImplantHeightMm;

  if (!url || !baseName) return;

  try {
    manager.boneMeshes = sceneState.models
      .filter(m => m.visible)
      .map(m => m.mesh);

    const placedName = await manager.loadImplantFromURL(url, baseName, mat, category, heightMm);

    // 진입점에 배치, 방향 설정
    const entry = manager.implants[placedName];
    if (entry) {
      entry.mesh.position.copy(_entryPoint);

      // +Y 축을 삽입 방향으로 회전
      const up = new THREE.Vector3(0, 1, 0);
      const quat = new THREE.Quaternion().setFromUnitVectors(up, direction);
      entry.mesh.quaternion.copy(quat);

      entry.mesh.visible = true;
      manager.selectImplant(placedName);
    }

    // 마커 정리
    manager.hideEntryMarker();
    _entryPoint  = null;
    _entryNormal = null;

    uiState.statusMessage = `${baseName} 배치 완료 — 핸들로 이동/회전 가능`;
    uiState.toast(`${baseName} 배치됨`, 'success');
  } catch (e) {
    console.error('임플란트 배치 실패:', e);
    uiState.toast('임플란트 STL 로드 실패', 'error');
  }
}

/**
 * 방향 프리뷰 라인 업데이트 (마우스 이동 시).
 * 진입점이 설정된 상태에서 커서 위치까지 빨간 라인을 보여준다.
 *
 * @param targetPoint 현재 커서가 가리키는 월드 좌표
 */
export function updateDirectionPreview(targetPoint: THREE.Vector3): void {
  if (!_entryPoint) return;
  const manager = sceneState.implantManager;
  if (!manager) return;

  manager.updatePreviewLine(targetPoint);
}

/**
 * 진입점 설정 취소 + 마커 제거.
 */
export function cancelScrewEntry(): void {
  _entryPoint  = null;
  _entryNormal = null;

  const manager = sceneState.implantManager;
  if (manager) manager.hideEntryMarker();
}

/**
 * 현재 진입점이 설정되었는지 확인 (2클릭 배치 단계 판단용).
 */
export function hasEntryPoint(): boolean {
  return _entryPoint !== null;
}

/**
 * 현재 진입점 좌표 반환.
 */
export function getEntryPoint(): THREE.Vector3 | null {
  return _entryPoint ? _entryPoint.clone() : null;
}

// ── 삭제/관리 ──

/**
 * 현재 선택된 임플란트 삭제.
 * Canvas3D.svelte에서 Delete 키 또는 ModelingPanel 버튼으로 호출.
 */
export function deleteSelectedImplant(): void {
  const manager = sceneState.implantManager;
  if (!manager || !manager.selectedImplant) return;

  const name = manager.selectedImplant;
  manager.removeImplant(name);
  uiState.toast(`${name} 삭제됨`, 'info');
  uiState.statusMessage = '임플란트 삭제됨';
}

/**
 * 케이지 디스트랙션 적용.
 * 케이지 높이에 맞춰 상위 척추를 위로 이동시켜 디스크 공간을 교정한다.
 *
 * @param cageName 케이지 임플란트 이름
 * @returns 교정 성공 여부
 */
export function applyCageDistraction(cageName: string): boolean {
  const manager = sceneState.implantManager;
  if (!manager) return false;

  // boneMeshes 최신화
  manager.boneMeshes = sceneState.models
    .filter(m => m.visible)
    .map(m => m.mesh);

  const result = manager.applyDistraction(cageName);
  if (!result) {
    uiState.toast('디스트랙션 조건 미충족 (케이지 높이 ≤ 현재 디스크 공간)', 'warn');
    return false;
  }

  const deltaStr = result.deltaH.toFixed(1);
  const gapStr   = result.originalGap.toFixed(1);
  const cageStr  = result.cageHeight.toFixed(1);
  uiState.toast(
    `디스트랙션 적용: ${gapStr}mm → ${cageStr}mm (상위 척추 +${deltaStr}mm)`,
    'success',
  );
  uiState.statusMessage = `케이지 디스트랙션 완료 (+${deltaStr}mm)`;
  return true;
}

/**
 * 모든 임플란트 삭제.
 */
export function clearAllImplants(): void {
  const manager = sceneState.implantManager;
  if (!manager) return;

  const count = manager.implantCount;
  manager.removeAll();
  uiState.toast(`임플란트 ${count}개 전체 삭제됨`, 'info');
  uiState.statusMessage = '임플란트 전체 삭제됨';
}

/**
 * 배치된 임플란트 목록 반환 (ModelingPanel UI 표시용).
 * implantManager.implantCount에 의존하므로 $derived와 연동 가능.
 */
export function getPlacedImplants(): Array<{
  name: string;
  label: string;
  material: string;
  category: ImplantCategory;
}> {
  const manager = sceneState.implantManager;
  if (!manager) return [];

  return Object.entries(manager.implants).map(([name, entry]) => ({
    name,
    label: name,
    material: entry.material,
    category: entry.category,
  }));
}
