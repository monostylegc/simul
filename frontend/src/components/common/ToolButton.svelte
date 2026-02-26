<script lang="ts">
  /**
   * 도구 버튼
   */
  interface Props {
    label: string;
    color?: string;
    disabled?: boolean;
    onclick?: () => void;
  }
  let { label, color = '#1976d2', disabled = false, onclick }: Props = $props();
</script>

<button
  class="tool-btn"
  style:background={disabled ? '#999' : color}
  {disabled}
  {onclick}
>
  {label}
</button>

<style>
  .tool-btn {
    width: 100%;
    padding: 7px 10px;
    border: none;
    border-radius: 4px;
    color: white;
    font-size: 11px;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .tool-btn:hover:not(:disabled) {
    opacity: 0.85;
  }
  .tool-btn:disabled {
    cursor: default;
    opacity: 0.5;
  }
</style>
