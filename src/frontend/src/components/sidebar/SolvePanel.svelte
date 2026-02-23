<script lang="ts">
  /**
   * SolvePanel — 모델별 솔버/재료 관리 + 해석 실행
   *
   * 기능:
   *  - 모델별 솔버 지정 (FEM / PD / SPG)
   *  - 모델별 재료 지정
   *  - 유효성 체크리스트
   *  - 해석 실행 + 진행률
   */
  import { sceneState } from '$lib/stores/scene.svelte';
  import { analysisState } from '$lib/stores/analysis.svelte';
  import { wsState } from '$lib/stores/websocket.svelte';
  import { uiState } from '$lib/stores/ui.svelte';
  import { initAnalysis, runAnalysis, assignSolver, assignMaterial, setDefaultMethod } from '$lib/actions/analysis';
  import { MATERIAL_PRESETS } from '$lib/analysis/PreProcessor';

  type SolverType = 'fem' | 'pd' | 'spg';

  /** 해석 가능 여부 */
  let canRun = $derived(
    sceneState.models.length > 0 && !analysisState.isRunning
  );

  /** 모델별 솔버 가져오기 */
  function getModelSolver(name: string): SolverType {
    return analysisState.solverAssignments[name] || analysisState.method;
  }

  /** 모델별 재료 가져오기 */
  function getModelMaterial(name: string): string {
    return analysisState.preProcessor?.materialAssignments[name] || 'bone';
  }

  /** 모델별 솔버 변경 */
  function handleSolverChange(name: string, e: Event) {
    const method = (e.target as HTMLSelectElement).value as SolverType;
    assignSolver(name, method);
  }

  /** 모델별 재료 변경 */
  function handleMaterialChange(name: string, e: Event) {
    const preset = (e.target as HTMLSelectElement).value;
    assignMaterial(name, preset);
  }

  /** 전체 솔버 일괄 적용 */
  function applyAllSolver(method: SolverType) {
    setDefaultMethod(method);
    sceneState.models.forEach(m => assignSolver(m.name, method));
    uiState.toast(`전체 모델 → ${solverLabels[method]}`, 'info');
  }

  /** 해석 시작 */
  async function handleRun() {
    if (sceneState.models.length === 0) {
      uiState.toast('모델을 먼저 로드하세요 (File 탭)', 'warn');
      return;
    }

    await initAnalysis();

    // 솔버 할당 동기화 (initAnalysis 이후 PreProcessor 준비됨)
    if (analysisState.preProcessor) {
      analysisState.preProcessor.solverAssignments = { ...analysisState.solverAssignments };
    }

    if (!wsState.connected) {
      uiState.toast('서버에 연결되지 않았습니다', 'error');
      return;
    }

    if (analysisState.bcCount === 0) {
      uiState.toast('경계조건(BC)이 설정되지 않았습니다', 'warn');
    }

    await runAnalysis();
  }

  /** 솔버 라벨 */
  const solverLabels: Record<SolverType, string> = {
    fem: 'FEM',
    pd:  'PD',
    spg: 'SPG',
  };

  /** 솔버 설명 */
  const solverDesc: Record<SolverType, string> = {
    fem: '선형 탄성 — 빠르고 정확, 파괴 불가',
    pd:  'Peridynamics — 파괴/균열 전파',
    spg: 'Meshfree — 대변형, 메쉬 불요',
  };

  /** 솔버별 색상 */
  const solverColors: Record<SolverType, string> = {
    fem: '#1976d2',
    pd:  '#e53935',
    spg: '#ff8f00',
  };

  /** 재료 프리셋 옵션 */
  const materialOptions = Object.entries(MATERIAL_PRESETS).map(([key, _p]) => ({
    value: key, label: key,
  }));

  /** 사용된 솔버 종류 요약 (solverAssignments 직접 참조로 반응성 보장) */
  let solverSummary = $derived(() => {
    const assignments = analysisState.solverAssignments;
    const defaultMethod = analysisState.method;
    const counts: Record<string, number> = {};
    sceneState.models.forEach(m => {
      const solver = assignments[m.name] || defaultMethod;
      counts[solver] = (counts[solver] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([s, n]) => `${solverLabels[s as SolverType]}×${n}`)
      .join(', ');
  });
</script>

<div class="panel">
  <h3>SOLVE</h3>

  <!-- 서버 상태 -->
  <div class="section">
    <div class="status-row">
      <span class="dot" class:connected={wsState.connected}></span>
      <span class="label">Server</span>
      <span class="status-text" class:connected={wsState.connected}>
        {wsState.connected ? 'Connected' : 'Disconnected'}
      </span>
    </div>
  </div>

  <!-- 체크리스트 -->
  <div class="section">
    <div class="section-title">Checklist</div>
    <div class="check-item" class:ok={sceneState.models.length > 0}>
      {sceneState.models.length > 0 ? '✓' : '✗'} Models: {sceneState.models.length}
    </div>
    <div class="check-item" class:ok={analysisState.bcCount > 0}>
      {analysisState.bcCount > 0 ? '✓' : '✗'} Boundary Conditions: {analysisState.bcCount}
    </div>
    <div class="check-item" class:ok={analysisState.materialCount > 0}>
      {analysisState.materialCount > 0 ? '✓' : '—'} Materials: {analysisState.materialCount}
    </div>
  </div>

  <!-- 모델별 솔버/재료 지정 테이블 -->
  {#if sceneState.models.length > 0}
    <div class="section solver-table-section">
      <div class="section-title">모델별 솔버 / 재료</div>

      <!-- 헤더 -->
      <div class="solver-row header-row">
        <span>모델</span>
        <span>솔버</span>
        <span>재료</span>
      </div>

      <div class="solver-table">
        {#each sceneState.models as model}
          {@const solver = (analysisState.solverAssignments[model.name] || analysisState.method) as SolverType}
          <div class="solver-row">
            <!-- 모델명 + 솔버 색상 표시 -->
            <div class="model-name">
              <span class="solver-dot" style="background: {solverColors[solver]}"></span>
              <span class="name-text" title={model.name}>
                {model.name.length > 10 ? model.name.slice(0, 10) + '…' : model.name}
              </span>
            </div>

            <!-- 솔버 선택 -->
            <select class="cell-select solver-sel"
              style="border-color: {solverColors[solver]}"
              value={solver}
              onchange={(e) => handleSolverChange(model.name, e)}>
              <option value="fem">FEM</option>
              <option value="pd">PD</option>
              <option value="spg">SPG</option>
            </select>

            <!-- 재료 선택 -->
            <select class="cell-select mat-sel"
              value={getModelMaterial(model.name)}
              onchange={(e) => handleMaterialChange(model.name, e)}>
              {#each materialOptions as opt}
                <option value={opt.value}>{opt.value}</option>
              {/each}
            </select>
          </div>
        {/each}
      </div>

      <!-- 일괄 적용 버튼 -->
      <div class="bulk-row">
        <span class="bulk-label">일괄:</span>
        <button class="bulk-btn" style="background: {solverColors.fem}" onclick={() => applyAllSolver('fem')}>All FEM</button>
        <button class="bulk-btn" style="background: {solverColors.pd}" onclick={() => applyAllSolver('pd')}>All PD</button>
        <button class="bulk-btn" style="background: {solverColors.spg}" onclick={() => applyAllSolver('spg')}>All SPG</button>
      </div>
    </div>
  {/if}

  <!-- 솔버 설명 -->
  <div class="section">
    <div class="section-title">솔버 설명</div>
    <div class="solver-descs">
      {#each (['fem', 'pd', 'spg'] as const) as s}
        <div class="desc-item">
          <span class="desc-badge" style="background: {solverColors[s]}">{solverLabels[s]}</span>
          <span class="desc-text">{solverDesc[s]}</span>
        </div>
      {/each}
    </div>
  </div>

  <!-- 해석 실행 -->
  <button
    class="run-btn"
    onclick={handleRun}
    disabled={!canRun}
  >
    {#if analysisState.isRunning}
      Running...
    {:else}
      🚀 Run Analysis
      {#if sceneState.models.length > 0}
        <span class="run-summary">({solverSummary()})</span>
      {/if}
    {/if}
  </button>

  <!-- 진행률 -->
  {#if analysisState.isRunning}
    <div class="progress-section">
      <div class="progress-text">{analysisState.progressMessage}</div>
      <div class="progress-bar-bg">
        <div class="progress-bar" style:width="{analysisState.progress * 100}%"></div>
      </div>
      <div class="progress-pct">{(analysisState.progress * 100).toFixed(0)}%</div>
    </div>
  {/if}

  {#if wsState.lastError}
    <div class="error-msg">{wsState.lastError}</div>
  {/if}
</div>

<style>
  .panel h3 {
    color: var(--color-primary); margin-bottom: 10px; font-size: 13px;
    text-transform: uppercase; letter-spacing: 1px; padding-bottom: 6px;
    border-bottom: 1px solid rgba(25, 118, 210, 0.2);
  }
  .section {
    margin-bottom: 10px; padding: 10px;
    background: var(--color-card); border: 1px solid #e8e8e8; border-radius: 6px;
  }
  .section-title {
    font-size: 11px; color: var(--color-primary); margin-bottom: 8px; font-weight: bold;
  }

  /* 서버 상태 */
  .status-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
  .dot {
    width: 8px; height: 8px; border-radius: 50%; background: #ff4444; flex-shrink: 0;
  }
  .dot.connected { background: #4caf50; }
  .label { color: #888; }
  .status-text { color: #ff4444; font-weight: 600; margin-left: auto; }
  .status-text.connected { color: #4caf50; }

  /* 체크리스트 */
  .check-item {
    font-size: 11px; color: #999; padding: 2px 0;
  }
  .check-item.ok { color: #2e7d32; }

  /* ── 솔버 테이블 ── */
  .solver-table-section {
    border-left: 3px solid var(--color-primary);
  }
  .solver-table {
    display: flex; flex-direction: column; gap: 4px;
  }
  .solver-row {
    display: grid;
    grid-template-columns: 1fr 58px 68px;
    gap: 4px;
    align-items: center;
  }
  .header-row {
    font-size: 9px; color: #aaa; text-transform: uppercase;
    padding-bottom: 2px; border-bottom: 1px solid #eee; margin-bottom: 2px;
  }
  .model-name {
    display: flex; align-items: center; gap: 4px;
    overflow: hidden;
  }
  .solver-dot {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  }
  .name-text {
    font-size: 11px; color: #444; font-weight: 600;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .cell-select {
    padding: 3px 2px; font-size: 10px;
    border: 1px solid #ccc; border-radius: 3px;
    background: #fff; text-align: center;
  }
  .solver-sel {
    font-weight: 700;
    border-width: 2px;
  }

  /* 일괄 적용 */
  .bulk-row {
    display: flex; align-items: center; gap: 3px; margin-top: 8px;
  }
  .bulk-label {
    font-size: 10px; color: #888; margin-right: 2px;
  }
  .bulk-btn {
    flex: 1; padding: 4px 2px; font-size: 9px; font-weight: 700;
    border: none; border-radius: 3px; color: #fff; cursor: pointer;
    transition: opacity 0.15s;
  }
  .bulk-btn:hover { opacity: 0.8; }

  /* 솔버 설명 */
  .solver-descs {
    display: flex; flex-direction: column; gap: 4px;
  }
  .desc-item {
    display: flex; align-items: center; gap: 6px;
  }
  .desc-badge {
    font-size: 9px; font-weight: 700; color: #fff;
    padding: 1px 6px; border-radius: 3px; min-width: 32px; text-align: center;
  }
  .desc-text {
    font-size: 10px; color: #777;
  }

  /* 실행 버튼 */
  .run-btn {
    width: 100%; padding: 12px; border: none; border-radius: 6px;
    background: #27ae60; color: #fff; cursor: pointer;
    font-size: 13px; font-weight: bold; transition: opacity 0.15s;
    display: flex; align-items: center; justify-content: center; gap: 6px;
  }
  .run-btn:hover:not(:disabled) { opacity: 0.85; }
  .run-btn:disabled { opacity: 0.4; cursor: default; }
  .run-summary {
    font-size: 10px; font-weight: normal; opacity: 0.8;
  }

  /* 진행률 */
  .progress-section {
    margin-top: 8px; padding: 8px; background: #e3f2fd; border-radius: 4px;
  }
  .progress-text { font-size: 11px; color: #1565c0; margin-bottom: 4px; }
  .progress-bar-bg {
    height: 4px; background: #bbdefb; border-radius: 2px; overflow: hidden;
  }
  .progress-bar {
    height: 100%; background: #1976d2; transition: width 0.3s;
  }
  .progress-pct {
    font-size: 10px; color: #1565c0; text-align: right; margin-top: 2px;
  }
  .error-msg {
    margin-top: 8px; padding: 6px; background: #ffebee; color: #c62828;
    border-radius: 4px; font-size: 11px;
  }
</style>
