<script lang="ts">
  /**
   * FilePanel — 모델 목록, STL 로드, NRRD 로드, 파이프라인
   */
  import { sceneState } from '$lib/stores/scene.svelte';
  import { uiState } from '$lib/stores/ui.svelte';
  import { loadSampleModels, loadSTLFiles, loadNRRDFile, clearAll } from '$lib/actions/loading';

  let isLoading = $state(false);

  /** 샘플 모델 로드 */
  async function handleLoadSample() {
    isLoading = true;
    try {
      await loadSampleModels();
      uiState.toast(`${sceneState.models.length}개 모델 로드 완료`, 'success');
    } catch (e) {
      uiState.toast('샘플 모델 로드 실패', 'error');
    } finally {
      isLoading = false;
    }
  }

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

  /** 숨겨진 파일 입력 */
  let stlInput: HTMLInputElement;
  let nrrdInput: HTMLInputElement;
</script>

<div class="panel">
  <h3>FILE</h3>

  <!-- 모델 목록 -->
  <div class="section">
    <div class="section-title">Models ({sceneState.models.length})</div>
    {#if sceneState.models.length === 0}
      <p class="empty">No models loaded</p>
    {:else}
      {#each sceneState.models as model}
        <div class="model-item">
          <button
            class="vis-btn"
            class:hidden={!model.visible}
            onclick={() => sceneState.toggleVisibility(model.name)}
            title={model.visible ? 'Hide' : 'Show'}
            aria-label="{model.visible ? 'Hide' : 'Show'} {model.name}"
          >
            {model.visible ? '●' : '○'}
          </button>
          <span class="model-name">{model.name}</span>
          <span class="model-count">
            {model.vertexCount.toLocaleString()}v
          </span>
        </div>
      {/each}
    {/if}
  </div>

  <!-- Import -->
  <div class="section">
    <div class="section-title">Import</div>
    <button class="tool-btn primary" onclick={handleLoadSample} disabled={isLoading}>
      {isLoading ? 'Loading...' : 'Load Sample (L4+L5+Disc)'}
    </button>
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
  .vis-btn {
    background: none; border: none; cursor: pointer;
    font-size: 12px; padding: 0; line-height: 1; color: #666;
  }
  .vis-btn.hidden { opacity: 0.4; }
  .model-name { flex: 1; }
  .model-count { font-size: 10px; color: var(--color-text-muted); }
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
</style>
