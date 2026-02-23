<script lang="ts">
  /**
   * Statusbar - 하단 상태바.
   *
   * FPS, 상태 메시지, 모델 정보를 표시한다.
   */

  import { sceneState } from '$lib/stores/scene.svelte';
  import { uiState } from '$lib/stores/ui.svelte';

  let totalVertices = $derived(
    sceneState.models.reduce((sum, m) => sum + m.vertexCount, 0)
  );
  let totalFaces = $derived(
    sceneState.models.reduce((sum, m) => sum + m.faceCount, 0)
  );
</script>

<div class="statusbar">
  <span class="status-col" title={uiState.statusMessage}>
    <span class="label">Status:</span>
    <span class="value status-msg">{uiState.statusMessage}</span>
  </span>
  <span class="sep"></span>
  <span>
    <span class="label">Models:</span>
    <span class="value">{sceneState.models.length}</span>
  </span>
  <span class="sep"></span>
  <span>
    <span class="label">Vertices:</span>
    <span class="value">{totalVertices.toLocaleString()}</span>
  </span>
  <span class="sep"></span>
  <span>
    <span class="label">Faces:</span>
    <span class="value">{totalFaces.toLocaleString()}</span>
  </span>
  <span class="sep"></span>
  <span>
    <span class="label">FPS:</span>
    <span class="value">{sceneState.fps}</span>
  </span>
</div>

<style>
  .statusbar {
    height: var(--statusbar-height);
    background: var(--color-card);
    color: var(--color-text-secondary);
    display: flex;
    align-items: center;
    padding: 0 16px;
    font-size: 11px;
    gap: 16px;
    border-top: 1px solid var(--color-border);
    flex-shrink: 0;
  }
  .label {
    color: var(--color-text-muted);
  }
  .value {
    color: var(--color-primary);
  }
  .status-col {
    flex: 1;
    min-width: 0;
    display: flex;
    gap: 4px;
    align-items: center;
  }
  .status-msg {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sep {
    width: 1px;
    height: 14px;
    background: var(--color-border);
    flex-shrink: 0;
  }
</style>
