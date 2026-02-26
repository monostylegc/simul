<script lang="ts">
  /**
   * Menubar - 상단 탭 바 + Undo/Redo 버튼.
   */

  import { uiState, type TabId } from '$lib/stores/ui.svelte';
  import { historyState } from '$lib/stores/history.svelte';

  const tabs: { id: TabId; label: string }[] = [
    { id: 'file', label: 'File' },
    { id: 'modeling', label: 'Modeling' },
    { id: 'material', label: 'Material' },
    { id: 'preprocess', label: 'Pre-process' },
    { id: 'solve', label: 'Solve' },
    { id: 'postprocess', label: 'Post-process' },
  ];

  function setTab(id: TabId) {
    uiState.activeTab = id;
  }
</script>

<div class="menubar">
  <span class="logo">Spine Simulator</span>

  <div class="tab-group">
    {#each tabs as tab}
      <button
        class="tab-btn"
        class:active={uiState.activeTab === tab.id}
        onclick={() => setTab(tab.id)}
      >
        {tab.label}
      </button>
    {/each}
  </div>

  <div class="right">
    <button class="icon-btn" title="Undo (Ctrl+Z)" aria-label="Undo"
      disabled={!historyState.canUndo}
      onclick={() => historyState.undo()}>&#8617;</button>
    <button class="icon-btn" title="Redo (Ctrl+Y)" aria-label="Redo"
      disabled={!historyState.canRedo}
      onclick={() => historyState.redo()}>&#8618;</button>
  </div>
</div>

<style>
  .menubar {
    height: var(--menubar-height);
    background: var(--color-card);
    display: flex;
    align-items: center;
    padding: 0 12px;
    border-bottom: 1px solid var(--color-border);
    flex-shrink: 0;
    z-index: 100;
  }

  .logo {
    color: var(--color-primary);
    font-weight: bold;
    font-size: 14px;
    margin-right: 16px;
    letter-spacing: 1px;
  }

  .tab-group {
    display: flex;
    gap: 0;
    height: 100%;
  }

  .tab-btn {
    background: transparent;
    color: var(--color-text-secondary);
    border: none;
    border-bottom: 2px solid transparent;
    padding: 0 14px;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s;
    height: 100%;
    display: flex;
    align-items: center;
  }
  .tab-btn:hover {
    color: var(--color-text);
    background: #f4f4f4;
  }
  .tab-btn.active {
    color: var(--color-primary);
    border-bottom-color: var(--color-primary);
    font-weight: 600;
  }

  .right {
    margin-left: auto;
    display: flex;
    gap: 4px;
    align-items: center;
  }

  .icon-btn {
    background: transparent;
    border: 1px solid var(--color-border);
    border-radius: 4px;
    width: 28px;
    height: 28px;
    font-size: 14px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #555;
  }
  .icon-btn:hover {
    background: #e8e8e8;
    color: var(--color-text);
  }
  .icon-btn:disabled {
    opacity: 0.35;
    cursor: default;
  }
  .icon-btn:disabled:hover {
    background: transparent;
    color: #555;
  }
</style>
