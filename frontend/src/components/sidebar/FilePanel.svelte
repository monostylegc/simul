<script lang="ts">
  /**
   * FilePanel — 모델 목록, STL 로드, NRRD 로드, 파이프라인
   */
  import { sceneState } from '$lib/stores/scene.svelte';
  import { uiState } from '$lib/stores/ui.svelte';
  import { pipelineState } from '$lib/stores/pipeline.svelte';
  import { loadSTLFiles, loadNRRDFile, clearAll } from '$lib/actions/loading';
  import { runDicomPipeline } from '$lib/actions/pipeline';

  let isLoading = $state(false);

  /** 사용자 STL 파일 로드 */
  async function handleSTLFiles(files: FileList) {
    isLoading = true;
    try {
      await loadSTLFiles(files);
      uiState.toast(`STL ${files.length}개 파일 로드 완료`, 'success');
    } catch (e) {
      uiState.toast('STL 로드 실패', 'error');
    } finally {
      isLoading = false;
    }
  }

  /** NRRD 파일 로드 */
  async function handleNRRDFiles(files: FileList) {
    if (files.length === 0) return;
    isLoading = true;
    try {
      await loadNRRDFile(files[0]);
      uiState.toast('NRRD 로드 완료', 'success');
    } catch (e) {
      uiState.toast('NRRD 로드 실패', 'error');
    } finally {
      isLoading = false;
    }
  }

  /** Clear All (확인 다이얼로그) */
  async function handleClearAll() {
    if (sceneState.models.length === 0) return;
    const ok = await uiState.confirm(
      '모두 삭제',
      `${sceneState.models.length}개 모델과 모든 해석 데이터를 삭제합니다. 계속하시겠습니까?`
    );
    if (ok) {
      clearAll();
      uiState.toast('모두 삭제됨', 'info');
    }
  }

  /** DICOM 폴더 업로드 + 파이프라인 실행 (Step 9) */
  async function handleDicomUpload(e: Event) {
    const target = e.target as HTMLInputElement;
    if (!target.files || target.files.length === 0) return;
    await runDicomPipeline(target.files);
    target.value = '';
  }

  /** 파이프라인 진행 표시 텍스트 */
  const stepLabels: Record<string, string> = {
    idle: '',
    uploading: 'DICOM 업로드 중...',
    segmentation: '세그멘테이션 중...',
    mesh_extraction: '메쉬 추출 중...',
    material_assignment: '재료 할당 중...',
    complete: '파이프라인 완료!',
    error: '파이프라인 오류',
  };

  /** 숨겨진 파일 입력 */
  let stlInput: HTMLInputElement;
  let nrrdInput: HTMLInputElement;
  let dicomInput: HTMLInputElement;

  /** 카테고리 접기 상태 */
  let collapsedCategories = $state<Record<string, boolean>>({});

  /** 카테고리 정의 (표시 순서) */
  const CATEGORY_ORDER = ['bone', 'disc', 'soft_tissue', 'implant', ''] as const;
  const CATEGORY_LABELS: Record<string, string> = {
    bone: 'Bone',
    disc: 'Disc',
    soft_tissue: 'Soft Tissue',
    implant: 'Implant',
    '': 'Other',
  };
  const CATEGORY_COLORS: Record<string, string> = {
    bone: '#e6d5c3',
    disc: '#6ba3d6',
    soft_tissue: '#f0a0b0',
    implant: '#b0b0b0',
    '': '#888888',
  };

  /** 카테고리별 모델 그룹핑 (반응형) */
  const modelsByCategory = $derived.by(() => {
    const groups: Record<string, typeof sceneState.models> = {};
    for (const cat of CATEGORY_ORDER) {
      const items = sceneState.models.filter(m => m.materialType === cat);
      if (items.length > 0) groups[cat] = items;
    }
    return groups;
  });

  /** 파이프라인 모델이 있으면 카테고리 뷰 사용 */
  const hasCategorizedModels = $derived(
    sceneState.models.some(m => m.materialType !== '')
  );

  /** 카테고리 접기/펼치기 토글 */
  function toggleCategory(cat: string) {
    collapsedCategories[cat] = !collapsedCategories[cat];
  }

  /** 카테고리 내 모델 전체 가시성 토글 */
  function toggleCategoryVisibility(cat: string) {
    const models = modelsByCategory[cat];
    if (!models) return;
    const allVisible = models.every(m => m.visible);
    sceneState.setCategoryVisibility(cat, !allVisible);
  }

  /** 개별 모델 삭제 */
  function handleRemoveModel(name: string) {
    sceneState.removeModel(name);
    uiState.toast(`${name} 삭제됨`, 'info');
  }

  /** 카테고리 내 모델 전체 삭제 */
  async function handleRemoveCategory(cat: string) {
    const models = modelsByCategory[cat];
    if (!models || models.length === 0) return;
    const label = CATEGORY_LABELS[cat] ?? cat;
    const ok = await uiState.confirm(
      '카테고리 삭제',
      `${label} 카테고리의 ${models.length}개 모델을 삭제합니다.`,
    );
    if (ok) {
      const names = models.map(m => m.name);
      names.forEach(n => sceneState.removeModel(n));
      uiState.toast(`${label} ${names.length}개 삭제됨`, 'info');
    }
  }
</script>

<div class="panel">
  <h3>FILE</h3>

  <!-- 모델 목록 -->
  <div class="section">
    <div class="section-title">Models ({sceneState.models.length})</div>
    {#if sceneState.models.length === 0}
      <p class="empty">No models loaded</p>
    {:else if hasCategorizedModels}
      <!-- 카테고리별 그룹핑 뷰 -->
      {#each Object.entries(modelsByCategory) as [cat, models]}
        <div class="category-group">
          <div class="category-header">
            <button class="category-toggle" onclick={() => toggleCategory(cat)}>
              {collapsedCategories[cat] ? '▶' : '▼'}
            </button>
            <span
              class="category-color-dot"
              style="background:{CATEGORY_COLORS[cat] ?? '#888'};"
            ></span>
            <span class="category-label">{CATEGORY_LABELS[cat] ?? cat}</span>
            <span class="category-count">({models.length})</span>
            <button
              class="category-vis-btn"
              onclick={() => toggleCategoryVisibility(cat)}
              title="전체 표시/숨김"
              aria-label="Toggle {CATEGORY_LABELS[cat]} visibility"
            >
              {models.every(m => m.visible) ? '👁' : '👁‍🗨'}
            </button>
            <button
              class="category-del-btn"
              onclick={() => handleRemoveCategory(cat)}
              title="카테고리 전체 삭제"
              aria-label="Delete all {CATEGORY_LABELS[cat]}"
            >🗑</button>
          </div>
          {#if !collapsedCategories[cat]}
            {#each models as model}
              <div class="model-item categorized">
                <input
                  type="checkbox"
                  class="vis-check"
                  checked={model.visible}
                  onchange={() => sceneState.toggleVisibility(model.name)}
                  title={model.visible ? 'Hide' : 'Show'}
                  aria-label="{model.visible ? 'Hide' : 'Show'} {model.name}"
                />
                <input
                  type="color"
                  class="color-input"
                  value={model.color}
                  oninput={(e) => sceneState.setColor(model.name, (e.target as HTMLInputElement).value)}
                  title="Change color"
                />
                <span class="model-name">{model.name}</span>
                <span class="model-count">
                  {model.vertexCount.toLocaleString()}v
                </span>
                <button
                  class="del-btn"
                  onclick={() => handleRemoveModel(model.name)}
                  title="삭제"
                  aria-label="Delete {model.name}"
                >✕</button>
              </div>
            {/each}
          {/if}
        </div>
      {/each}
    {:else}
      <!-- 플랫 목록 (카테고리 없는 경우) -->
      {#each sceneState.models as model}
        <div class="model-item">
          <input
            type="checkbox"
            class="vis-check"
            checked={model.visible}
            onchange={() => sceneState.toggleVisibility(model.name)}
            title={model.visible ? 'Hide' : 'Show'}
            aria-label="{model.visible ? 'Hide' : 'Show'} {model.name}"
          />
          <span class="model-name">{model.name}</span>
          <span class="model-count">
            {model.vertexCount.toLocaleString()}v
          </span>
          <button
            class="del-btn"
            onclick={() => handleRemoveModel(model.name)}
            title="삭제"
            aria-label="Delete {model.name}"
          >✕</button>
        </div>
      {/each}
    {/if}
  </div>

  <!-- Import -->
  <div class="section">
    <div class="section-title">Import</div>
    <button class="tool-btn secondary" onclick={() => stlInput.click()} disabled={isLoading}>
      Load STL...
    </button>
    <button class="tool-btn secondary" onclick={() => nrrdInput.click()} disabled={isLoading}>
      Load NRRD...
    </button>
    <button class="tool-btn danger"
      onclick={handleClearAll}
      disabled={isLoading || sceneState.models.length === 0}>
      Clear All
    </button>

    <!-- 숨겨진 파일 입력 -->
    <input bind:this={stlInput} type="file" accept=".stl" multiple
      onchange={(e) => { const t = e.target as HTMLInputElement; if(t.files) handleSTLFiles(t.files); t.value=''; }}
      style="display:none;" aria-hidden="true">
    <input bind:this={nrrdInput} type="file" accept=".nrrd"
      onchange={(e) => { const t = e.target as HTMLInputElement; if(t.files) handleNRRDFiles(t.files); t.value=''; }}
      style="display:none;" aria-hidden="true">
  </div>

  <!-- DICOM 파이프라인 (Step 9) -->
  <div class="section pipeline-section">
    <div class="section-title">CT/MRI Pipeline</div>
    <button class="tool-btn dicom-btn"
      onclick={() => dicomInput.click()}
      disabled={pipelineState.step !== 'idle' && pipelineState.step !== 'complete' && pipelineState.step !== 'error'}>
      🏥 Load DICOM (CT/MRI)
    </button>
    <div class="pipeline-hint">
      DICOM 폴더를 선택하면 자동으로:<br>
      세그멘테이션 → 메쉬 추출 → 3D 모델 로드
    </div>

    <!-- 파이프라인 진행 상태 -->
    {#if pipelineState.step !== 'idle'}
      <div class="pipeline-progress">
        <div class="pipeline-step-text">
          {stepLabels[pipelineState.step] ?? pipelineState.message}
        </div>
        {#if pipelineState.step !== 'complete' && pipelineState.step !== 'error'}
          <div class="pipeline-bar-bg">
            <div class="pipeline-bar" style="width:{pipelineState.progress * 100}%"></div>
          </div>
        {/if}
        {#if pipelineState.step === 'error'}
          <div class="pipeline-error">{pipelineState.error}</div>
        {/if}
        {#if pipelineState.step === 'complete' && pipelineState.extractedMeshes.length > 0}
          <div class="pipeline-result">
            {pipelineState.extractedMeshes.length}개 구조물 자동 로드됨
          </div>
        {/if}
      </div>
    {/if}

    <!-- 숨겨진 DICOM 폴더 입력 -->
    <!-- svelte-ignore a11y_missing_attribute -->
    <input bind:this={dicomInput} type="file" multiple
      onchange={handleDicomUpload}
      style="display:none;" aria-hidden="true">
  </div>
</div>

<style>
  .panel h3 {
    color: var(--color-primary);
    margin-bottom: 10px;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(25, 118, 210, 0.2);
  }
  .section {
    margin-bottom: 12px;
    padding: 10px;
    background: var(--color-card);
    border: 1px solid #e8e8e8;
    border-radius: 6px;
  }
  .section-title {
    font-size: 11px;
    color: var(--color-primary);
    margin-bottom: 6px;
    font-weight: bold;
  }
  .empty { font-size: 11px; color: var(--color-text-muted); }
  .model-item {
    display: flex; align-items: center; gap: 6px;
    padding: 3px 0; font-size: 12px;
  }
  .vis-check {
    width: 13px; height: 13px; margin: 0; cursor: pointer;
    accent-color: var(--color-primary); flex-shrink: 0;
  }
  .model-name { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .model-count { font-size: 10px; color: var(--color-text-muted); white-space: nowrap; }

  /* 카테고리 그룹 */
  .category-group { margin-bottom: 4px; }
  .category-header {
    display: flex; align-items: center; gap: 4px;
    padding: 4px 0; font-size: 11px; font-weight: 600;
    border-bottom: 1px solid #eee; margin-bottom: 2px;
  }
  .category-toggle {
    background: none; border: none; cursor: pointer;
    font-size: 9px; padding: 0; line-height: 1; color: #888;
    width: 14px; text-align: center;
  }
  .category-color-dot {
    width: 8px; height: 8px; border-radius: 50%;
    display: inline-block; flex-shrink: 0;
  }
  .category-label { color: #444; }
  .category-count { color: var(--color-text-muted); font-weight: normal; font-size: 10px; }
  .category-vis-btn {
    background: none; border: none; cursor: pointer;
    font-size: 11px; padding: 0; margin-left: auto; opacity: 0.7;
  }
  .category-vis-btn:hover { opacity: 1; }
  .category-del-btn {
    background: none; border: none; cursor: pointer;
    font-size: 10px; padding: 0; opacity: 0.4;
    transition: opacity 0.15s;
  }
  .category-del-btn:hover { opacity: 1; }
  .model-item.categorized { padding-left: 14px; }

  /* 개별 삭제 버튼 */
  .del-btn {
    background: none; border: none; cursor: pointer;
    font-size: 11px; color: #c62828; padding: 0 2px;
    opacity: 0; transition: opacity 0.15s;
    flex-shrink: 0; line-height: 1;
  }
  .model-item:hover .del-btn { opacity: 0.6; }
  .del-btn:hover { opacity: 1 !important; }

  /* per-model 색상 입력 */
  .color-input {
    width: 18px; height: 18px; border: none; padding: 0;
    cursor: pointer; background: none; flex-shrink: 0;
    border-radius: 3px; overflow: hidden;
  }
  .color-input::-webkit-color-swatch-wrapper { padding: 1px; }
  .color-input::-webkit-color-swatch { border: 1px solid #ccc; border-radius: 2px; }

  .tool-btn {
    width: 100%; padding: 8px; margin: 3px 0;
    border: none; border-radius: 4px; color: #fff;
    cursor: pointer; font-size: 12px; transition: opacity 0.15s;
  }
  .tool-btn:hover:not(:disabled) { opacity: 0.85; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .tool-btn.primary { background: var(--color-primary); }
  .tool-btn.secondary { background: #757575; }
  .tool-btn.danger { background: var(--color-danger); }

  /* DICOM 파이프라인 (Step 9) */
  .pipeline-section { border-left: 3px solid #00897b; }
  .dicom-btn { background: #00897b !important; font-weight: 600; }
  .pipeline-hint { font-size: 10px; color: #888; line-height: 1.4; margin: 6px 0; }
  .pipeline-progress {
    margin-top: 8px; padding: 8px; background: #e0f2f1; border-radius: 4px;
  }
  .pipeline-step-text { font-size: 11px; color: #00695c; margin-bottom: 4px; }
  .pipeline-bar-bg {
    height: 4px; background: #b2dfdb; border-radius: 2px; overflow: hidden;
  }
  .pipeline-bar {
    height: 100%; background: #00897b; transition: width 0.3s;
  }
  .pipeline-error {
    font-size: 10px; color: #c62828; margin-top: 4px;
  }
  .pipeline-result {
    font-size: 11px; color: #2e7d32; margin-top: 4px; font-weight: 600;
  }
</style>
