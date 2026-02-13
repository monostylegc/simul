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
class WSClient {
    constructor(url) {
        // 자동으로 현재 호스트 기반 WS URL 결정
        if (!url) {
            const loc = window.location;
            const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
            url = `${protocol}//${loc.host}/ws`;
        }
        this.url = url;
        this.ws = null;
        this.connected = false;

        // 콜백 레지스트리
        this._onProgress = null;
        this._onResult = null;
        this._onError = null;
        this._onConnect = null;
        this._onDisconnect = null;

        // 확장 콜백 (세그멘테이션, 메쉬, 재료)
        this._onSegmentResult = null;
        this._onMeshesResult = null;
        this._onMaterialResult = null;

        // DICOM 파이프라인 콜백
        this._onPipelineStep = null;
        this._onPipelineResult = null;

        // 자동 재연결
        this._reconnectTimer = null;
        this._reconnectDelay = 2000;
    }

    /**
     * 서버 연결
     */
    connect() {
        if (this.ws && this.ws.readyState <= 1) return; // 이미 연결됨

        try {
            this.ws = new WebSocket(this.url);
        } catch (e) {
            console.warn('WebSocket 연결 실패:', e.message);
            this._scheduleReconnect();
            return;
        }

        this.ws.onopen = () => {
            this.connected = true;
            console.log('WebSocket 연결됨:', this.url);
            if (this._onConnect) this._onConnect();
        };

        this.ws.onclose = () => {
            this.connected = false;
            console.log('WebSocket 연결 해제');
            if (this._onDisconnect) this._onDisconnect();
            this._scheduleReconnect();
        };

        this.ws.onerror = (e) => {
            console.warn('WebSocket 에러');
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                this._dispatch(msg);
            } catch (e) {
                console.error('WebSocket 메시지 파싱 실패:', e);
            }
        };
    }

    /**
     * 메시지 전송
     */
    send(type, data) {
        if (!this.ws || this.ws.readyState !== 1) {
            console.warn('WebSocket 미연결 — 메시지 전송 불가');
            if (this._onError) this._onError({ message: '서버 미연결' });
            return false;
        }
        this.ws.send(JSON.stringify({ type, data }));
        return true;
    }

    /**
     * 콜백 등록
     */
    onProgress(cb) { this._onProgress = cb; }
    onResult(cb)   { this._onResult = cb; }
    onError(cb)    { this._onError = cb; }
    onConnect(cb)  { this._onConnect = cb; }
    onDisconnect(cb) { this._onDisconnect = cb; }
    onSegmentResult(cb)  { this._onSegmentResult = cb; }
    onMeshesResult(cb)   { this._onMeshesResult = cb; }
    onMaterialResult(cb) { this._onMaterialResult = cb; }
    onPipelineStep(cb)   { this._onPipelineStep = cb; }
    onPipelineResult(cb) { this._onPipelineResult = cb; }

    /**
     * 연결 해제
     */
    disconnect() {
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

    _dispatch(msg) {
        switch (msg.type) {
            case 'progress':
                if (this._onProgress) this._onProgress(msg.data);
                break;
            case 'result':
                if (this._onResult) this._onResult(msg.data);
                break;
            case 'segment_result':
                if (this._onSegmentResult) this._onSegmentResult(msg.data);
                break;
            case 'meshes_result':
                if (this._onMeshesResult) this._onMeshesResult(msg.data);
                break;
            case 'material_result':
                if (this._onMaterialResult) this._onMaterialResult(msg.data);
                break;
            case 'pipeline_step':
                if (this._onPipelineStep) this._onPipelineStep(msg.data);
                break;
            case 'pipeline_result':
                if (this._onPipelineResult) this._onPipelineResult(msg.data);
                break;
            case 'error':
                console.error('서버 에러:', msg.data.message);
                if (this._onError) this._onError(msg.data);
                break;
            case 'pong':
                break;
            default:
                console.warn('알 수 없는 메시지:', msg.type);
        }
    }

    _scheduleReconnect() {
        if (this._reconnectTimer) return;
        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            console.log('WebSocket 재연결 시도...');
            this.connect();
        }, this._reconnectDelay);
    }
}
