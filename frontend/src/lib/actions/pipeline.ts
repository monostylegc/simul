/**
 * DICOM/NIfTI 파이프라인 액션
 * — 업로드 → 세그멘테이션 → 메쉬 추출 → 재료 할당
 */

import { pipelineState } from '$lib/stores/pipeline.svelte';
import { wsState } from '$lib/stores/websocket.svelte';
import { uiState } from '$lib/stores/ui.svelte';
import { sceneState } from '$lib/stores/scene.svelte';
import { analysisState } from '$lib/stores/analysis.svelte';
import { WSClient } from '$lib/ws/client';
import {
  loadMeshFromInlineData,
  centerMeshesAtOrigin,
  initializeVoxels,
} from './loading';
import { assignMaterial } from './analysis';
import type { ResolvedMaterial } from '$lib/analysis/PreProcessor';
import type {
  PipelineStepData,
  PipelineResultData,
  PipelineMeshData,
  SegmentResultData,
  MeshesResultData,
  MaterialResultData,
} from '$lib/ws/types';

/**
 * DICOM 파이프라인 실행
 */
export async function runDicomPipeline(
  files: FileList,
  options: {
    engine?: string;
    device?: string;
    fast?: boolean;
    smooth?: boolean;
    resolution?: number;
  } = {},
): Promise<void> {
  // GPU 정보 미조회 시 사전 확인
  if (!pipelineState.gpuChecked) {
    await pipelineState.fetchGpuInfo();
  }

  pipelineState.reset();
  pipelineState.updateProgress('uploading', 0, 'Uploading DICOM files...');

  // WebSocket 연결 확인
  if (!wsState.client) {
    const client = new WSClient();
    wsState.client = client;
    client.onConnect(() => wsState.setConnected(true));
    client.onDisconnect(() => wsState.setConnected(false));
    client.connect();
  }

  // 파이프라인 콜백 등록
  const client = wsState.client!;
  client.onPipelineStep(_onPipelineStep);
  client.onPipelineResult(_onPipelineResult);
  client.onSegmentResult(_onSegmentResult);
  client.onMeshesResult(_onMeshesResult);
  client.onMaterialResult(_onMaterialResult);

  try {
    // 1단계: REST로 DICOM 업로드
    const formData = new FormData();
    for (const file of Array.from(files)) {
      formData.append('files', file);
    }

    const response = await fetch('/api/upload_dicom', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }

    const uploadData = await response.json();
    pipelineState.updateProgress('uploading', 1.0, `Uploaded ${uploadData.n_files} files`);

    // 2단계: WebSocket으로 파이프라인 시작
    client.send('run_dicom_pipeline', {
      dicom_dir: uploadData.dicom_dir,
      engine: options.engine ?? 'auto',
      device: options.device ?? pipelineState.autoDevice,
      fast: options.fast ?? false,
      smooth: options.smooth ?? true,
      resolution: options.resolution ?? 64,
    });

  } catch (e) {
    pipelineState.setError((e as Error).message);
    uiState.statusMessage = `Pipeline error: ${(e as Error).message}`;
  }
}

/**
 * 단일 NIfTI 파일로 세그멘테이션 요청
 */
export function requestSegmentation(niftiPath: string): void {
  const client = wsState.client;
  if (!client?.connected) {
    uiState.statusMessage = 'Server not connected';
    return;
  }

  pipelineState.updateProgress('segmentation', 0, 'Running segmentation...');
  client.send('segment', { nifti_path: niftiPath });
}

/**
 * 세그멘테이션 결과에서 메쉬 추출 요청
 */
export function requestMeshExtraction(segPath: string, labels?: Record<string, number>): void {
  const client = wsState.client;
  if (!client?.connected) {
    uiState.statusMessage = 'Server not connected';
    return;
  }

  pipelineState.updateProgress('mesh_extraction', 0, 'Extracting meshes...');
  client.send('extract_meshes', { seg_path: segPath, labels });
}

/**
 * 자동 재료 할당 요청
 */
export function requestAutoMaterial(meshNames: string[]): void {
  const client = wsState.client;
  if (!client?.connected) {
    uiState.statusMessage = 'Server not connected';
    return;
  }

  pipelineState.updateProgress('material_assignment', 0, 'Auto-assigning materials...');
  client.send('auto_material', { mesh_names: meshNames });
}

// ── 내부 콜백 ──

function _onPipelineStep(data: PipelineStepData): void {
  const stepMap: Record<string, typeof pipelineState.step> = {
    dicom_convert: 'uploading',
    dicom_convert_done: 'uploading',
    segmentation: 'segmentation',
    segmentation_done: 'segmentation',
    mesh_extract: 'mesh_extraction',
    mesh_extract_done: 'mesh_extraction',
    material_assign: 'material_assignment',
    material_assign_done: 'material_assignment',
  };

  const step = stepMap[data.step] ?? pipelineState.step;
  const isDone = data.step.endsWith('_done');
  pipelineState.updateProgress(step, isDone ? 1.0 : 0.5, data.message ?? data.step);
}

async function _onPipelineResult(data: PipelineResultData): Promise<void> {
  pipelineState.updateProgress('complete', 1.0, 'Pipeline complete');
  pipelineState.markComplete();

  if (data.meshes && data.meshes.length > 0) {
    // 파이프라인 상태에 메쉬 정보 저장
    pipelineState.extractedMeshes = data.meshes.map(m => ({
      name: m.name,
      label: m.label,
      material_type: m.material_type,
    }));

    // ── base64 인코딩 메쉬 데이터로 Three.js 씬에 직접 로드 ──
    await _loadPipelineMeshes(data.meshes);

    // ── 자동 재료 할당 (material_type → 기본 물성치) ──
    _autoAssignMaterials(data.meshes);

    // ── 자동 BC 추천 (SACRUM → 고정, 최상위 척추 → 하중) ──
    _suggestBoundaryConditions(data.meshes);
  }

  // 환자 정보 로그
  if (data.patient_info) {
    const pi = data.patient_info;
    console.log(`환자 정보: ${pi.patient_name ?? ''} (${pi.modality ?? ''}, ${pi.study_date ?? ''})`);
  }

  uiState.statusMessage = 'DICOM pipeline complete';
  uiState.activeTab = 'file';
}

/**
 * 파이프라인 결과 메쉬를 인라인 vertices/faces 데이터로 Three.js 씬에 로드.
 * 로드 후 원점 중심화 + 자동 복셀화까지 실행.
 */
async function _loadPipelineMeshes(meshes: PipelineMeshData[]): Promise<void> {
  let loaded = 0;
  for (const mesh of meshes) {
    try {
      loadMeshFromInlineData({
        name: mesh.name,
        vertices_b64: mesh.vertices_b64,
        faces_b64: mesh.faces_b64,
        n_vertices: mesh.n_vertices,
        n_faces: mesh.n_faces,
        color: mesh.color,
        material_type: mesh.material_type,
      });
      loaded++;
    } catch (e) {
      console.error(`파이프라인 메쉬 로드 실패: ${mesh.name}`, e);
    }
  }

  if (loaded > 0) {
    // 원점 중심화 (CT 좌표 → 원점 근처)
    const allMeshes = sceneState.models.map(m => m.mesh);
    centerMeshesAtOrigin(allMeshes);

    // 자동 복셀화
    await initializeVoxels();
    uiState.toast(`${loaded}개 구조물 자동 로드 완료`, 'success');

    // 카메라 포커스
    const mgr = sceneState.manager;
    if (mgr && sceneState.models.length > 0) {
      mgr.focusOnAllMeshes(sceneState.models.map(m => m.mesh));
    }
  }
}

function _onSegmentResult(data: SegmentResultData): void {
  if (data.nrrd_path) {
    pipelineState.segmentationPath = data.nrrd_path;
  }
  pipelineState.updateProgress('segmentation', 1.0, 'Segmentation complete');
}

function _onMeshesResult(data: MeshesResultData): void {
  if (data.meshes) {
    pipelineState.extractedMeshes = data.meshes.map(m => ({ name: m.name }));
  }
  pipelineState.updateProgress('mesh_extraction', 1.0, 'Mesh extraction complete');
}

function _onMaterialResult(data: MaterialResultData): void {
  if (data.assignments) {
    pipelineState.materialAssignments = data.assignments;
  }
  pipelineState.updateProgress('material_assignment', 1.0, 'Material assignment complete');
}

// ── 자동 재료/BC 추천 ──

/** material_type별 기본 물성치 매핑 */
const MATERIAL_TYPE_DEFAULTS: Record<string, ResolvedMaterial> = {
  bone: {
    key: 'cortical_bone', label: '피질골',
    E: 15e9, nu: 0.3, density: 1850,
    constitutiveModel: 'linear_elastic',
  },
  disc: {
    key: 'disc_annulus', label: '추간판 (섬유륜)',
    E: 10e6, nu: 0.45, density: 1050,
    constitutiveModel: 'linear_elastic',
  },
  soft_tissue: {
    key: 'ligament', label: '인대',
    E: 50e6, nu: 0.4, density: 1100,
    constitutiveModel: 'linear_elastic',
  },
};

/**
 * 파이프라인 메쉬의 material_type에 따라 기본 재료를 자동 할당.
 * PreProcessor가 초기화된 경우에만 실행.
 * 사용자가 Material 탭에서 개별 수정 가능.
 */
function _autoAssignMaterials(meshes: PipelineMeshData[]): void {
  if (!analysisState.preProcessor) return;

  let assigned = 0;
  for (const mesh of meshes) {
    const defaultMat = MATERIAL_TYPE_DEFAULTS[mesh.material_type];
    if (defaultMat) {
      assignMaterial(mesh.name, defaultMat);
      assigned++;
    }
  }

  if (assigned > 0) {
    analysisState.updateMaterialCount();
    uiState.toast(`${assigned}개 구조물에 기본 재료 자동 할당됨`, 'info');
  }
}

/**
 * 세그멘테이션 라벨 기반 경계조건 자동 추천.
 * - SACRUM → "하부 고정 (Fixed BC)"
 * - 최상위 척추 → "상면 하중 (Force BC) 500N"
 *
 * 실제 적용은 하지 않고 suggestedBCs에 저장 → PreProcessPanel에서 확인/적용.
 */
function _suggestBoundaryConditions(meshes: PipelineMeshData[]): void {
  const suggestions: typeof analysisState.suggestedBCs = [];

  // 척추 이름 순서 (상→하)
  const VERTEBRA_ORDER = [
    'C1','C2','C3','C4','C5','C6','C7',
    'T1','T2','T3','T4','T5','T6','T7','T8','T9','T10','T11','T12',
    'L1','L2','L3','L4','L5','SACRUM',
  ];

  // 뼈 모델만 추출 + 척추 순서로 정렬
  const boneModels = meshes
    .filter(m => m.material_type === 'bone')
    .sort((a, b) => {
      const idxA = VERTEBRA_ORDER.indexOf(a.name);
      const idxB = VERTEBRA_ORDER.indexOf(b.name);
      return (idxA < 0 ? 999 : idxA) - (idxB < 0 ? 999 : idxB);
    });

  if (boneModels.length === 0) return;

  // SACRUM 또는 최하위 척추 → Fixed BC 추천
  const bottomBone = boneModels[boneModels.length - 1];
  suggestions.push({
    meshName: bottomBone.name,
    type: 'fixed',
    label: `${bottomBone.name} 하부 고정`,
    applied: false,
  });

  // 최상위 척추 → Force BC 추천 (500N 압축)
  const topBone = boneModels[0];
  if (topBone.name !== bottomBone.name) {
    suggestions.push({
      meshName: topBone.name,
      type: 'force',
      label: `${topBone.name} 상면 하중 500N`,
      magnitude: 500,
      direction: [0, -1, 0],
      applied: false,
    });
  }

  analysisState.suggestedBCs = suggestions;

  if (suggestions.length > 0) {
    const labels = suggestions.map(s => s.label).join(', ');
    uiState.toast(`자동 BC 제안: ${labels}`, 'info');
  }
}
