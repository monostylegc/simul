/**
 * SceneManager - Three.js 씬, 카메라, 렌더러, 컨트롤을 관리하는 클래스.
 *
 * 기존 main.js의 init(), setupLights(), animate() 로직을 캡슐화한다.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

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
          geometry.computeBoundingBox();

          // 원본 좌표 유지 (중심화하지 않음)

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

  /** 카메라를 메쉬에 포커스 */
  focusOnMesh(mesh: THREE.Mesh) {
    const box = new THREE.Box3().setFromObject(mesh);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);

    this.controls.target.copy(center);
    this.camera.position.set(
      center.x + maxDim * 1.5,
      center.y + maxDim * 1.5,
      center.z + maxDim * 1.5,
    );
    this.controls.update();
  }

  /** 리소스 해제 */
  dispose() {
    this.stop();
    window.removeEventListener('resize', this.handleResize);
    this.controls.dispose();
    this.renderer.dispose();

    // DOM에서 캔버스 제거
    if (this.renderer.domElement.parentElement) {
      this.renderer.domElement.parentElement.removeChild(this.renderer.domElement);
    }
  }
}
