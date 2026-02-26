/**
 * Three.js 씬 상태 관리 (Svelte 5 runes).
 *
 * SceneManager 인스턴스와 로드된 메쉬 목록을 관리한다.
 */

import type { SceneManager } from '$lib/three/SceneManager';
import type { ImplantManager } from '$lib/three/ImplantManager.svelte';
import type { ForceArrowHandle } from '$lib/three/ForceArrowHandle';
import type * as THREE from 'three';

/** 모델 정보 */
export interface ModelInfo {
  name: string;
  mesh: THREE.Mesh;
  visible: boolean;
  vertexCount: number;
  faceCount: number;
  /** per-model 불투명도 (0~1) */
  opacity: number;
  /** 재료 타입 ("bone" | "disc" | "soft_tissue" | "implant" | "") */
  materialType: string;
  /** 16진 색상 ("#e6d5c3") */
  color: string;
}

/** addModel 옵션 */
export interface AddModelOptions {
  materialType?: string;
  color?: string;
}

/** 씬 상태 */
class SceneState {
  manager = $state<SceneManager | null>(null);
  models = $state<ModelInfo[]>([]);
  fps = $state(0);

  /** ImplantManager 인스턴스 (Canvas3D onMount 시 생성) */
  implantManager = $state<ImplantManager | null>(null);

  /** ForceArrowHandle 인스턴스 (Canvas3D onMount 시 생성) */
  forceArrowHandle = $state<ForceArrowHandle | null>(null);

  /** 모델 추가 */
  addModel(name: string, mesh: THREE.Mesh, opts?: AddModelOptions) {
    const geo = mesh.geometry;
    // 메쉬 머티리얼에서 현재 색상 추출
    const mat = mesh.material as THREE.MeshStandardMaterial;
    const hexColor = opts?.color ?? `#${mat.color?.getHexString() ?? 'cccccc'}`;
    this.models.push({
      name,
      mesh,
      visible: true,
      vertexCount: geo.attributes.position?.count ?? 0,
      faceCount: geo.index ? geo.index.count / 3 : (geo.attributes.position?.count ?? 0) / 3,
      opacity: 1.0,
      materialType: opts?.materialType ?? '',
      color: hexColor,
    });
  }

  /** 모델 제거 */
  removeModel(name: string) {
    const idx = this.models.findIndex((m) => m.name === name);
    if (idx >= 0) {
      const model = this.models[idx];
      model.mesh.geometry.dispose();
      if (Array.isArray(model.mesh.material)) {
        model.mesh.material.forEach((m) => m.dispose());
      } else {
        model.mesh.material.dispose();
      }
      this.manager?.scene.remove(model.mesh);
      this.models.splice(idx, 1);
    }
  }

  /** 전체 모델 제거 */
  clearAll() {
    const names = this.models.map((m) => m.name);
    names.forEach((n) => this.removeModel(n));
  }

  /** 모델 가시성 토글 */
  toggleVisibility(name: string) {
    const model = this.models.find((m) => m.name === name);
    if (model) {
      model.visible = !model.visible;
      model.mesh.visible = model.visible;
    }
  }

  /** per-model 불투명도 설정 */
  setOpacity(name: string, value: number) {
    const model = this.models.find((m) => m.name === name);
    if (model) {
      model.opacity = Math.max(0, Math.min(1, value));
      const mat = model.mesh.material as THREE.MeshStandardMaterial;
      mat.transparent = model.opacity < 1.0;
      mat.opacity = model.opacity;
      mat.depthWrite = model.opacity >= 0.99;
      mat.needsUpdate = true;
    }
  }

  /** per-model 색상 설정 */
  setColor(name: string, hex: string) {
    const model = this.models.find((m) => m.name === name);
    if (model) {
      model.color = hex;
      const mat = model.mesh.material as THREE.MeshStandardMaterial;
      mat.color.set(hex);
      mat.needsUpdate = true;
    }
  }

  /** 카테고리별 일괄 가시성 설정 */
  setCategoryVisibility(category: string, visible: boolean) {
    for (const model of this.models) {
      if (model.materialType === category) {
        model.visible = visible;
        model.mesh.visible = visible;
      }
    }
  }
}

export const sceneState = new SceneState();
