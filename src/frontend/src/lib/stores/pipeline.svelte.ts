/**
 * DICOM/NIfTI 파이프라인 상태 관리 (Svelte 5 runes).
 */

/** 파이프라인 단계 */
export type PipelineStep =
  | 'idle'
  | 'uploading'
  | 'segmentation'
  | 'mesh_extraction'
  | 'material_assignment'
  | 'complete'
  | 'error';

class PipelineState {
  /** 현재 단계 */
  step = $state<PipelineStep>('idle');

  /** 진행률 (0~1) */
  progress = $state(0);

  /** 상태 메시지 */
  message = $state('');

  /** 에러 메시지 */
  error = $state<string | null>(null);

  /** 세그멘테이션 결과 (NRRD 경로) */
  segmentationPath = $state<string | null>(null);

  /** 추출된 메쉬 목록 */
  extractedMeshes = $state<Array<{ name: string; path: string }>>([]);

  /** 재료 할당 결과 */
  materialAssignments = $state<Record<string, string>>({});

  /** 진행 업데이트 */
  updateProgress(step: PipelineStep, progress: number, message: string): void {
    this.step = step;
    this.progress = progress;
    this.message = message;
  }

  /** 에러 설정 */
  setError(message: string): void {
    this.step = 'error';
    this.error = message;
  }

  /** 초기화 */
  reset(): void {
    this.step = 'idle';
    this.progress = 0;
    this.message = '';
    this.error = null;
    this.segmentationPath = null;
    this.extractedMeshes = [];
    this.materialAssignments = {};
  }
}

export const pipelineState = new PipelineState();
