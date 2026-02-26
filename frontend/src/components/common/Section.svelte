<script lang="ts">
  /**
   * 사이드바 섹션 래퍼 — prop-section 스타일
   */
  interface Props {
    title?: string;
    borderColor?: string;
    titleColor?: string;
  }
  let { title, borderColor, titleColor }: Props = $props();
</script>

<div class="section" style:border-left-color={borderColor}>
  {#if title}
    <div class="section-title" style:color={titleColor}>{title}</div>
  {/if}
  {@render children()}
</div>

{#snippet children()}{/snippet}

<style>
  .section {
    padding: 8px;
    border-bottom: 1px solid #e0e0e0;
    border-left: 3px solid transparent;
  }
  .section-title {
    font-size: 11px;
    font-weight: 600;
    color: #555;
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
</style>
