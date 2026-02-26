/**
 * Undo/Redo 히스토리 관리 (Svelte 5 runes).
 *
 * 복셀 스냅샷 기반 — 드릴/편집 전후 상태를 저장.
 */

import type { VoxelGrid } from '$lib/three/VoxelGrid';

/** 히스토리 엔트리 */
interface HistoryEntry {
  label: string;
  snapshots: Map<string, Uint8Array>;
}

class HistoryState {
  /** Undo 스택 */
  private undoStack: HistoryEntry[] = [];
  /** Redo 스택 */
  private redoStack: HistoryEntry[] = [];

  /** Undo 가능 여부 */
  canUndo = $state(false);
  /** Redo 가능 여부 */
  canRedo = $state(false);
  /** 히스토리 크기 */
  undoCount = $state(0);
  redoCount = $state(0);

  /** 최대 히스토리 크기 */
  private MAX_HISTORY = 20;

  /** 복셀 그리드 참조 */
  private voxelGrids: Record<string, VoxelGrid> = {};

  /** 복셀 그리드 참조 설정 */
  setVoxelGrids(grids: Record<string, VoxelGrid>): void {
    this.voxelGrids = grids;
  }

  /** 현재 상태 저장 (작업 전 호출) */
  push(label: string): void {
    const snapshots = new Map<string, Uint8Array>();
    for (const [name, grid] of Object.entries(this.voxelGrids)) {
      const snap = grid.createSnapshot();
      if (snap) snapshots.set(name, snap);
    }

    if (snapshots.size === 0) return;

    this.undoStack.push({ label, snapshots });
    this.redoStack = []; // Redo 스택 초기화

    // 최대 크기 제한
    if (this.undoStack.length > this.MAX_HISTORY) {
      this.undoStack.shift();
    }

    this._updateState();
  }

  /** Undo */
  undo(): string | null {
    if (this.undoStack.length === 0) return null;

    // 현재 상태를 Redo에 저장
    const currentSnapshots = new Map<string, Uint8Array>();
    for (const [name, grid] of Object.entries(this.voxelGrids)) {
      const snap = grid.createSnapshot();
      if (snap) currentSnapshots.set(name, snap);
    }
    this.redoStack.push({ label: 'redo', snapshots: currentSnapshots });

    // Undo 스택에서 복원
    const entry = this.undoStack.pop()!;
    entry.snapshots.forEach((snapshot, name) => {
      const grid = this.voxelGrids[name];
      if (grid) grid.restoreSnapshot(snapshot);
    });

    this._updateState();
    return entry.label;
  }

  /** Redo */
  redo(): string | null {
    if (this.redoStack.length === 0) return null;

    // 현재 상태를 Undo에 저장
    const currentSnapshots = new Map<string, Uint8Array>();
    for (const [name, grid] of Object.entries(this.voxelGrids)) {
      const snap = grid.createSnapshot();
      if (snap) currentSnapshots.set(name, snap);
    }
    this.undoStack.push({ label: 'undo', snapshots: currentSnapshots });

    // Redo 스택에서 복원
    const entry = this.redoStack.pop()!;
    entry.snapshots.forEach((snapshot, name) => {
      const grid = this.voxelGrids[name];
      if (grid) grid.restoreSnapshot(snapshot);
    });

    this._updateState();
    return entry.label;
  }

  /** 히스토리 초기화 */
  clear(): void {
    this.undoStack = [];
    this.redoStack = [];
    this._updateState();
  }

  private _updateState(): void {
    this.canUndo = this.undoStack.length > 0;
    this.canRedo = this.redoStack.length > 0;
    this.undoCount = this.undoStack.length;
    this.redoCount = this.redoStack.length;
  }
}

export const historyState = new HistoryState();
