/**
 * Three.js 씬 상태 관리 (Svelte 5 runes).
 *
 * SceneManager 인스턴스와 로드된 메쉬 목록을 관리한다.
 */

import type { SceneManager } from '$lib/three/SceneManager';
import type * as THREE from 'three';

/** 모델 정보 */
export interface ModelInfo {
  name: string;
  mesh: THREE.Mesh;
  visible: boolean;
  vertexCount: number;
  faceCount: number;
}

/** 씬 상태 */
class SceneState {
  manager = $state<SceneManager | null>(null);
  models = $state<ModelInfo[]>([]);
  fps = $state(0);

  /** 모델 추가 */
  addModel(name: string, mesh: THREE.Mesh) {
    const geo = mesh.geometry;
    this.models.push({
      name,
      mesh,
      visible: true,
      vertexCount: geo.attributes.position?.count ?? 0,
      faceCount: geo.index ? geo.index.count / 3 : (geo.attributes.position?.count ?? 0) / 3,
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
}

export const sceneState = new SceneState();
