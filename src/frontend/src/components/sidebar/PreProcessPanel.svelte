<script lang="ts">
  /**
   * PreProcessPanel — 브러쉬 선택, BC 설정, 재료 할당
   *
   * 시뮬레이션 전처리 3단계:
   *  Step 1: 고정 경계조건 (Fixed BC) — 브러쉬로 영역 선택 후 고정
   *  Step 2: 하중 경계조건 (Force BC) — 방향 + 크기 설정 (개선된 UI)
   *  Step 3: 재료 할당 — 모델별 물성치 프리셋 적용
   */
  import { toolsState } from '$lib/stores/tools.svelte';
  import { analysisState } from '$lib/stores/analysis.svelte';
  import { sceneState } from '$lib/stores/scene.svelte';
  import { uiState } from '$lib/stores/ui.svelte';
  import { addFixedBC, addForceBC, removeLastBC, clearAllBC, assignMaterial } from '$lib/actions/analysis';
  import { MATERIAL_PRESETS } from '$lib/analysis/PreProcessor';

  /** 하중 크기 (N) */
  let forceMagnitude = $state(100);

  /** 하중 방향 벡터 (정규화) */
  let dirX = $state(0);
  let dirY = $state(-1);
  let dirZ = $state(0);

  let materialTarget = $state('__all__');
  let materialPreset = $state('bone');

  /** 모델 존재 여부 */
  let hasModels = $derived(sceneState.models.length > 0);

  /** 방향 벡터 크기 (정규화 확인용) */
  let dirMag = $derived(
    Math.sqrt(dirX * dirX + dirY * dirY + dirZ * dirZ)
  );

  /** 실제 힘 벡터 (표시용) */
  let forceVec = $derived({
    x: (dirMag > 0 ? dirX / dirMag : 0) * forceMagnitude,
    y: (dirMag > 0 ? dirY / dirMag : 0) * forceMagnitude,
    z: (dirMag > 0 ? dirZ / dirMag : 0) * forceMagnitude,
  });

  /** 브러쉬 모드 토글 */
  function toggleBrush() {
    if (!hasModels) {
      uiState.toast('모델을 먼저 로드하세요', 'warn');
      return;
    }
    toolsState.setMode(toolsState.mode === 'brush' ? 'none' : 'brush');
  }

  /** Fixed BC 적용 */
  function handleApplyFixed() {
    if (!hasModels) { uiState.toast('모델을 먼저 로드하세요', 'warn'); return; }
    addFixedBC();
    uiState.toast('Fixed BC 적용됨', 'success');
  }

  /** Force BC 적용 */
  function handleApplyForce() {
    if (!hasModels) { uiState.toast('모델을 먼저 로드하세요', 'warn'); return; }
    if (dirMag < 0.01) { uiState.toast('방향 벡터를 설정하세요', 'warn'); return; }

    const nx = dirX / dirMag;
    const ny = dirY / dirMag;
    const nz = dirZ / dirMag;

    const force: [number, number, number] = [
      nx * forceMagnitude,
      ny * forceMagnitude,
      nz * forceMagnitude,
    ];
    addForceBC(force);
    uiState.toast(`Force BC: ${forceMagnitude}N → (${nx.toFixed(1)}, ${ny.toFixed(1)}, ${nz.toFixed(1)})`, 'success');
  }

  /** 방향 프리셋 설정 */
  function setDirection(x: number, y: number, z: number) {
    dirX = x; dirY = y; dirZ = z;
  }

  /** 크기 프리셋 설정 */
  function setMagnitude(val: number) {
    forceMagnitude = val;
  }

  /** 크기 직접 입력 */
  function handleMagnitudeInput(e: Event) {
    const val = parseFloat((e.target as HTMLInputElement).value);
    if (!isNaN(val) && val > 0) forceMagnitude = val;
  }

  /** 재료 적용 */
  function handleAssignMaterial() {
    if (!hasModels) { uiState.toast('모델을 먼저 로드하세요', 'warn'); return; }
    if (materialTarget === '__all__') {
      sceneState.models.forEach(m => assignMaterial(m.name, materialPreset));
    } else {
      assignMaterial(materialTarget, materialPreset);
    }
    const preset = MATERIAL_PRESETS[materialPreset as keyof typeof MATERIAL_PRESETS];
    uiState.toast(`재료 할당: ${preset?.label ?? materialPreset}`, 'success');
  }

  /** 전체 BC 삭제 (확인) */
  async function handleClearAllBC() {
    if (analysisState.bcCount === 0) return;
    const ok = await uiState.confirm(
      'BC 전체 삭제',
      `${analysisState.bcCount}개 경계조건을 모두 삭제합니다.`
    );
    if (ok) {
      clearAllBC();
      uiState.toast('모든 BC 삭제됨', 'info');
    }
  }

  const presetOptions = Object.entries(MATERIAL_PRESETS).map(([key, p]) => ({
    value: key, label: p.label,
  }));
</script>

<div class="panel">
  <h3>PRE-PROCESS</h3>

  <!-- 브러쉬 선택 -->
  <div class="section">
    <div class="section-title">Brush Selection</div>
    <div class="slider-row">
      <label for="brush-radius">반경</label>
      <input id="brush-radius" type="range" min="1" max="15" step="0.5" bind:value={toolsState.brushRadius}>
      <span class="val">{toolsState.brushRadius.toFixed(1)} mm</span>
    </div>
    <div class="hint">모델 위에서 클릭/드래그로 영역 선택</div>
    <button class="tool-btn" onclick={toggleBrush}
      class:active={toolsState.mode === 'brush'}
      disabled={!hasModels}>
      Brush: {toolsState.mode === 'brush' ? 'ON' : 'OFF'}
    </button>
    <button class="tool-btn secondary" onclick={() => analysisState.preProcessor?.clearBrushSelection()}
      disabled={!hasModels}>
      Clear Selection
    </button>
  </div>

  <!-- Step 1: Fixed BC -->
  <div class="section bc-section fixed">
    <div class="section-title" style="color: #00cc44;">Step 1: Fixed BC (고정)</div>
    <div class="hint">브러쉬로 영역 선택 → 고정 적용</div>
    <button class="tool-btn" style="background: #00cc44;" onclick={handleApplyFixed}
      disabled={!hasModels}>
      Apply Fixed BC
    </button>
  </div>

  <!-- Step 2: Force BC (개선된 UI) -->
  <div class="section bc-section force">
    <div class="section-title" style="color: #ff2222;">Step 2: Force BC (하중)</div>

    <!-- 크기 설정 -->
    <div class="force-mag-section">
      <span class="subsection-label">📏 크기 (N)</span>

      <!-- 크기 빠른 선택 -->
      <div class="mag-presets">
        {#each [50, 100, 200, 500, 1000] as v}
          <button class="mag-btn" class:active={forceMagnitude === v}
            onclick={() => setMagnitude(v)}>{v}</button>
        {/each}
      </div>

      <!-- 크기 슬라이더 + 직접 입력 -->
      <div class="mag-input-row">
        <input type="range" min="1" max="2000" step="1" bind:value={forceMagnitude} class="mag-slider">
        <input type="number" min="1" max="10000" step="1"
          value={forceMagnitude} onchange={handleMagnitudeInput} class="mag-number">
        <span class="mag-unit">N</span>
      </div>
    </div>

    <!-- 방향 설정 -->
    <div class="force-dir-section">
      <span class="subsection-label">🧭 방향</span>

      <!-- 방향 빠른 프리셋 (해부학적) -->
      <div class="dir-presets">
        <button class="dir-btn" class:active={dirX === 0 && dirY === -1 && dirZ === 0}
          onclick={() => setDirection(0, -1, 0)} title="압축 (아래)">
          <span class="dir-arrow">↓</span><span class="dir-text">압축</span>
        </button>
        <button class="dir-btn" class:active={dirX === 0 && dirY === 1 && dirZ === 0}
          onclick={() => setDirection(0, 1, 0)} title="인장 (위)">
          <span class="dir-arrow">↑</span><span class="dir-text">인장</span>
        </button>
        <button class="dir-btn" class:active={dirX === 1 && dirY === 0 && dirZ === 0}
          onclick={() => setDirection(1, 0, 0)} title="측방 (+X)">
          <span class="dir-arrow">→</span><span class="dir-text">측방</span>
        </button>
        <button class="dir-btn" class:active={dirX === 0 && dirY === 0 && dirZ === 1}
          onclick={() => setDirection(0, 0, 1)} title="전방 (+Z)">
          <span class="dir-arrow">⊙</span><span class="dir-text">전방</span>
        </button>
        <button class="dir-btn" class:active={dirX === 0 && dirY === -1 && dirZ === -1}
          onclick={() => setDirection(0, -0.7, -0.7)} title="전방굴곡">
          <span class="dir-arrow">↙</span><span class="dir-text">굴곡</span>
        </button>
        <button class="dir-btn" class:active={dirX === 0 && dirY === -1 && dirZ === 1}
          onclick={() => setDirection(0, -0.7, 0.7)} title="후방신전">
          <span class="dir-arrow">↘</span><span class="dir-text">신전</span>
        </button>
      </div>

      <!-- X / Y / Z 직접 입력 -->
      <div class="dir-xyz">
        <div class="dir-axis">
          <span class="axis-label x">X</span>
          <input type="number" step="0.1" min="-1" max="1" bind:value={dirX}>
        </div>
        <div class="dir-axis">
          <span class="axis-label y">Y</span>
          <input type="number" step="0.1" min="-1" max="1" bind:value={dirY}>
        </div>
        <div class="dir-axis">
          <span class="axis-label z">Z</span>
          <input type="number" step="0.1" min="-1" max="1" bind:value={dirZ}>
        </div>
      </div>
    </div>

    <!-- 결과 힘 벡터 미리보기 -->
    <div class="force-preview">
      <span class="force-preview-label">F =</span>
      <span class="force-preview-val">({forceVec.x.toFixed(0)}, {forceVec.y.toFixed(0)}, {forceVec.z.toFixed(0)})</span>
      <span class="force-preview-unit">N</span>
    </div>

    <button class="tool-btn force-apply-btn" onclick={handleApplyForce}
      disabled={!hasModels || dirMag < 0.01}>
      Apply Force BC ({forceMagnitude}N)
    </button>
  </div>

  <!-- BC 관리 -->
  <div class="section">
    <div class="bc-info">
      <span>BCs: <strong>{analysisState.bcCount}</strong></span>
      <button class="tool-btn-sm" onclick={() => removeLastBC()}
        disabled={analysisState.bcCount === 0}>Remove Last</button>
    </div>
    <button class="tool-btn secondary" onclick={handleClearAllBC}
      disabled={analysisState.bcCount === 0}>Clear All BC</button>
  </div>

  <!-- Step 3: Material -->
  <div class="section bc-section material">
    <div class="section-title" style="color: #1976d2;">Step 3: Material (재료)</div>
    <div class="field-row">
      <label for="mat-target" class="field-label">대상</label>
      <select id="mat-target" bind:value={materialTarget} class="field-select">
        <option value="__all__">All</option>
        {#each sceneState.models as m}
          <option value={m.name}>{m.name}</option>
        {/each}
      </select>
    </div>
    <div class="field-row">
      <label for="mat-preset" class="field-label">물성치</label>
      <select id="mat-preset" bind:value={materialPreset} class="field-select">
        {#each presetOptions as opt}
          <option value={opt.value}>{opt.label}</option>
        {/each}
      </select>
    </div>
    <button class="tool-btn" onclick={handleAssignMaterial}
      disabled={!hasModels}>Assign Material</button>
  </div>
</div>

<style>
  .panel h3 {
    color: var(--color-primary); margin-bottom: 10px; font-size: 13px;
    text-transform: uppercase; letter-spacing: 1px; padding-bottom: 6px;
    border-bottom: 1px solid rgba(25, 118, 210, 0.2);
  }
  .section {
    margin-bottom: 10px; padding: 10px;
    background: var(--color-card); border: 1px solid #e8e8e8; border-radius: 6px;
  }
  .bc-section.fixed { border-left: 3px solid #00cc44; }
  .bc-section.force { border-left: 3px solid #ff2222; }
  .bc-section.material { border-left: 3px solid #1976d2; }
  .section-title {
    font-size: 11px; color: var(--color-primary); margin-bottom: 6px; font-weight: bold;
  }
  .subsection-label {
    font-size: 11px; color: #555; font-weight: 600; display: block; margin-bottom: 4px;
  }

  /* 일반 버튼 */
  .tool-btn {
    width: 100%; padding: 7px; margin: 3px 0; border: none; border-radius: 4px;
    background: var(--color-primary); color: #fff; cursor: pointer;
    font-size: 11px; transition: opacity 0.15s;
  }
  .tool-btn:hover:not(:disabled) { opacity: 0.85; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .tool-btn.secondary { background: #757575; }
  .tool-btn.active { background: #e53935; }

  /* Force 적용 버튼 강조 */
  .force-apply-btn { background: #ff2222; font-weight: 600; }

  /* 슬라이더 */
  .slider-row {
    display: flex; align-items: center; gap: 6px; font-size: 11px; color: #666; margin-bottom: 4px;
  }
  .slider-row input[type="range"] { flex: 1; }
  .slider-row label { min-width: 40px; }
  .val { font-size: 10px; color: #555; min-width: 50px; text-align: right;
         font-family: 'Consolas', monospace; font-weight: 600; }
  .hint { font-size: 10px; color: #888; margin: 4px 0; }

  /* 필드 행 (재료) */
  .field-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
  .field-label { font-size: 11px; color: #666; min-width: 36px; }
  .field-select {
    flex: 1; padding: 5px 6px; font-size: 11px;
    border: 1px solid #ccc; border-radius: 3px;
  }

  /* ── 크기 프리셋 ── */
  .force-mag-section { margin-bottom: 10px; }
  .mag-presets {
    display: flex; gap: 3px; margin-bottom: 6px;
  }
  .mag-btn {
    flex: 1; padding: 5px 2px; font-size: 11px; font-weight: 600;
    border: 1px solid #ddd; border-radius: 4px;
    background: #f8f8f8; cursor: pointer; color: #555;
    transition: all 0.15s;
  }
  .mag-btn:hover { background: #eee; border-color: #bbb; }
  .mag-btn.active {
    background: #ff2222; color: #fff; border-color: #ff2222;
  }

  /* 크기 슬라이더 + 숫자 입력 */
  .mag-input-row {
    display: flex; align-items: center; gap: 6px;
  }
  .mag-slider { flex: 1; }
  .mag-number {
    width: 60px; padding: 4px; font-size: 12px; font-weight: 600;
    text-align: center; border: 1px solid #ccc; border-radius: 3px;
    font-family: 'Consolas', monospace;
  }
  .mag-unit { font-size: 11px; color: #888; font-weight: 600; }

  /* ── 방향 프리셋 ── */
  .force-dir-section { margin-bottom: 8px; }
  .dir-presets {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 3px; margin-bottom: 8px;
  }
  .dir-btn {
    display: flex; flex-direction: column; align-items: center;
    padding: 5px 2px; border: 1px solid #ddd; border-radius: 4px;
    background: #f8f8f8; cursor: pointer;
    transition: all 0.15s; gap: 1px;
  }
  .dir-btn:hover { background: #eee; border-color: #bbb; }
  .dir-btn.active {
    background: #ff4444; color: #fff; border-color: #ff4444;
  }
  .dir-arrow { font-size: 14px; line-height: 1; }
  .dir-text { font-size: 9px; color: #666; }
  .dir-btn.active .dir-text { color: #fff; }

  /* X/Y/Z 입력 */
  .dir-xyz {
    display: flex; gap: 4px;
  }
  .dir-axis {
    flex: 1; display: flex; align-items: center; gap: 3px;
  }
  .axis-label {
    font-size: 10px; font-weight: 700; width: 16px; text-align: center;
    padding: 2px 0; border-radius: 2px; color: #fff;
  }
  .axis-label.x { background: #e53935; }
  .axis-label.y { background: #43a047; }
  .axis-label.z { background: #1e88e5; }
  .dir-axis input {
    width: 100%; padding: 3px 2px; font-size: 11px; text-align: center;
    border: 1px solid #ccc; border-radius: 3px;
    font-family: 'Consolas', monospace;
  }

  /* 힘 벡터 미리보기 */
  .force-preview {
    display: flex; align-items: center; justify-content: center;
    gap: 4px; padding: 5px 8px; margin: 6px 0;
    background: #fff3e0; border: 1px solid #ffe0b2; border-radius: 4px;
    font-family: 'Consolas', monospace; font-size: 11px;
  }
  .force-preview-label { color: #e65100; font-weight: 700; }
  .force-preview-val { color: #bf360c; font-weight: 600; }
  .force-preview-unit { color: #999; font-size: 10px; }

  /* BC 관리 */
  .bc-info {
    display: flex; align-items: center; justify-content: space-between;
    font-size: 11px; color: #666; margin-bottom: 6px;
  }
  .tool-btn-sm {
    padding: 3px 8px; font-size: 10px; border: 1px solid #ccc;
    border-radius: 3px; background: #f5f5f5; cursor: pointer; color: #555;
  }
  .tool-btn-sm:hover:not(:disabled) { background: #e0e0e0; }
  .tool-btn-sm:disabled { opacity: 0.4; cursor: default; }
</style>
