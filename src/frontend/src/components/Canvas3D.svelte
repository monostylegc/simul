<script lang="ts">
  /**
   * Canvas3D — Three.js 렌더링 캔버스 + 포인터/키보드 이벤트
   */
  import { onMount } from 'svelte';
  import * as THREE from 'three';
  import { SceneManager } from '$lib/three/SceneManager';
  import { sceneState } from '$lib/stores/scene.svelte';
  import { toolsState } from '$lib/stores/tools.svelte';
  import { historyState } from '$lib/stores/history.svelte';
  import { updateDrillPreview, performDrill } from '$lib/actions/drilling';
  import { loadSTLFiles } from '$lib/actions/loading';
  import { analysisState } from '$lib/stores/analysis.svelte';

  let containerEl: HTMLDivElement;

  // 레이캐스터
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();

  onMount(() => {
    const manager = new SceneManager(containerEl);
    sceneState.manager = manager;

    // FPS 업데이트 콜백
    manager.onBeforeRender = () => {
      sceneState.fps = manager.fps;
    };

    manager.start();

    // ── 포인터 이벤트 ──
    const canvas = manager.renderer.domElement;

    function getMouseNDC(e: MouseEvent): THREE.Vector2 {
      const rect = canvas.getBoundingClientRect();
      return new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1,
      );
    }

    function getIntersection(e: MouseEvent): THREE.Intersection | null {
      mouse.copy(getMouseNDC(e));
      raycaster.setFromCamera(mouse, manager.camera);

      // 가시 메쉬만 대상으로
      const targets = sceneState.models
        .filter(m => m.visible)
        .map(m => m.mesh);

      const intersections = raycaster.intersectObjects(targets, false);
      return intersections.length > 0 ? intersections[0] : null;
    }

    function handlePointerMove(e: MouseEvent) {
      // 드릴 프리뷰
      if (toolsState.mode === 'drill') {
        const hit = getIntersection(e);
        if (hit) {
          updateDrillPreview(hit.point);
        }
      }
    }

    function handlePointerDown(e: MouseEvent) {
      // 좌클릭만 처리 (0 = left)
      if (e.button !== 0) return;

      // 드릴
      if (toolsState.mode === 'drill') {
        const hit = getIntersection(e);
        if (hit) {
          performDrill(hit.point);
        }
      }

      // 브러쉬
      if (toolsState.mode === 'brush') {
        const hit = getIntersection(e);
        if (hit) {
          analysisState.preProcessor?.brushSelectSphere(hit.point, toolsState.brushRadius);
        }
      }
    }

    canvas.addEventListener('pointermove', handlePointerMove);
    canvas.addEventListener('pointerdown', handlePointerDown);

    // ── 키보드 이벤트 ──
    function handleKeyDown(e: KeyboardEvent) {
      // Ctrl+Z: Undo
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        historyState.undo();
      }
      // Ctrl+Y 또는 Ctrl+Shift+Z: Redo
      if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        historyState.redo();
      }
      // Escape: 도구 해제
      if (e.key === 'Escape') {
        toolsState.reset();
      }
    }

    window.addEventListener('keydown', handleKeyDown);

    // ── 파일 드래그앤드롭 ──
    function handleDragOver(e: DragEvent) {
      e.preventDefault();
      e.stopPropagation();
    }

    function handleDrop(e: DragEvent) {
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
        loadSTLFiles(e.dataTransfer.files);
      }
    }

    containerEl.addEventListener('dragover', handleDragOver);
    containerEl.addEventListener('drop', handleDrop);

    return () => {
      canvas.removeEventListener('pointermove', handlePointerMove);
      canvas.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
      containerEl.removeEventListener('dragover', handleDragOver);
      containerEl.removeEventListener('drop', handleDrop);
      manager.dispose();
      sceneState.manager = null;
    };
  });
</script>

<div class="canvas-container" bind:this={containerEl}></div>

<style>
  .canvas-container {
    flex: 1;
    position: relative;
    overflow: hidden;
  }
</style>
