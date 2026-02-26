<script lang="ts">
  /**
   * ModelingPanel — 드릴 도구, 임플란트 카탈로그 배치, 가이드라인, Undo/Redo
   *
   * 임플란트 섹션:
   *   - 카탈로그 탭 (Screw / Cage) → Place 버튼 → 뷰포트 클릭 배치
   *   - 배치된 임플란트 목록 → Move / Rotate / Delete
   *   - 케이지 배치 시 뼈와 충돌하면 빨간색 경고 표시
   */
  import { sceneState } from '$lib/stores/scene.svelte';
  import { toolsState } from '$lib/stores/tools.svelte';
  import { historyState } from '$lib/stores/history.svelte';
  import { uiState } from '$lib/stores/ui.svelte';
  import { enableDrill, disableDrill } from '$lib/actions/drilling';
  import {
    requestGuidelines, clearGuidelines,
  } from '$lib/actions/implants';
  import {
    CATALOG_BY_CATEGORY,
    selectImplantForPlacement,
    deleteSelectedImplant,
    clearAllImplants,
    getPlacedImplants,
    applyCageDistraction,
    type ImplantCategory,
  } from '$lib/actions/implantCatalog';

  // ── 카탈로그 탭 상태 ──

  /** 현재 표시 중인 카탈로그 탭 */
  let activeTab = $state<ImplantCategory>('screw');

  // ── 배치된 임플란트 목록 (반응성) ──

  /**
   * implantCount가 변경될 때마다 목록 갱신.
   * implantManager?.implantCount를 $derived로 추적.
   */
  const implantCount = $derived(sceneState.implantManager?.implantCount ?? 0);
  const placedImplants = $derived(implantCount >= 0 ? getPlacedImplants() : []);

  /** 선택된 임플란트 이름 */
  const selectedImplant = $derived(sceneState.implantManager?.selectedImplant ?? null);

  /** 선택된 임플란트가 케이지인지 여부 */
  const selectedIsCage = $derived(
    selectedImplant !== null &&
    sceneState.implantManager?.implants[selectedImplant]?.category === 'cage'
  );

  // ── 가이드라인 상태 ──

  /** 대상 척추 레벨 */
  let guidelineVertebra = $state('L4');
  /** 내측각 (도) */
  let guidelineAngle = $state(10);
  /** 삽입 깊이 (mm) */
  let guidelineDepth = $state(45);

  // ── 드릴 ──

  function toggleDrill() {
    if (toolsState.mode === 'drill') {
      disableDrill();
    } else {
      enableDrill();
    }
  }

  // ── Undo/Redo ──

  function handleUndo() {
    const label = historyState.undo();
    if (label) uiState.statusMessage = `Undo: ${label}`;
  }

  function handleRedo() {
    const label = historyState.redo();
    if (label) uiState.statusMessage = `Redo: ${label}`;
  }

  // ── 임플란트 Transform 모드 ──

  function setMoveMode() {
    sceneState.implantManager?.setTransformMode('translate');
  }

  function setRotateMode() {
    sceneState.implantManager?.setTransformMode('rotate');
  }

  function handleDeleteSelected() {
    deleteSelectedImplant();
  }

  function handleClearAll() {
    if (implantCount === 0) return;
    clearAllImplants();
  }

  // ── 배치 모드 취소 ──

  function cancelPlaceMode() {
    toolsState.exitImplantPlaceMode();
    uiState.statusMessage = '배치 모드 취소됨';
  }

  // ── 가이드라인 ──

  function showGuidelines() {
    uiState.statusMessage = `가이드라인 생성 중... (${guidelineVertebra})`;
    const posMap: Record<string, [number, number, number]> = {
      L1: [0, 150, 0], L2: [0, 120, 0], L3: [0, 90, 0],
      L4: [0,  60, 0], L5: [0,  30, 0], S1: [0,   0, 0],
    };
    const pos = posMap[guidelineVertebra] ?? [0, 60, 0];
    requestGuidelines(pos, guidelineVertebra, {
      medial_angle: guidelineAngle,
      depth: guidelineDepth,
    });
    uiState.statusMessage = `${guidelineVertebra} 가이드라인 요청됨`;
  }

  function removeGuidelines() {
    clearGuidelines();
    uiState.statusMessage = '가이드라인 제거됨';
  }
</script>

<div class="panel">
  <h3>MODELING</h3>

  <!-- ── 드릴 도구 ── -->
  <div class="section">
    <div class="section-title">Bone Drill</div>
    <button
      class="tool-btn"
      class:active={toolsState.mode === 'drill'}
      onclick={toggleDrill}
    >
      Drill: {toolsState.mode === 'drill' ? 'ON' : 'OFF'}
    </button>
    <div class="slider-row" style="margin-top:6px">
      <label for="drill-radius">Radius</label>
      <input id="drill-radius" type="range" min="1" max="15" step="0.5"
        bind:value={toolsState.drillRadius}>
      <span class="val">{toolsState.drillRadius.toFixed(1)} mm</span>
    </div>
    <div class="hint">Hover = preview &nbsp;·&nbsp; Click = drill</div>
  </div>

  <!-- ── 임플란트 카탈로그 ── -->
  <div class="section">
    <div class="section-title">Implant Catalog</div>

    <!-- 카테고리 탭 -->
    <div class="tab-bar">
      <button
        class="tab-btn"
        class:tab-active={activeTab === 'screw'}
        onclick={() => activeTab = 'screw'}
      >Screw</button>
      <button
        class="tab-btn"
        class:tab-active={activeTab === 'cage'}
        onclick={() => activeTab = 'cage'}
      >Cage</button>
      <button
        class="tab-btn"
        class:tab-active={activeTab === 'rod'}
        onclick={() => activeTab = 'rod'}
      >Rod</button>
    </div>

    <!-- 카탈로그 목록 -->
    <div class="catalog-list">
      {#each CATALOG_BY_CATEGORY[activeTab] as item (item.id)}
        <div class="catalog-item"
          class:catalog-item-active={toolsState.pendingImplantName === item.id && toolsState.mode === 'implantPlace'}>
          <div class="catalog-info">
            <span class="catalog-label">{item.label}</span>
            <span class="catalog-desc">{item.description}</span>
          </div>
          <button
            class="place-btn"
            class:place-btn-active={toolsState.pendingImplantName === item.id && toolsState.mode === 'implantPlace'}
            onclick={() => selectImplantForPlacement(item)}
          >
            {toolsState.pendingImplantName === item.id && toolsState.mode === 'implantPlace'
              ? '배치 중...'
              : 'Place'}
          </button>
        </div>
      {/each}
      {#if CATALOG_BY_CATEGORY[activeTab].length === 0}
        <div class="hint" style="text-align:center;padding:8px 0">
          준비 중입니다
        </div>
      {/if}
    </div>

    <!-- 배치 모드 힌트 -->
    {#if toolsState.mode === 'implantPlace'}
      <div class="place-hint">
        {#if toolsState.pendingImplantCategory === 'screw' || toolsState.pendingImplantCategory === 'rod'}
          {toolsState.pendingImplantCategory === 'screw' ? '🔩' : '🔗'} 1. 진입점 클릭 → 카메라 회전 → 2. 끝점 클릭
        {:else}
          🦴 뼈 표면을 클릭해 배치
        {/if}
        &nbsp;·&nbsp;
        <button class="cancel-btn" onclick={cancelPlaceMode}>Esc / 취소</button>
      </div>
    {/if}
  </div>

  <!-- ── 배치된 임플란트 목록 ── -->
  <div class="section">
    <div class="section-title-row">
      <span class="section-title">Placed Implants</span>
      <span class="count-badge">{implantCount}개</span>
      {#if implantCount > 0}
        <button class="warn-sm" onclick={handleClearAll}>Clear All</button>
      {/if}
    </div>

    {#if implantCount === 0}
      <div class="hint" style="text-align:center;padding:6px 0">
        배치된 임플란트 없음
      </div>
    {:else}
      <!-- 배치 목록 -->
      <div class="implant-list">
        {#each placedImplants as impl (impl.name)}
          <div
            class="implant-row"
            class:implant-selected={selectedImplant === impl.name}
            onclick={() => sceneState.implantManager?.selectImplant(impl.name)}
            role="button"
            tabindex="0"
            onkeydown={(e) => e.key === 'Enter' && sceneState.implantManager?.selectImplant(impl.name)}
          >
            <span class="impl-cat-badge" class:badge-cage={impl.category === 'cage'}
              class:badge-screw={impl.category === 'screw'}
              class:badge-rod={impl.category === 'rod'}>
              {impl.category === 'cage' ? 'C' : impl.category === 'screw' ? 'S' : 'R'}
            </span>
            <span class="impl-name">{impl.name}</span>
            <span class="impl-mat">{impl.material}</span>
            <button
              class="del-btn"
              onclick={(e) => { e.stopPropagation(); sceneState.implantManager?.removeImplant(impl.name); }}
              title="삭제"
            >✕</button>
          </div>
        {/each}
      </div>

      <!-- 선택된 임플란트 Transform 컨트롤 -->
      {#if selectedImplant}
        <div class="transform-bar">
          <span class="transform-label">Transform:</span>
          <button class="transform-btn" onclick={setMoveMode}>Move</button>
          <button class="transform-btn" onclick={setRotateMode}>Rotate</button>
          <button class="transform-btn warn" onclick={handleDeleteSelected}>Del</button>
        </div>

        <!-- 케이지 전용: 디스트랙션 적용 버튼 -->
        {#if selectedIsCage}
          <div class="distraction-bar">
            <span class="distraction-icon">🦴</span>
            <div class="distraction-info">
              <span class="distraction-title">Distraction</span>
              <span class="distraction-desc">케이지 높이로 디스크 공간 교정</span>
            </div>
            <button
              class="distraction-btn"
              onclick={() => selectedImplant && applyCageDistraction(selectedImplant)}
            >Apply</button>
          </div>
        {/if}
      {/if}
    {/if}
  </div>

  <!-- ── Pedicle 가이드라인 ── -->
  <div class="section">
    <div class="section-title">Pedicle Guidelines</div>

    <div class="inline-row">
      <label for="gl-vertebra" class="row-label">척추</label>
      <select id="gl-vertebra" bind:value={guidelineVertebra}>
        <option>L1</option><option>L2</option><option>L3</option>
        <option>L4</option><option>L5</option><option>S1</option>
      </select>
    </div>

    <div class="slider-row" style="margin-top:6px">
      <label for="gl-angle">내측각</label>
      <input id="gl-angle" type="range" min="0" max="25" step="1"
        bind:value={guidelineAngle}>
      <span class="val">{guidelineAngle}°</span>
    </div>

    <div class="slider-row">
      <label for="gl-depth">삽입깊이</label>
      <input id="gl-depth" type="range" min="30" max="60" step="5"
        bind:value={guidelineDepth}>
      <span class="val">{guidelineDepth} mm</span>
    </div>

    <div class="btn-row" style="margin-top:7px">
      <button class="tool-btn half" onclick={showGuidelines}>Show</button>
      <button class="tool-btn half warn-btn" onclick={removeGuidelines}>Clear</button>
    </div>
    <div class="hint">양측(좌/우) 가이드라인 자동 생성</div>
  </div>

  <!-- ── History (Undo/Redo) ── -->
  <div class="section">
    <div class="section-title">History</div>
    <div class="btn-row">
      <button class="tool-btn half" disabled={!historyState.canUndo} onclick={handleUndo}>
        Undo ({historyState.undoCount})
      </button>
      <button class="tool-btn half" disabled={!historyState.canRedo} onclick={handleRedo}>
        Redo ({historyState.redoCount})
      </button>
    </div>
  </div>
</div>

<style>
  .panel h3 {
    color: var(--color-primary); margin-bottom: 10px; font-size: 13px;
    text-transform: uppercase; letter-spacing: 1px; padding-bottom: 6px;
    border-bottom: 1px solid rgba(25, 118, 210, 0.2);
  }
  .section {
    margin-bottom: 12px; padding: 10px;
    background: var(--color-card); border: 1px solid #e8e8e8; border-radius: 6px;
  }
  .section-title {
    font-size: 11px; color: var(--color-primary); margin-bottom: 6px; font-weight: bold;
  }
  .section-title-row {
    display: flex; align-items: center; gap: 6px; margin-bottom: 6px;
  }
  .section-title-row .section-title { margin-bottom: 0; }
  .count-badge {
    font-size: 10px; color: #fff; background: var(--color-primary);
    border-radius: 10px; padding: 1px 6px; font-weight: bold;
  }

  /* 카탈로그 탭 */
  .tab-bar {
    display: flex; gap: 3px; margin-bottom: 6px;
  }
  .tab-btn {
    flex: 1; padding: 4px 0; font-size: 11px; border: 1px solid #ccc;
    border-radius: 4px; background: #f5f5f5; cursor: pointer; color: #555;
    transition: all 0.15s;
  }
  .tab-btn:hover { background: #e8e8e8; }
  .tab-active {
    background: var(--color-primary) !important; color: #fff !important;
    border-color: var(--color-primary) !important;
  }

  /* 카탈로그 목록 */
  .catalog-list {
    display: flex; flex-direction: column; gap: 3px;
  }
  .catalog-item {
    display: flex; align-items: center; gap: 6px;
    padding: 5px 6px; border-radius: 4px; border: 1px solid #eee;
    background: #fafafa; transition: background 0.1s;
  }
  .catalog-item:hover { background: #f0f4ff; }
  .catalog-item-active {
    background: #e8f0ff; border-color: var(--color-primary);
  }
  .catalog-info { flex: 1; min-width: 0; }
  .catalog-label {
    font-size: 11px; font-weight: bold; color: #333; display: block;
  }
  .catalog-desc {
    font-size: 10px; color: #888;
  }
  .place-btn {
    padding: 3px 8px; font-size: 10px; border: 1px solid var(--color-primary);
    border-radius: 3px; background: #fff; color: var(--color-primary);
    cursor: pointer; white-space: nowrap; flex-shrink: 0;
    transition: all 0.15s;
  }
  .place-btn:hover { background: var(--color-primary); color: #fff; }
  .place-btn-active {
    background: var(--color-primary); color: #fff;
  }

  /* 배치 모드 힌트 */
  .place-hint {
    margin-top: 6px; padding: 5px 8px; background: #fff3cd;
    border: 1px solid #ffc107; border-radius: 4px;
    font-size: 11px; color: #856404; display: flex; align-items: center; gap: 6px;
  }
  .cancel-btn {
    padding: 1px 6px; font-size: 10px; border: 1px solid #856404;
    border-radius: 3px; background: transparent; color: #856404;
    cursor: pointer; flex-shrink: 0;
  }
  .cancel-btn:hover { background: #856404; color: #fff; }

  /* 배치된 임플란트 목록 */
  .implant-list {
    display: flex; flex-direction: column; gap: 2px; margin-bottom: 5px;
  }
  .implant-row {
    display: flex; align-items: center; gap: 5px;
    padding: 4px 6px; border-radius: 4px; border: 1px solid #eee;
    background: #fafafa; cursor: pointer; font-size: 11px;
    transition: background 0.1s;
  }
  .implant-row:hover { background: #f0f4ff; }
  .implant-selected {
    background: #e8f0ff; border-color: var(--color-primary);
  }
  .impl-cat-badge {
    font-size: 9px; font-weight: bold; color: #fff;
    width: 16px; height: 16px; border-radius: 3px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }
  .badge-screw { background: #607d8b; }
  .badge-cage  { background: #795548; }
  .badge-rod   { background: #1565c0; }
  .impl-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .impl-mat  { font-size: 10px; color: #888; flex-shrink: 0; }
  .del-btn {
    padding: 1px 5px; font-size: 10px; border: 1px solid #e53935;
    border-radius: 3px; background: transparent; color: #e53935;
    cursor: pointer; flex-shrink: 0; line-height: 1;
  }
  .del-btn:hover { background: #e53935; color: #fff; }

  /* Transform 바 */
  .transform-bar {
    display: flex; align-items: center; gap: 4px;
    padding: 4px 0; margin-top: 2px;
  }
  .transform-label { font-size: 10px; color: #888; flex-shrink: 0; }
  .transform-btn {
    flex: 1; padding: 4px 0; font-size: 11px; border: 1px solid #ccc;
    border-radius: 3px; background: #fff; cursor: pointer; color: #333;
    transition: all 0.15s;
  }
  .transform-btn:hover { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
  .transform-btn.warn { border-color: #e53935; color: #e53935; }
  .transform-btn.warn:hover { background: #e53935; color: #fff; }

  /* 디스트랙션 바 (케이지 전용) */
  .distraction-bar {
    display: flex; align-items: center; gap: 6px;
    margin-top: 5px; padding: 6px 8px;
    background: #f3e5f5; border: 1px solid #ce93d8; border-radius: 5px;
  }
  .distraction-icon { font-size: 15px; flex-shrink: 0; }
  .distraction-info { flex: 1; min-width: 0; }
  .distraction-title {
    display: block; font-size: 11px; font-weight: bold; color: #6a1b9a;
  }
  .distraction-desc {
    display: block; font-size: 9px; color: #888;
  }
  .distraction-btn {
    padding: 4px 10px; font-size: 11px; font-weight: 600;
    border: 1px solid #6a1b9a; border-radius: 4px;
    background: #6a1b9a; color: #fff; cursor: pointer;
    flex-shrink: 0; transition: opacity 0.15s;
  }
  .distraction-btn:hover { opacity: 0.85; }

  /* Clear All 버튼 */
  .warn-sm {
    margin-left: auto; padding: 2px 7px; font-size: 10px;
    border: 1px solid #e53935; border-radius: 3px;
    background: transparent; color: #e53935; cursor: pointer;
    transition: all 0.15s;
  }
  .warn-sm:hover { background: #e53935; color: #fff; }

  /* 공통 */
  .tool-btn {
    width: 100%; padding: 8px; border: none; border-radius: 4px;
    background: var(--color-primary); color: #fff; cursor: pointer;
    font-size: 12px; transition: opacity 0.15s;
  }
  .tool-btn:hover:not(:disabled) { opacity: 0.85; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .tool-btn.active { background: #e53935; }
  .tool-btn.half { width: 48%; }
  .tool-btn.warn-btn { background: #e53935; }
  .btn-row { display: flex; gap: 4%; }
  .inline-row {
    display: flex; align-items: center; gap: 6px; font-size: 11px; color: #666;
  }
  .inline-row select {
    flex: 1; font-size: 11px; padding: 3px 4px;
    border: 1px solid #ccc; border-radius: 3px; background: #fff;
  }
  .row-label { min-width: 36px; color: #888; flex-shrink: 0; }
  .slider-row {
    display: flex; align-items: center; gap: 6px; font-size: 11px; color: #666;
  }
  .slider-row label { min-width: 36px; flex-shrink: 0; }
  .slider-row input[type="range"] { flex: 1; }
  .val { font-size: 10px; color: #888; min-width: 40px; text-align: right; }
  .hint { font-size: 11px; color: #888; margin-top: 4px; }
</style>
