/**
 * SceneManager - Three.js 씬, 카메라, 렌더러, 컨트롤을 관리하는 클래스.
 *
 * 기존 main.js의 init(), setupLights(), animate() 로직을 캡슐화한다.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

/**
 * STL geometry 자동 오리엔테이션 — CT 스캐너 Z(상하) → Three.js Y(상하) 변환.
 *
 * 의료 CT STL 좌표계:
 *   - X: 좌우 (transverse, ~90mm) ← 최장축이지만 상하 방향 아님
 *   - Y: 전후 (anterior-posterior, ~86mm)
 *   - Z: 상하 (superior-inferior, ~50mm) ← CT 스캐너 축 = 실제 상하 방향
 *
 * Three.js Y=up 이므로, CT Z(상하)를 Y로 변환.
 * makeRotationX(-90°): (x, y, z) → (x, z, -y)
 *   - 원래 Z(상하) → 새 Y(Three.js 수직) ✓
 *   - 원래 Y(전후) → 새 -Z(Three.js 깊이)
 *
 * ⚠️ 최장축 탐지를 사용하지 않는 이유:
 *    요추 개별 STL은 X(좌우 ~90mm) > Y(전후 ~86mm) > Z(상하 ~50mm).
 *    최장축(X)으로 정렬하면 좌우 폭이 수직이 되어 방향이 틀어진다.
 *    CT STL은 항상 Z = 스캐너 상하 방향이므로 무조건 Z→Y 변환한다.
 *
 * ⚠️ 여러 STL 동시 로드 시 각 geometry에 동일 회전 → 상대 위치 보존.
 *    (L4 Z center=-1134 > L5 Z center=-1167 → 회전 후 L4 Y > L5 Y, L4가 위)
 */
export function autoOrientGeometry(geometry: THREE.BufferGeometry): void {
  // CT Z(superior-inferior) → Three.js Y(상하) 변환
  // 변환: (x, y, z) → (x, z, -y)  — Z가 새 Y축(수직), Y가 새 -Z(깊이)
  geometry.applyMatrix4(new THREE.Matrix4().makeRotationX(-Math.PI / 2));
}

export class SceneManager {
  /* Three.js 핵심 객체 */
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  controls: OrbitControls;
  raycaster: THREE.Raycaster;
  mouse: THREE.Vector2;

  /* 헬퍼 */
  gridHelper: THREE.GridHelper;
  axesHelper: THREE.AxesHelper;

  /* 조명 */
  ambientLight: THREE.AmbientLight;
  dirLight: THREE.DirectionalLight;

  /* 내부 상태 */
  private container: HTMLElement;
  private animationId: number = 0;
  private stlLoader: STLLoader;

  /* FPS 추적 */
  private frameCount = 0;
  private lastTime = performance.now();
  fps = 0;

  /* 콜백 */
  onBeforeRender: (() => void) | null = null;

  constructor(container: HTMLElement) {
    this.container = container;

    const width = container.clientWidth;
    const height = container.clientHeight;

    // 씬
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xe8e8e8);

    // 카메라
    this.camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 2000);
    this.camera.position.set(150, 150, 150);
    this.camera.lookAt(0, 0, 0);

    // 렌더러
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.shadowMap.enabled = true;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(this.renderer.domElement);

    // 컨트롤 (CAD 스타일: 우클릭=회전, 중클릭=팬)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;
    this.controls.mouseButtons = {
      MIDDLE: THREE.MOUSE.PAN,
      RIGHT: THREE.MOUSE.ROTATE,
    };

    // 레이캐스터
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();

    // 조명
    this.ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    this.scene.add(this.ambientLight);

    this.dirLight = new THREE.DirectionalLight(0xffffff, 0.7);
    this.dirLight.position.set(100, 200, 100);
    this.dirLight.castShadow = true;
    this.scene.add(this.dirLight);

    const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
    fillLight.position.set(-100, 50, -100);
    this.scene.add(fillLight);

    // 그리드 + 축
    this.gridHelper = new THREE.GridHelper(300, 30, 0xbbbbbb, 0xcccccc);
    this.scene.add(this.gridHelper);

    this.axesHelper = new THREE.AxesHelper(50);
    this.scene.add(this.axesHelper);

    // STL 로더
    this.stlLoader = new STLLoader();

    // 리사이즈 핸들러
    window.addEventListener('resize', this.handleResize);
  }

  /** 애니메이션 루프 시작 */
  start() {
    const animate = () => {
      this.animationId = requestAnimationFrame(animate);
      this.controls.update();

      // FPS 계산
      this.frameCount++;
      const now = performance.now();
      if (now - this.lastTime >= 1000) {
        this.fps = this.frameCount;
        this.frameCount = 0;
        this.lastTime = now;
      }

      // 사용자 콜백
      this.onBeforeRender?.();

      this.renderer.render(this.scene, this.camera);
    };
    animate();
  }

  /** 애니메이션 루프 정지 */
  stop() {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = 0;
    }
  }

  /** 리사이즈 처리 */
  private handleResize = () => {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  };

  /** STL 파일 로드 */
  async loadSTL(url: string, name: string, color: number = 0xcccccc): Promise<THREE.Mesh> {
    return new Promise((resolve, reject) => {
      this.stlLoader.load(
        url,
        (geometry) => {
          geometry.computeVertexNormals();
          // 자동 오리엔테이션: 최장축 → Y축(상하) 정렬
          autoOrientGeometry(geometry);

          const material = new THREE.MeshStandardMaterial({
            color,
            roughness: 0.6,
            metalness: 0.1,
            transparent: false,
            opacity: 1.0,
            depthWrite: true,
            side: THREE.DoubleSide,
          });
          const mesh = new THREE.Mesh(geometry, material);
          mesh.name = name;
          mesh.castShadow = true;
          mesh.receiveShadow = true;

          this.scene.add(mesh);
          resolve(mesh);
        },
        undefined,
        reject,
      );
    });
  }

  /** 그리드를 모델 바운딩박스에 맞게 조절 */
  adjustGrid(meshes: THREE.Mesh[]) {
    if (meshes.length === 0) return;

    const box = new THREE.Box3();
    meshes.forEach((m) => box.expandByObject(m));
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const gridSize = Math.ceil(maxDim * 2 / 10) * 10;

    this.scene.remove(this.gridHelper);
    this.gridHelper = new THREE.GridHelper(gridSize, gridSize / 10, 0xbbbbbb, 0xcccccc);
    this.scene.add(this.gridHelper);
  }

  /** 카메라를 메쉬에 포커스 — Y-up 3/4 사선 뷰 */
  focusOnMesh(mesh: THREE.Mesh) {
    const box = new THREE.Box3().setFromObject(mesh);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);

    this.controls.target.copy(center);
    // Y=위(상방) 보장 + 3/4 사선 뷰: 전방-우측-상방에서 바라봄
    // 어떤 모델이든 Y-up 자동 오리엔테이션 후 척추가 똑바로 서서 보이도록
    this.camera.position.set(
      center.x + maxDim * 0.8,
      center.y + maxDim * 0.6,
      center.z + maxDim * 1.8,
    );
    this.camera.up.set(0, 1, 0);
    this.controls.update();
  }

  /** 모든 로드된 메쉬를 기준으로 카메라 포커스 */
  focusOnAllMeshes(meshes: THREE.Mesh[]) {
    if (meshes.length === 0) return;
    const box = new THREE.Box3();
    meshes.forEach(m => box.expandByObject(m));
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);

    this.controls.target.copy(center);
    // Y=위(상방) 보장 + 3/4 사선 뷰
    this.camera.position.set(
      center.x + maxDim * 0.8,
      center.y + maxDim * 0.6,
      center.z + maxDim * 1.8,
    );
    this.camera.up.set(0, 1, 0);
    this.controls.update();
  }

  /** 리소스 해제 — 메모리 누수 방지를 위해 모든 Three.js 리소스를 정리 */
  dispose() {
    // 1. 애니메이션 루프 중단
    this.stop();

    // 2. 이벤트 리스너 제거
    window.removeEventListener('resize', this.handleResize);

    // 3. OrbitControls 해제
    this.controls.dispose();

    // 4. 씬 내 모든 오브젝트 geometry/material 정리
    this.scene.traverse((obj) => {
      if (obj instanceof THREE.Mesh || obj instanceof THREE.InstancedMesh) {
        obj.geometry?.dispose();
        if (Array.isArray(obj.material)) {
          obj.material.forEach((m: THREE.Material) => {
            this._disposeMaterial(m);
          });
        } else if (obj.material) {
          this._disposeMaterial(obj.material as THREE.Material);
        }
      }
      if (obj instanceof THREE.Line) {
        obj.geometry?.dispose();
        if (obj.material instanceof THREE.Material) {
          this._disposeMaterial(obj.material);
        }
      }
      if (obj instanceof THREE.Points) {
        obj.geometry?.dispose();
        if (obj.material instanceof THREE.Material) {
          this._disposeMaterial(obj.material);
        }
      }
    });

    // 5. 씬 자식 모두 제거
    while (this.scene.children.length > 0) {
      this.scene.remove(this.scene.children[0]);
    }

    // 6. 렌더러 리소스 해제 + WebGL 컨텍스트 강제 해제
    this.renderer.dispose();
    this.renderer.forceContextLoss();

    // 7. DOM에서 캔버스 제거
    if (this.renderer.domElement.parentElement) {
      this.renderer.domElement.parentElement.removeChild(this.renderer.domElement);
    }

    // 8. 콜백 해제
    this.onBeforeRender = null;
  }

  /** 재료의 텍스처까지 포함한 완전 정리 */
  private _disposeMaterial(mat: THREE.Material): void {
    // MeshStandardMaterial 등의 맵 정리
    const anyMat = mat as Record<string, unknown>;
    const mapKeys = ['map', 'normalMap', 'roughnessMap', 'metalnessMap',
      'aoMap', 'emissiveMap', 'bumpMap', 'displacementMap', 'envMap'];
    for (const key of mapKeys) {
      const tex = anyMat[key] as THREE.Texture | undefined;
      if (tex) tex.dispose();
    }
    mat.dispose();
  }
}
