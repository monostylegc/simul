/**
 * WebSocket 클라이언트 — Python 서버와 실시간 통신
 *
 * 프로토콜:
 *   → {"type": "run_analysis",   "data": AnalysisRequest}
 *   → {"type": "segment",        "data": SegmentationRequest}
 *   → {"type": "extract_meshes", "data": MeshExtractRequest}
 *   → {"type": "auto_material",  "data": AutoMaterialRequest}
 *   ← {"type": "progress",          "data": {...}}
 *   ← {"type": "result",            "data": {...}}
 *   ← {"type": "segment_result",    "data": {...}}
 *   ← {"type": "meshes_result",     "data": {...}}
 *   ← {"type": "material_result",   "data": {...}}
 *   ← {"type": "error",             "data": {"message": "..."}}
 */

import type {
  WSMessage,
  ProgressCallback,
  ResultCallback,
  ErrorCallback,
  ConnectCallback,
  DisconnectCallback,
  SegmentResultCallback,
  MeshesResultCallback,
  MaterialResultCallback,
  PipelineStepCallback,
  PipelineResultCallback,
} from './types';

export class WSClient {
  url: string;
  ws: WebSocket | null = null;
  connected = false;

  // 콜백 레지스트리
  private _onProgress: ProgressCallback | null = null;
  private _onResult: ResultCallback | null = null;
  private _onError: ErrorCallback | null = null;
  private _onConnect: ConnectCallback | null = null;
  private _onDisconnect: DisconnectCallback | null = null;

  // 확장 콜백 (세그멘테이션, 메쉬, 재료)
  private _onSegmentResult: SegmentResultCallback | null = null;
  private _onMeshesResult: MeshesResultCallback | null = null;
  private _onMaterialResult: MaterialResultCallback | null = null;

  // DICOM 파이프라인 콜백
  private _onPipelineStep: PipelineStepCallback | null = null;
  private _onPipelineResult: PipelineResultCallback | null = null;

  // 자동 재연결
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private _reconnectDelay = 2000;

  constructor(url?: string) {
    // 자동으로 현재 호스트 기반 WS URL 결정
    if (!url) {
      const loc = window.location;
      const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      url = `${protocol}//${loc.host}/ws`;
    }
    this.url = url;
  }

  /**
   * 서버 연결
   */
  connect(): void {
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return;

    try {
      this.ws = new WebSocket(this.url);
    } catch (e) {
      console.warn('WebSocket 연결 실패:', (e as Error).message);
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.connected = true;
      console.log('WebSocket 연결됨:', this.url);
      this._onConnect?.();
    };

    this.ws.onclose = () => {
      this.connected = false;
      console.log('WebSocket 연결 해제');
      this._onDisconnect?.();
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      console.warn('WebSocket 에러');
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        this._dispatch(msg);
      } catch (e) {
        console.error('WebSocket 메시지 파싱 실패:', e);
      }
    };
  }

  /**
   * 메시지 전송
   */
  send(type: string, data: unknown): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('WebSocket 미연결 — 메시지 전송 불가');
      this._onError?.({ message: '서버 미연결' });
      return false;
    }
    this.ws.send(JSON.stringify({ type, data }));
    return true;
  }

  /**
   * 콜백 등록
   */
  onProgress(cb: ProgressCallback): void { this._onProgress = cb; }
  onResult(cb: ResultCallback): void { this._onResult = cb; }
  onError(cb: ErrorCallback): void { this._onError = cb; }
  onConnect(cb: ConnectCallback): void { this._onConnect = cb; }
  onDisconnect(cb: DisconnectCallback): void { this._onDisconnect = cb; }
  onSegmentResult(cb: SegmentResultCallback): void { this._onSegmentResult = cb; }
  onMeshesResult(cb: MeshesResultCallback): void { this._onMeshesResult = cb; }
  onMaterialResult(cb: MaterialResultCallback): void { this._onMaterialResult = cb; }
  onPipelineStep(cb: PipelineStepCallback): void { this._onPipelineStep = cb; }
  onPipelineResult(cb: PipelineResultCallback): void { this._onPipelineResult = cb; }

  /**
   * 연결 해제
   */
  disconnect(): void {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null; // 재연결 방지
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
  }

  // ── 내부 메서드 ──

  private _dispatch(msg: WSMessage): void {
    switch (msg.type) {
      case 'progress':
        this._onProgress?.(msg.data as Parameters<ProgressCallback>[0]);
        break;
      case 'result':
        this._onResult?.(msg.data as Parameters<ResultCallback>[0]);
        break;
      case 'segment_result':
        this._onSegmentResult?.(msg.data as Parameters<SegmentResultCallback>[0]);
        break;
      case 'meshes_result':
        this._onMeshesResult?.(msg.data as Parameters<MeshesResultCallback>[0]);
        break;
      case 'material_result':
        this._onMaterialResult?.(msg.data as Parameters<MaterialResultCallback>[0]);
        break;
      case 'pipeline_step':
        this._onPipelineStep?.(msg.data as Parameters<PipelineStepCallback>[0]);
        break;
      case 'pipeline_result':
        this._onPipelineResult?.(msg.data as Parameters<PipelineResultCallback>[0]);
        break;
      case 'error':
        console.error('서버 에러:', (msg.data as { message: string }).message);
        this._onError?.(msg.data as Parameters<ErrorCallback>[0]);
        break;
      case 'pong':
        break;
      default:
        console.warn('알 수 없는 메시지:', msg.type);
    }
  }

  private _scheduleReconnect(): void {
    if (this._reconnectTimer) return;
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      console.log('WebSocket 재연결 시도...');
      this.connect();
    }, this._reconnectDelay);
  }
}
