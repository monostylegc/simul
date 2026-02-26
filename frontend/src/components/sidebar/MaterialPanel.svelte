<script lang="ts">
  /**
   * MaterialPanel — 재료 라이브러리 전용 사이드바 탭
   *
   * 기능:
   *  - 카테고리별 탭 (Bone/Disc/Implant/Soft/Custom)
   *  - 재료 카드 리스트 (병리학적 변이 표시)
   *  - 속성 편집기 (E/nu/density — 대수 슬라이더 + 숫자 입력)
   *  - 구성 모델 선택 (Linear Elastic / Neo-Hookean / Mooney-Rivlin / Ogden)
   *  - 커스텀 재료 저장/삭제 (localStorage)
   *  - 재료 할당 (대상 모델 선택 + Assign)
   */
  import { materialLibrary, formatE, sliderToE, eToSlider, CATEGORY_LABELS_KO, CONSTITUTIVE_MODELS, enuToMooneyRivlin, enuToOgden } from '$lib/stores/materials.svelte';
  import type { MaterialEntry, MaterialCategory, ConstitutiveModel } from '$lib/stores/materials.svelte';
  import { sceneState } from '$lib/stores/scene.svelte';
  import { assignMaterial } from '$lib/actions/analysis';
  import { uiState } from '$lib/stores/ui.svelte';
  import type { ResolvedMaterial } from '$lib/analysis/PreProcessor';

  // ── 대상 모델 선택 ──
  let materialTarget = $state('__all__');

  // ── 현재 선택된 재료 ──
  let selectedMaterial = $state<MaterialEntry | null>(null);

  // ── 속성 편집기 값 (선택 시 복사, 편집 시 여기서 수정) ──
  let editE = $state(15e9);
  let editNu = $state(0.3);
  let editDensity = $state(1850);

  // ── E 단위 모드 ──
  let eUnitMode = $state<'GPa' | 'MPa'>('GPa');

  // ── E 슬라이더 위치 (대수 스케일 0~1000) ──
  let eSliderPos = $state(eToSlider(15e9));

  // ── 구성 모델 편집 ──
  let editConstitutiveModel = $state<ConstitutiveModel>('linear_elastic');
  let editC10 = $state(0);
  let editC01 = $state(0);
  let editD1 = $state(0);
  let editMuOgden = $state(0);
  let editAlphaOgden = $state(2.0);

  // ── 모델 존재 여부 ──
  let hasModels = $derived(sceneState.models.length > 0);

  // ── 카테고리 탭 목록 ──
  const categoryTabs: Array<MaterialCategory | 'all'> = ['all', 'bone', 'disc', 'implant', 'soft_tissue', 'custom'];

  // ── 필터링된 재료 목록 ──
  let filteredList = $derived(materialLibrary.filtered);

  // ── E 표시값 (단위에 따라 변환) ──
  let displayE = $derived(eUnitMode === 'GPa' ? editE / 1e9 : editE / 1e6);

  // ── 재료 선택 핸들러 ──
  function selectMaterial(entry: MaterialEntry) {
    selectedMaterial = entry;
    editE = entry.E;
    editNu = entry.nu;
    editDensity = entry.density;
    eSliderPos = eToSlider(entry.E);
    // 자동 단위 결정
    eUnitMode = entry.E >= 1e9 ? 'GPa' : 'MPa';
    // 구성 모델 로드
    editConstitutiveModel = entry.constitutiveModel ?? 'linear_elastic';
    editC10 = entry.C10 ?? 0;
    editC01 = entry.C01 ?? 0;
    editD1 = entry.D1 ?? 0;
    editMuOgden = entry.mu_ogden ?? 0;
    editAlphaOgden = entry.alpha_ogden ?? 2.0;
  }

  // ── E 슬라이더 변경 ──
  function handleESlider(e: Event) {
    eSliderPos = parseInt((e.target as HTMLInputElement).value);
    editE = sliderToE(eSliderPos);
  }

  // ── E 숫자 입력 변경 ──
  function handleEInput(e: Event) {
    const val = parseFloat((e.target as HTMLInputElement).value);
    if (isNaN(val) || val <= 0) return;
    editE = eUnitMode === 'GPa' ? val * 1e9 : val * 1e6;
    eSliderPos = eToSlider(editE);
  }

  // ── 단위 전환 ──
  function toggleEUnit() {
    eUnitMode = eUnitMode === 'GPa' ? 'MPa' : 'GPa';
  }

  // ── nu 슬라이더 변경 ──
  function handleNuSlider(e: Event) {
    editNu = parseFloat((e.target as HTMLInputElement).value);
  }

  // ── density 슬라이더 변경 ──
  function handleDensitySlider(e: Event) {
    editDensity = parseInt((e.target as HTMLInputElement).value);
  }

  // ── 구성 모델 변경 ──
  function handleConstitutiveModelChange(e: Event) {
    const val = (e.target as HTMLSelectElement).value as ConstitutiveModel;
    editConstitutiveModel = val;
    // 모델 전환 시 E/ν에서 초탄성 파라미터 자동계산
    if (val === 'mooney_rivlin') autoCalcMR();
    else if (val === 'ogden') autoCalcOgden();
  }

  // ── Mooney-Rivlin 자동계산 (E/ν → C10, C01, D1) ──
  function autoCalcMR() {
    const { C10, C01, D1 } = enuToMooneyRivlin(editE, editNu);
    editC10 = C10;
    editC01 = C01;
    editD1 = D1;
  }

  // ── Ogden 자동계산 (E/ν → μ, α, D1) ──
  function autoCalcOgden() {
    const { mu_ogden, alpha_ogden, D1 } = enuToOgden(editE, editNu, editAlphaOgden);
    editMuOgden = mu_ogden;
    editAlphaOgden = alpha_ogden;
    editD1 = D1;
  }

  // ── 재료 할당 ──
  function handleAssign() {
    if (!selectedMaterial) {
      uiState.toast('재료를 먼저 선택하세요', 'warn');
      return;
    }
    if (!hasModels) {
      uiState.toast('모델을 먼저 로드하세요', 'warn');
      return;
    }

    const resolved: ResolvedMaterial = {
      key: selectedMaterial.key,
      label: selectedMaterial.labelKo,
      E: editE,
      nu: editNu,
      density: editDensity,
      constitutiveModel: editConstitutiveModel,
    };

    // 초탄성 파라미터 추가
    if (editConstitutiveModel === 'mooney_rivlin') {
      resolved.C10 = editC10;
      resolved.C01 = editC01;
      resolved.D1 = editD1;
    } else if (editConstitutiveModel === 'ogden') {
      resolved.mu_ogden = editMuOgden;
      resolved.alpha_ogden = editAlphaOgden;
      resolved.D1 = editD1;
    }

    if (materialTarget === '__all__') {
      sceneState.models.forEach(m => assignMaterial(m.name, resolved));
    } else {
      assignMaterial(materialTarget, resolved);
    }

    // 수정 여부 체크
    const edited = editE !== selectedMaterial.E || editNu !== selectedMaterial.nu || editDensity !== selectedMaterial.density
      || editConstitutiveModel !== (selectedMaterial.constitutiveModel ?? 'linear_elastic');
    const suffix = edited ? ' (수정됨)' : '';
    const modelLabel = CONSTITUTIVE_MODELS[editConstitutiveModel].label;
    uiState.toast(`재료 할당: ${resolved.label}${suffix} — ${modelLabel}, E=${formatE(editE)}`, 'success');
  }

  // ── 속성 초기화 (원본 값 복원) ──
  function handleReset() {
    if (!selectedMaterial) return;
    editE = selectedMaterial.E;
    editNu = selectedMaterial.nu;
    editDensity = selectedMaterial.density;
    eSliderPos = eToSlider(selectedMaterial.E);
    eUnitMode = selectedMaterial.E >= 1e9 ? 'GPa' : 'MPa';
    // 구성 모델 복원
    editConstitutiveModel = selectedMaterial.constitutiveModel ?? 'linear_elastic';
    editC10 = selectedMaterial.C10 ?? 0;
    editC01 = selectedMaterial.C01 ?? 0;
    editD1 = selectedMaterial.D1 ?? 0;
    editMuOgden = selectedMaterial.mu_ogden ?? 0;
    editAlphaOgden = selectedMaterial.alpha_ogden ?? 2.0;
  }

  // ── 커스텀 재료 저장 ──
  function handleSaveCustom() {
    const name = prompt('커스텀 재료 이름을 입력하세요:');
    if (!name || name.trim().length === 0) return;

    const modelLabel = CONSTITUTIVE_MODELS[editConstitutiveModel].label;
    const customParams: Parameters<typeof materialLibrary.addCustom>[0] = {
      label: name.trim(),
      labelKo: name.trim(),
      E: editE,
      nu: editNu,
      density: editDensity,
      constitutiveModel: editConstitutiveModel,
      description: `사용자 정의: ${modelLabel}, E=${formatE(editE)}, ν=${editNu}`,
    };

    // 초탄성 파라미터 포함
    if (editConstitutiveModel === 'mooney_rivlin') {
      customParams.C10 = editC10;
      customParams.C01 = editC01;
      customParams.D1 = editD1;
    } else if (editConstitutiveModel === 'ogden') {
      customParams.mu_ogden = editMuOgden;
      customParams.alpha_ogden = editAlphaOgden;
      customParams.D1 = editD1;
    }

    materialLibrary.addCustom(customParams);
    uiState.toast(`커스텀 재료 저장: ${name} (${modelLabel})`, 'success');
    // Custom 카테고리로 전환
    materialLibrary.activeCategory = 'custom';
  }

  // ── 커스텀 재료 삭제 ──
  function handleDeleteCustom(key: string) {
    materialLibrary.removeCustom(key);
    if (selectedMaterial?.key === key) selectedMaterial = null;
    uiState.toast('커스텀 재료 삭제됨', 'info');
  }

  // ── 검색 핸들러 ──
  function handleSearch(e: Event) {
    materialLibrary.searchQuery = (e.target as HTMLInputElement).value;
  }
</script>

<div class="panel">
  <h3>MATERIAL LIBRARY</h3>

  <!-- 카테고리 탭 -->
  <div class="mat-tabs">
    {#each categoryTabs as cat}
      <button
        class="mat-tab"
        class:active={materialLibrary.activeCategory === cat}
        onclick={() => { materialLibrary.activeCategory = cat; }}
      >{CATEGORY_LABELS_KO[cat]}</button>
    {/each}
  </div>

  <!-- 검색 -->
  <input
    type="text"
    class="mat-search"
    placeholder="검색..."
    value={materialLibrary.searchQuery}
    oninput={handleSearch}
  />

  <!-- 재료 리스트 -->
  <div class="mat-list">
    {#each filteredList as entry (entry.key)}
      <div
        class="mat-card"
        class:selected={selectedMaterial?.key === entry.key}
        class:pathological={entry.isPathological}
        class:custom={entry.isCustom}
        role="button"
        tabindex="0"
        onclick={() => selectMaterial(entry)}
        onkeydown={(e: KeyboardEvent) => { if (e.key === 'Enter') selectMaterial(entry); }}
      >
        <div class="mat-card-header">
          <span class="mat-card-name">
            {#if entry.isPathological}<span class="path-icon" title="병리학적 변이">▲</span>{/if}
            {entry.labelKo}
          </span>
          <span class="mat-card-model">{CONSTITUTIVE_MODELS[entry.constitutiveModel ?? 'linear_elastic'].label}</span>
          {#if entry.isCustom}
            <button class="mat-del-btn" title="삭제"
              onclick={(e: MouseEvent) => { e.stopPropagation(); handleDeleteCustom(entry.key); }}>×</button>
          {/if}
        </div>
        <div class="mat-card-props">
          <span>E={formatE(entry.E)}</span>
          <span>ν={entry.nu}</span>
          <span>ρ={entry.density}</span>
        </div>
      </div>
    {:else}
      <div class="mat-empty">해당하는 재료가 없습니다</div>
    {/each}
  </div>

  <!-- 속성 편집기 (재료 선택 시 표시) -->
  {#if selectedMaterial}
    <div class="mat-editor">
      <div class="editor-title">속성 편집 — {selectedMaterial.labelKo}</div>

      <!-- 구성 모델 선택 -->
      <div class="editor-row">
        <label class="editor-label">구성 모델 (Constitutive Model)</label>
        <select class="model-select" value={editConstitutiveModel} onchange={handleConstitutiveModelChange}>
          {#each Object.entries(CONSTITUTIVE_MODELS) as [key, meta]}
            <option value={key}>{meta.label}</option>
          {/each}
        </select>
        <div class="model-desc">{CONSTITUTIVE_MODELS[editConstitutiveModel].description}</div>
        {#if CONSTITUTIVE_MODELS[editConstitutiveModel].femOnly}
          <div class="model-hint">⚠ FEM 전용 — PD/SPG에서는 Linear Elastic으로 대체</div>
        {/if}
      </div>

      {#if editConstitutiveModel === 'linear_elastic' || editConstitutiveModel === 'neo_hookean'}
        <!-- ━━━ Linear Elastic / Neo-Hookean: E/ν ━━━ -->
        <div class="editor-row">
          <label for="edit-e" class="editor-label">E (Young's modulus)</label>
          <div class="editor-controls">
            <input id="edit-e-slider" type="range" min="0" max="1000" step="1"
              value={eSliderPos} oninput={handleESlider} class="editor-slider" />
            <input id="edit-e" type="number" step="0.1" min="0.01"
              value={displayE.toFixed(displayE >= 10 ? 1 : 2)}
              onchange={handleEInput} class="editor-num" />
            <button class="unit-btn" onclick={toggleEUnit}>{eUnitMode}</button>
          </div>
        </div>
        <div class="editor-row">
          <label for="edit-nu" class="editor-label">ν (Poisson's ratio)</label>
          <div class="editor-controls">
            <input id="edit-nu" type="range" min="0.01" max="0.499" step="0.01"
              value={editNu} oninput={handleNuSlider} class="editor-slider" />
            <span class="editor-val">{editNu.toFixed(2)}</span>
          </div>
        </div>

      {:else if editConstitutiveModel === 'mooney_rivlin'}
        <!-- ━━━ Mooney-Rivlin: 기본 물성 (참조) + C10/C01/D1 ━━━ -->
        <div class="editor-row ref-section">
          <label class="editor-label ref-label">기본 물성 (참조)</label>
          <div class="ref-values">
            <span>E = {formatE(editE)}</span>
            <span>ν = {editNu.toFixed(2)}</span>
          </div>
        </div>
        <div class="editor-row">
          <label class="editor-label">C₁₀ [Pa]</label>
          <div class="editor-controls">
            <input type="text" inputmode="decimal"
              value={editC10 !== 0 ? editC10.toPrecision(6) : '0'}
              onchange={(e: Event) => { editC10 = parseFloat((e.target as HTMLInputElement).value) || 0; }}
              class="editor-num-wide" />
          </div>
        </div>
        <div class="editor-row">
          <label class="editor-label">C₀₁ [Pa]</label>
          <div class="editor-controls">
            <input type="text" inputmode="decimal"
              value={editC01 !== 0 ? editC01.toPrecision(6) : '0'}
              onchange={(e: Event) => { editC01 = parseFloat((e.target as HTMLInputElement).value) || 0; }}
              class="editor-num-wide" />
          </div>
        </div>
        <div class="editor-row">
          <label class="editor-label">D₁ [1/Pa]</label>
          <div class="editor-controls">
            <input type="text" inputmode="decimal"
              value={editD1 !== 0 ? editD1.toPrecision(4) : '0'}
              onchange={(e: Event) => { editD1 = parseFloat((e.target as HTMLInputElement).value) || 0; }}
              class="editor-num-wide" />
          </div>
        </div>
        <div class="auto-calc-row">
          <button class="auto-calc-btn" onclick={autoCalcMR}
            title="현재 E/ν 값에서 C10, C01, D1 자동 변환">⟳ E/ν에서 자동계산</button>
        </div>

      {:else if editConstitutiveModel === 'ogden'}
        <!-- ━━━ Ogden: 기본 물성 (참조) + μ/α/D1 ━━━ -->
        <div class="editor-row ref-section">
          <label class="editor-label ref-label">기본 물성 (참조)</label>
          <div class="ref-values">
            <span>E = {formatE(editE)}</span>
            <span>ν = {editNu.toFixed(2)}</span>
          </div>
        </div>
        <div class="editor-row">
          <label class="editor-label">μ (Shear modulus) [Pa]</label>
          <div class="editor-controls">
            <input type="text" inputmode="decimal"
              value={editMuOgden !== 0 ? editMuOgden.toPrecision(6) : '0'}
              onchange={(e: Event) => { editMuOgden = parseFloat((e.target as HTMLInputElement).value) || 0; }}
              class="editor-num-wide" />
          </div>
        </div>
        <div class="editor-row">
          <label class="editor-label">α (Exponent)</label>
          <div class="editor-controls">
            <input type="text" inputmode="decimal"
              value={editAlphaOgden}
              onchange={(e: Event) => { editAlphaOgden = parseFloat((e.target as HTMLInputElement).value) || 2.0; }}
              class="editor-num-wide" />
          </div>
        </div>
        <div class="editor-row">
          <label class="editor-label">D₁ [1/Pa]</label>
          <div class="editor-controls">
            <input type="text" inputmode="decimal"
              value={editD1 !== 0 ? editD1.toPrecision(4) : '0'}
              onchange={(e: Event) => { editD1 = parseFloat((e.target as HTMLInputElement).value) || 0; }}
              class="editor-num-wide" />
          </div>
        </div>
        <div class="auto-calc-row">
          <button class="auto-calc-btn" onclick={autoCalcOgden}
            title="현재 E/ν 값에서 μ, α, D1 자동 변환">⟳ E/ν에서 자동계산</button>
        </div>
      {/if}

      <!-- density (모든 모델 공통) -->
      <div class="editor-row">
        <label for="edit-density" class="editor-label">ρ (Density, kg/m³)</label>
        <div class="editor-controls">
          <input id="edit-density" type="range" min="500" max="9000" step="50"
            value={editDensity} oninput={handleDensitySlider} class="editor-slider" />
          <span class="editor-val">{editDensity}</span>
        </div>
      </div>
    </div>
  {/if}

  <!-- 할당 섹션 -->
  <div class="assign-section">
    <div class="assign-row">
      <label for="mat-target" class="assign-label">대상</label>
      <select id="mat-target" bind:value={materialTarget} class="assign-select">
        <option value="__all__">All</option>
        {#each sceneState.models as m}
          <option value={m.name}>{m.name}</option>
        {/each}
      </select>
    </div>
    <button class="assign-btn" onclick={handleAssign}
      disabled={!hasModels || !selectedMaterial}>
      Assign Material
    </button>
  </div>

  <!-- 편집 액션 -->
  {#if selectedMaterial}
    <div class="editor-actions">
      <button class="action-btn save" onclick={handleSaveCustom}>+ 커스텀 저장</button>
      <button class="action-btn" onclick={handleReset}>초기화</button>
    </div>
  {/if}
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .panel h3 {
    color: var(--color-primary); margin-bottom: 10px; font-size: 13px;
    text-transform: uppercase; letter-spacing: 1px; padding-bottom: 6px;
    border-bottom: 1px solid rgba(25, 118, 210, 0.2);
    flex-shrink: 0;
  }

  /* ── 카테고리 탭 ── */
  .mat-tabs {
    display: flex; flex-wrap: wrap; gap: 2px; margin-bottom: 8px;
    flex-shrink: 0;
  }
  .mat-tab {
    flex: 1; min-width: 0; padding: 5px 2px; border: 1px solid #ddd; border-radius: 4px;
    background: #f5f5f5; color: #666; font-size: 10px; cursor: pointer;
    text-align: center; transition: all 0.15s;
  }
  .mat-tab:hover { background: #e3f2fd; }
  .mat-tab.active {
    background: var(--color-primary); color: #fff; border-color: var(--color-primary);
  }

  /* ── 검색 ── */
  .mat-search {
    width: 100%; padding: 6px 8px; font-size: 11px;
    border: 1px solid #ddd; border-radius: 4px; margin-bottom: 8px;
    box-sizing: border-box; flex-shrink: 0;
  }
  .mat-search::placeholder { color: #aaa; }

  /* ── 재료 리스트 ── */
  .mat-list {
    flex: 1; min-height: 120px; max-height: 280px;
    overflow-y: auto; margin-bottom: 8px;
    border: 1px solid #e0e0e0; border-radius: 4px;
  }
  .mat-card {
    display: block; width: 100%; padding: 8px 10px; border: none;
    border-bottom: 1px solid #f0f0f0; background: #fff;
    cursor: pointer; text-align: left; transition: background 0.1s;
    border-left: 3px solid transparent;
  }
  .mat-card:last-child { border-bottom: none; }
  .mat-card:hover { background: #f5f8ff; }
  .mat-card.selected { background: #e3f2fd; border-left-color: var(--color-primary); }
  .mat-card.pathological { border-left-color: #ff8f00; }
  .mat-card.pathological.selected { border-left-color: #e65100; }
  .mat-card.custom { border-left-color: #9c27b0; }
  .mat-card.custom.selected { border-left-color: #6a1b9a; }

  .mat-card-header {
    display: flex; align-items: center; gap: 6px;
  }
  .mat-card-name {
    font-size: 11px; font-weight: 600; color: #333; flex: 1;
  }
  .mat-card-model {
    font-size: 9px; color: #888; background: #f0f0f0;
    padding: 1px 5px; border-radius: 3px; flex-shrink: 0;
  }
  .path-icon {
    color: #ff8f00; font-size: 9px; margin-right: 2px;
  }
  .mat-del-btn {
    background: none; border: none; color: #999; font-size: 14px;
    cursor: pointer; padding: 0 2px; line-height: 1; flex-shrink: 0;
  }
  .mat-del-btn:hover { color: #e53935; }

  .mat-card-props {
    display: flex; gap: 8px; font-size: 9px; color: #888; margin-top: 3px;
    font-family: 'Consolas', monospace;
  }

  .mat-empty {
    padding: 16px; text-align: center; color: #aaa; font-size: 11px;
  }

  /* ── 속성 편집기 ── */
  .mat-editor {
    padding: 10px; background: #fafafa; border: 1px solid #e0e0e0;
    border-radius: 6px; margin-bottom: 8px; flex-shrink: 0;
  }
  .editor-title {
    font-size: 11px; font-weight: 600; color: var(--color-primary); margin-bottom: 8px;
    padding-bottom: 4px; border-bottom: 1px solid #e8e8e8;
  }
  .editor-row {
    margin-bottom: 8px;
  }
  .editor-label {
    display: block; font-size: 10px; color: #666; margin-bottom: 3px;
  }
  .editor-controls {
    display: flex; align-items: center; gap: 6px;
  }
  .editor-slider {
    flex: 1; height: 18px;
  }
  .editor-num {
    width: 60px; padding: 3px 5px; font-size: 10px;
    border: 1px solid #ccc; border-radius: 3px; text-align: right;
    font-family: 'Consolas', monospace;
  }
  .editor-val {
    min-width: 44px; font-size: 10px; color: #555; text-align: right;
    font-family: 'Consolas', monospace; font-weight: 600;
  }
  .unit-btn {
    padding: 3px 8px; font-size: 9px; border: 1px solid #ccc;
    border-radius: 3px; background: #f0f0f0; cursor: pointer; color: #555;
    min-width: 36px;
  }
  .unit-btn:hover { background: #e0e0e0; }

  /* ── 구성 모델 선택기 ── */
  .model-select {
    width: 100%; padding: 5px 8px; font-size: 11px;
    border: 1px solid #ccc; border-radius: 4px; margin-top: 2px;
  }
  .model-desc {
    font-size: 9px; color: #888; margin-top: 3px;
  }
  .model-hint {
    font-size: 9px; color: #e65100; margin-top: 3px;
    padding: 3px 6px; background: #fff3e0; border-radius: 3px;
  }

  /* ── 기본 물성 참조 섹션 ── */
  .ref-section {
    background: #f5f5f5; padding: 6px 8px; border-radius: 4px;
    margin-bottom: 8px;
  }
  .ref-label {
    font-size: 9px; color: #999; margin-bottom: 2px;
  }
  .ref-values {
    display: flex; gap: 12px; font-size: 10px; color: #666;
    font-family: 'Consolas', monospace;
  }

  /* ── 초탄성 파라미터 입력 ── */
  .editor-num-wide {
    width: 100%; padding: 4px 8px; font-size: 11px;
    border: 1px solid #ccc; border-radius: 3px; text-align: right;
    font-family: 'Consolas', monospace; box-sizing: border-box;
  }

  /* ── E/ν 자동계산 ── */
  .auto-calc-row {
    display: flex; justify-content: flex-end; margin: 4px 0 8px;
  }
  .auto-calc-btn {
    padding: 4px 10px; font-size: 10px; border: 1px solid #1976d2;
    border-radius: 4px; background: #e3f2fd; color: #1976d2;
    cursor: pointer; white-space: nowrap; font-weight: 500;
  }
  .auto-calc-btn:hover { background: #bbdefb; }

  /* ── 할당 섹션 ── */
  .assign-section {
    padding: 10px; background: var(--color-card); border: 1px solid #e8e8e8;
    border-radius: 6px; margin-bottom: 8px; flex-shrink: 0;
  }
  .assign-row {
    display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
  }
  .assign-label {
    font-size: 11px; color: #666; flex-shrink: 0;
  }
  .assign-select {
    flex: 1; padding: 5px 8px; font-size: 11px;
    border: 1px solid #ccc; border-radius: 4px;
  }
  .assign-btn {
    width: 100%; padding: 9px; border: none; border-radius: 5px;
    background: var(--color-primary); color: #fff; cursor: pointer;
    font-size: 12px; font-weight: 600; transition: opacity 0.15s;
  }
  .assign-btn:hover:not(:disabled) { opacity: 0.85; }
  .assign-btn:disabled { opacity: 0.4; cursor: default; }

  /* ── 편집 액션 ── */
  .editor-actions {
    display: flex; gap: 6px; flex-shrink: 0;
  }
  .action-btn {
    flex: 1; padding: 7px 10px; border: 1px solid #ccc; border-radius: 4px;
    background: #fff; color: #555; font-size: 11px; cursor: pointer;
    transition: all 0.15s;
  }
  .action-btn:hover { background: #f0f0f0; }
  .action-btn.save {
    border-color: #9c27b0; color: #9c27b0;
  }
  .action-btn.save:hover { background: #f3e5f5; }
</style>
