/**
 * DICOM/NIfTI 파이프라인 액션
 * — 업로드 → 세그멘테이션 → 메쉬 추출 → 재료 할당
 */

import { pipelineState } from '$lib/stores/pipeline.svelte';
import { wsState } from '$lib/stores/websocket.svelte';
import { uiState } from '$lib/stores/ui.svelte';
import { sceneState } from '$lib/stores/scene.svelte';
import { WSClient } from '$lib/ws/client';
import { loadNRRDFile } from './loading';
import type {
  PipelineStepData,
  PipelineResultData,
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
      device: options.device ?? 'gpu',
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

function _onPipelineResult(data: PipelineResultData): void {
  pipelineState.updateProgress('complete', 1.0, 'Pipeline complete');

  if (data.meshes) {
    pipelineState.extractedMeshes = data.meshes;
  }

  uiState.statusMessage = 'DICOM pipeline complete';
  uiState.activeTab = 'file';
}

function _onSegmentResult(data: SegmentResultData): void {
  if (data.nrrd_path) {
    pipelineState.segmentationPath = data.nrrd_path;
  }
  pipelineState.updateProgress('segmentation', 1.0, 'Segmentation complete');
}

function _onMeshesResult(data: MeshesResultData): void {
  if (data.meshes) {
    pipelineState.extractedMeshes = data.meshes.map(m => ({ name: m.name, path: m.path }));
  }
  pipelineState.updateProgress('mesh_extraction', 1.0, 'Mesh extraction complete');
}

function _onMaterialResult(data: MaterialResultData): void {
  if (data.assignments) {
    pipelineState.materialAssignments = data.assignments;
  }
  pipelineState.updateProgress('material_assignment', 1.0, 'Material assignment complete');
}
