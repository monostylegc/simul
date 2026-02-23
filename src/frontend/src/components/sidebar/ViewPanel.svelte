<script lang="ts">
  /**
   * ViewPanel — 카메라 프리셋, 조명, 배경, 헬퍼
   */
  import { sceneState } from '$lib/stores/scene.svelte';
  import * as THREE from 'three';

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
</script>

<div class="panel">
  <h3>VIEW</h3>

  <!-- 카메라 프리셋 -->
  <div class="section">
    <div class="section-title">Camera Preset</div>
    <button class="tool-btn primary" onclick={resetCamera}>Reset</button>
    <div class="btn-grid">
      <button class="tool-btn small" onclick={() => setCameraView('front')}>Front</button>
      <button class="tool-btn small" onclick={() => setCameraView('back')}>Back</button>
      <button class="tool-btn small" onclick={() => setCameraView('top')}>Top</button>
      <button class="tool-btn small" onclick={() => setCameraView('bottom')}>Bottom</button>
      <button class="tool-btn small" onclick={() => setCameraView('left')}>Left</button>
      <button class="tool-btn small" onclick={() => setCameraView('right')}>Right</button>
    </div>
  </div>

  <!-- 배경색 -->
  <div class="section">
    <div class="section-title">Background</div>
    <label for="bg-color" class="sr-only">Background Color</label>
    <select id="bg-color" class="prop-select" onchange={(e) => setBgColor((e.target as HTMLSelectElement).value)}>
      <option value="#e8e8e8">Light Gray (Default)</option>
      <option value="#ffffff">White</option>
      <option value="#1a1a1a">Dark</option>
      <option value="#d0d8e0">Blue Gray</option>
    </select>
  </div>

  <!-- 헬퍼 -->
  <div class="section">
    <div class="section-title">Helpers</div>
    <label class="check-row">
      <input type="checkbox" checked={showGrid} onchange={toggleGrid}>
      Grid
    </label>
    <label class="check-row">
      <input type="checkbox" checked={showAxes} onchange={toggleAxes}>
      Axes
    </label>
  </div>
</div>

<style>
  .panel h3 {
    color: var(--color-primary); margin-bottom: 10px; font-size: 13px;
    text-transform: uppercase; letter-spacing: 1px; padding-bottom: 6px;
    border-bottom: 1px solid rgba(25, 118, 210, 0.2);
  }
  .section {
    margin-bottom: 12px; padding: 10px;
    background: var(--color-card); border: 1px solid #e8e8e8; border-radius: 6px;
  }
  .section-title {
    font-size: 11px; color: var(--color-primary); margin-bottom: 6px; font-weight: bold;
  }
  .tool-btn {
    width: 100%; padding: 7px; border: none; border-radius: 4px;
    background: #757575; color: #fff; cursor: pointer;
    font-size: 11px; transition: opacity 0.15s; margin-bottom: 3px;
  }
  .tool-btn.primary { background: var(--color-primary); }
  .tool-btn.small { padding: 5px; font-size: 10px; }
  .tool-btn:hover { opacity: 0.85; }
  .btn-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 4px;
  }
  .prop-select {
    width: 100%; padding: 5px 6px; font-size: 11px;
    border: 1px solid #ccc; border-radius: 3px;
  }
  .check-row {
    display: flex; align-items: center; cursor: pointer;
    font-size: 11px; color: #666; margin-bottom: 5px;
  }
  .check-row input { margin-right: 8px; }
  .sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0,0,0,0); border: 0;
  }
</style>
