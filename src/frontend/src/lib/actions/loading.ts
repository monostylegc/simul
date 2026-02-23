/**
 * 모델 로딩 액션
 * — STL 파일 로드, 샘플 모델 로드, NRRD 적용
 */

import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { sceneState } from '$lib/stores/scene.svelte';
import { uiState } from '$lib/stores/ui.svelte';
import { historyState } from '$lib/stores/history.svelte';
import { VoxelGrid } from '$lib/three/VoxelGrid';
import { NRRDLoader } from '$lib/three/NRRDLoader';

// 복셀 관련 공유 상태
export const voxelGrids: Record<string, VoxelGrid> = {};
export const voxelMeshes: Record<string, THREE.Mesh> = {};
export let isDrillInitialized = false;

/** STL 색상 팔레트 */
const COLOR_PALETTE: Record<string, number> = {
  L4: 0xccccbb,
  L5: 0xbbccbb,
  disc: 0xdd9966,
};

const stlLoader = new STLLoader();

/**
 * 샘플 모델 로드 (L4, L5, Disc)
 */
export async function loadSampleModels(): Promise<void> {
  const manager = sceneState.manager;
  if (!manager) return;

  uiState.statusMessage = 'Loading sample models...';

  const files = [
    { name: 'L4', url: '/stl/L4.stl', color: COLOR_PALETTE.L4 },
    { name: 'L5', url: '/stl/L5.stl', color: COLOR_PALETTE.L5 },
    { name: 'disc', url: '/stl/disc.stl', color: COLOR_PALETTE.disc },
  ];

  for (const f of files) {
    try {
      const mesh = await manager.loadSTL(f.url, f.name, f.color);
      sceneState.addModel(f.name, mesh);
    } catch (e) {
      console.error(`STL 로드 실패: ${f.name}`, e);
    }
  }

  // 카메라 포커스
  if (sceneState.models.length > 0) {
    manager.focusOnMesh(sceneState.models[0].mesh);
  }

  isDrillInitialized = false;
  uiState.statusMessage = `${sceneState.models.length}개 모델 로드 완료`;
}

/**
 * 사용자 STL 파일 로드
 */
export async function loadSTLFiles(files: FileList): Promise<void> {
  const manager = sceneState.manager;
  if (!manager) return;

  uiState.statusMessage = 'Loading STL files...';

  for (const file of Array.from(files)) {
    try {
      const name = file.name.replace(/\.[^/.]+$/, '');
      const arrayBuffer = await file.arrayBuffer();
      const geometry = stlLoader.parse(arrayBuffer);
      geometry.computeVertexNormals();
      geometry.computeBoundingBox();

      const material = new THREE.MeshStandardMaterial({
        color: 0xcccccc,
        roughness: 0.6,
        metalness: 0.1,
        transparent: false,
        opacity: 1.0,
        depthWrite: true,
        side: THREE.DoubleSide,
      });

      const mesh = new THREE.Mesh(geometry, material);
      mesh.name = name;
      mesh.castShadow = true;
      mesh.receiveShadow = true;

      manager.scene.add(mesh);
      sceneState.addModel(name, mesh);
    } catch (e) {
      console.error(`STL 로드 실패: ${file.name}`, e);
    }
  }

  if (sceneState.models.length > 0) {
    manager.focusOnMesh(sceneState.models[0].mesh);
  }

  isDrillInitialized = false;
  uiState.statusMessage = `${sceneState.models.length}개 모델 로드 완료`;
}

/**
 * NRRD 파일 로드 및 복셀화
 */
export async function loadNRRDFile(
  file: File,
  options: { threshold?: number; resolution?: number } = {},
): Promise<void> {
  const manager = sceneState.manager;
  if (!manager) return;

  uiState.statusMessage = 'Loading NRRD file...';

  try {
    const arrayBuffer = await file.arrayBuffer();
    const nrrdData = NRRDLoader.parse(arrayBuffer);
    const name = file.name.replace(/\.[^/.]+$/, '');

    // 기존 모델 제거
    sceneState.clearAll();
    Object.keys(voxelGrids).forEach(k => delete voxelGrids[k]);
    Object.keys(voxelMeshes).forEach(k => {
      manager.scene.remove(voxelMeshes[k]);
      voxelMeshes[k].geometry.dispose();
      (voxelMeshes[k].material as THREE.Material).dispose();
      delete voxelMeshes[k];
    });

    // 복셀 그리드 생성
    const resolution = options.resolution ?? 64;
    const grid = new VoxelGrid(resolution);
    grid.fromNRRD(nrrdData, options.threshold ?? 200);

    // Marching Cubes 메쉬 생성
    const geometry = grid.toMesh();
    if (!geometry) {
      console.error('NRRD → 메쉬 변환 실패');
      return;
    }

    const material = new THREE.MeshPhongMaterial({
      color: 0xccccbb,
      flatShading: false,
      side: THREE.DoubleSide,
    });

    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = name;
    manager.scene.add(mesh);

    voxelGrids[name] = grid;
    voxelMeshes[name] = mesh;
    sceneState.addModel(name, mesh);

    manager.focusOnMesh(mesh);
    isDrillInitialized = true;
    uiState.statusMessage = `NRRD 로드 완료: ${name}`;
  } catch (e) {
    console.error('NRRD 로드 실패:', e);
    uiState.statusMessage = 'NRRD 로드 실패';
  }
}

/**
 * 복셀 초기화 (드릴/해석 진입 시)
 * STL 메쉬를 복셀 그리드로 변환
 */
export async function initializeVoxels(resolution = 64): Promise<void> {
  if (isDrillInitialized) return;

  const manager = sceneState.manager;
  if (!manager) return;

  uiState.statusMessage = 'Initializing voxels...';

  const meshEntries = sceneState.models.filter(m => m.mesh.visible);
  if (meshEntries.length === 0) return;

  for (const entry of meshEntries) {
    const { name, mesh } = entry;

    const grid = new VoxelGrid(resolution);
    grid.fromMesh(mesh);

    // Marching Cubes 메쉬 생성
    const mcGeometry = grid.toMesh();
    if (!mcGeometry) continue;

    const mcMaterial = new THREE.MeshPhongMaterial({
      color: (mesh.material as THREE.MeshStandardMaterial).color ?? new THREE.Color(0xcccccc),
      flatShading: false,
      side: THREE.DoubleSide,
    });

    const voxelMesh = new THREE.Mesh(mcGeometry, mcMaterial);
    voxelMesh.name = `voxel_${name}`;
    manager.scene.add(voxelMesh);

    // 원본 메쉬 숨김
    mesh.visible = false;

    voxelGrids[name] = grid;
    voxelMeshes[name] = voxelMesh;
  }

  isDrillInitialized = true;
  // History에 복셀 그리드 참조 연결
  historyState.setVoxelGrids(voxelGrids);
  uiState.statusMessage = 'Voxel initialization complete';
}

/**
 * 모든 모델 제거
 */
export function clearAll(): void {
  const manager = sceneState.manager;
  if (!manager) return;

  // 복셀 메쉬 제거
  Object.entries(voxelMeshes).forEach(([_name, mesh]) => {
    manager.scene.remove(mesh);
    mesh.geometry.dispose();
    (mesh.material as THREE.Material).dispose();
  });
  Object.keys(voxelGrids).forEach(k => delete voxelGrids[k]);
  Object.keys(voxelMeshes).forEach(k => delete voxelMeshes[k]);

  sceneState.clearAll();
  historyState.clear();
  isDrillInitialized = false;
  uiState.statusMessage = 'Ready';
}
