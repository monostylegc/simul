/**
 * 도구 상태 관리 (Svelte 5 runes).
 *
 * 드릴, 브러쉬, 임플란트 배치, 3D 하중 편집 등 인터랙션 도구 상태.
 */

export type ToolMode = 'none' | 'drill' | 'brush' | 'faceSelect' | 'forceArrow' | 'implantPlace';

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

  // ── 임플란트 배치 모드 상태 ──

  /** 배치 대기 중인 임플란트 STL URL */
  pendingImplantUrl = $state<string | null>(null);

  /** 배치 대기 중인 임플란트 식별자 (카탈로그 id) */
  pendingImplantName = $state<string | null>(null);

  /** 배치 대기 중인 임플란트 재료 타입 */
  pendingImplantMat = $state<string>('titanium');

  /** 배치 대기 중인 임플란트 카테고리 */
  pendingImplantCategory = $state<'screw' | 'cage' | 'rod'>('screw');

  /** 배치 대기 중인 케이지 높이 (mm) — 디스트랙션 계산용 */
  pendingImplantHeightMm = $state<number | undefined>(undefined);

  // ── 3D 하중 편집기 ──

  /** 3D Force 편집 모드 활성 여부 */
  forceEditMode3D = $state(false);

  /** 도구 활성화 */
  setMode(mode: ToolMode): void {
    this.mode = mode;
  }

  /** 도구 비활성화 */
  reset(): void {
    this.mode = 'none';
  }

  /**
   * 임플란트 배치 모드 진입.
   *
   * @param url      STL 파일 public 경로
   * @param name     카탈로그 id (예: 'M6x45')
   * @param mat      재료 타입 ('titanium' | 'peek' | ...)
   * @param category 임플란트 분류
   */
  enterImplantPlaceMode(
    url: string,
    name: string,
    mat: string,
    category: 'screw' | 'cage' | 'rod',
    heightMm?: number,
  ): void {
    this.pendingImplantUrl        = url;
    this.pendingImplantName       = name;
    this.pendingImplantMat        = mat;
    this.pendingImplantCategory   = category;
    this.pendingImplantHeightMm   = heightMm;
    this.mode = 'implantPlace';
  }

  /**
   * 임플란트 배치 모드 종료 (배치 완료 또는 Esc 취소).
   */
  exitImplantPlaceMode(): void {
    this.pendingImplantUrl  = null;
    this.pendingImplantName = null;
    this.mode = 'none';
  }
}

export const toolsState = new ToolsState();
