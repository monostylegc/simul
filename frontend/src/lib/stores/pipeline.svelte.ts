/**
 * DICOM/NIfTI 파이프라인 상태 관리 (Svelte 5 runes).
 */

/** GPU 정보 */
export interface GpuInfo {
  available: boolean;
  name: string;
  memory_mb: number;
  cuda_version: string;
  driver_version: string;
}

/** 파이프라인 단계 */
export type PipelineStep =
  | 'idle'
  | 'uploading'
  | 'segmentation'
  | 'mesh_extraction'
  | 'material_assignment'
  | 'complete'
  | 'error';

/** 단계별 표시 정보 */
export const PIPELINE_STEP_INFO: Record<PipelineStep, { label: string; icon: string; order: number }> = {
  idle:                { label: '',                icon: '',   order: 0 },
  uploading:           { label: 'DICOM 변환',      icon: '📁', order: 1 },
  segmentation:        { label: '세그멘테이션',     icon: '🧠', order: 2 },
  mesh_extraction:     { label: '3D 모델 생성',    icon: '🔷', order: 3 },
  material_assignment: { label: '재료 할당',        icon: '🧪', order: 4 },
  complete:            { label: '완료',             icon: '✅', order: 5 },
  error:               { label: '오류',             icon: '❌', order: -1 },
};

class PipelineState {
  /** GPU 정보 (서버에서 조회) */
  gpuInfo = $state<GpuInfo | null>(null);

  /** GPU 정보 로드 완료 여부 */
  gpuChecked = $state(false);

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

  /** 추출된 메쉬 목록 (라벨 + 이름 + 재료 타입) */
  extractedMeshes = $state<Array<{ name: string; label?: number; material_type?: string }>>([]);

  /** 재료 할당 결과 */
  materialAssignments = $state<Record<string, string>>({});

  /** 파이프라인 시작 시각 (ms) */
  startTime = $state(0);

  /** 경과 시간 (초) — 타이머로 갱신 */
  elapsedSec = $state(0);

  /** 경과 시간 타이머 ID */
  private _timer: ReturnType<typeof setInterval> | null = null;

  /** 파이프라인 활성 여부 (오버레이 표시 조건) */
  get isActive(): boolean {
    return this.step !== 'idle' && this.step !== 'complete' && this.step !== 'error';
  }

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
    this._stopTimer();
  }

  /** 초기화 + 타이머 시작 */
  reset(): void {
    this.step = 'idle';
    this.progress = 0;
    this.message = '';
    this.error = null;
    this.segmentationPath = null;
    this.extractedMeshes = [];
    this.materialAssignments = {};
    this.startTime = Date.now();
    this.elapsedSec = 0;
    this._startTimer();
  }

  /** 파이프라인 완료 처리 */
  markComplete(): void {
    this._stopTimer();
  }

  /** 서버에서 GPU 정보 조회 */
  async fetchGpuInfo(): Promise<void> {
    try {
      const res = await fetch('/api/gpu-info');
      if (res.ok) {
        this.gpuInfo = await res.json();
      }
    } catch (e) {
      console.warn('GPU 정보 조회 실패:', e);
      this.gpuInfo = { available: false, name: 'N/A', memory_mb: 0, cuda_version: 'N/A', driver_version: 'N/A' };
    }
    this.gpuChecked = true;
  }

  /** GPU 사용 가능 여부 (편의 getter) */
  get hasGpu(): boolean {
    return this.gpuInfo?.available ?? false;
  }

  /** 최적 디바이스 자동 선택 */
  get autoDevice(): string {
    return this.hasGpu ? 'gpu' : 'cpu';
  }

  /** 경과 시간 타이머 시작 */
  private _startTimer(): void {
    this._stopTimer();
    this._timer = setInterval(() => {
      if (this.startTime > 0) {
        this.elapsedSec = Math.floor((Date.now() - this.startTime) / 1000);
      }
    }, 1000);
  }

  /** 경과 시간 타이머 정지 */
  private _stopTimer(): void {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }
}

export const pipelineState = new PipelineState();
