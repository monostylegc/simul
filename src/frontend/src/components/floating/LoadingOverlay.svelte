<script lang="ts">
  /**
   * LoadingOverlay — 파이프라인 / 해석 실행 중 3D 뷰포트 위 로딩 오버레이.
   *
   * 표시 항목:
   *  - 단계별 진행 스텝 인디케이터 (완료 ✓ / 진행 중 ● / 대기 ○)
   *  - 현재 상태 메시지
   *  - 경과 시간 카운터
   *  - 전체 진행 바
   */
  import { pipelineState, PIPELINE_STEP_INFO } from '$lib/stores/pipeline.svelte';
  import { analysisState } from '$lib/stores/analysis.svelte';

  /** 파이프라인 표시할 단계 목록 (idle/complete/error 제외) */
  const PIPELINE_STEPS = ['uploading', 'segmentation', 'mesh_extraction', 'material_assignment'] as const;

  /** 현재 단계 순서 번호 */
  const currentOrder = $derived(PIPELINE_STEP_INFO[pipelineState.step]?.order ?? 0);

  /** 경과 시간 포맷 (mm:ss) */
  const elapsedFormatted = $derived(() => {
    const sec = pipelineState.elapsedSec;
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  });

  /** 전체 진행률 (4단계 기준, 0~1) */
  const overallProgress = $derived(() => {
    if (pipelineState.step === 'complete') return 1;
    if (pipelineState.step === 'error') return 0;
    const order = currentOrder;
    if (order <= 0) return 0;
    // 각 단계 내 진행률 반영
    return ((order - 1) + pipelineState.progress) / 4;
  });

  /** 해석 진행 중 여부 */
  const isAnalysisRunning = $derived(analysisState.isRunning);

  /** 오버레이 표시 여부 */
  const showOverlay = $derived(pipelineState.isActive || isAnalysisRunning);
</script>

{#if showOverlay}
  <div class="overlay">
    <div class="overlay-card">
      {#if pipelineState.isActive}
        <!-- 파이프라인 로딩 -->
        <div class="title">CT/MRI 파이프라인 실행 중</div>

        <!-- GPU 정보 배지 -->
        {#if pipelineState.gpuInfo}
          <div class="device-badge" class:gpu={pipelineState.gpuInfo.available}>
            {#if pipelineState.gpuInfo.available}
              🖥️ GPU: {pipelineState.gpuInfo.name}
              ({pipelineState.gpuInfo.memory_mb.toLocaleString()}MB)
            {:else}
              💻 CPU 모드 (GPU 미감지)
            {/if}
          </div>
        {/if}

        <!-- 단계 인디케이터 -->
        <div class="steps">
          {#each PIPELINE_STEPS as stepKey}
            {@const info = PIPELINE_STEP_INFO[stepKey]}
            {@const stepOrder = info.order}
            {@const isDone = currentOrder > stepOrder}
            {@const isCurrent = pipelineState.step === stepKey}
            <div class="step" class:done={isDone} class:current={isCurrent}>
              <span class="step-icon">
                {#if isDone}✓{:else if isCurrent}●{:else}○{/if}
              </span>
              <span class="step-label">{info.icon} {info.label}</span>
            </div>
          {/each}
        </div>

        <!-- 현재 메시지 -->
        <div class="message">{pipelineState.message}</div>

        <!-- 전체 진행 바 -->
        <div class="progress-bar-bg">
          <div class="progress-bar" style="width:{overallProgress() * 100}%"></div>
        </div>

        <!-- 경과 시간 -->
        <div class="elapsed">
          경과 시간: <strong>{elapsedFormatted()}</strong>
        </div>

      {:else if isAnalysisRunning}
        <!-- 해석 로딩 -->
        <div class="title">구조 해석 실행 중</div>

        <div class="analysis-icon">⚙️</div>

        <div class="message">{analysisState.progressMessage || '해석 진행 중...'}</div>

        <!-- 해석 진행 바 -->
        <div class="progress-bar-bg">
          <div class="progress-bar analysis-bar" style="width:{analysisState.progress * 100}%"></div>
        </div>

        <div class="elapsed">
          진행률: <strong>{(analysisState.progress * 100).toFixed(0)}%</strong>
        </div>
      {/if}

      <!-- 스피너 -->
      <div class="spinner"></div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: absolute;
    inset: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.45);
    backdrop-filter: blur(2px);
    pointer-events: auto;
  }

  .overlay-card {
    background: #fff;
    border-radius: 12px;
    padding: 28px 36px;
    min-width: 360px;
    max-width: 480px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
    text-align: center;
  }

  .title {
    font-size: 16px;
    font-weight: 700;
    color: #333;
    margin-bottom: 20px;
  }

  /* GPU 정보 배지 */
  .device-badge {
    display: inline-block;
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 12px;
    margin-bottom: 16px;
    background: #f5f5f5;
    color: #888;
  }
  .device-badge.gpu {
    background: #e8f5e9;
    color: #2e7d32;
    font-weight: 600;
  }

  /* 단계 인디케이터 */
  .steps {
    display: flex;
    justify-content: space-between;
    margin-bottom: 18px;
    gap: 4px;
  }
  .step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    flex: 1;
    opacity: 0.4;
    transition: opacity 0.3s;
  }
  .step.done { opacity: 1; }
  .step.current { opacity: 1; }
  .step-icon {
    font-size: 18px;
    width: 28px; height: 28px;
    line-height: 28px;
    border-radius: 50%;
    display: block;
  }
  .step.done .step-icon { color: #2e7d32; background: #e8f5e9; }
  .step.current .step-icon { color: #1565c0; background: #e3f2fd; animation: pulse 1.5s infinite; }
  .step-label { font-size: 10px; color: #666; white-space: nowrap; }
  .step.current .step-label { color: #1565c0; font-weight: 600; }
  .step.done .step-label { color: #2e7d32; }

  /* 현재 메시지 */
  .message {
    font-size: 12px;
    color: #555;
    margin-bottom: 14px;
    min-height: 18px;
  }

  /* 진행 바 */
  .progress-bar-bg {
    height: 6px;
    background: #e0e0e0;
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 12px;
  }
  .progress-bar {
    height: 100%;
    background: linear-gradient(90deg, #1976d2, #42a5f5);
    border-radius: 3px;
    transition: width 0.5s ease;
  }
  .progress-bar.analysis-bar {
    background: linear-gradient(90deg, #ff6f00, #ffa726);
  }

  /* 경과 시간 */
  .elapsed {
    font-size: 12px;
    color: #888;
    margin-bottom: 8px;
  }

  /* 해석 아이콘 */
  .analysis-icon {
    font-size: 36px;
    margin-bottom: 12px;
    animation: spin 2s linear infinite;
  }

  /* 스피너 */
  .spinner {
    width: 24px; height: 24px;
    border: 3px solid #e0e0e0;
    border-top: 3px solid #1976d2;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin: 0 auto;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  @keyframes pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.15); }
  }
</style>
