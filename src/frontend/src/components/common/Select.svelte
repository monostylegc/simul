<script lang="ts">
  /**
   * 셀렉트 드롭다운
   */
  interface SelectOption {
    value: string;
    label: string;
  }
  interface Props {
    label?: string;
    options: SelectOption[];
    value: string;
    onchange?: (value: string) => void;
  }
  let { label, options, value = $bindable(), onchange }: Props = $props();

  function handleChange(e: Event) {
    value = (e.target as HTMLSelectElement).value;
    onchange?.(value);
  }
</script>

<div class="select-container">
  {#if label}
    <label>{label}</label>
  {/if}
  <select {value} onchange={handleChange}>
    {#each options as opt}
      <option value={opt.value}>{opt.label}</option>
    {/each}
  </select>
</div>

<style>
  .select-container {
    margin-bottom: 4px;
  }
  label {
    display: block;
    font-size: 11px;
    color: #666;
    margin-bottom: 2px;
  }
  select {
    width: 100%;
    padding: 5px 6px;
    font-size: 11px;
    border: 1px solid #ccc;
    border-radius: 3px;
    background: white;
    cursor: pointer;
  }
</style>
