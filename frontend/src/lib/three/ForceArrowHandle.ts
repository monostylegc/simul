/**
 * ForceArrowHandle — 3D 하중 벡터 편집기
 *
 * Three.js 씬에 힘 벡터 화살표를 표시한다.
 * 일러스트 스타일로 뷰포트 어디서든 클릭-드래그하면 화살표 방향/크기가 변경된다.
 *
 * 사용 흐름:
 *   1. Canvas3D onMount → new ForceArrowHandle(scene, camera, renderer)
 *   2. PreProcessPanel "3D 편집" 버튼 → setVisible(true)
 *   3. Canvas3D: forceEditMode3D 시 뷰포트 어디서든 pointerdown → 드래그 시작
 *   4. pointermove 중 updateFromDrag() 호출
 *   5. toolsState.forceVector 변경 → PreProcessPanel X/Y/Z 패널 자동 동기화
 */

import * as THREE from 'three';
import { toolsState } from '$lib/stores/tools.svelte';

// ── 시각 설정 ──

const ARROW_COLOR   = 0xff2222;  // 화살표 색상 (빨강)
const TAIL_COLOR    = 0xff6600;  // 꼬리 구 색상 (주황) — 화살표 시작점 표시
const TAIL_RADIUS   = 5;         // 시작점 구 반경

/** 화살표 시각 길이 = BASE + ||F|| / SCALE */
const ARROW_BASE_LEN  = 40;
const ARROW_FORCE_SCALE = 8;  // 100N → +12.5 씬단위

export class ForceArrowHandle {
  private scene: THREE.Scene;
  private camera: THREE.Camera;

  private arrowHelper: THREE.ArrowHelper;
  /** 시작점 마커 구 (화살표 꼬리, 드래그 기준점 시각화) */
  private tailMesh: THREE.Mesh;
  /** 씬에 추가되는 그룹 (화살표 + 꼬리) */
  private group: THREE.Group;

  private _visible = false;

  constructor(
    scene: THREE.Scene,
    camera: THREE.Camera,
    _renderer: THREE.WebGLRenderer,  // 확장성 대비 (현재 미사용)
  ) {
    this.scene  = scene;
    this.camera = camera;

    // ── 화살표 초기화 (원점 기준 로컬 좌표) ──
    const initDir = new THREE.Vector3(0, -1, 0);
    const initLen = ARROW_BASE_LEN + 100 / ARROW_FORCE_SCALE;
    this.arrowHelper = new THREE.ArrowHelper(
      initDir,
      new THREE.Vector3(0, 0, 0),  // 그룹 로컬 원점
      initLen,
      ARROW_COLOR,
      10, 6,
    );

    // ── 꼬리 마커 (시작점 구) ──
    const tailGeo = new THREE.SphereGeometry(TAIL_RADIUS, 16, 16);
    const tailMat = new THREE.MeshPhongMaterial({
      color: TAIL_COLOR,
      shininess: 80,
      transparent: true,
      opacity: 0.85,
    });
    this.tailMesh = new THREE.Mesh(tailGeo, tailMat);
    this.tailMesh.name = '__forceArrowTail__';
    // 주의: tailMesh는 raycaster 히트 대상이 아님 (드래그는 뷰포트 전체에서 시작)
    this.tailMesh.userData.isForceHandle = false;

    // ── 그룹으로 묶어 씬에 추가 ──
    this.group = new THREE.Group();
    this.group.name = '__forceArrow__';
    this.group.add(this.arrowHelper);
    this.group.add(this.tailMesh);
    this.group.visible = false;

    scene.add(this.group);

    // 초기 forceVector로 동기화
    this._syncFromForceVector();
  }

  // ── 가시성 ──

  /**
   * 화살표 표시/숨김.
   * 표시 시 현재 forceVector를 즉시 반영한다.
   */
  setVisible(visible: boolean): void {
    this._visible = visible;
    this.group.visible = visible;
    if (visible) this._syncFromForceVector();
  }

  get isVisible(): boolean { return this._visible; }

  // ── 동기화 ──

  /**
   * toolsState.forceVector → 화살표 방향/길이 동기화.
   * 패널에서 값이 변경될 때 호출한다.
   */
  syncFromForceVector(): void {
    if (this._visible) this._syncFromForceVector();
  }

  private _syncFromForceVector(): void {
    const [fx, fy, fz] = toolsState.forceVector;
    const vec = new THREE.Vector3(fx, fy, fz);
    const mag = vec.length();
    if (mag < 0.001) return;

    const dir = vec.clone().normalize();
    const arrowLen = ARROW_BASE_LEN + mag / ARROW_FORCE_SCALE;

    this.arrowHelper.setDirection(dir);
    this.arrowHelper.setLength(arrowLen, 10, 6);
    // 꼬리 마커는 로컬 원점(0,0,0)에 고정 — 이동 불필요
  }

  // ── 위치/스케일 설정 ──

  /**
   * 화살표 그룹 기준점 설정 (월드 좌표).
   * 모델 bbox 상단으로 이동시켜 척추 위에 화살표가 표시되도록 한다.
   */
  setOrigin(pos: THREE.Vector3): void {
    this.group.position.copy(pos);
  }

  /**
   * 현재 그룹 기준점 반환 (월드 좌표).
   * Canvas3D에서 드래그 평면 원점으로 사용한다.
   */
  getOrigin(): THREE.Vector3 {
    return this.group.position.clone();
  }

  /**
   * 화살표 + 꼬리 크기 비례 스케일.
   * bbox 높이에 맞춰 척추 모델 크기에 관계없이 화살표가 잘 보이도록 조정한다.
   */
  setScale(scale: number): void {
    this.group.scale.setScalar(scale);
  }

  // ── 일러스트 스타일 드래그 업데이트 ──

  /**
   * 드래그 중 마우스 NDC 좌표로 forceVector 업데이트.
   *
   * 일러스트 스타일: 클릭한 지점(dragPlaneOrigin)에서 현재 커서 방향으로 화살표가 그려진다.
   * dragPlaneOrigin → hitPoint 벡터가 힘 방향, 거리가 크기에 비례.
   *
   * 드래그 평면: 화살표 기준점을 지나며 카메라 정면에 수직인 평면.
   *
   * @param ndcCurrent       현재 마우스 NDC 좌표 (-1~1)
   * @param dragPlaneNormal  드래그 평면 법선 (카메라 -Z 방향)
   * @param dragPlaneOrigin  드래그 평면이 지나는 점 (화살표 기준점 월드 좌표)
   * @param initialMagnitude 드래그 시작 시점의 ||forceVector|| — 방향 변경 후에도 이 크기를 유지
   */
  updateFromDrag(
    ndcCurrent: THREE.Vector2,
    dragPlaneNormal: THREE.Vector3,
    dragPlaneOrigin: THREE.Vector3,
    initialMagnitude: number,
  ): void {
    // 현재 마우스 레이
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(ndcCurrent, this.camera);

    // 드래그 평면: 기준점을 지나는 카메라 정면 평면
    const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(
      dragPlaneNormal,
      dragPlaneOrigin,
    );

    const hitPoint = new THREE.Vector3();
    if (!raycaster.ray.intersectPlane(plane, hitPoint)) return;

    // 기준점 → 히트점 벡터 = 새 힘 방향
    // (그룹이 이동되어 있으므로 기준점을 빼야 올바른 방향이 나옴)
    const origin = this.group.position;
    const newDir = hitPoint.clone().sub(origin);
    const dist   = newDir.length();
    if (dist < 0.001) return;
    newDir.normalize();

    // 드래그는 방향만 변경 — 힘의 크기(initialMagnitude)는 유지
    // 크기는 패널의 숫자 입력/슬라이더에서 직접 조절한다
    toolsState.forceVector = [
      newDir.x * initialMagnitude,
      newDir.y * initialMagnitude,
      newDir.z * initialMagnitude,
    ];

    // 화살표 즉시 갱신
    this._syncFromForceVector();
  }

  // ── 정리 ──

  dispose(): void {
    this.scene.remove(this.group);
    this.tailMesh.geometry.dispose();
    (this.tailMesh.material as THREE.Material).dispose();
  }
}
