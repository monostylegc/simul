/**
 * 도구 상태 관리 (Svelte 5 runes).
 *
 * 드릴, 브러쉬, 면선택 등 인터랙션 도구 상태.
 */

export type ToolMode = 'none' | 'drill' | 'brush' | 'faceSelect' | 'forceArrow';

class ToolsState {
  /** 현재 활성 도구 */
  mode = $state<ToolMode>('none');

  /** 드릴 반경 (mm) */
  drillRadius = $state(3.0);

  /** 브러쉬 반경 (mm) */
  brushRadius = $state(5.0);

  /** 드릴 프리뷰 표시 여부 */
  showDrillPreview = $state(true);

  /** 하중 벡터 [fx, fy, fz] (N) */
  forceVector = $state<[number, number, number]>([0, -100, 0]);

  /** 도구 활성화 */
  setMode(mode: ToolMode): void {
    this.mode = mode;
  }

  /** 도구 비활성화 */
  reset(): void {
    this.mode = 'none';
  }
}

export const toolsState = new ToolsState();
