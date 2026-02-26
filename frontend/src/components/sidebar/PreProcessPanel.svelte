<script lang="ts">
  /**
   * PreProcessPanel — 브러쉬 선택, BC 설정, 재료 할당
   *
   * 시뮬레이션 전처리 3단계:
   *  Step 1: 고정 경계조건 (Fixed BC) — 브러쉬로 영역 선택 후 고정
   *  Step 2: 하중 경계조건 (Force BC) — 방향 + 크기 설정 + 3D 화살표 편집
   *  Step 3: 재료 할당 — 모델별 물성치 프리셋 적용
   */
  import * as THREE from 'three';
  import { onMount } from 'svelte';
  import { toolsState } from '$lib/stores/tools.svelte';
  import { analysisState } from '$lib/stores/analysis.svelte';
  import { sceneState } from '$lib/stores/scene.svelte';
  import { uiState } from '$lib/stores/ui.svelte';
  import { initAnalysis, addFixedBC, addForceBC, removeLastBC, clearAllBC } from '$lib/actions/analysis';
  import { voxelMeshes } from '$lib/actions/loading';

  // ── Pre-process 패널 마운트 시 PreProcessor 자동 초기화 ──
  // 복셀화는 모델 로드 시 자동으로 되지만, PreProcessor 생성은 이 시점에 수행한다
  onMount(() => {
    if (sceneState.models.length > 0 && !analysisState.preProcessor) {
      initAnalysis();  // PreProcessor 생성 + WebSocket 연결 (실패해도 안전)
    }
  });

  /** 하중 크기 (N) */
  let forceMagnitude = $state(100);

  /** 하중 방향 벡터 (정규화) */
  let dirX = $state(0);
  let dirY = $state(-1);
  let dirZ = $state(0);

  // 재료 관련 상태는 MaterialLibraryPanel로 이동

  /** 모델 존재 여부 */
  let hasModels = $derived(sceneState.models.length > 0);

  /** 방향 벡터 크기 (정규화 확인용) */
  let dirMag = $derived(
    Math.sqrt(dirX * dirX + dirY * dirY + dirZ * dirZ)
  );

  /** 실제 힘 벡터 (표시용) */
  let forceVec = $derived({
    x: (dirMag > 0 ? dirX / dirMag : 0) * forceMagnitude,
    y: (dirMag > 0 ? dirY / dirMag : 0) * forceMagnitude,
    z: (dirMag > 0 ? dirZ / dirMag : 0) * forceMagnitude,
  });

  // ── 3D 하중 편집기 동기화 ──

  /**
   * toolsState.forceVector 변화를 패널 UI에 반영.
   * 3D 핸들 드래그 시 실시간 동기화.
   */
  $effect(() => {
    const [fx, fy, fz] = toolsState.forceVector;
    const mag = Math.sqrt(fx * fx + fy * fy + fz * fz);
    if (mag > 0.001) {
      forceMagnitude = Math.round(mag);
      dirX = +(fx / mag).toFixed(3);
      dirY = +(fy / mag).toFixed(3);
      dirZ = +(fz / mag).toFixed(3);
    }
  });

  /** 패널 값 → toolsState.forceVector 동기화 */
  function syncPanelToForceVector() {
    if (dirMag < 0.001) return;
    const nx = dirX / dirMag;
    const ny = dirY / dirMag;
    const nz = dirZ / dirMag;
    toolsState.forceVector = [
      +(nx * forceMagnitude).toFixed(2),
      +(ny * forceMagnitude).toFixed(2),
      +(nz * forceMagnitude).toFixed(2),
    ];
  }

  // ── 3D 편집 모드 토글 ──

  function toggle3DEdit() {
    toolsState.forceEditMode3D = !toolsState.forceEditMode3D;

    if (toolsState.forceEditMode3D) {
      // 현재 패널 값을 forceVector에 먼저 반영
      syncPanelToForceVector();

      const handle = sceneState.forceArrowHandle;
      if (handle) {
        // ── 스케일: 복셀 메쉬(실제 표시) bbox 높이 기준 ──
        // 원본 STL은 복셀화 후 숨겨지므로 voxelMeshes 기준으로 계산
        const box = new THREE.Box3();
        const voxelArr = Object.values(voxelMeshes);
        if (voxelArr.length > 0) {
          voxelArr.forEach(vm => box.expandByObject(vm));
        } else {
          // 복셀화 전 fallback: 원본 메쉬 사용
          sceneState.models.forEach(m => box.expandByObject(m.mesh));
        }
        const height = box.isEmpty() ? 80 : (box.max.y - box.min.y);
        handle.setScale(Math.max(1, height / 80));

        // ── 화살표 기준점 결정 (우선순위):
        //   1. 현재 브러쉬 선택 영역 중심 (라이브 — 브러쉬 ON 상태)
        //   2. Apply Force BC 후 저장된 하중 영역 중심
        //   3. 폴백: Force BC 미적용 → 모델 전체 중심 + 경고 토스트 ──
        const liveCentroid = analysisState.preProcessor?.getBrushSelectionCentroid();
        if (liveCentroid) {
          // 브러쉬로 선택 중인 영역 중심 — 가장 직관적
          handle.setOrigin(liveCentroid);
          uiState.toast('3D Force 편집 활성화 — 브러쉬 선택 중심에서 시작', 'info');
        } else if (analysisState.forceBCOrigin) {
          // Apply Force BC 클릭 시 저장된 하중 영역 중심
          const [ox, oy, oz] = analysisState.forceBCOrigin;
          handle.setOrigin(new THREE.Vector3(ox, oy, oz));
          uiState.toast('3D Force 편집 활성화 — 하중 영역 중심에서 시작', 'info');
        } else if (!box.isEmpty()) {
          // 폴백: Force BC 미적용 — 모델 전체 중심(top face 아님)
          // 사용자가 브러쉬로 Force 면을 선택 → Apply Force BC 순서를 안내
          const center = box.getCenter(new THREE.Vector3());
          handle.setOrigin(center);
          uiState.toast('⚠ Force BC 영역을 먼저 브러쉬로 선택한 뒤 Apply Force BC를 클릭하세요', 'warn');
        }
      }

      // 화살표 표시 + 동기화
      sceneState.forceArrowHandle?.setVisible(true);
      sceneState.forceArrowHandle?.syncFromForceVector();
    } else {
      sceneState.forceArrowHandle?.setVisible(false);
      uiState.toast('3D Force 편집 비활성화', 'info');
    }
  }

  // ── 브러쉬 ──

  /** 브러쉬 모드 토글 — 미초기화 시 자동 복셀화/전처리 초기화 */
  async function toggleBrush() {
    if (!hasModels) {
      uiState.toast('모델을 먼저 로드하세요', 'warn');
      return;
    }
    // PreProcessor가 없으면 자동 초기화 (복셀화 + PreProcessor 생성)
    if (!analysisState.preProcessor) {
      uiState.toast('전처리 초기화 중... (복셀화)', 'info');
      await initAnalysis();
    }
    toolsState.setMode(toolsState.mode === 'brush' ? 'none' : 'brush');
  }

  // ── Force BC ──

  /** 브러쉬 선택 카운트 (Force BC 적용 가이드용) */
  let brushCount = $derived(analysisState.preProcessor?.getBrushSelectionCount() ?? 0);

  /** Force BC 적용 완료 여부 (방향/크기 편집 섹션 표시 조건) */
  let hasForceBC = $derived(analysisState.forceBCOrigin !== null);

  /**
   * Force BC 적용 — 브러쉬 선택 영역에 현재 힘 벡터 적용.
   * centroid 저장 후 자동으로 3D 편집 모드 활성화.
   */
  function handleApplyForce() {
    if (!hasModels) { uiState.toast('모델을 먼저 로드하세요', 'warn'); return; }

    // 브러쉬 선택 여부 확인 — Force BC는 브러쉬 선택 영역이 필요
    const brushN = analysisState.preProcessor?.getBrushSelectionCount() ?? 0;
    if (brushN === 0) {
      uiState.toast('⚠ 먼저 Brush로 Force 영역을 선택하세요', 'warn');
      return;
    }

    const nx = dirMag > 0.01 ? dirX / dirMag : 0;
    const ny = dirMag > 0.01 ? dirY / dirMag : -1;
    const nz = dirMag > 0.01 ? dirZ / dirMag : 0;

    const force: [number, number, number] = [
      nx * forceMagnitude,
      ny * forceMagnitude,
      nz * forceMagnitude,
    ];
    addForceBC(force);
    uiState.toast(`Force BC 적용 (${brushN}개 복셀, ${forceMagnitude}N) — 방향/크기를 편집하세요`, 'success');

    // ── Apply 후 자동으로 3D 편집 모드 활성화 ──
    // 위치(centroid)가 확정되었으므로 즉시 방향 편집 가능
    if (!toolsState.forceEditMode3D && analysisState.forceBCOrigin) {
      toggle3DEdit();
    }
  }

  /**
   * 마지막 Force BC의 방향/크기 업데이트.
   * 기존 BC를 삭제 후 현재 패널 설정으로 다시 적용한다.
   */
  function handleUpdateForce() {
    if (!hasModels || dirMag < 0.01) return;
    // 마지막 BC 삭제
    removeLastBC();
    // forceBCOrigin 유지하면서 새 힘 벡터로 재적용
    const nx = dirX / dirMag;
    const ny = dirY / dirMag;
    const nz = dirZ / dirMag;
    const force: [number, number, number] = [
      nx * forceMagnitude,
      ny * forceMagnitude,
      nz * forceMagnitude,
    ];
    // addForceBC가 centroid를 다시 계산하지만 이미 brushSelection이 비어있으면
    // 기존 forceBCOrigin이 유지됨
    addForceBC(force);
    uiState.toast(`Force BC 업데이트: ${forceMagnitude}N → (${nx.toFixed(1)}, ${ny.toFixed(1)}, ${nz.toFixed(1)})`, 'success');
  }

  /** Fixed BC 적용 */
  function handleApplyFixed() {
    if (!hasModels) { uiState.toast('모델을 먼저 로드하세요', 'warn'); return; }
    addFixedBC();
    uiState.toast('Fixed BC 적용됨', 'success');
  }

  /** 방향 프리셋 설정 */
  function setDirection(x: number, y: number, z: number) {
    dirX = x; dirY = y; dirZ = z;
    // 3D 편집 모드일 때 화살표도 즉시 업데이트
    if (toolsState.forceEditMode3D) {
      syncPanelToForceVector();
      sceneState.forceArrowHandle?.syncFromForceVector();
    }
  }

  /** 크기 프리셋 설정 */
  function setMagnitude(val: number) {
    forceMagnitude = val;
    if (toolsState.forceEditMode3D) {
      syncPanelToForceVector();
      sceneState.forceArrowHandle?.syncFromForceVector();
    }
  }

  /** 크기 직접 입력 */
  function handleMagnitudeInput(e: Event) {
    const val = parseFloat((e.target as HTMLInputElement).value);
    if (!isNaN(val) && val > 0) {
      forceMagnitude = val;
      if (toolsState.forceEditMode3D) {
        syncPanelToForceVector();
        sceneState.forceArrowHandle?.syncFromForceVector();
      }
    }
  }

  /** 크기 슬라이더 입력 */
  function handleMagnitudeSlider(e: Event) {
    const val = parseFloat((e.target as HTMLInputElement).value);
    forceMagnitude = val;
    if (toolsState.forceEditMode3D) {
      syncPanelToForceVector();
      sceneState.forceArrowHandle?.syncFromForceVector();
    }
  }

  /** X/Y/Z 방향 입력 변경 */
  function handleDirChange() {
    if (toolsState.forceEditMode3D) {
      syncPanelToForceVector();
      sceneState.forceArrowHandle?.syncFromForceVector();
    }
  }

  /** 전체 BC 삭제 (확인) */
  async function handleClearAllBC() {
    if (analysisState.bcCount === 0) return;
    const ok = await uiState.confirm(
      'BC 전체 삭제',
      `${analysisState.bcCount}개 경계조건을 모두 삭제합니다.`
    );
    if (ok) {
      clearAllBC();
      uiState.toast('모든 BC 삭제됨', 'info');
    }
  }

  // presetOptions 삭제 — MaterialLibraryPanel에서 관리

  /** 추천 BC 적용 — suggestedBCs[i]를 실제 BC로 적용 */
  async function applySuggestedBC(index: number) {
    const suggestion = analysisState.suggestedBCs[index];
    if (!suggestion || suggestion.applied) return;

    // PreProcessor가 없으면 초기화
    if (!analysisState.preProcessor) {
      uiState.toast('전처리 초기화 중...', 'info');
      await initAnalysis();
    }

    if (suggestion.type === 'fixed') {
      // Fixed BC: 해당 모델의 전체 복셀을 고정
      // 현재 구현에서는 브러쉬 선택 기반이므로, 안내 메시지 표시
      uiState.toast(`📌 ${suggestion.meshName}을 Brush로 선택 후 Apply Fixed BC를 클릭하세요`, 'info');
      suggestion.applied = true;
    } else if (suggestion.type === 'force') {
      // Force BC: 안내 메시지 표시
      if (suggestion.magnitude) {
        forceMagnitude = suggestion.magnitude;
      }
      if (suggestion.direction) {
        dirX = suggestion.direction[0];
        dirY = suggestion.direction[1];
        dirZ = suggestion.direction[2];
      }
      uiState.toast(`⚡ ${suggestion.meshName}을 Brush로 선택 후 Apply Force BC를 클릭하세요 (${suggestion.magnitude ?? 500}N)`, 'info');
      suggestion.applied = true;
    }

    // 반응형 업데이트 트리거
    analysisState.suggestedBCs = [...analysisState.suggestedBCs];
  }
</script>

<div class="panel">
  <h3>PRE-PROCESS</h3>

  <!-- 브러쉬 선택 -->
  <div class="section">
    <div class="section-title">Brush Selection</div>
    <div class="slider-row">
      <label for="brush-radius">반경</label>
      <input id="brush-radius" type="range" min="1" max="15" step="0.5" bind:value={toolsState.brushRadius}>
      <span class="val">{toolsState.brushRadius.toFixed(1)} mm</span>
    </div>
    <div class="hint">모델 위에서 클릭/드래그로 영역 선택</div>
    <button class="tool-btn" onclick={toggleBrush}
      class:active={toolsState.mode === 'brush'}
      disabled={!hasModels}>
      Brush: {toolsState.mode === 'brush' ? 'ON' : 'OFF'}
    </button>
    <button class="tool-btn secondary" onclick={() => analysisState.preProcessor?.clearBrushSelection()}
      disabled={!hasModels}>
      Clear Selection
    </button>
  </div>

  <!-- Step 1: Fixed BC -->
  <div class="section bc-section fixed">
    <div class="section-title" style="color: #00cc44;">Step 1: Fixed BC (고정)</div>
    <div class="hint">브러쉬로 영역 선택 → 고정 적용</div>
    <button class="tool-btn" style="background: #00cc44;" onclick={handleApplyFixed}
      disabled={!hasModels}>
      Apply Fixed BC
    </button>
  </div>

  <!-- Step 2: Force BC -->
  <div class="section bc-section force">
    <div class="section-title" style="color:#ff2222;">Step 2: Force BC (하중)</div>

    <!-- Step 2a: 영역 선택 + 적용 (먼저!) -->
    <div class="hint">1) 브러쉬로 영역 선택 → 2) Apply → 3) 방향/크기 편집</div>
    <button class="tool-btn force-apply-btn" onclick={handleApplyForce}
      disabled={!hasModels}>
      Apply Force BC ({forceMagnitude}N)
    </button>

    <!-- Step 2b: 방향/크기 편집 (Apply 후 활성화) -->
    {#if hasForceBC}
      <div style="margin-top:8px; border-top:1px dashed #ff9999; padding-top:8px;">
        <!-- 3D 편집 토글 -->
        <div class="force-header">
          <span class="subsection-label" style="margin:0">🎯 방향/크기 편집</span>
          <button
            class="edit3d-btn"
            class:edit3d-active={toolsState.forceEditMode3D}
            onclick={toggle3DEdit}
            title="뷰포트에서 화살표 핸들로 직접 편집"
          >
            {#if toolsState.forceEditMode3D}
              🎯 3D 편집 ON
            {:else}
              🎯 3D 편집
            {/if}
          </button>
        </div>

        <!-- 3D 편집 모드 힌트 -->
        {#if toolsState.forceEditMode3D}
          <div class="edit3d-hint">
            뷰포트에서 드래그 → 방향 변경. 크기는 아래 슬라이더.
          </div>
        {/if}

        <!-- 크기 설정 -->
        <div class="force-mag-section">
          <span class="subsection-label">📏 크기 (N)</span>
          <div class="mag-presets">
            {#each [50, 100, 200, 500, 1000] as v}
              <button class="mag-btn" class:active={forceMagnitude === v}
                onclick={() => setMagnitude(v)}>{v}</button>
            {/each}
          </div>
          <div class="mag-input-row">
            <input type="range" min="1" max="2000" step="1"
              value={forceMagnitude} oninput={handleMagnitudeSlider} class="mag-slider">
            <input type="number" min="1" max="10000" step="1"
              value={forceMagnitude} onchange={handleMagnitudeInput} class="mag-number">
            <span class="mag-unit">N</span>
          </div>
        </div>

        <!-- 방향 설정 -->
        <div class="force-dir-section">
          <span class="subsection-label">🧭 방향</span>
          <div class="dir-presets">
            <button class="dir-btn" class:active={dirX === 0 && dirY === -1 && dirZ === 0}
              onclick={() => setDirection(0, -1, 0)} title="압축 (아래)">
              <span class="dir-arrow">↓</span><span class="dir-text">압축</span>
            </button>
            <button class="dir-btn" class:active={dirX === 0 && dirY === 1 && dirZ === 0}
              onclick={() => setDirection(0, 1, 0)} title="인장 (위)">
              <span class="dir-arrow">↑</span><span class="dir-text">인장</span>
            </button>
            <button class="dir-btn" class:active={dirX === 1 && dirY === 0 && dirZ === 0}
              onclick={() => setDirection(1, 0, 0)} title="측방 (+X)">
              <span class="dir-arrow">→</span><span class="dir-text">측방</span>
            </button>
            <button class="dir-btn" class:active={dirX === 0 && dirY === 0 && dirZ === 1}
              onclick={() => setDirection(0, 0, 1)} title="전방 (+Z)">
              <span class="dir-arrow">⊙</span><span class="dir-text">전방</span>
            </button>
            <button class="dir-btn"
              onclick={() => setDirection(0, -0.7, -0.7)} title="전방굴곡">
              <span class="dir-arrow">↙</span><span class="dir-text">굴곡</span>
            </button>
            <button class="dir-btn"
              onclick={() => setDirection(0, -0.7, 0.7)} title="후방신전">
              <span class="dir-arrow">↘</span><span class="dir-text">신전</span>
            </button>
          </div>
          <div class="dir-xyz">
            <div class="dir-axis">
              <span class="axis-label x">X</span>
              <input type="number" step="0.1" min="-1" max="1"
                bind:value={dirX} onchange={handleDirChange}>
            </div>
            <div class="dir-axis">
              <span class="axis-label y">Y</span>
              <input type="number" step="0.1" min="-1" max="1"
                bind:value={dirY} onchange={handleDirChange}>
            </div>
            <div class="dir-axis">
              <span class="axis-label z">Z</span>
              <input type="number" step="0.1" min="-1" max="1"
                bind:value={dirZ} onchange={handleDirChange}>
            </div>
          </div>
        </div>

        <!-- 결과 힘 벡터 미리보기 -->
        <div class="force-preview">
          <span class="force-preview-label">F =</span>
          <span class="force-preview-val">({forceVec.x.toFixed(0)}, {forceVec.y.toFixed(0)}, {forceVec.z.toFixed(0)})</span>
          <span class="force-preview-unit">N</span>
        </div>

        <!-- 방향/크기 변경 후 업데이트 버튼 -->
        <button class="tool-btn force-apply-btn" onclick={handleUpdateForce}
          disabled={!hasModels || dirMag < 0.01}>
          Force BC 업데이트 ({forceMagnitude}N)
        </button>
      </div>
    {/if}
  </div>

  <!-- BC 관리 -->
  <div class="section">
    <div class="bc-info">
      <span>BCs: <strong>{analysisState.bcCount}</strong></span>
      <button class="tool-btn-sm" onclick={() => removeLastBC()}
        disabled={analysisState.bcCount === 0}>Remove Last</button>
    </div>
    <button class="tool-btn secondary" onclick={handleClearAllBC}
      disabled={analysisState.bcCount === 0}>Clear All BC</button>
  </div>

  <!-- 자동 추천 BC (파이프라인 완료 후 표시) -->
  {#if analysisState.suggestedBCs.length > 0}
    <div class="section suggested-section">
      <div class="section-title" style="color:#ff6f00;">자동 추천 BC</div>
      <div class="hint">파이프라인에서 자동 생성된 경계조건 제안입니다.</div>
      {#each analysisState.suggestedBCs as suggestion, i}
        <div class="suggested-item" class:applied={suggestion.applied}>
          <span class="suggested-icon">
            {suggestion.type === 'fixed' ? '📌' : '⚡'}
          </span>
          <span class="suggested-label">{suggestion.label}</span>
          {#if !suggestion.applied}
            <button
              class="suggested-apply-btn"
              onclick={() => applySuggestedBC(i)}
              disabled={!hasModels}
            >
              적용
            </button>
          {:else}
            <span class="suggested-applied-badge">✓</span>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  <!-- 재료 안내 -->
  <div class="section hint-section">
    <span class="hint-text">💡 재료 설정은
      <button class="link-btn" onclick={() => uiState.activeTab = 'material'}>Material 탭</button>
      에서 관리합니다</span>
  </div>
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
  .bc-section.fixed { border-left: 3px solid #00cc44; }
  .bc-section.force { border-left: 3px solid #ff2222; }
  .section-title {
    font-size: 11px; color: var(--color-primary); margin-bottom: 6px; font-weight: bold;
  }
  .subsection-label {
    font-size: 11px; color: #555; font-weight: 600; display: block; margin-bottom: 4px;
  }

  /* ── Force 헤더 (제목 + 3D 편집 버튼) ── */
  .force-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 8px;
  }
  .edit3d-btn {
    padding: 3px 8px; font-size: 10px; font-weight: 600;
    border: 1px solid #ff2222; border-radius: 4px;
    background: #fff; color: #ff2222; cursor: pointer;
    transition: all 0.15s; white-space: nowrap;
  }
  .edit3d-btn:hover { background: #ff2222; color: #fff; }
  .edit3d-active {
    background: #ff2222 !important; color: #fff !important;
  }

  /* 3D 편집 힌트 */
  .edit3d-hint {
    margin-bottom: 8px; padding: 5px 8px;
    background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px;
    font-size: 10px; color: #856404;
  }

  /* 일반 버튼 */
  .tool-btn {
    width: 100%; padding: 7px; margin: 3px 0; border: none; border-radius: 4px;
    background: var(--color-primary); color: #fff; cursor: pointer;
    font-size: 11px; transition: opacity 0.15s;
  }
  .tool-btn:hover:not(:disabled) { opacity: 0.85; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .tool-btn.secondary { background: #757575; }
  .tool-btn.active { background: #e53935; }

  /* Force 적용 버튼 강조 */
  .force-apply-btn { background: #ff2222; font-weight: 600; }

  /* 슬라이더 */
  .slider-row {
    display: flex; align-items: center; gap: 6px; font-size: 11px; color: #666; margin-bottom: 4px;
  }
  .slider-row input[type="range"] { flex: 1; }
  .slider-row label { min-width: 40px; }
  .val { font-size: 10px; color: #555; min-width: 50px; text-align: right;
         font-family: 'Consolas', monospace; font-weight: 600; }
  .hint { font-size: 10px; color: #888; margin: 4px 0; }

  /* ── 크기 프리셋 ── */
  .force-mag-section { margin-bottom: 10px; }
  .mag-presets {
    display: flex; gap: 3px; margin-bottom: 6px;
  }
  .mag-btn {
    flex: 1; padding: 5px 2px; font-size: 11px; font-weight: 600;
    border: 1px solid #ddd; border-radius: 4px;
    background: #f8f8f8; cursor: pointer; color: #555;
    transition: all 0.15s;
  }
  .mag-btn:hover { background: #eee; border-color: #bbb; }
  .mag-btn.active {
    background: #ff2222; color: #fff; border-color: #ff2222;
  }

  /* 크기 슬라이더 + 숫자 입력 */
  .mag-input-row {
    display: flex; align-items: center; gap: 6px;
  }
  .mag-slider { flex: 1; }
  .mag-number {
    width: 60px; padding: 4px; font-size: 12px; font-weight: 600;
    text-align: center; border: 1px solid #ccc; border-radius: 3px;
    font-family: 'Consolas', monospace;
  }
  .mag-unit { font-size: 11px; color: #888; font-weight: 600; }

  /* ── 방향 프리셋 ── */
  .force-dir-section { margin-bottom: 8px; }
  .dir-presets {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 3px; margin-bottom: 8px;
  }
  .dir-btn {
    display: flex; flex-direction: column; align-items: center;
    padding: 5px 2px; border: 1px solid #ddd; border-radius: 4px;
    background: #f8f8f8; cursor: pointer;
    transition: all 0.15s; gap: 1px;
  }
  .dir-btn:hover { background: #eee; border-color: #bbb; }
  .dir-btn.active {
    background: #ff4444; color: #fff; border-color: #ff4444;
  }
  .dir-arrow { font-size: 14px; line-height: 1; }
  .dir-text { font-size: 9px; color: #666; }
  .dir-btn.active .dir-text { color: #fff; }

  /* X/Y/Z 입력 */
  .dir-xyz {
    display: flex; gap: 4px;
  }
  .dir-axis {
    flex: 1; display: flex; align-items: center; gap: 3px;
  }
  .axis-label {
    font-size: 10px; font-weight: 700; width: 16px; text-align: center;
    padding: 2px 0; border-radius: 2px; color: #fff;
  }
  .axis-label.x { background: #e53935; }
  .axis-label.y { background: #43a047; }
  .axis-label.z { background: #1e88e5; }
  .dir-axis input {
    width: 100%; padding: 3px 2px; font-size: 11px; text-align: center;
    border: 1px solid #ccc; border-radius: 3px;
    font-family: 'Consolas', monospace;
  }

  /* 힘 벡터 미리보기 */
  .force-preview {
    display: flex; align-items: center; justify-content: center;
    gap: 4px; padding: 5px 8px; margin: 6px 0;
    background: #fff3e0; border: 1px solid #ffe0b2; border-radius: 4px;
    font-family: 'Consolas', monospace; font-size: 11px;
  }
  .force-preview-label { color: #e65100; font-weight: 700; }
  .force-preview-val { color: #bf360c; font-weight: 600; }
  .force-preview-unit { color: #999; font-size: 10px; }

  /* BC 관리 */
  .bc-info {
    display: flex; align-items: center; justify-content: space-between;
    font-size: 11px; color: #666; margin-bottom: 6px;
  }
  .tool-btn-sm {
    padding: 3px 8px; font-size: 10px; border: 1px solid #ccc;
    border-radius: 3px; background: #f5f5f5; cursor: pointer; color: #555;
  }
  .tool-btn-sm:hover:not(:disabled) { background: #e0e0e0; }
  .tool-btn-sm:disabled { opacity: 0.4; cursor: default; }

  /* ── 자동 추천 BC ── */
  .suggested-section { border-left: 3px solid #ff6f00; }
  .suggested-item {
    display: flex; align-items: center; gap: 6px;
    padding: 5px 0; font-size: 11px;
    border-bottom: 1px solid #f0f0f0;
  }
  .suggested-item:last-child { border-bottom: none; }
  .suggested-item.applied { opacity: 0.6; }
  .suggested-icon { font-size: 13px; flex-shrink: 0; }
  .suggested-label { flex: 1; color: #555; }
  .suggested-apply-btn {
    padding: 3px 10px; font-size: 10px; font-weight: 600;
    border: 1px solid #ff6f00; border-radius: 4px;
    background: #fff; color: #ff6f00; cursor: pointer;
    transition: all 0.15s; white-space: nowrap;
  }
  .suggested-apply-btn:hover { background: #ff6f00; color: #fff; }
  .suggested-apply-btn:disabled { opacity: 0.4; cursor: default; }
  .suggested-applied-badge {
    font-size: 11px; color: #2e7d32; font-weight: 600;
  }

  /* ── 재료 안내 힌트 ── */
  .hint-section {
    border-left: 3px solid #1976d2;
    display: flex; align-items: center; justify-content: center;
    padding: 12px 10px;
  }
  .hint-text {
    font-size: 11px; color: #666;
  }
  .link-btn {
    background: none; border: none; padding: 0; margin: 0;
    color: var(--color-primary); font-size: 11px; font-weight: 600;
    cursor: pointer; text-decoration: underline;
  }
  .link-btn:hover { color: #1565c0; }
</style>
