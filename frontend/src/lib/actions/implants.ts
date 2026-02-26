/**
 * 가이드라인 액션 (Pedicle Guideline)
 *
 * - 백엔드 WebSocket으로 가이드라인 메쉬 생성 요청
 * - 수신된 메쉬를 Three.js로 렌더링
 *
 * NOTE: 임플란트 배치는 ImplantManager + implantCatalog.ts 로 이전됨.
 *       requestScrew / requestCage 는 제거. 가이드라인만 유지.
 */

import * as THREE from 'three';
import { wsState } from '$lib/stores/websocket.svelte';
import type { GuidelineMeshResult, MeshData } from '$lib/ws/types';

// ── 가이드라인 씬 그룹 ──

/** 가이드라인 시각화 그룹 (삽입경로·안전영역·깊이마커) */
export const guidelineGroup = new THREE.Group();
guidelineGroup.name = 'guidelines';

let _initialized = false;

// ── 카운터 ──

/** 현재 씬에 표시된 가이드라인 오브젝트 수 */
export function getGuidelineCount(): number {
  return guidelineGroup.children.length;
}

// ── 초기화 ──

/**
 * 가이드라인 레이어 초기화.
 *
 * Canvas3D onMount 에서 호출. guidelineGroup 을 씬에 추가하고
 * WebSocket 클라이언트 콜백을 등록한다.
 *
 * @param scene Three.js 씬
 */
export function initGuidelineLayer(scene: THREE.Scene): void {
  if (_initialized) return;

  scene.add(guidelineGroup);

  // wsState.client 가 아직 없으면 콜백 지연 등록 (initAnalysis 이후 호출 보장)
  const client = wsState.client;
  if (client) {
    client.onGuidelineMeshResult((data: GuidelineMeshResult) => _renderGuidelines(data));
  }

  _initialized = true;
}

// ── 가이드라인 요청 ──

/**
 * 척추경 가이드라인 메쉬 요청.
 *
 * @param vertebraPos  척추 중심 좌표 [x, y, z] (mm)
 * @param vertebraName 척추 이름 (예: "L4")
 * @param opts         추가 파라미터 (내측각·삽입깊이 등)
 */
export function requestGuidelines(
  vertebraPos: [number, number, number],
  vertebraName: string = 'L4',
  opts?: {
    pedicle_offset?: number;
    medial_angle?: number;
    caudal_angle?: number;
    depth?: number;
    show_trajectory?: boolean;
    show_safe_zone?: boolean;
    show_depth_marker?: boolean;
  },
): void {
  wsState.client?.send('get_guideline_meshes', {
    vertebra_position: vertebraPos,
    vertebra_name: vertebraName,
    pedicle_offset: opts?.pedicle_offset ?? 15,
    medial_angle: opts?.medial_angle ?? 10,
    caudal_angle: opts?.caudal_angle ?? 0,
    depth: opts?.depth ?? 45,
    show_trajectory: opts?.show_trajectory ?? true,
    show_safe_zone: opts?.show_safe_zone ?? true,
    show_depth_marker: opts?.show_depth_marker ?? true,
  });
}

// ── 씬 정리 ──

/** 가이드라인 그룹 내 모든 오브젝트 제거 */
export function clearGuidelines(): void {
  _disposeGroup(guidelineGroup);
}

// ── 내부 헬퍼 ──

/**
 * MeshData → THREE.Mesh 변환 (가이드라인 반투명 렌더링용).
 */
function _meshDataToMesh(data: MeshData, transparent = false): THREE.Mesh {
  const geom = new THREE.BufferGeometry();

  // 정점 좌표
  const verts = new Float32Array(data.vertices.length * 3);
  for (let i = 0; i < data.vertices.length; i++) {
    verts[i * 3]     = data.vertices[i][0];
    verts[i * 3 + 1] = data.vertices[i][1];
    verts[i * 3 + 2] = data.vertices[i][2];
  }
  geom.setAttribute('position', new THREE.BufferAttribute(verts, 3));

  // 면 인덱스
  const inds = new Uint32Array(data.faces.length * 3);
  for (let i = 0; i < data.faces.length; i++) {
    inds[i * 3]     = data.faces[i][0];
    inds[i * 3 + 1] = data.faces[i][1];
    inds[i * 3 + 2] = data.faces[i][2];
  }
  geom.setIndex(new THREE.BufferAttribute(inds, 1));
  geom.computeVertexNormals();

  const mat = new THREE.MeshPhongMaterial({
    color: new THREE.Color(data.color[0], data.color[1], data.color[2]),
    specular: new THREE.Color(0.4, 0.4, 0.4),
    shininess: 60,
    transparent,
    opacity: transparent ? 0.65 : 1.0,
    side: THREE.DoubleSide,
  });

  const mesh = new THREE.Mesh(geom, mat);
  mesh.name = data.name;
  mesh.castShadow = true;
  return mesh;
}

/** 가이드라인 메쉬 수신 → 기존 가이드라인 교체 */
function _renderGuidelines(data: GuidelineMeshResult): void {
  _disposeGroup(guidelineGroup);
  for (const meshData of data.meshes) {
    const obj = _meshDataToMesh(meshData, true);
    guidelineGroup.add(obj);
  }
}

/** 그룹 내 모든 Mesh 지오메트리·재질 해제 후 제거 */
function _disposeGroup(group: THREE.Group): void {
  while (group.children.length > 0) {
    const child = group.children[0];
    if (child instanceof THREE.Mesh) {
      child.geometry.dispose();
      if (Array.isArray(child.material)) {
        child.material.forEach((m: THREE.Material) => m.dispose());
      } else {
        child.material.dispose();
      }
    }
    group.remove(child);
  }
}
