<script lang="ts">
  /**
   * PostProcessPanel — 결과 시각화 패널
   *
   * 변위/응력/손상 결과를 컬러맵으로 시각화.
   * 컬러맵 선택, 범위 표시, 워프(변형 확대), 포인트 크기 조절.
   */
  import { analysisState } from '$lib/stores/analysis.svelte';
  import { uiState } from '$lib/stores/ui.svelte';
  import {
    setPostMode, setComponent, setColormap, setDispScale,
    setParticleSize, setOpacity, setClipPlane,
    savePreOpResults, showComparison, exportResultsCSV,
  } from '$lib/actions/analysis';
  import type { PostProcessMode, VectorComponent } from '$lib/analysis/PostProcessor';
  import type { ColormapName } from '$lib/analysis/colormap';
  import { COLORMAP_NAMES, COLORMAPS, colormapToCSS } from '$lib/analysis/colormap';

  /** 모드 변경 */
  function handleModeChange(e: Event) {
    const mode = (e.target as HTMLSelectElement).value as PostProcessMode;
    setPostMode(mode);
  }

  /** 컴포넌트 변경 */
  function handleComponentChange(e: Event) {
    const comp = (e.target as HTMLSelectElement).value as VectorComponent;
    setComponent(comp);
  }

  /** 컬러맵 변경 */
  function handleColormapChange(name: ColormapName) {
    setColormap(name);
  }

  /** Warp 스케일 변경 */
  function handleDispScale(e: Event) {
    const val = parseFloat((e.target as HTMLInputElement).value);
    setDispScale(val);
  }

  /** 입자 크기 변경 */
  function handleParticleSize(e: Event) {
    const size = parseFloat((e.target as HTMLInputElement).value);
    setParticleSize(size);
  }

  /** 불투명도 변경 */
  function handleOpacity(e: Event) {
    const val = parseFloat((e.target as HTMLInputElement).value);
    setOpacity(val);
  }

  /** Pre-Op 결과 저장 */
  function handleSavePreOp() {
    savePreOpResults();
    uiState.toast('수술 전 결과 저장됨', 'success');
  }

  /** Pre/Post 비교 */
  function handleCompare() {
    showComparison();
    uiState.toast('수술 전/후 비교 표시', 'info');
  }

  // ── 클리핑 평면 핸들러 (Step 6) ──

  function handleClipToggle(e: Event) {
    const enabled = (e.target as HTMLInputElement).checked;
    setClipPlane(enabled);
  }
  function handleClipAxis(e: Event) {
    const axis = (e.target as HTMLSelectElement).value as 'x' | 'y' | 'z';
    setClipPlane(analysisState.clipEnabled, axis);
  }
  function handleClipPosition(e: Event) {
    const pos = parseFloat((e.target as HTMLInputElement).value);
    setClipPlane(analysisState.clipEnabled, undefined, pos);
  }
  function handleClipInvert(e: Event) {
    const invert = (e.target as HTMLInputElement).checked;
    setClipPlane(analysisState.clipEnabled, undefined, undefined, invert);
  }

  // ── Export (Step 7) ──

  function handleExportCSV() {
    exportResultsCSV();
  }

  /** 단위 */
  const modeUnits: Record<PostProcessMode, string> = {
    displacement: 'mm',
    stress: 'Pa',
    damage: '',
  };
</script>

<div class="panel">
  <h3>POST-PROCESS</h3>

  {#if !analysisState.hasResult}
    <div class="empty-section">
      <div class="empty-icon">🔬</div>
      <div class="empty-title">해석 결과 없음</div>
      <div class="empty-msg">Solve 탭에서 해석을 실행하면<br>여기에서 결과를 시각화합니다.</div>
    </div>
  {:else}

    <!-- 결과 필드 선택 -->
    <div class="section">
      <div class="section-title">Color By</div>

      <div class="field-row">
        <label for="post-mode" class="field-label">필드</label>
        <select id="post-mode" class="field-select" value={analysisState.postMode} onchange={handleModeChange}>
          <option value="displacement">Displacement (변위)</option>
          <option value="stress">Stress — von Mises (응력)</option>
          <option value="damage">Damage (손상)</option>
        </select>
      </div>

      {#if analysisState.postMode !== 'damage'}
        <div class="field-row">
          <label for="post-comp" class="field-label">성분</label>
          <select id="post-comp" class="field-select" value={analysisState.component} onchange={handleComponentChange}>
            <option value="magnitude">Magnitude (크기)</option>
            <option value="x">X</option>
            <option value="y">Y</option>
            <option value="z">Z</option>
          </select>
        </div>
      {/if}
    </div>

    <!-- 컬러맵 -->
    <div class="section">
      <div class="section-title">Color Map</div>

      <div class="cm-grid">
        {#each COLORMAP_NAMES as cm}
          <button
            class="cm-chip"
            class:active={analysisState.colormap === cm}
            style="background: {colormapToCSS(cm, 8)};"
            onclick={() => handleColormapChange(cm)}
            title={COLORMAPS[cm].label}
          >
            <span class="cm-name">{COLORMAPS[cm].label}</span>
          </button>
        {/each}
      </div>

      <!-- 컬러바 -->
      <div id="analysis-colorbar" class="colorbar-container"></div>

      <!-- 데이터 범위 표시 -->
      <div class="range-info">
        <span class="range-val">{analysisState.dataMin.toExponential(2)}</span>
        <span class="range-dash">—</span>
        <span class="range-val">{analysisState.dataMax.toExponential(2)}</span>
        <span class="range-unit">{modeUnits[analysisState.postMode]}</span>
      </div>
    </div>

    <!-- 표시 설정 -->
    <div class="section">
      <div class="section-title">Display</div>

      <div class="slider-row">
        <label for="warp-scale">변형 배율</label>
        <input id="warp-scale" type="range" min="0" max="200" step="1"
          value={analysisState.dispScale} oninput={handleDispScale}>
        <span class="val">×{analysisState.dispScale}</span>
      </div>

      <div class="slider-row">
        <label for="pt-size">포인트 크기</label>
        <input id="pt-size" type="range" min="0.5" max="10" step="0.5"
          value={analysisState.particleSize} oninput={handleParticleSize}>
        <span class="val">{analysisState.particleSize.toFixed(1)}</span>
      </div>

      <div class="slider-row">
        <label for="opacity">불투명도</label>
        <input id="opacity" type="range" min="0.1" max="1.0" step="0.05"
          value={analysisState.opacity} oninput={handleOpacity}>
        <span class="val">{(analysisState.opacity * 100).toFixed(0)}%</span>
      </div>
    </div>

    <!-- 통계 -->
    <div class="section">
      <div class="section-title">Statistics</div>
      <table class="stat-table">
        <tbody>
          <tr>
            <td class="stat-label">입자</td>
            <td class="stat-value">{analysisState.visibleCount.toLocaleString()}개</td>
          </tr>
          <tr>
            <td class="stat-label">Max 변위</td>
            <td class="stat-value">{analysisState.postProcessor?.stats.maxDisp.toExponential(3) ?? '—'} mm</td>
          </tr>
          <tr>
            <td class="stat-label">Max 응력</td>
            <td class="stat-value">{analysisState.postProcessor?.stats.maxStress.toExponential(3) ?? '—'} Pa</td>
          </tr>
          <tr>
            <td class="stat-label">Max 손상</td>
            <td class="stat-value">{analysisState.postProcessor?.stats.maxDamage.toFixed(4) ?? '—'}</td>
          </tr>
          <tr>
            <td class="stat-label">방법</td>
            <td class="stat-value">{analysisState.postProcessor?.data?.info?.method?.toUpperCase() ?? '—'}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 클리핑 평면 (Step 6) -->
    <div class="section">
      <div class="section-title">Clip Plane</div>
      <div class="toggle-row">
        <label><input type="checkbox" checked={analysisState.clipEnabled}
          onchange={handleClipToggle}> 활성화</label>
      </div>
      {#if analysisState.clipEnabled}
        <div class="clip-controls">
          <div class="field-row">
            <label for="clip-axis" class="field-label">축</label>
            <select id="clip-axis" class="field-select" value={analysisState.clipAxis}
              onchange={handleClipAxis}>
              <option value="x">X</option>
              <option value="y">Y</option>
              <option value="z">Z</option>
            </select>
          </div>
          <div class="slider-row">
            <label for="clip-pos">위치</label>
            <input id="clip-pos" type="range" min="-1" max="1" step="0.01"
              value={analysisState.clipPosition} oninput={handleClipPosition}>
            <span class="val">{analysisState.clipPosition.toFixed(2)}</span>
          </div>
          <div class="toggle-row">
            <label><input type="checkbox" checked={analysisState.clipInvert}
              onchange={handleClipInvert}> 반전</label>
          </div>
        </div>
      {/if}
    </div>

    <!-- 내보내기 (Step 7) -->
    <div class="section">
      <div class="section-title">Export</div>
      <button class="tool-btn export-btn" onclick={handleExportCSV}>
        📄 Export CSV
      </button>
    </div>

    <!-- 수술 전/후 비교 -->
    <div class="section compare">
      <div class="section-title" style="color: #ff6f00;">Pre/Post-Op 비교</div>
      <div class="hint">수술 전 결과를 저장 → 수술 후 해석 → 비교</div>
      <button class="tool-btn save-btn" onclick={handleSavePreOp}>
        💾 Save Pre-Op
      </button>
      <button class="tool-btn compare-btn"
        disabled={!analysisState.hasPreOpResult}
        onclick={handleCompare}>
        🔄 Compare
      </button>
    </div>
  {/if}
</div>

<style>
  .panel h3 {
    color: var(--color-primary); margin-bottom: 10px; font-size: 13px;
    text-transform: uppercase; letter-spacing: 1px; padding-bottom: 6px;
    border-bottom: 1px solid rgba(25, 118, 210, 0.2);
  }
  .section {
    margin-bottom: 8px; padding: 10px;
    background: var(--color-card); border: 1px solid #e8e8e8; border-radius: 6px;
  }
  .compare { border-left: 3px solid #ff6f00; }
  .section-title {
    font-size: 11px; color: var(--color-primary); margin-bottom: 8px; font-weight: bold;
  }

  /* 빈 상태 */
  .empty-section { text-align: center; padding: 30px 10px; color: #999; }
  .empty-icon { font-size: 36px; margin-bottom: 10px; }
  .empty-title { font-size: 13px; font-weight: 600; color: #666; margin-bottom: 6px; }
  .empty-msg { font-size: 11px; line-height: 1.5; }

  /* 필드 선택 */
  .field-row {
    display: flex; align-items: center; gap: 6px; margin-bottom: 6px;
  }
  .field-label {
    font-size: 11px; color: #666; min-width: 32px; flex-shrink: 0;
  }
  .field-select {
    flex: 1; padding: 5px 6px; font-size: 11px;
    border: 1px solid #ccc; border-radius: 3px; background: #fff;
  }

  /* 컬러맵 그리드 */
  .cm-grid {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 3px; margin-bottom: 8px;
  }
  .cm-chip {
    height: 24px; border: 2px solid transparent; border-radius: 4px;
    cursor: pointer; position: relative; transition: border-color 0.15s; overflow: hidden;
  }
  .cm-chip:hover { border-color: #aaa; }
  .cm-chip.active {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 1px var(--color-primary);
  }
  .cm-name {
    position: absolute; inset: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 9px; font-weight: 700; color: #fff;
    text-shadow: 0 1px 2px rgba(0,0,0,0.8);
    pointer-events: none;
  }

  /* 컬러바 */
  .colorbar-container { margin: 4px 0; }

  /* 데이터 범위 표시 */
  .range-info {
    display: flex; align-items: center; justify-content: center;
    gap: 4px; padding: 4px 0; margin-top: 2px;
    font-family: 'Consolas', 'Courier New', monospace; font-size: 10px;
  }
  .range-val { color: #444; font-weight: 600; }
  .range-dash { color: #bbb; }
  .range-unit { color: #999; font-size: 9px; margin-left: 2px; }

  /* 슬라이더 */
  .slider-row {
    display: flex; align-items: center; gap: 6px; font-size: 11px; color: #666; margin-bottom: 4px;
  }
  .slider-row input[type="range"] { flex: 1; }
  .slider-row label { min-width: 65px; }
  .val {
    font-size: 10px; color: #555; min-width: 40px; text-align: right;
    font-family: 'Consolas', monospace; font-weight: 600;
  }

  /* 통계 테이블 */
  .stat-table { width: 100%; font-size: 11px; border-collapse: collapse; }
  .stat-table td { padding: 3px 0; }
  .stat-label { color: #888; }
  .stat-value {
    color: #333; text-align: right;
    font-family: 'Consolas', monospace; font-size: 10px;
  }

  /* 버튼 */
  .tool-btn {
    width: 100%; padding: 7px; border: none; border-radius: 4px;
    color: #fff; cursor: pointer; font-size: 11px;
    transition: opacity 0.15s; margin: 3px 0;
  }
  .tool-btn:hover:not(:disabled) { opacity: 0.85; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .save-btn { background: #ff8f00; }
  .compare-btn { background: #ff6f00; }

  .hint { font-size: 10px; color: #888; margin: 4px 0; }

  /* 토글 행 */
  .toggle-row { font-size: 11px; color: #555; margin-bottom: 4px; }
  .toggle-row label { display: flex; align-items: center; gap: 4px; cursor: pointer; }
  .clip-controls { margin-top: 6px; }

  /* Export 버튼 */
  .export-btn { background: #43a047; }
</style>
