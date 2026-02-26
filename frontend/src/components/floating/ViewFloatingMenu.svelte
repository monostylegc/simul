<script lang="ts">
  /**
   * ViewFloatingMenu — 3D 뷰포트 우상단 플로팅 메뉴
   *
   * 기능:
   *  - 카메라 프리셋 (Front/Back/Top/Bottom/Left/Right + Reset)
   *  - 배경색 변경
   *  - 렌더링 모드 (Solid / Wireframe / Solid+Wire)
   *  - 투명도 / 조명 강도 슬라이더
   *  - 그리드 / 축 토글
   *  - 스크린샷 캡처
   *  - 접기/펼치기 토글 (기본: 접힘)
   */
  import { sceneState } from '$lib/stores/scene.svelte';
  import * as THREE from 'three';

  // ── 접기/펼치기 상태 ──
  let isOpen = $state(false);

  /** 카메라 프리셋 방향 */
  function setCameraView(direction: string) {
    const mgr = sceneState.manager;
    if (!mgr) return;

    const target = mgr.controls.target.clone();
    const dist = mgr.camera.position.distanceTo(target);

    const positions: Record<string, [number, number, number]> = {
      front:  [0, 0, dist],
      back:   [0, 0, -dist],
      top:    [0, dist, 0],
      bottom: [0, -dist, 0],
      left:   [-dist, 0, 0],
      right:  [dist, 0, 0],
    };

    const pos = positions[direction];
    if (pos) {
      mgr.camera.position.set(
        target.x + pos[0],
        target.y + pos[1],
        target.z + pos[2],
      );
      mgr.camera.lookAt(target);
      mgr.controls.update();
    }
  }

  /** 카메라 리셋 */
  function resetCamera() {
    const mgr = sceneState.manager;
    if (!mgr) return;
    if (sceneState.models.length > 0) {
      mgr.focusOnMesh(sceneState.models[0].mesh);
    }
  }

  /** 배경색 변경 */
  function setBgColor(color: string) {
    const mgr = sceneState.manager;
    if (mgr) {
      mgr.renderer.setClearColor(new THREE.Color(color));
    }
  }

  /** 그리드 토글 */
  let showGrid = $state(true);
  let showAxes = $state(true);

  function toggleGrid() {
    showGrid = !showGrid;
    const mgr = sceneState.manager;
    if (mgr) {
      mgr.scene.traverse(obj => {
        if (obj.type === 'GridHelper') obj.visible = showGrid;
      });
    }
  }

  function toggleAxes() {
    showAxes = !showAxes;
    const mgr = sceneState.manager;
    if (mgr) {
      mgr.scene.traverse(obj => {
        if (obj.type === 'AxesHelper') obj.visible = showAxes;
      });
    }
  }

  // ── 렌더링 모드 ──

  type RenderMode = 'solid' | 'wireframe' | 'solid+wire';
  let renderMode = $state<RenderMode>('solid');

  function setRenderMode(mode: RenderMode) {
    renderMode = mode;
    const mgr = sceneState.manager;
    if (!mgr) return;

    sceneState.models.forEach(({ mesh }) => {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      mat.wireframe = mode === 'wireframe';
      if (mode === 'solid+wire') {
        mat.wireframe = false;
        _clearWireOverlay(mesh);
        _addWireOverlay(mesh);
      } else {
        _clearWireOverlay(mesh);
      }
    });
  }

  function _addWireOverlay(mesh: THREE.Mesh) {
    const wireMat = new THREE.MeshBasicMaterial({
      color: 0x000000, wireframe: true, transparent: true, opacity: 0.15,
      depthTest: true,
    });
    const wireClone = new THREE.Mesh(mesh.geometry, wireMat);
    wireClone.name = '__wireOverlay';
    wireClone.renderOrder = 1;
    mesh.add(wireClone);
  }

  function _clearWireOverlay(mesh: THREE.Mesh) {
    const overlay = mesh.getObjectByName('__wireOverlay');
    if (overlay) {
      mesh.remove(overlay);
      if ((overlay as THREE.Mesh).material) {
        ((overlay as THREE.Mesh).material as THREE.Material).dispose();
      }
    }
  }

  // ── 모델 투명도 ──

  let modelOpacity = $state(1.0);

  function handleModelOpacity(e: Event) {
    modelOpacity = parseFloat((e.target as HTMLInputElement).value);
    sceneState.models.forEach(({ mesh }) => {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      mat.transparent = modelOpacity < 1.0;
      mat.opacity = modelOpacity;
      mat.depthWrite = modelOpacity >= 1.0;
      mat.needsUpdate = true;
    });
  }

  // ── 조명 강도 ──

  let lightIntensity = $state(0.7);

  function handleLightIntensity(e: Event) {
    lightIntensity = parseFloat((e.target as HTMLInputElement).value);
    const mgr = sceneState.manager;
    if (mgr) {
      mgr.dirLight.intensity = lightIntensity;
    }
  }

  // ── 스크린샷 ──

  function captureScreenshot() {
    const mgr = sceneState.manager;
    if (!mgr) return;

    // 현재 프레임 강제 렌더링
    mgr.renderer.render(mgr.scene, mgr.camera);
    const dataURL = mgr.renderer.domElement.toDataURL('image/png');

    const a = document.createElement('a');
    a.href = dataURL;
    a.download = `screenshot_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.png`;
    a.click();
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="view-float" onpointerdown={(e) => e.stopPropagation()}>
  {#if !isOpen}
    <!-- 접힌 상태: 컴팩트 토글 버튼 -->
    <button class="toggle-btn collapsed" onclick={() => { isOpen = true; }} title="View 설정">
      🎨 View
    </button>
  {:else}
    <!-- 펼친 상태: 전체 메뉴 -->
    <div class="menu-panel">
      <div class="menu-header">
        <span class="menu-title">View</span>
        <button class="toggle-btn-close" onclick={() => { isOpen = false; }} title="접기">▲</button>
      </div>

      <!-- 카메라 프리셋 -->
      <div class="menu-section">
        <div class="sec-label">Camera</div>
        <div class="cam-grid">
          <button class="cam-btn" onclick={() => setCameraView('front')} title="Front">F</button>
          <button class="cam-btn" onclick={() => setCameraView('back')} title="Back">Bk</button>
          <button class="cam-btn" onclick={() => setCameraView('top')} title="Top">T</button>
          <button class="cam-btn" onclick={() => setCameraView('bottom')} title="Bottom">Bo</button>
          <button class="cam-btn" onclick={() => setCameraView('left')} title="Left">L</button>
          <button class="cam-btn" onclick={() => setCameraView('right')} title="Right">R</button>
          <button class="cam-btn reset" onclick={resetCamera} title="Reset Camera">⟳</button>
        </div>
      </div>

      <!-- 배경 + 렌더모드 -->
      <div class="menu-section">
        <div class="sec-row">
          <span class="sec-label-inline">BG</span>
          <select class="mini-select" onchange={(e) => setBgColor((e.target as HTMLSelectElement).value)}>
            <option value="#e8e8e8">Light Gray</option>
            <option value="#ffffff">White</option>
            <option value="#1a1a1a">Dark</option>
            <option value="#d0d8e0">Blue Gray</option>
          </select>
        </div>
        <div class="sec-row" style="margin-top: 4px;">
          <span class="sec-label-inline">Mode</span>
          <div class="mode-btns">
            <button class="mode-btn" class:active={renderMode === 'solid'}
              onclick={() => setRenderMode('solid')}>Solid</button>
            <button class="mode-btn" class:active={renderMode === 'wireframe'}
              onclick={() => setRenderMode('wireframe')}>Wire</button>
            <button class="mode-btn" class:active={renderMode === 'solid+wire'}
              onclick={() => setRenderMode('solid+wire')}>S+W</button>
          </div>
        </div>
      </div>

      <!-- 투명도 / 조명 -->
      <div class="menu-section">
        <div class="slider-row">
          <span class="slider-label">Opacity</span>
          <input type="range" min="0.1" max="1.0" step="0.05"
            value={modelOpacity} oninput={handleModelOpacity} class="mini-slider">
          <span class="slider-val">{modelOpacity.toFixed(2)}</span>
        </div>
        <div class="slider-row">
          <span class="slider-label">Light</span>
          <input type="range" min="0.0" max="2.0" step="0.1"
            value={lightIntensity} oninput={handleLightIntensity} class="mini-slider">
          <span class="slider-val">{lightIntensity.toFixed(1)}</span>
        </div>
      </div>

      <!-- 헬퍼 + 스크린샷 -->
      <div class="menu-section bottom-section">
        <label class="check-row">
          <input type="checkbox" checked={showGrid} onchange={toggleGrid}>
          <span>Grid</span>
        </label>
        <label class="check-row">
          <input type="checkbox" checked={showAxes} onchange={toggleAxes}>
          <span>Axes</span>
        </label>
        <button class="screenshot-btn" onclick={captureScreenshot}>📷 Screenshot</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .view-float {
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 10;
    pointer-events: auto;
  }

  /* ── 접힌 상태 토글 버튼 ── */
  .toggle-btn.collapsed {
    padding: 6px 12px;
    background: rgba(255, 255, 255, 0.92);
    backdrop-filter: blur(8px);
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
    color: #555;
    transition: all 0.15s;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  }
  .toggle-btn.collapsed:hover {
    background: rgba(255, 255, 255, 1);
    border-color: var(--color-primary);
    color: var(--color-primary);
  }

  /* ── 펼친 메뉴 패널 ── */
  .menu-panel {
    width: 220px;
    background: rgba(255, 255, 255, 0.94);
    backdrop-filter: blur(10px);
    border: 1px solid #d0d0d0;
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    overflow: hidden;
  }

  .menu-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border-bottom: 1px solid #e8e8e8;
    background: rgba(245, 245, 245, 0.6);
  }
  .menu-title {
    font-size: 12px;
    font-weight: 700;
    color: var(--color-primary);
    letter-spacing: 0.5px;
  }
  .toggle-btn-close {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 10px;
    color: #888;
    padding: 2px 4px;
    border-radius: 3px;
  }
  .toggle-btn-close:hover {
    background: #e0e0e0;
    color: #555;
  }

  /* ── 섹션 ── */
  .menu-section {
    padding: 8px 10px;
    border-bottom: 1px solid #f0f0f0;
  }
  .menu-section:last-child {
    border-bottom: none;
  }
  .sec-label {
    font-size: 9px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 5px;
    font-weight: 600;
  }

  /* ── 카메라 그리드 ── */
  .cam-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
  }
  .cam-btn {
    flex: 1;
    min-width: 24px;
    padding: 4px 2px;
    border: 1px solid #ddd;
    border-radius: 3px;
    background: #f8f8f8;
    cursor: pointer;
    font-size: 9px;
    font-weight: 600;
    color: #555;
    text-align: center;
    transition: all 0.12s;
  }
  .cam-btn:hover {
    background: #e3f2fd;
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
  .cam-btn.reset {
    font-size: 12px;
    color: var(--color-primary);
  }

  /* ── 인라인 행 ── */
  .sec-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .sec-label-inline {
    font-size: 9px;
    color: #888;
    font-weight: 600;
    min-width: 32px;
    flex-shrink: 0;
  }
  .mini-select {
    flex: 1;
    padding: 3px 4px;
    font-size: 10px;
    border: 1px solid #ddd;
    border-radius: 3px;
    background: #fff;
  }

  /* ── 렌더모드 버튼 ── */
  .mode-btns {
    display: flex;
    gap: 2px;
    flex: 1;
  }
  .mode-btn {
    flex: 1;
    padding: 3px 4px;
    border: 1px solid #ddd;
    border-radius: 3px;
    background: #f8f8f8;
    cursor: pointer;
    font-size: 9px;
    color: #666;
    text-align: center;
    transition: all 0.12s;
  }
  .mode-btn:hover {
    background: #e3f2fd;
  }
  .mode-btn.active {
    background: var(--color-primary);
    color: #fff;
    border-color: var(--color-primary);
  }

  /* ── 슬라이더 행 ── */
  .slider-row {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-bottom: 3px;
  }
  .slider-row:last-child {
    margin-bottom: 0;
  }
  .slider-label {
    font-size: 9px;
    color: #888;
    min-width: 40px;
    flex-shrink: 0;
  }
  .mini-slider {
    flex: 1;
    height: 14px;
  }
  .slider-val {
    font-size: 9px;
    color: #555;
    font-family: 'Consolas', monospace;
    font-weight: 600;
    min-width: 28px;
    text-align: right;
  }

  /* ── 체크박스 + 스크린샷 ── */
  .bottom-section {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .check-row {
    display: flex;
    align-items: center;
    gap: 3px;
    cursor: pointer;
    font-size: 10px;
    color: #666;
  }
  .check-row input {
    margin: 0;
    width: 13px;
    height: 13px;
  }
  .screenshot-btn {
    margin-left: auto;
    padding: 3px 8px;
    border: 1px solid #ddd;
    border-radius: 3px;
    background: #f8f8f8;
    cursor: pointer;
    font-size: 9px;
    color: #555;
    transition: all 0.12s;
  }
  .screenshot-btn:hover {
    background: #e3f2fd;
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
</style>
