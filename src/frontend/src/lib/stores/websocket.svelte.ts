/**
 * WebSocket 연결 상태 관리 (Svelte 5 runes).
 */

import type { WSClient } from '$lib/ws/client';

class WebSocketState {
  /** WSClient 인스턴스 */
  client = $state<WSClient | null>(null);

  /** 연결 상태 */
  connected = $state(false);

  /** 마지막 에러 메시지 */
  lastError = $state<string | null>(null);

  /** 연결 상태 업데이트 */
  setConnected(value: boolean): void {
    this.connected = value;
    if (value) this.lastError = null;
  }

  /** 에러 설정 */
  setError(message: string): void {
    this.lastError = message;
  }
}

export const wsState = new WebSocketState();
