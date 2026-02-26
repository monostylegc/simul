<script lang="ts">
  /**
   * Sidebar — 탭별 패널 전환
   */
  import { uiState } from '$lib/stores/ui.svelte';
  import FilePanel from './FilePanel.svelte';
  import ModelingPanel from './ModelingPanel.svelte';
  import PreProcessPanel from './PreProcessPanel.svelte';
  import SolvePanel from './SolvePanel.svelte';
  import PostProcessPanel from './PostProcessPanel.svelte';
  import MaterialPanel from './MaterialPanel.svelte';
</script>

<aside class="sidebar">
  {#if uiState.activeTab === 'file'}
    <FilePanel />
  {:else if uiState.activeTab === 'modeling'}
    <ModelingPanel />
  {:else if uiState.activeTab === 'material'}
    <MaterialPanel />
  {:else if uiState.activeTab === 'preprocess'}
    <PreProcessPanel />
  {:else if uiState.activeTab === 'solve'}
    <SolvePanel />
  {:else if uiState.activeTab === 'postprocess'}
    <PostProcessPanel />
  {/if}
</aside>

<style>
  .sidebar {
    width: var(--sidebar-width);
    background: var(--color-surface);
    padding: 12px;
    color: var(--color-text);
    overflow-y: auto;
    border-left: 1px solid var(--color-border);
    flex-shrink: 0;
  }
</style>
