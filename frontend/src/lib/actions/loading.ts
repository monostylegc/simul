/**
 * 모델 로딩 액션
 * — STL 파일 로드, 샘플 모델 로드, NRRD 적용, 인라인 메쉬 로드
 */

import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { sceneState } from '$lib/stores/scene.svelte';
import { uiState } from '$lib/stores/ui.svelte';
import { historyState } from '$lib/stores/history.svelte';
import { VoxelGrid } from '$lib/three/VoxelGrid';
import { NRRDLoader } from '$lib/three/NRRDLoader';
import { autoOrientGeometry } from '$lib/three/SceneManager';

/**
 * 로드된 메쉬 전체를 원점 중심으로 이동.
 *
 * 각 메쉬 geometry의 combined bounding box 중심을 계산해
 * 모든 geometry에 동일한 -center 평행이동을 적용한다.
 * 상대 위치 관계(L4/L5/disc 간격)는 그대로 유지되며
 * 전체 집합의 무게 중심이 (0, 0, 0) 근처로 이동된다.
 *
 * @param meshes 중심화할 THREE.Mesh 배열
 */
export function centerMeshesAtOrigin(meshes: THREE.Mesh[]): void {
  if (meshes.length === 0) return;

  // 전체 combined bounding box 계산
  const combinedBox = new THREE.Box3();
  meshes.forEach(m => {
    m.geometry.computeBoundingBox();
    combinedBox.expandByObject(m);
  });

  const center = combinedBox.getCenter(new THREE.Vector3());
  if (center.lengthSq() < 0.001) return;  // 이미 원점 근처

  // 각 geometry에 동일한 -center 이동 적용 (상대 위치 보존)
  const translateMat = new THREE.Matrix4().makeTranslation(-center.x, -center.y, -center.z);
  meshes.forEach(m => {
    m.geometry.applyMatrix4(translateMat);
    m.geometry.computeBoundingBox();
    m.geometry.computeVertexNormals();
  });
}

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
 * 샘플 모델 로드 (L4, L5, Disc) + 자동 복셀화
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

  const modelCount = sceneState.models.length;
  if (modelCount === 0) return;

  // ── 원점 중심화: 상대 위치 유지하면서 전체를 origin 근처로 이동 ──
  // L4/L5/disc는 CT 스캐너 좌표(Z ≈ -1150) 그대로 로드되므로
  // 전체 combined bbox 중심을 (0,0,0)으로 평행이동한다
  const allMeshes = sceneState.models.map(m => m.mesh);
  centerMeshesAtOrigin(allMeshes);

  // ── 자동 복셀화: 로드 직후 즉시 복셀 그리드 생성 ──
  // 복셀 모델이 바로 표시되어야 전처리/해석 워크플로우가 자연스럽게 이어짐
  uiState.statusMessage = '복셀화 중...';
  await initializeVoxels();

  // 복셀화 후 카메라 포커스 — 보이는 복셀 메쉬 기준
  const visibleVoxelMeshes = Object.values(voxelMeshes);
  if (visibleVoxelMeshes.length > 0) {
    manager.focusOnAllMeshes(visibleVoxelMeshes);
  }

  uiState.statusMessage = `${modelCount}개 모델 로드 완료`;
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
      // 자동 오리엔테이션: CT Z(상하) → Three.js Y(상하) 변환
      autoOrientGeometry(geometry);

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

  const modelCount = sceneState.models.length;
  if (modelCount === 0) return;

  // ── 원점 중심화: STL 상대 위치 유지하면서 전체를 origin으로 이동 ──
  const allMeshes2 = sceneState.models.map(m => m.mesh);
  centerMeshesAtOrigin(allMeshes2);

  // ── 자동 복셀화 ──
  uiState.statusMessage = '복셀화 중...';
  await initializeVoxels();

  const visibleVoxelMeshes = Object.values(voxelMeshes);
  if (visibleVoxelMeshes.length > 0) {
    manager.focusOnAllMeshes(visibleVoxelMeshes);
  }

  uiState.statusMessage = `${modelCount}개 모델 로드 완료`;
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
 * 서버 경로에서 STL 파일을 fetch → Three.js 씬에 로드 (Step 9: DICOM 파이프라인 결과 로드)
 *
 * @param url  서버 경로 (예: /api/meshes/L4.stl)
 * @param name 모델 이름
 */
export async function loadSTLFromURL(url: string, name: string): Promise<void> {
  const manager = sceneState.manager;
  if (!manager) return;

  const response = await fetch(url);
  if (!response.ok) throw new Error(`STL 다운로드 실패: ${url} (${response.status})`);

  const buffer = await response.arrayBuffer();
  const geometry = stlLoader.parse(buffer);
  geometry.computeVertexNormals();

  // CT 좌표계 보정 (Z→Y)
  autoOrientGeometry(geometry);

  const material = new THREE.MeshStandardMaterial({
    color: _autoColor(name),
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
}

/** 구조 이름에 따른 자동 색상 할당 */
function _autoColor(name: string): number {
  const lower = name.toLowerCase();
  if (lower.includes('disc') || lower.includes('ivd')) return 0xdd9966;
  if (lower.includes('sacrum') || lower.includes('s1')) return 0xbbbbaa;
  if (lower.match(/l\d/)) return 0xccccbb;    // L1~L5 요추
  if (lower.match(/c\d/)) return 0xaaccbb;    // C1~C7 경추
  if (lower.match(/t\d/)) return 0xbbcccc;    // T1~T12 흉추
  return 0xcccccc;
}

/**
 * base64 인코딩된 바이너리 메쉬 데이터로 Three.js 메쉬 생성 → 씬에 추가.
 * DICOM 파이프라인 결과 메쉬 로드에 사용.
 *
 * @param data  메쉬 데이터 (name, vertices_b64, faces_b64, n_vertices, n_faces, color)
 */
export function loadMeshFromInlineData(
  data: {
    name: string;
    vertices_b64: string;
    faces_b64: string;
    n_vertices: number;
    n_faces: number;
    color?: string;
    material_type?: string;
  },
): void {
  const manager = sceneState.manager;
  if (!manager) return;

  const geometry = new THREE.BufferGeometry();

  // base64 → ArrayBuffer → Float32Array (정점)
  const vertsBinary = atob(data.vertices_b64);
  const vertsBytes = new Uint8Array(vertsBinary.length);
  for (let i = 0; i < vertsBinary.length; i++) {
    vertsBytes[i] = vertsBinary.charCodeAt(i);
  }
  const verts = new Float32Array(vertsBytes.buffer);
  geometry.setAttribute('position', new THREE.BufferAttribute(verts, 3));

  // base64 → ArrayBuffer → Int32Array → Uint32Array (면 인덱스)
  const facesBinary = atob(data.faces_b64);
  const facesBytes = new Uint8Array(facesBinary.length);
  for (let i = 0; i < facesBinary.length; i++) {
    facesBytes[i] = facesBinary.charCodeAt(i);
  }
  const indices = new Uint32Array(new Int32Array(facesBytes.buffer));
  geometry.setIndex(new THREE.BufferAttribute(indices, 1));

  geometry.computeVertexNormals();
  // CT 좌표계 보정 (Z→Y)
  autoOrientGeometry(geometry);

  // 색상: hex 문자열 또는 이름 기반 자동 색상
  const hexColor = data.color
    ? parseInt(data.color.replace('#', ''), 16)
    : _autoColor(data.name);

  const material = new THREE.MeshStandardMaterial({
    color: hexColor,
    roughness: 0.6,
    metalness: 0.1,
    transparent: false,
    opacity: 1.0,
    depthWrite: true,
    side: THREE.DoubleSide,
  });

  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = data.name;
  mesh.castShadow = true;
  mesh.receiveShadow = true;

  manager.scene.add(mesh);
  sceneState.addModel(data.name, mesh, {
    materialType: data.material_type ?? '',
    color: data.color ?? `#${hexColor.toString(16).padStart(6, '0')}`,
  });
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
