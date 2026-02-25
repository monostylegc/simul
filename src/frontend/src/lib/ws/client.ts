/**
 * WebSocket 클라이언트 — Python 서버와 실시간 통신
 *
 * 프로토콜:
 *   → {"type": "run_analysis",      "data": AnalysisRequest}
 *   → {"type": "cancel_analysis",   "data": {"request_id": "..."}}
 *   → {"type": "segment",           "data": SegmentationRequest}
 *   → {"type": "extract_meshes",    "data": MeshExtractRequest}
 *   → {"type": "auto_material",     "data": AutoMaterialRequest}
 *   ← {"type": "progress",          "data": {...}}
 *   ← {"type": "result",            "data": {...}}
 *   ← {"type": "cancelled",         "data": {"request_id": "..."}}
 *   ← {"type": "error",             "data": {"message": "..."}}
 *
 * 기능:
 *   - 해석 타임아웃 (기본 10분)
 *   - 해석 취소 요청
 *   - 지수 백오프 자동 재연결 (최대 5회)
 *   - 재연결 시 해석 진행 상태 확인
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
  ImplantMeshResultCallback,
  GuidelineMeshResultCallback,
  CancelledCallback,
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

  // 임플란트/가이드라인 콜백
  private _onImplantMeshResult: ImplantMeshResultCallback | null = null;
  private _onGuidelineMeshResult: GuidelineMeshResultCallback | null = null;

  // 취소 콜백
  private _onCancelled: CancelledCallback | null = null;

  // ── 해석 타임아웃/취소 ──
  private _solveTimeout: ReturnType<typeof setTimeout> | null = null;
  private _currentRequestId: string | null = null;

  /** 해석 타임아웃 (ms). 기본 10분 */
  solveTimeoutMs = 600_000;

  // ── 지수 백오프 재연결 ──
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private _reconnectAttempt = 0;
  /** 최대 재연결 시도 횟수 */
  maxReconnect = 5;

  constructor(url?: string) {
    // 자동으로 현재 호스트 기반 WS URL 결정
    if (!url) {
      const loc = window.location;
      const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      url = `${protocol}//${loc.host}/ws`;
    }
    this.url = url;
  }

  // ====================================================================
  // 연결 관리
  // ====================================================================

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
      this._reconnectAttempt = 0;  // 성공 시 카운터 리셋
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
   * 연결 해제
   */
  disconnect(): void {
    this._clearSolveTimeout();
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

  // ====================================================================
  // 해석 타임아웃/취소 (Step 2)
  // ====================================================================

  /**
   * 해석 요청 전송 + 타임아웃 설정.
   * 기존 send('run_analysis', ...) 대신 이 메서드 사용 권장.
   */
  sendAnalysis(request: unknown, timeoutMs?: number): boolean {
    this._currentRequestId = crypto.randomUUID();
    const ok = this.send('run_analysis', {
      ...request as Record<string, unknown>,
      request_id: this._currentRequestId,
    });

    if (ok) {
      this._startSolveTimeout(timeoutMs ?? this.solveTimeoutMs);
    }
    return ok;
  }

  /**
   * 해석 취소 요청.
   * 서버에 cancel_analysis 메시지를 보내고 타임아웃 정리.
   */
  cancelAnalysis(): void {
    if (this._currentRequestId) {
      this.send('cancel_analysis', { request_id: this._currentRequestId });
      this._clearSolveTimeout();
      this._currentRequestId = null;
    }
  }

  /** 현재 진행 중인 해석 요청 ID */
  get currentRequestId(): string | null {
    return this._currentRequestId;
  }

  // ====================================================================
  // 콜백 등록
  // ====================================================================

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
  onImplantMeshResult(cb: ImplantMeshResultCallback): void { this._onImplantMeshResult = cb; }
  onGuidelineMeshResult(cb: GuidelineMeshResultCallback): void { this._onGuidelineMeshResult = cb; }
  onCancelled(cb: CancelledCallback): void { this._onCancelled = cb; }

  // ====================================================================
  // 내부: 메시지 디스패치
  // ====================================================================

  private _dispatch(msg: WSMessage): void {
    switch (msg.type) {
      case 'progress':
        this._onProgress?.(msg.data as Parameters<ProgressCallback>[0]);
        break;
      case 'result':
        this._clearSolveTimeout();
        this._currentRequestId = null;
        this._onResult?.(msg.data as Parameters<ResultCallback>[0]);
        break;
      case 'cancelled':
        this._clearSolveTimeout();
        this._currentRequestId = null;
        this._onCancelled?.(msg.data as Parameters<CancelledCallback>[0]);
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
      case 'implant_mesh_result':
        this._onImplantMeshResult?.(msg.data as Parameters<ImplantMeshResultCallback>[0]);
        break;
      case 'guideline_meshes_result':
        this._onGuidelineMeshResult?.(msg.data as Parameters<GuidelineMeshResultCallback>[0]);
        break;
      case 'error':
        this._clearSolveTimeout();
        this._currentRequestId = null;
        console.error('서버 에러:', (msg.data as { message: string }).message);
        this._onError?.(msg.data as Parameters<ErrorCallback>[0]);
        break;
      case 'pong':
        break;
      default:
        console.warn('알 수 없는 메시지:', msg.type);
    }
  }

  // ====================================================================
  // 내부: 타임아웃 관리
  // ====================================================================

  private _startSolveTimeout(ms: number): void {
    this._clearSolveTimeout();
    this._solveTimeout = setTimeout(() => {
      console.warn(`해석 타임아웃 (${ms / 1000}초 초과)`);
      this.cancelAnalysis();
      // 에러 콜백 호출로 UI 상태 정리
      this._onError?.({ message: `해석 타임아웃 (${Math.floor(ms / 60000)}분 초과) — 메쉬를 단순화하거나 서버 상태를 확인하세요` });
    }, ms);
  }

  private _clearSolveTimeout(): void {
    if (this._solveTimeout) {
      clearTimeout(this._solveTimeout);
      this._solveTimeout = null;
    }
  }

  // ====================================================================
  // 내부: 지수 백오프 재연결 (Step 3)
  // ====================================================================

  private _scheduleReconnect(): void {
    if (this._reconnectTimer) return;
    if (this._reconnectAttempt >= this.maxReconnect) {
      console.error(`WebSocket 재연결 ${this.maxReconnect}회 실패 — 포기`);
      this._onError?.({ message: `서버 연결 ${this.maxReconnect}회 실패 — 서버를 확인하세요` });
      return;
    }

    // 지수 백오프: 2s, 4s, 8s, 16s, 30s (최대)
    const delay = Math.min(2000 * Math.pow(2, this._reconnectAttempt), 30000);
    this._reconnectAttempt++;

    console.log(`WebSocket 재연결 시도 ${this._reconnectAttempt}/${this.maxReconnect} (${delay / 1000}초 후)...`);

    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this.connect();
    }, delay);
  }

  /** 재연결 카운터 리셋 (수동 재연결 시) */
  resetReconnect(): void {
    this._reconnectAttempt = 0;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  }
}
