<script lang="ts">
  /**
   * Canvas3D — Three.js 렌더링 캔버스 + 포인터/키보드 이벤트
   *
   * 이벤트 모드:
   *   - drill: 뼈 표면 드릴
   *   - brush: 브러쉬 영역 선택
   *   - implantPlace: 임플란트 배치
   *       스크류: 2클릭 (1. 진입점 → 카메라 자유 → 2. 끝점 → 배치)
   *       케이지: 1클릭 (표면 법선 방향 즉시 배치)
   *   - forceEditMode3D: 하중 화살표 편집
   *       일러스트 스타일: 뷰포트 어디서든 클릭-드래그 → 화살표 방향/크기 변경
   */
  import { onMount } from 'svelte';
  import * as THREE from 'three';
  import { SceneManager } from '$lib/three/SceneManager';
  import { ImplantManager } from '$lib/three/ImplantManager.svelte';
  import { ForceArrowHandle } from '$lib/three/ForceArrowHandle';
  import { sceneState } from '$lib/stores/scene.svelte';
  import { toolsState } from '$lib/stores/tools.svelte';
  import { historyState } from '$lib/stores/history.svelte';
  import { updateDrillPreview, performDrill } from '$lib/actions/drilling';
  import { loadSTLFiles } from '$lib/actions/loading';
  import { analysisState } from '$lib/stores/analysis.svelte';
  import {
    placeImplantAtClick,
    deleteSelectedImplant,
    setEntryPoint,
    placeAtDirection,
    updateDirectionPreview,
    cancelScrewEntry,
    hasEntryPoint,
    getEntryPoint,
  } from '$lib/actions/implantCatalog';
  import { initGuidelineLayer } from '$lib/actions/implants';
  import { voxelMeshes } from '$lib/actions/loading';
  import ViewFloatingMenu from './floating/ViewFloatingMenu.svelte';

  let containerEl: HTMLDivElement;

  // 레이캐스터
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();

  // ForceArrow 드래그 상태
  let isDraggingForceHandle = false;
  let dragPlaneNormal = new THREE.Vector3();
  let dragHandleWorldPos = new THREE.Vector3();
  let dragInitialMagnitude = 100;

  onMount(() => {
    const manager = new SceneManager(containerEl);
    sceneState.manager = manager;

    // FPS 업데이트 콜백
    manager.onBeforeRender = () => {
      sceneState.fps = manager.fps;
    };

    manager.start();

    // ── 가이드라인 레이어 초기화 (WebSocket 가이드라인 씬 그룹 추가) ──
    initGuidelineLayer(manager.scene);

    // ── ImplantManager 생성 ──
    const implantMgr = new ImplantManager(
      manager.scene,
      manager.camera,
      manager.renderer,
      manager.controls,
    );
    sceneState.implantManager = implantMgr;

    // ── ForceArrowHandle 생성 ──
    const forceHandle = new ForceArrowHandle(
      manager.scene,
      manager.camera,
      manager.renderer,
    );
    sceneState.forceArrowHandle = forceHandle;

    // ── 포인터 이벤트 ──
    const canvas = manager.renderer.domElement;

    function getMouseNDC(e: MouseEvent): THREE.Vector2 {
      const rect = canvas.getBoundingClientRect();
      return new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1,
      );
    }

    /**
     * 뼈 메쉬 대상 레이캐스트.
     * 복셀화 후 원본 메쉬가 숨겨지므로 복셀 메쉬도 대상에 포함한다.
     */
    function getIntersection(e: MouseEvent): THREE.Intersection | null {
      mouse.copy(getMouseNDC(e));
      raycaster.setFromCamera(mouse, manager.camera);
      // 원본 메쉬 (visible인 것) + 복셀 메쉬
      const targets: THREE.Object3D[] = [
        ...sceneState.models.filter(m => m.mesh.visible).map(m => m.mesh),
        ...Object.values(voxelMeshes).filter(m => m.visible),
      ];
      const hits = raycaster.intersectObjects(targets, false);
      return hits.length > 0 ? hits[0] : null;
    }

    /** 뼈 + 임플란트 대상 레이캐스트 */
    function getIntersectionAll(e: MouseEvent): THREE.Intersection | null {
      mouse.copy(getMouseNDC(e));
      raycaster.setFromCamera(mouse, manager.camera);

      const targets: THREE.Object3D[] = [
        ...sceneState.models.filter(m => m.mesh.visible).map(m => m.mesh),
        ...Object.values(voxelMeshes).filter(m => m.visible),
        ...Object.values(implantMgr.implants).map(entry => entry.mesh),
      ];
      const hits = raycaster.intersectObjects(targets, false);
      return hits.length > 0 ? hits[0] : null;
    }

    /**
     * NDC → 카메라 정면 평면 교차점 계산.
     * 2클릭 배치 시 끝점을 뼈 표면이 아닌 곳에서도 지정할 수 있도록.
     */
    function getPlaneHitFromEvent(e: MouseEvent, planeOrigin: THREE.Vector3): THREE.Vector3 | null {
      const ndc = getMouseNDC(e);
      const rc = new THREE.Raycaster();
      rc.setFromCamera(ndc, manager.camera);
      // 카메라 정면에 수직인 평면
      const planeNormal = new THREE.Vector3();
      planeNormal.setFromMatrixColumn(manager.camera.matrixWorld, 2).negate();
      const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(planeNormal, planeOrigin);
      const hit = new THREE.Vector3();
      if (!rc.ray.intersectPlane(plane, hit)) return null;
      return hit;
    }

    function handlePointerMove(e: MouseEvent) {
      // ── 스크류 2클릭: 진입점 설정 후 프리뷰 라인 업데이트 ──
      if (toolsState.mode === 'implantPlace' && hasEntryPoint()) {
        const hit = getIntersection(e);
        if (hit) {
          updateDirectionPreview(hit.point);
        } else {
          // 뼈 밖이면 카메라 평면에 투영
          const ep = getEntryPoint();
          if (ep) {
            const planeHit = getPlaneHitFromEvent(e, ep);
            if (planeHit) updateDirectionPreview(planeHit);
          }
        }
        // 참고: 카메라 OrbitControls는 활성 상태 (자유 회전 가능)
      }

      // ForceArrow 핸들 드래그 중
      if (isDraggingForceHandle) {
        forceHandle.updateFromDrag(
          getMouseNDC(e),
          dragPlaneNormal,
          dragHandleWorldPos,
          dragInitialMagnitude,
        );
        return;
      }

      // 드릴 프리뷰
      if (toolsState.mode === 'drill') {
        const hit = getIntersection(e);
        if (hit) updateDrillPreview(hit.point);
      }
    }

    function handlePointerDown(e: MouseEvent) {
      if (e.button !== 0) return;

      // ── 임플란트 배치 모드 ──
      if (toolsState.mode === 'implantPlace') {
        const hit = getIntersection(e);
        if (!hit || !hit.face) return;

        // 법선 벡터를 월드 좌표로 변환
        const normal = hit.face.normal
          .clone()
          .transformDirection(hit.object.matrixWorld)
          .normalize();

        const category = toolsState.pendingImplantCategory;

        if (category === 'screw' || category === 'rod') {
          // ── 스크류/로드 2클릭 배치 ──
          if (!hasEntryPoint()) {
            // 1단계: 진입점 설정 (카메라 자유 유지)
            setEntryPoint(hit.point, normal);
          } else {
            // 2단계: 끝점 클릭 → 배치
            placeAtDirection(hit.point);
          }
        } else {
          // ── 케이지: 즉시 배치 ──
          placeImplantAtClick(hit.point, normal);
        }
        return;
      }

      // ── Force 화살표 편집 (일러스트 스타일: 뷰포트 어디서든 클릭-드래그) ──
      if (toolsState.forceEditMode3D) {
        isDraggingForceHandle = true;

        // 드래그 평면 법선: 카메라 -Z 방향
        dragPlaneNormal.setFromMatrixColumn(manager.camera.matrixWorld, 2).negate();
        // 드래그 평면 기준점: 화살표 기준점
        dragHandleWorldPos.copy(forceHandle.getOrigin());
        // 드래그 시작 시점의 힘 크기
        const [fx, fy, fz] = toolsState.forceVector;
        dragInitialMagnitude = Math.sqrt(fx * fx + fy * fy + fz * fz) || 100;
        // OrbitControls 비활성화
        manager.controls.enabled = false;
        return;
      }

      // ── 임플란트 클릭 선택 ──
      if (toolsState.mode === 'none') {
        const hit = getIntersectionAll(e);
        if (hit?.object.userData.isImplant) {
          const name = hit.object.userData.implantName as string;
          implantMgr.selectImplant(name);
          return;
        }
        // 빈 공간 클릭 → 선택 해제
        implantMgr.deselectImplant();
      }

      // ── 드릴 ──
      if (toolsState.mode === 'drill') {
        const hit = getIntersection(e);
        if (hit) performDrill(hit.point);
      }

      // ── 브러쉬 ──
      if (toolsState.mode === 'brush') {
        const hit = getIntersection(e);
        if (hit) {
          analysisState.preProcessor?.brushSelectSphere(hit.point, toolsState.brushRadius);
        }
      }
    }

    function handlePointerUp(_e: MouseEvent) {
      if (isDraggingForceHandle) {
        isDraggingForceHandle = false;
        manager.controls.enabled = true;
      }
    }

    canvas.addEventListener('pointermove', handlePointerMove);
    canvas.addEventListener('pointerdown', handlePointerDown);
    canvas.addEventListener('pointerup', handlePointerUp);

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
      // Delete: 선택된 임플란트 삭제
      if (e.key === 'Delete') {
        deleteSelectedImplant();
      }
      // Escape: 도구 해제 + 배치 모드 종료
      if (e.key === 'Escape') {
        cancelScrewEntry();
        toolsState.exitImplantPlaceMode();
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
      canvas.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('keydown', handleKeyDown);
      containerEl.removeEventListener('dragover', handleDragOver);
      containerEl.removeEventListener('drop', handleDrop);
      forceHandle.dispose();
      implantMgr.dispose();
      sceneState.implantManager = null;
      sceneState.forceArrowHandle = null;
      sceneState.manager = null;
      manager.dispose();
    };
  });
</script>

<div class="canvas-container" bind:this={containerEl}>
  <ViewFloatingMenu />
</div>

<style>
  .canvas-container {
    flex: 1;
    position: relative;
    overflow: hidden;
  }
</style>
