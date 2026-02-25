/**
 * WebSocket 연결 상태 관리 (Svelte 5 runes).
 *
 * 상태: disconnected → connecting → connected → failed
 */

import type { WSClient } from '$lib/ws/client';

/** 연결 상태 */
export type WSStatus = 'disconnected' | 'connecting' | 'connected' | 'failed';

class WebSocketState {
  /** WSClient 인스턴스 */
  client = $state<WSClient | null>(null);

  /** 연결 상태 */
  connected = $state(false);

  /** 상세 연결 상태 */
  status = $state<WSStatus>('disconnected');

  /** 마지막 에러 메시지 */
  lastError = $state<string | null>(null);

  /** 재연결 시도 횟수 */
  reconnectAttempt = $state(0);

  /** 최대 재연결 횟수 */
  maxReconnect = $state(5);

  /** 연결 상태 업데이트 */
  setConnected(value: boolean): void {
    this.connected = value;
    this.status = value ? 'connected' : 'disconnected';
    if (value) {
      this.lastError = null;
      this.reconnectAttempt = 0;
    }
  }

  /** 에러 설정 */
  setError(message: string): void {
    this.lastError = message;
  }

  /** 연결 실패 (최대 재시도 초과) */
  setFailed(): void {
    this.status = 'failed';
    this.connected = false;
  }
}

export const wsState = new WebSocketState();
