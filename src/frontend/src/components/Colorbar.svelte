<script lang="ts">
  /**
   * 컬러바 컴포넌트 — Jet 컬러맵 시각화
   */
  interface Props {
    minVal?: number;
    maxVal?: number;
    label?: string;
    visible?: boolean;
  }
  let { minVal = 0, maxVal = 1, label = '', visible = false }: Props = $props();
</script>

{#if visible}
  <div class="colorbar">
    <div class="gradient-bar"></div>
    <div class="range-labels">
      <span>{minVal.toExponential(2)}</span>
      <span>{maxVal.toExponential(2)}</span>
    </div>
    {#if label}
      <div class="unit-label">{label}</div>
    {/if}
  </div>
{/if}

<style>
  .colorbar {
    padding: 4px 8px;
  }
  .gradient-bar {
    width: 100%;
    height: 16px;
    border-radius: 3px;
    background: linear-gradient(to right,
      rgb(0,0,255), rgb(0,255,255), rgb(0,255,0),
      rgb(255,255,0), rgb(255,0,0));
  }
  .range-labels {
    display: flex;
    justify-content: space-between;
    font-size: 10px;
    color: #aaa;
    margin-top: 2px;
  }
  .unit-label {
    font-size: 10px;
    color: #888;
    text-align: center;
    margin-top: 2px;
  }
</style>
