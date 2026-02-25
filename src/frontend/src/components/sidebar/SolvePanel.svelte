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
  import { initAnalysis, runAnalysis, cancelAnalysis, assignSolver, setDefaultMethod } from '$lib/actions/analysis';
  import { formatE, constitutiveModelShort } from '$lib/stores/materials.svelte';

  type SolverType = 'fem' | 'pd' | 'spg';

  /** 해석 가능 여부 (모델 + BC + 미실행 + 서버 연결) */
  let canRun = $derived(
    sceneState.models.length > 0
    && analysisState.bcCount > 0
    && !analysisState.isRunning
    && wsState.connected
  );

  /** 검증 에러 목록 (Run 버튼 비활성화 사유 표시용) */
  let validationErrors = $derived.by(() => {
    const errs: string[] = [];
    if (sceneState.models.length === 0) errs.push('모델 미로드');
    if (analysisState.bcCount === 0) errs.push('경계조건(BC) 미설정');
    if (!wsState.connected) errs.push('서버 미연결');
    return errs;
  });

  /** 모델별 솔버 가져오기 */
  function getModelSolver(name: string): SolverType {
    return analysisState.solverAssignments[name] || analysisState.method;
  }

  /** 모델별 재료 라벨 (읽기 전용 — Material 탭에서 설정) */
  function getModelMaterialLabel(name: string): string {
    const mat = analysisState.preProcessor?.materialAssignments[name];
    if (!mat) return '미할당';
    return mat.label;
  }

  /** 모델별 재료 상세 (툴팁용) */
  function getModelMaterialSummary(name: string): string {
    const mat = analysisState.preProcessor?.materialAssignments[name];
    if (!mat) return '재료 미할당 — Material 탭에서 설정';
    const model = constitutiveModelShort(mat.constitutiveModel ?? 'linear_elastic');
    return `${mat.label} [${model}] E=${formatE(mat.E)}, ν=${mat.nu}`;
  }

  /** 모델별 솔버 변경 */
  function handleSolverChange(name: string, e: Event) {
    const method = (e.target as HTMLSelectElement).value as SolverType;
    assignSolver(name, method);
  }

  /** 전체 솔버 일괄 적용 */
  function applyAllSolver(method: SolverType) {
    setDefaultMethod(method);
    sceneState.models.forEach(m => assignSolver(m.name, method));
    uiState.toast(`전체 모델 → ${solverLabels[method]}`, 'info');
  }

  /** 해석 시작 */
  async function handleRun() {
    // 검증 — canRun이 false이면 사유를 표시
    if (!canRun) {
      if (validationErrors.length > 0) {
        uiState.toast(`해석 불가: ${validationErrors.join(', ')}`, 'error');
      }
      return;
    }

    await initAnalysis();

    // 솔버 할당 동기화 (initAnalysis 이후 PreProcessor 준비됨)
    if (analysisState.preProcessor) {
      analysisState.preProcessor.solverAssignments = { ...analysisState.solverAssignments };
    }

    // 재료 미할당 경고 (기본값 bone으로 진행)
    if (analysisState.materialCount === 0) {
      uiState.toast('재료 미할당 — 기본 bone 재료 적용', 'warn');
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
    <div class="check-item" class:ok={wsState.connected}>
      {wsState.connected ? '✓' : '✗'} Server Connected
    </div>
    <div class="check-item" class:ok={sceneState.models.length > 0}>
      {sceneState.models.length > 0 ? '✓' : '✗'} Models: {sceneState.models.length}
    </div>
    <div class="check-item" class:ok={analysisState.bcCount > 0}>
      {analysisState.bcCount > 0 ? '✓' : '✗'} Boundary Conditions: {analysisState.bcCount}
    </div>
    <div class="check-item" class:ok={analysisState.materialCount > 0}>
      {analysisState.materialCount > 0 ? '✓' : '—'} Materials: {analysisState.materialCount}
      {#if analysisState.materialCount === 0}
        <span class="hint">(기본: bone)</span>
      {/if}
    </div>
  </div>

  <!-- 검증 에러 메시지 -->
  {#if validationErrors.length > 0 && !analysisState.isRunning}
    <div class="validation-errors">
      {#each validationErrors as err}
        <div class="validation-item">⚠ {err}</div>
      {/each}
    </div>
  {/if}

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

            <!-- 재료 표시 (읽기 전용 — Material 탭에서 설정) -->
            <span class="mat-summary" title={getModelMaterialSummary(model.name)}>
              {getModelMaterialLabel(model.name)}
            </span>
          </div>
        {/each}
      </div>

      <!-- 재료 안내 -->
      <div class="mat-hint">※ 재료 변경은 Material 탭에서</div>

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

  <!-- 진행률 + 취소 버튼 -->
  {#if analysisState.isRunning}
    <div class="progress-section">
      <div class="progress-header">
        <span class="progress-text">{analysisState.progressMessage}</span>
        <button class="cancel-btn" onclick={cancelAnalysis}>✕ Cancel</button>
      </div>
      <div class="progress-bar-bg">
        <div class="progress-bar" style:width="{analysisState.progress * 100}%"></div>
      </div>
      <div class="progress-footer">
        <span class="progress-pct">{(analysisState.progress * 100).toFixed(0)}%</span>
        <span class="elapsed">{(analysisState.elapsedMs / 1000).toFixed(1)}s</span>
      </div>
    </div>
  {/if}

  <!-- 해석 완료 후 소요 시간 -->
  {#if !analysisState.isRunning && analysisState.hasResult && analysisState.elapsedMs > 0}
    <div class="result-info">
      ✅ 해석 완료 — {(analysisState.elapsedMs / 1000).toFixed(1)}초
    </div>
  {/if}

  <!-- 에러 메시지 -->
  {#if analysisState.lastError}
    <div class="error-msg">❌ {analysisState.lastError}</div>
  {:else if wsState.lastError}
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

  /* 재료 요약 (읽기 전용) */
  .mat-summary {
    font-size: 9px; color: #555; font-weight: 500;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    cursor: help; padding: 2px 4px; background: #f5f5f5;
    border-radius: 2px; border: 1px solid #e0e0e0;
  }
  .mat-hint {
    font-size: 9px; color: #999; text-align: center;
    margin-top: 6px; padding: 2px 0;
  }

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

  /* 체크리스트 보조 텍스트 */
  .hint { font-size: 9px; color: #aaa; margin-left: 2px; }

  /* 검증 에러 */
  .validation-errors {
    margin-bottom: 8px; padding: 6px 8px;
    background: #fff3e0; border: 1px solid #ffcc80; border-radius: 4px;
  }
  .validation-item {
    font-size: 10px; color: #e65100; padding: 1px 0;
  }

  /* 진행률 */
  .progress-section {
    margin-top: 8px; padding: 8px; background: #e3f2fd; border-radius: 4px;
  }
  .progress-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 4px;
  }
  .progress-text { font-size: 11px; color: #1565c0; }
  .cancel-btn {
    padding: 2px 8px; font-size: 10px; font-weight: 600;
    border: 1px solid #e53935; border-radius: 3px;
    background: #fff; color: #e53935; cursor: pointer;
    transition: all 0.15s;
  }
  .cancel-btn:hover {
    background: #e53935; color: #fff;
  }
  .progress-bar-bg {
    height: 4px; background: #bbdefb; border-radius: 2px; overflow: hidden;
  }
  .progress-bar {
    height: 100%; background: #1976d2; transition: width 0.3s;
  }
  .progress-footer {
    display: flex; justify-content: space-between; margin-top: 2px;
  }
  .progress-pct {
    font-size: 10px; color: #1565c0;
  }
  .elapsed {
    font-size: 10px; color: #888;
  }

  /* 결과 정보 */
  .result-info {
    margin-top: 8px; padding: 6px 8px;
    background: #e8f5e9; border-radius: 4px;
    font-size: 11px; color: #2e7d32;
  }

  /* 에러 메시지 */
  .error-msg {
    margin-top: 8px; padding: 6px 8px; background: #ffebee; color: #c62828;
    border-radius: 4px; font-size: 11px;
  }
</style>
