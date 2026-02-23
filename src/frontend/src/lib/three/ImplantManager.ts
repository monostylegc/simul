/**
 * 임플란트 매니저 (ImplantManager)
 * — 외부 STL 임플란트 로드, TransformControls 기반 배치, 수술 계획 JSON 관리
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
}

export interface ImplantTransform {
  position: [number, number, number];
  rotation: [number, number, number];
  scale: [number, number, number];
}

export interface SurgicalPlan {
  implants: Array<{
    name: string;
    stl_path: string;
    position: [number, number, number];
    rotation: [number, number, number];
    scale: [number, number, number];
    material: string;
  }>;
  bone_modifications: Record<string, unknown>;
}

// ── 재료별 색상 ──

const MATERIAL_COLORS: Record<string, number> = {
  titanium: 0x8899aa,
  peek: 0xccbb88,
  cobalt_chrome: 0x99aacc,
  stainless_steel: 0xaaaaaa,
};

export class ImplantManager {
  private scene: THREE.Scene;
  private camera: THREE.Camera;
  private renderer: THREE.WebGLRenderer;
  private orbitControls: OrbitControls | null;

  // 임플란트 목록
  implants: Record<string, ImplantEntry> = {};

  // TransformControls
  transformControls: TransformControls | null = null;
  selectedImplant: string | null = null;
  private _transformMode: 'translate' | 'rotate' | 'scale' = 'translate';

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

  /**
   * TransformControls 초기화
   */
  private _initTransformControls(): void {
    this.transformControls = new TransformControls(this.camera, this.renderer.domElement);
    this.transformControls.setSize(0.8);
    this.scene.add(this.transformControls as unknown as THREE.Object3D);

    // TransformControls 드래그 중 OrbitControls 비활성화
    this.transformControls.addEventListener('dragging-changed', (event) => {
      if (this.orbitControls) {
        this.orbitControls.enabled = !event.value;
      }
    });
  }

  /**
   * 외부 STL 파일 로드
   */
  async loadImplantSTL(
    file: File,
    name?: string,
    materialType = 'titanium',
  ): Promise<string> {
    if (!name) {
      name = file.name.replace(/\.[^/.]+$/, '');
    }

    // 중복 이름 처리
    if (this.implants[name]) {
      let i = 2;
      while (this.implants[`${name}_${i}`]) i++;
      name = `${name}_${i}`;
    }

    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const geometry = this.stlLoader.parse(e.target!.result as ArrayBuffer);
          geometry.computeVertexNormals();
          geometry.computeBoundingBox();

          // 임플란트 색상 (재료별)
          const color = MATERIAL_COLORS[materialType] ?? 0x8899aa;
          const material = new THREE.MeshPhongMaterial({
            color,
            flatShading: false,
            side: THREE.DoubleSide,
            shininess: 60,
            transparent: true,
            opacity: 0.85,
          });

          const mesh = new THREE.Mesh(geometry, material);
          mesh.name = 'implant_' + name;
          mesh.userData.isImplant = true;
          mesh.userData.implantName = name;
          mesh.userData.materialType = materialType;
          mesh.castShadow = true;

          // 씬의 중심에 배치
          const box = new THREE.Box3();
          this.scene.traverse(obj => {
            if ((obj as THREE.Mesh).isMesh && !obj.userData.isImplant) {
              box.expandByObject(obj);
            }
          });
          if (!box.isEmpty()) {
            const center = box.getCenter(new THREE.Vector3());
            mesh.position.copy(center);
          }

          this.scene.add(mesh);
          this.implants[name!] = {
            mesh,
            stlPath: file.name,
            material: materialType,
          };

          console.log(`임플란트 로드: ${name} (${materialType})`);
          resolve(name!);
        } catch (err) {
          reject(err);
        }
      };
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(file);
    });
  }

  /**
   * 임플란트 선택 (TransformControls 바인딩)
   */
  selectImplant(name: string): void {
    if (!this.implants[name]) {
      console.warn(`임플란트 없음: ${name}`);
      return;
    }

    this.selectedImplant = name;
    const mesh = this.implants[name].mesh;

    if (this.transformControls) {
      this.transformControls.attach(mesh);
    }
  }

  /**
   * 선택 해제
   */
  deselectImplant(): void {
    this.selectedImplant = null;
    if (this.transformControls) {
      this.transformControls.detach();
    }
  }

  /**
   * TransformControls 모드 설정
   */
  setTransformMode(mode: 'translate' | 'rotate' | 'scale'): void {
    this._transformMode = mode;
    if (this.transformControls) {
      this.transformControls.setMode(mode);
    }
  }

  /**
   * 임플란트 변환 정보 반환
   */
  getImplantTransform(name: string): ImplantTransform | null {
    const entry = this.implants[name];
    if (!entry) return null;

    const mesh = entry.mesh;
    return {
      position: [mesh.position.x, mesh.position.y, mesh.position.z],
      rotation: [mesh.rotation.x, mesh.rotation.y, mesh.rotation.z],
      scale: [mesh.scale.x, mesh.scale.y, mesh.scale.z],
    };
  }

  /**
   * 임플란트 제거
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
    console.log(`임플란트 제거: ${name}`);
  }

  /**
   * 모든 임플란트 이름 목록
   */
  getImplantNames(): string[] {
    return Object.keys(this.implants);
  }

  /**
   * 수술 계획 JSON 내보내기
   */
  exportPlan(): SurgicalPlan {
    const implants: SurgicalPlan['implants'] = [];
    for (const [name, entry] of Object.entries(this.implants)) {
      const transform = this.getImplantTransform(name)!;
      implants.push({
        name,
        stl_path: entry.stlPath,
        position: transform.position,
        rotation: transform.rotation,
        scale: transform.scale,
        material: entry.material,
      });
    }

    return {
      implants,
      bone_modifications: {},
    };
  }

  /**
   * 수술 계획 JSON에서 복원
   */
  importPlan(planData: SurgicalPlan): void {
    if (!planData?.implants) return;

    for (const impl of planData.implants) {
      const entry = this.implants[impl.name];
      if (!entry) continue;

      const mesh = entry.mesh;
      if (impl.position) mesh.position.set(...impl.position);
      if (impl.rotation) mesh.rotation.set(...impl.rotation);
      if (impl.scale) mesh.scale.set(...impl.scale);
      if (impl.material) entry.material = impl.material;
    }
  }

  /**
   * OrbitControls 참조 업데이트
   */
  setOrbitControls(controls: OrbitControls): void {
    this.orbitControls = controls;
  }

  /**
   * 정리
   */
  dispose(): void {
    this.deselectImplant();
    for (const name of Object.keys(this.implants)) {
      this.removeImplant(name);
    }
    if (this.transformControls) {
      this.scene.remove(this.transformControls as unknown as THREE.Object3D);
      this.transformControls.dispose();
      this.transformControls = null;
    }
  }
}
