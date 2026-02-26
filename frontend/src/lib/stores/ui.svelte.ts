/**
 * UI 상태 관리 (Svelte 5 runes).
 *
 * 활성 탭, 상태바 메시지, 토스트 알림 등.
 */

/** 탭 타입 */
export type TabId = 'file' | 'modeling' | 'material' | 'preprocess' | 'solve' | 'postprocess';

/** 토스트 타입 */
export type ToastLevel = 'info' | 'success' | 'error' | 'warn';

export interface Toast {
  id: number;
  message: string;
  level: ToastLevel;
}

let _toastId = 0;

class UIState {
  activeTab = $state<TabId>('file');
  statusMessage = $state('Ready');
  currentTool = $state<string | null>(null);

  /** 토스트 알림 목록 */
  toasts = $state<Toast[]>([]);

  /** 확인 다이얼로그 상태 */
  confirmDialog = $state<{
    title: string;
    message: string;
    resolve: (ok: boolean) => void;
  } | null>(null);

  /** 토스트 알림 표시 (3초 후 자동 제거) */
  toast(message: string, level: ToastLevel = 'info'): void {
    const id = ++_toastId;
    this.toasts = [...this.toasts, { id, message, level }];
    setTimeout(() => {
      this.toasts = this.toasts.filter(t => t.id !== id);
    }, 3000);
  }

  /** 확인 다이얼로그 (Promise 기반) */
  confirm(title: string, message: string): Promise<boolean> {
    return new Promise(resolve => {
      this.confirmDialog = { title, message, resolve };
    });
  }

  /** 확인 다이얼로그 닫기 */
  closeConfirm(result: boolean): void {
    this.confirmDialog?.resolve(result);
    this.confirmDialog = null;
  }
}

export const uiState = new UIState();
