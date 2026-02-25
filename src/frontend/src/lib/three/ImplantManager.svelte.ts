/**
 * 임플란트 매니저 (ImplantManager)
 *
 * - STL URL 기반 임플란트 로드
 * - 뼈 표면 클릭 위치에 배치 (표면 법선 방향 자동 정렬)
 * - TransformControls 기반 이동/회전 (자유)
 * - 케이지 AABB 충돌 감지 (이동/회전 시 실시간)
 * - 수술 계획 JSON 내보내기/가져오기
 */

import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ── 타입 정의 ──

export interface ImplantEntry {
  mesh: THREE.Mesh;
  stlPath: string;
  material: string;
  category: 'screw' | 'cage' | 'rod';
  /** 원래 색상 (충돌 시각 복원용) */
  originalColor: number;
  /** 케이지 높이 (mm) — 카탈로그 기준, 디스트랙션 계산에 사용 */
  heightMm?: number;
}

/** 케이지 디스트랙션(추간판 공간 교정) 결과 */
export interface DistractionResult {
  /** 교정된 상위 척추 메쉬 */
  superiorMesh: THREE.Mesh;
  /** 상위 척추 이동 거리 (mm) — 양수: 위로 이동 */
  deltaH: number;
  /** 케이지 삽입 전 디스크 공간 높이 (mm) */
  originalGap: number;
  /** 케이지 높이 (mm) */
  cageHeight: number;
}

export interface ImplantTransform {
  position: [number, number, number];
  rotation: [number, number, number];
  scale: [number, number, number];
}

export interface SurgicalPlanData {
  implants: Array<{
    name: string;
    stl_path: string;
    category: string;
    position: [number, number, number];
    rotation: [number, number, number];
    scale: [number, number, number];
    material: string;
  }>;
  bone_modifications: Record<string, unknown>;
}

// ── 재료별 색상 ──

const MATERIAL_COLORS: Record<string, number> = {
  titanium:        0x8899aa,
  peek:            0xccbb88,
  cobalt_chrome:   0x99aacc,
  stainless_steel: 0xaaaaaa,
};

// ── 진입점 마커 / 방향 프리뷰 설정 ──

const ENTRY_MARKER_COLOR  = 0xffcc00;  // 진입점 구 색상 (노랑)
const ENTRY_MARKER_RADIUS = 1.5;       // 진입점 구 반경 (mm)
const PREVIEW_LINE_COLOR  = 0xff4444;  // 방향 프리뷰 라인 색상 (빨강)

export class ImplantManager {
  private scene: THREE.Scene;
  private camera: THREE.Camera;
  private renderer: THREE.WebGLRenderer;
  private orbitControls: OrbitControls | null;

  /** 배치된 임플란트 목록 */
  implants: Record<string, ImplantEntry> = {};

  /**
   * 배치된 임플란트 수 — Svelte $derived 반응성 추적용.
   * add/remove 시마다 갱신.
   */
  implantCount = $state(0);

  /** 현재 선택된 임플란트 이름 */
  selectedImplant = $state<string | null>(null);

  /** 충돌 검사 대상 뼈 메쉬 배열 */
  boneMeshes: THREE.Mesh[] = [];

  // TransformControls
  transformControls: TransformControls | null = null;
  private _transformMode: 'translate' | 'rotate' | 'scale' = 'translate';

  /** objectChange 이벤트 리스너 제거 함수 (재등록 시 정리용) */
  private _objectChangeCleanup: (() => void) | null = null;

  // ── 2클릭 배치: 진입점 마커 + 방향 프리뷰 ──

  /** 진입점 시각 마커 (노란 구) */
  private _entryMarker: THREE.Mesh | null = null;
  /** 방향 프리뷰 라인 (진입점 → 커서) */
  private _previewLine: THREE.Line | null = null;
  /** 프리뷰 라인 지오메트리 (위치 갱신용) */
  private _previewLineGeo: THREE.BufferGeometry | null = null;

  private stlLoader: STLLoader;

  constructor(
    threeScene: THREE.Scene,
    threeCamera: THREE.Camera,
    threeRenderer: THREE.WebGLRenderer,
    orbitControls?: OrbitControls | null,
  ) {
    this.scene = threeScene;
    this.camera = threeCamera;
    this.renderer = threeRenderer;
    this.orbitControls = orbitControls ?? null;
    this.stlLoader = new STLLoader();

    this._initTransformControls();
  }

  // ── 초기화 ──

  /**
   * TransformControls 초기화.
   *
   * Three.js r170+: TransformControls는 더 이상 Object3D를 상속하지 않음.
   * getHelper()로 씬에 추가할 Object3D를 얻는다.
   * 드래그 중 OrbitControls 자동 비활성화.
   */
  private _initTransformControls(): void {
    this.transformControls = new TransformControls(this.camera, this.renderer.domElement);
    this.transformControls.setSize(0.8);

    // r170+: scene.add(tc.getHelper()) 로 씬에 기즈모 추가
    const helper = (this.transformControls as unknown as { getHelper: () => THREE.Object3D }).getHelper?.();
    if (helper) {
      this.scene.add(helper);
    }

    // 드래그 중 OrbitControls 비활성화
    this.transformControls.addEventListener('dragging-changed', (event) => {
      if (this.orbitControls) {
        this.orbitControls.enabled = !event.value;
      }
    });
  }

  // ── STL 로드 ──

  /**
   * URL에서 STL 로드 후 씬에 추가 (배치 전까지 숨김 상태).
   *
   * @param url          public 경로 (예: '/stl/implants/screws/M6x45.stl')
   * @param baseName     이름 접두사 (미지정 시 URL 파일명)
   * @param materialType 재료 타입
   * @param category     임플란트 분류
   */
  async loadImplantFromURL(
    url: string,
    baseName?: string,
    materialType = 'titanium',
    category: 'screw' | 'cage' | 'rod' = 'screw',
    heightMm?: number,
  ): Promise<string> {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`STL fetch 실패: ${url} (${resp.status})`);
    const buffer = await resp.arrayBuffer();

    // 이름 결정
    if (!baseName) {
      baseName = url.split('/').pop()?.replace(/\.[^/.]+$/, '') ?? 'implant';
    }

    // 중복 이름 처리
    let name = baseName;
    if (this.implants[name]) {
      let i = 2;
      while (this.implants[`${name}_${i}`]) i++;
      name = `${name}_${i}`;
    }

    const geometry = this.stlLoader.parse(buffer);
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();

    const colorHex = MATERIAL_COLORS[materialType] ?? 0x8899aa;
    const mat = new THREE.MeshPhongMaterial({
      color: colorHex,
      flatShading: false,
      side: THREE.DoubleSide,
      shininess: 60,
      transparent: true,
      opacity: 0.85,
    });

    const mesh = new THREE.Mesh(geometry, mat);
    mesh.name = 'implant_' + name;
    mesh.userData.isImplant       = true;
    mesh.userData.implantName     = name;
    mesh.userData.materialType    = materialType;
    mesh.userData.implantCategory = category;
    mesh.userData.stlUrl          = url;
    mesh.castShadow = true;
    mesh.visible    = false; // 배치 전까지 숨김

    this.scene.add(mesh);
    this.implants[name] = { mesh, stlPath: url, material: materialType, category, originalColor: colorHex, heightMm };
    this.implantCount++;

    return name;
  }

  /**
   * 외부 File 객체로 STL 로드.
   */
  async loadImplantFromFile(
    file: File,
    materialType = 'titanium',
    category: 'screw' | 'cage' | 'rod' = 'screw',
  ): Promise<string> {
    const buffer = await file.arrayBuffer();
    const baseName = file.name.replace(/\.[^/.]+$/, '');

    let name = baseName;
    if (this.implants[name]) {
      let i = 2;
      while (this.implants[`${name}_${i}`]) i++;
      name = `${name}_${i}`;
    }

    const geometry = this.stlLoader.parse(buffer);
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();

    const colorHex = MATERIAL_COLORS[materialType] ?? 0x8899aa;
    const mat = new THREE.MeshPhongMaterial({
      color: colorHex,
      flatShading: false,
      side: THREE.DoubleSide,
      shininess: 60,
      transparent: true,
      opacity: 0.85,
    });

    const mesh = new THREE.Mesh(geometry, mat);
    mesh.name = 'implant_' + name;
    mesh.userData.isImplant       = true;
    mesh.userData.implantName     = name;
    mesh.userData.materialType    = materialType;
    mesh.userData.implantCategory = category;
    mesh.userData.stlUrl          = file.name;
    mesh.castShadow = true;

    // 씬 중심에 초기 배치
    const box = new THREE.Box3();
    this.scene.traverse(obj => {
      if ((obj as THREE.Mesh).isMesh && !obj.userData.isImplant) {
        box.expandByObject(obj);
      }
    });
    if (!box.isEmpty()) {
      mesh.position.copy(box.getCenter(new THREE.Vector3()));
    }

    this.scene.add(mesh);
    this.implants[name] = { mesh, stlPath: file.name, material: materialType, category, originalColor: colorHex };
    this.implantCount++;

    return name;
  }

  // ── 배치 ──

  /**
   * 임플란트를 뼈 표면 위치에 배치.
   *
   * - 위치: 레이캐스터 교차점
   * - 방향: 표면 법선 벡터 방향으로 임플란트 +Y 축 정렬
   * - 배치 후 TransformControls 자동 연결
   *
   * @param name     임플란트 식별자
   * @param position 배치 위치 (월드 좌표)
   * @param normal   표면 법선 벡터 (월드 좌표)
   */
  placeImplantAtSurface(
    name: string,
    position: THREE.Vector3,
    normal: THREE.Vector3,
  ): void {
    const entry = this.implants[name];
    if (!entry) return;

    const mesh = entry.mesh;
    mesh.position.copy(position);

    // 임플란트 +Y 축을 표면 법선 방향으로 회전
    const up = new THREE.Vector3(0, 1, 0);
    const n = normal.clone().normalize();
    if (Math.abs(n.dot(up)) < 0.999) {
      const quat = new THREE.Quaternion().setFromUnitVectors(up, n);
      mesh.quaternion.copy(quat);
    }

    mesh.visible = true;
    this.selectImplant(name);
  }

  // ── 2클릭 배치: 진입점 마커 + 방향 프리뷰 ──

  /**
   * 진입점 마커 표시 (2클릭 배치 1단계).
   *
   * 뼈 표면 클릭 위치에 노란 구를 표시한다.
   * 카메라 회전이 자유로운 상태에서 방향을 확인할 수 있다.
   *
   * @param position 진입점 월드 좌표
   */
  showEntryMarker(position: THREE.Vector3): void {
    this.hideEntryMarker();

    const geo = new THREE.SphereGeometry(ENTRY_MARKER_RADIUS, 16, 16);
    const mat = new THREE.MeshPhongMaterial({
      color: ENTRY_MARKER_COLOR,
      shininess: 80,
      transparent: true,
      opacity: 0.9,
    });
    this._entryMarker = new THREE.Mesh(geo, mat);
    this._entryMarker.position.copy(position);
    this._entryMarker.name = '__entryMarker__';
    this.scene.add(this._entryMarker);

    // 프리뷰 라인 초기화 (진입점 → 진입점, 길이 0)
    const linePositions = new Float32Array(6);  // 2 points × 3 coords
    linePositions[0] = position.x;
    linePositions[1] = position.y;
    linePositions[2] = position.z;
    linePositions[3] = position.x;
    linePositions[4] = position.y;
    linePositions[5] = position.z;

    this._previewLineGeo = new THREE.BufferGeometry();
    this._previewLineGeo.setAttribute('position', new THREE.BufferAttribute(linePositions, 3));

    const lineMat = new THREE.LineBasicMaterial({
      color: PREVIEW_LINE_COLOR,
      linewidth: 2,
      transparent: true,
      opacity: 0.7,
    });
    this._previewLine = new THREE.Line(this._previewLineGeo, lineMat);
    this._previewLine.name = '__previewLine__';
    this._previewLine.frustumCulled = false;
    this.scene.add(this._previewLine);
  }

  /**
   * 방향 프리뷰 라인 업데이트 (마우스 이동 시).
   *
   * 진입점 → 커서 위치까지 빨간 라인을 그려
   * 삽입 방향을 미리 볼 수 있게 한다.
   *
   * @param targetPoint 현재 커서가 가리키는 월드 좌표
   */
  updatePreviewLine(targetPoint: THREE.Vector3): void {
    if (!this._previewLineGeo || !this._entryMarker) return;

    const posAttr = this._previewLineGeo.getAttribute('position') as THREE.BufferAttribute;
    // 끝점만 갱신 (시작점 = 진입점, 이미 설정됨)
    posAttr.setXYZ(1, targetPoint.x, targetPoint.y, targetPoint.z);
    posAttr.needsUpdate = true;
  }

  /**
   * 진입점 마커 + 프리뷰 라인 제거.
   */
  hideEntryMarker(): void {
    if (this._entryMarker) {
      this.scene.remove(this._entryMarker);
      this._entryMarker.geometry.dispose();
      (this._entryMarker.material as THREE.Material).dispose();
      this._entryMarker = null;
    }
    if (this._previewLine) {
      this.scene.remove(this._previewLine);
      this._previewLineGeo?.dispose();
      (this._previewLine.material as THREE.Material).dispose();
      this._previewLine = null;
      this._previewLineGeo = null;
    }
  }

  // ── 선택/해제 ──

  /**
   * 임플란트 선택 → TransformControls 바인딩.
   * 케이지인 경우 이동/회전 시 충돌 감지 이벤트 등록.
   */
  selectImplant(name: string): void {
    if (!this.implants[name]) return;

    // 이전 objectChange 리스너 제거
    if (this._objectChangeCleanup) {
      this._objectChangeCleanup();
      this._objectChangeCleanup = null;
    }

    this.selectedImplant = name;
    const entry = this.implants[name];

    if (this.transformControls) {
      this.transformControls.attach(entry.mesh);
      this.transformControls.setMode(this._transformMode);
    }

    // 케이지인 경우 실시간 충돌 감지 등록
    if (entry.category === 'cage') {
      const handler = () => {
        const colliding = this.checkCageCollision(name);
        this.setCageCollisionVisual(name, colliding);
      };
      this.transformControls?.addEventListener('objectChange', handler);
      this._objectChangeCleanup = () => {
        this.transformControls?.removeEventListener('objectChange', handler);
      };
    }
  }

  /**
   * 임플란트 선택 해제.
   */
  deselectImplant(): void {
    if (this._objectChangeCleanup) {
      this._objectChangeCleanup();
      this._objectChangeCleanup = null;
    }
    this.selectedImplant = null;
    this.transformControls?.detach();
  }

  // ── TransformControls 모드 ──

  /**
   * TransformControls 모드 설정.
   */
  setTransformMode(mode: 'translate' | 'rotate' | 'scale'): void {
    this._transformMode = mode;
    this.transformControls?.setMode(mode);
  }

  // ── 충돌 감지 ──

  /**
   * 케이지 AABB와 뼈 메쉬 AABB 교차 여부 반환.
   * TransformControls objectChange 이벤트마다 호출된다.
   */
  checkCageCollision(cageName: string): boolean {
    const entry = this.implants[cageName];
    if (!entry || entry.category !== 'cage') return false;
    if (this.boneMeshes.length === 0) return false;

    const cageBox = new THREE.Box3().setFromObject(entry.mesh);
    for (const bone of this.boneMeshes) {
      if (!bone.visible) continue;
      const boneBox = new THREE.Box3().setFromObject(bone);
      if (cageBox.intersectsBox(boneBox)) return true;
    }
    return false;
  }

  /**
   * 케이지 충돌 시각 표시.
   * 충돌 → 빨간색 반투명 / 정상 → 원래 색상 복원.
   */
  setCageCollisionVisual(cageName: string, isColliding: boolean): void {
    const entry = this.implants[cageName];
    if (!entry) return;
    const mat = entry.mesh.material as THREE.MeshPhongMaterial;
    if (isColliding) {
      mat.color.setHex(0xff2222);
      mat.opacity = 0.65;
    } else {
      mat.color.setHex(entry.originalColor);
      mat.opacity = 0.85;
    }
  }

  // ── 케이지 디스트랙션 ──

  /**
   * 케이지 삽입에 의한 추간판 공간 교정 계산.
   *
   * 케이지 Y 중심을 기준으로 상위·하위 척추를 자동 판별하고,
   * 케이지 높이가 현재 디스크 공간보다 클 경우 상위 척추를 위로 이동시킨다.
   *
   * @param cageName 케이지 임플란트 이름
   * @returns 교정 결과, 또는 조건 미충족 시 null
   */
  applyDistraction(cageName: string): DistractionResult | null {
    const entry = this.implants[cageName];
    if (!entry || entry.category !== 'cage') return null;
    if (this.boneMeshes.length === 0) return null;

    // 케이지 월드 좌표 바운딩 박스
    const cageBox = new THREE.Box3().setFromObject(entry.mesh);
    const cageCenterY = (cageBox.max.y + cageBox.min.y) / 2;
    // 카탈로그 heightMm가 있으면 우선 사용 (기울어진 배치 시 bounding box 오차 방지)
    const cageHeight  = entry.heightMm ?? (cageBox.max.y - cageBox.min.y);

    // 상위/하위 척추 탐색
    let superiorMesh:   THREE.Mesh | null = null;
    let inferiorMesh:   THREE.Mesh | null = null;
    let superiorBottomY = Infinity;
    let inferiorTopY   = -Infinity;

    for (const bone of this.boneMeshes) {
      if (!bone.visible) continue;
      const boneBox    = new THREE.Box3().setFromObject(bone);
      const boneCenterY = (boneBox.max.y + boneBox.min.y) / 2;

      if (boneCenterY > cageCenterY) {
        // 케이지 위에 있는 뼈 → 상위 척추 (하단 Y가 케이지에 가장 가까운 것 선택)
        if (boneBox.min.y < superiorBottomY) {
          superiorBottomY = boneBox.min.y;
          superiorMesh    = bone;
        }
      } else {
        // 케이지 아래에 있는 뼈 → 하위 척추 (상단 Y가 케이지에 가장 가까운 것 선택)
        if (boneBox.max.y > inferiorTopY) {
          inferiorTopY = boneBox.max.y;
          inferiorMesh = bone;
        }
      }
    }

    if (!superiorMesh) return null;

    // 현재 추간판 공간 높이
    const originalGap = inferiorMesh
      ? Math.max(0, superiorBottomY - inferiorTopY)
      : 0;

    // 케이지 높이가 현재 공간보다 클 때만 교정 적용
    const deltaH = cageHeight - originalGap;
    if (deltaH <= 0.5) return null; // 0.5 mm 이하 차이는 무시

    // 상위 척추 위로 이동
    superiorMesh.position.y += deltaH;

    // 케이지도 절반만큼 위로 이동 (디스크 공간 중앙에 위치하도록)
    entry.mesh.position.y += deltaH * 0.5;

    // TransformControls가 이 케이지에 연결돼 있으면 재갱신
    if (this.selectedImplant === cageName && this.transformControls) {
      this.transformControls.attach(entry.mesh);
    }

    return { superiorMesh, deltaH, originalGap, cageHeight };
  }

  /**
   * 케이지 디스트랙션 되돌리기.
   * applyDistraction 결과를 받아 원래 위치로 복구.
   */
  undoDistraction(cageName: string, result: DistractionResult): void {
    const entry = this.implants[cageName];
    if (!entry) return;

    result.superiorMesh.position.y -= result.deltaH;
    entry.mesh.position.y          -= result.deltaH * 0.5;

    if (this.selectedImplant === cageName && this.transformControls) {
      this.transformControls.attach(entry.mesh);
    }
  }

  // ── 임플란트 제거 ──

  /**
   * 임플란트 제거 (씬에서 삭제 + GPU 메모리 해제).
   */
  removeImplant(name: string): void {
    const entry = this.implants[name];
    if (!entry) return;

    if (this.selectedImplant === name) {
      this.deselectImplant();
    }

    this.scene.remove(entry.mesh);
    entry.mesh.geometry.dispose();
    (entry.mesh.material as THREE.Material).dispose();

    delete this.implants[name];
    this.implantCount--;
  }

  /**
   * 모든 임플란트 제거.
   */
  removeAll(): void {
    const names = Object.keys(this.implants);
    names.forEach(n => this.removeImplant(n));
  }

  // ── 정보 조회 ──

  getImplantNames(): string[] {
    return Object.keys(this.implants);
  }

  getImplantTransform(name: string): ImplantTransform | null {
    const entry = this.implants[name];
    if (!entry) return null;
    const m = entry.mesh;
    return {
      position: [m.position.x, m.position.y, m.position.z],
      rotation: [m.rotation.x, m.rotation.y, m.rotation.z],
      scale:    [m.scale.x,    m.scale.y,    m.scale.z],
    };
  }

  // ── 수술 계획 JSON ──

  exportPlan(): SurgicalPlanData {
    const implants: SurgicalPlanData['implants'] = [];
    for (const [name, entry] of Object.entries(this.implants)) {
      const t = this.getImplantTransform(name)!;
      implants.push({
        name,
        stl_path: entry.stlPath,
        category: entry.category,
        position: t.position,
        rotation: t.rotation,
        scale:    t.scale,
        material: entry.material,
      });
    }
    return { implants, bone_modifications: {} };
  }

  importPlan(planData: SurgicalPlanData): void {
    if (!planData?.implants) return;
    for (const impl of planData.implants) {
      const entry = this.implants[impl.name];
      if (!entry) continue;
      const m = entry.mesh;
      if (impl.position) m.position.set(...impl.position);
      if (impl.rotation) m.rotation.set(...impl.rotation);
      if (impl.scale)    m.scale.set(...impl.scale);
      if (impl.material) entry.material = impl.material;
    }
  }

  // ── 기타 ──

  setOrbitControls(controls: OrbitControls): void {
    this.orbitControls = controls;
  }

  dispose(): void {
    this.hideEntryMarker();
    this.removeAll();
    if (this.transformControls) {
      // r170+: getHelper()로 씬에서 제거
      const helper = (this.transformControls as unknown as { getHelper: () => THREE.Object3D }).getHelper?.();
      if (helper) this.scene.remove(helper);
      this.transformControls.dispose();
      this.transformControls = null;
    }
  }
}
