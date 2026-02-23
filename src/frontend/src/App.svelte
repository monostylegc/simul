<script lang="ts">
  /**
   * App - 루트 컴포넌트.
   *
   * Menubar + Canvas3D + Sidebar + Statusbar 레이아웃.
   * 토스트 알림 + 확인 다이얼로그 전역 관리.
   */

  import Menubar from './components/Menubar.svelte';
  import Canvas3D from './components/Canvas3D.svelte';
  import Sidebar from './components/sidebar/Sidebar.svelte';
  import Statusbar from './components/Statusbar.svelte';
  import { uiState } from '$lib/stores/ui.svelte';
</script>

<Menubar />

<div class="main-container">
  <Canvas3D />
  <Sidebar />
</div>

<Statusbar />

<!-- 토스트 알림 -->
{#if uiState.toasts.length > 0}
  <div class="toast-container">
    {#each uiState.toasts as toast (toast.id)}
      <div class="toast {toast.level}">{toast.message}</div>
    {/each}
  </div>
{/if}

<!-- 확인 다이얼로그 -->
{#if uiState.confirmDialog}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="confirm-overlay" onclick={() => uiState.closeConfirm(false)}>
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
    <div class="confirm-dialog" onclick={(e) => e.stopPropagation()}>
      <h4>{uiState.confirmDialog.title}</h4>
      <p>{uiState.confirmDialog.message}</p>
      <div class="btn-row">
        <button class="btn-cancel" onclick={() => uiState.closeConfirm(false)}>취소</button>
        <button class="btn-confirm" onclick={() => uiState.closeConfirm(true)}>확인</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .main-container {
    flex: 1;
    display: flex;
    overflow: hidden;
  }
</style>
