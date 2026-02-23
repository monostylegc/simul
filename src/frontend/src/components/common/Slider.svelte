<script lang="ts">
  /**
   * 범위 슬라이더 + 라벨 + 값 표시
   */
  interface Props {
    label: string;
    value: number;
    min?: number;
    max?: number;
    step?: number;
    unit?: string;
    onchange?: (value: number) => void;
  }
  let { label, value = $bindable(), min = 0, max = 100, step = 1, unit = '', onchange }: Props = $props();

  function handleInput(e: Event) {
    const target = e.target as HTMLInputElement;
    value = parseFloat(target.value);
    onchange?.(value);
  }
</script>

<div class="slider-container">
  <label>{label}</label>
  <input type="range" {min} {max} {step} {value} oninput={handleInput}>
  <div class="slider-value">{value}{unit}</div>
</div>

<style>
  .slider-container {
    margin-bottom: 4px;
  }
  label {
    display: block;
    font-size: 11px;
    color: #666;
    margin-bottom: 2px;
  }
  input[type="range"] {
    width: 100%;
    height: 4px;
    appearance: none;
    background: #ddd;
    border-radius: 2px;
    outline: none;
  }
  input[type="range"]::-webkit-slider-thumb {
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #1976d2;
    cursor: pointer;
  }
  .slider-value {
    font-size: 10px;
    color: #888;
    text-align: right;
    margin-top: 1px;
  }
</style>
