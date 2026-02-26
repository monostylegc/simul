/**
 * WebSocket 메시지 타입 정의
 */

// ── 서버 → 클라이언트 메시지 타입 ──

export type WSMessageType =
  | 'progress'
  | 'result'
  | 'segment_result'
  | 'meshes_result'
  | 'material_result'
  | 'pipeline_step'
  | 'pipeline_result'
  | 'implant_mesh_result'
  | 'guideline_meshes_result'
  | 'cancelled'
  | 'error'
  | 'pong';

// ── 클라이언트 → 서버 요청 타입 ──

export type WSRequestType =
  | 'run_analysis'
  | 'cancel_analysis'
  | 'segment'
  | 'extract_meshes'
  | 'auto_material'
  | 'pipeline'
  | 'get_implant_mesh'
  | 'get_guideline_meshes';

// ── 메시지 구조 ──

export interface WSMessage {
  type: WSMessageType;
  data: unknown;
}

export interface WSRequest {
  type: WSRequestType;
  data: unknown;
}

// ── 진행률 ──

export interface ProgressData {
  step: string;
  progress: number;
  message?: string;
}

// ── 해석 결과 ──

/** FEM 영역 결과 (볼륨 메쉬 기반) */
export interface FEMRegionResult {
  name: string;
  displacements: number[][];  // (n_nodes, 3) 노드별 변위
  stress: number[];           // (n_nodes,) 노드별 von Mises 응력
  nodes: number[][];          // (n_nodes, 3) 참조 좌표
  elements: number[][];       // (n_elements, 8) HEX8 연결정보
}

/** 입자 영역 결과 (PD/SPG 포인트 클라우드) */
export interface ParticleRegionResult {
  name: string;
  displacements: number[][];  // (n_particles, 3) 입자별 변위
  stress: number[];           // (n_particles,) 입자별 응력
  damage: number[];           // (n_particles,) 입자별 손상도
  positions: number[][];      // (n_particles, 3) 참조 좌표
}

export interface AnalysisResultData {
  /** 레거시 플랫 배열 (하위 호환) */
  displacements: number[][];
  stress: number[] | number[][];
  damage?: number[];
  info: {
    method: string;
    n_particles: number;
    converged: boolean;
    iterations?: number;
    time_seconds?: number;
    multi_solver?: boolean;
    solver_groups?: Record<string, string[]>;
  };
  /** FEM 영역별 볼륨 메쉬 결과 */
  fem_regions?: FEMRegionResult[];
  /** PD/SPG 영역별 포인트 클라우드 결과 */
  particle_regions?: ParticleRegionResult[];
}

// ── 에러 ──

export interface ErrorData {
  message: string;
}

// ── 세그멘테이션 결과 ──

export interface SegmentResultData {
  nrrd_path?: string;
  labels?: Record<string, number>;
  [key: string]: unknown;
}

// ── 메쉬 추출 결과 ──

export interface MeshesResultData {
  meshes?: Array<{
    name: string;
    path: string;
    vertices: number;
    faces: number;
  }>;
  [key: string]: unknown;
}

// ── 재료 결과 ──

export interface MaterialResultData {
  assignments?: Record<string, string>;
  [key: string]: unknown;
}

// ── 파이프라인 ──

export interface PipelineStepData {
  step: string;
  status: string;
  message?: string;
}

/** 파이프라인에서 추출된 개별 메쉬 데이터 (base64 바이너리 인코딩) */
export interface PipelineMeshData {
  label: number;
  name: string;
  vertices_b64: string;    // base64 인코딩 Float32Array (n_vertices * 3 * 4 bytes)
  faces_b64: string;       // base64 인코딩 Int32Array (n_faces * 3 * 4 bytes)
  material_type: string;   // "bone" | "disc" | "soft_tissue" | "unknown"
  color: string;           // 16진 색상 (예: "#e6d5c3")
  bounds: { min: number[]; max: number[] };
  n_vertices: number;
  n_faces: number;
}

export interface PipelineResultData {
  meshes?: PipelineMeshData[];
  nifti_path?: string;
  labels_path?: string;
  seg_info?: Array<{
    label: number;
    name: string;
    material_type: string;
    voxel_count: number;
  }>;
  patient_info?: Record<string, string>;
  [key: string]: unknown;
}

// ── 임플란트/가이드라인 ──

/** 단일 메쉬 데이터 (임플란트·가이드라인 공통) */
export interface MeshData {
  name: string;
  vertices: number[][];               // (N, 3) float
  faces: number[][];                  // (M, 3) int
  color: [number, number, number];    // RGB 0~1
}

/** 임플란트 메쉬 생성 결과 */
export interface ImplantMeshResult extends MeshData {
  implant_type: 'screw' | 'cage' | 'rod';
}

/** 가이드라인 메쉬 생성 결과 (양측 경로/안전영역/마커 포함) */
export interface GuidelineMeshResult {
  vertebra_name: string;
  meshes: MeshData[];
}

// ── 콜백 타입 ──

export type ProgressCallback = (data: ProgressData) => void;
export type ResultCallback = (data: AnalysisResultData) => void;
export type ErrorCallback = (data: ErrorData) => void;
export type ConnectCallback = () => void;
export type DisconnectCallback = () => void;
export type SegmentResultCallback = (data: SegmentResultData) => void;
export type MeshesResultCallback = (data: MeshesResultData) => void;
export type MaterialResultCallback = (data: MaterialResultData) => void;
export type PipelineStepCallback = (data: PipelineStepData) => void;
export type PipelineResultCallback = (data: PipelineResultData) => void;
export type ImplantMeshResultCallback = (data: ImplantMeshResult) => void;
export type GuidelineMeshResultCallback = (data: GuidelineMeshResult) => void;
export type CancelledCallback = (data: { request_id: string }) => void;
