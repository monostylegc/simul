<script lang="ts">
  /**
   * ModelingPanel — 임플란트 관리, 드릴, 복셀 해상도, Undo/Redo
   */
  import { toolsState } from '$lib/stores/tools.svelte';
  import { historyState } from '$lib/stores/history.svelte';
  import { uiState } from '$lib/stores/ui.svelte';
  import { enableDrill, disableDrill, disposeDrillHighlight } from '$lib/actions/drilling';

  /** 드릴 토글 */
  function toggleDrill() {
    if (toolsState.mode === 'drill') {
      disableDrill();
    } else {
      enableDrill();
    }
  }

  /** Undo */
  function handleUndo() {
    const label = historyState.undo();
    if (label) uiState.statusMessage = `Undo: ${label}`;
  }

  /** Redo */
  function handleRedo() {
    const label = historyState.redo();
    if (label) uiState.statusMessage = `Redo: ${label}`;
  }
</script>

<div class="panel">
  <h3>MODELING</h3>

  <!-- 드릴 토글 -->
  <div class="section">
    <button
      class="tool-btn"
      class:active={toolsState.mode === 'drill'}
      onclick={toggleDrill}
    >
      Drill: {toolsState.mode === 'drill' ? 'ON' : 'OFF'}
    </button>
  </div>

  <!-- 드릴 반경 -->
  <div class="section">
    <div class="slider-row">
      <label for="drill-radius">Radius</label>
      <input id="drill-radius" type="range" min="1" max="15" step="0.5"
        bind:value={toolsState.drillRadius}>
      <span class="val">{toolsState.drillRadius.toFixed(1)} mm</span>
    </div>
  </div>

  <!-- 드릴 안내 -->
  <div class="section">
    <div class="hint">
      Shape: Sphere<br>
      Hover = preview, Click = drill
    </div>
  </div>

  <!-- History (Undo/Redo) -->
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
  .tool-btn {
    width: 100%; padding: 8px; border: none; border-radius: 4px;
    background: var(--color-primary); color: #fff; cursor: pointer;
    font-size: 12px; transition: opacity 0.15s;
  }
  .tool-btn:hover:not(:disabled) { opacity: 0.85; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .tool-btn.active { background: #e53935; }
  .tool-btn.half { width: 48%; }
  .btn-row { display: flex; gap: 4%; }
  .slider-row {
    display: flex; align-items: center; gap: 6px; font-size: 11px; color: #666;
  }
  .slider-row input[type="range"] { flex: 1; }
  .val { font-size: 10px; color: #888; min-width: 50px; text-align: right; }
  .hint { font-size: 11px; color: #888; }
</style>
