<script lang="ts">
  /**
   * 파일 업로드 버튼 (숨겨진 input + 커스텀 버튼)
   */
  interface Props {
    label: string;
    accept?: string;
    multiple?: boolean;
    color?: string;
    onfiles?: (files: FileList) => void;
  }
  let { label, accept = '.stl', multiple = false, color = '#555', onfiles }: Props = $props();

  let inputEl: HTMLInputElement;

  function handleClick() {
    inputEl.click();
  }

  function handleChange(e: Event) {
    const target = e.target as HTMLInputElement;
    if (target.files && target.files.length > 0) {
      onfiles?.(target.files);
      target.value = ''; // 동일 파일 재선택 허용
    }
  }
</script>

<button class="file-btn" style:background={color} onclick={handleClick}>
  {label}
</button>
<input
  bind:this={inputEl}
  type="file"
  {accept}
  {multiple}
  onchange={handleChange}
  style="display: none;"
>

<style>
  .file-btn {
    width: 100%;
    padding: 7px 10px;
    border: none;
    border-radius: 4px;
    color: white;
    font-size: 11px;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .file-btn:hover {
    opacity: 0.85;
  }
</style>
