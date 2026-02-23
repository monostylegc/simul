/**
 * 전처리기 (PreProcessor)
 * — 면 선택, 경계조건 설정, 재료 할당, 해석 요청 조립
 */

import * as THREE from 'three';
import type { VoxelGrid } from '$lib/three/VoxelGrid';

// ── 타입 정의 ──

export interface MaterialPreset {
  E: number;
  nu: number;
  density: number;
  label: string;
}

export interface BoundaryCondition {
  type: 'fixed' | 'force';
  indices: Set<number>;
  voxelIndices?: Map<string, Set<number>>;
  values: number[][];
  color: number;
  _visual?: THREE.Object3D;
  _arrowVisual?: THREE.Object3D & {
    line?: THREE.Line;
    cone?: THREE.Mesh;
  };
}

/** FEM 볼륨 메쉬 데이터 (복셀 → HEX8) */
export interface FEMMeshData {
  nodes: number[][];          // (n_nodes, 3) 코너 노드 좌표
  elements: number[][];       // (n_elements, 8) HEX8 연결정보
  voxelToElement: Map<number, number>;  // 복셀 linearIdx → element idx
  cornerToNode: Map<string, number>;    // "ix,iy,iz" → compact node idx
}

/** 재료 영역 (FEM 또는 PD/SPG) */
export interface MaterialRegionRequest {
  name: string;
  method: string;
  E: number;
  nu: number;
  density: number;
  node_indices: number[];
  // FEM 전용: 볼륨 메쉬 데이터
  nodes?: number[][];
  elements?: number[][];
  // 영역별 경계조건
  boundary_conditions?: Array<{
    type: string;
    node_indices: number[];
    values: number[][];
  }>;
}

export interface AnalysisRequest {
  positions: number[][];
  volumes: number[];
  method: string;
  boundary_conditions: Array<{
    type: string;
    node_indices: number[];
    values: number[][];
  }>;
  materials: MaterialRegionRequest[];
  options: Record<string, unknown>;
}

// ── 재료 프리셋 ──

export const MATERIAL_PRESETS: Record<string, MaterialPreset> = {
  bone:     { E: 15e9,  nu: 0.3,  density: 1850, label: 'Bone (15 GPa)' },
  disc:     { E: 10e6,  nu: 0.45, density: 1200, label: 'Disc (10 MPa)' },
  ligament: { E: 50e6,  nu: 0.4,  density: 1100, label: 'Ligament (50 MPa)' },
  titanium: { E: 110e9, nu: 0.34, density: 4500, label: 'Titanium (110 GPa)' },
};

export class PreProcessor {
  private scene: THREE.Scene;
  private meshes: Record<string, THREE.Mesh>;
  private voxelGrids: Record<string, VoxelGrid>;

  // 선택 상태
  selectedFaceIndices: number[] = [];
  selectedNodeIndices: Set<number> = new Set();

  // 경계조건 목록
  boundaryConditions: BoundaryCondition[] = [];

  // 재료 할당 (메쉬명 → 프리셋키)
  materialAssignments: Record<string, string> = {};

  // 브러쉬 선택 (gridName → Set<linearIdx>)
  brushSelection: Map<string, Set<number>> = new Map();

  // 시각화 오브젝트
  private _selectionHighlight: THREE.Mesh | null = null;
  private _bcVisuals: THREE.Object3D[] = [];

  // 설정
  private FACE_NORMAL_THRESHOLD = Math.cos(30 * Math.PI / 180);
  private MAX_HIGHLIGHT = 5000;

  constructor(
    threeScene: THREE.Scene,
    meshesRef: Record<string, THREE.Mesh>,
    voxelGridsRef: Record<string, VoxelGrid>,
  ) {
    this.scene = threeScene;
    this.meshes = meshesRef;
    this.voxelGrids = voxelGridsRef;
  }

  // ====================================================================
  // 면 선택 (Raycasting + BFS 인접 확장)
  // ====================================================================

  /**
   * 클릭한 면 + BFS 인접 면 선택
   */
  selectFace(intersection: THREE.Intersection, additive = false): void {
    if (!intersection || intersection.faceIndex === undefined) return;

    if (!additive) {
      this.clearSelection();
    }

    const mesh = intersection.object as THREE.Mesh;
    const geometry = mesh.geometry as THREE.BufferGeometry;
    const faceIndex = intersection.faceIndex!;

    const posAttr = geometry.attributes.position as THREE.BufferAttribute;
    let normalAttr = geometry.attributes.normal as THREE.BufferAttribute;

    if (!normalAttr) {
      geometry.computeVertexNormals();
      normalAttr = geometry.attributes.normal as THREE.BufferAttribute;
    }

    // 클릭한 면의 법선 계산
    const clickedNormal = this._getFaceNormal(posAttr, faceIndex);

    // BFS로 인접 면 확장
    const selectedFaces = this._bfsFaceSelect(posAttr, normalAttr, faceIndex, clickedNormal);

    // vertex 인덱스 수집
    selectedFaces.forEach(fi => {
      this.selectedFaceIndices.push(fi);
      const i0 = fi * 3;
      this.selectedNodeIndices.add(i0);
      this.selectedNodeIndices.add(i0 + 1);
      this.selectedNodeIndices.add(i0 + 2);
    });

    // 시각화 업데이트
    this._updateSelectionVisual(mesh);

    console.log(`선택: ${selectedFaces.length}개 면, ${this.selectedNodeIndices.size}개 노드`);
  }

  /**
   * 선택 해제
   */
  clearSelection(): void {
    this.selectedFaceIndices = [];
    this.selectedNodeIndices.clear();
    this._clearSelectionVisual();
  }

  // ====================================================================
  // 브러쉬 선택 (복셀 기반)
  // ====================================================================

  /**
   * 구체 브러쉬로 복셀 선택 (누적)
   */
  brushSelectSphere(worldPos: THREE.Vector3, radius: number): void {
    Object.entries(this.voxelGrids).forEach(([name, grid]) => {
      const affected = grid.previewDrill(worldPos, radius);
      if (affected.length === 0) return;

      if (!this.brushSelection.has(name)) {
        this.brushSelection.set(name, new Set());
      }
      const selSet = this.brushSelection.get(name)!;
      const gsx = grid.gridSize!.x;
      const gsy = grid.gridSize!.y;
      affected.forEach((pos: { x: number; y: number; z: number }) => {
        const linearIdx = pos.x + pos.y * gsx + pos.z * gsx * gsy;
        selSet.add(linearIdx);
      });
    });
  }

  /**
   * 브러쉬 선택 초기화
   */
  clearBrushSelection(): void {
    this.brushSelection.clear();
  }

  /**
   * 선택된 총 복셀 수
   */
  getBrushSelectionCount(): number {
    let count = 0;
    this.brushSelection.forEach(s => count += s.size);
    return count;
  }

  /**
   * 선택된 복셀의 월드 좌표 목록 반환 (시각화용)
   */
  getBrushSelectionWorldPositions(): Array<{ x: number; y: number; z: number }> {
    const positions: Array<{ x: number; y: number; z: number }> = [];
    this.brushSelection.forEach((selSet, gridName) => {
      const grid = this.voxelGrids[gridName];
      if (!grid) return;
      const gsx = grid.gridSize!.x;
      const gsy = grid.gridSize!.y;
      selSet.forEach(linearIdx => {
        const x = linearIdx % gsx;
        const y = Math.floor(linearIdx / gsx) % gsy;
        const z = Math.floor(linearIdx / (gsx * gsy));
        const wp = grid.gridToWorld(x, y, z);
        positions.push(wp);
      });
    });
    return positions;
  }

  // ====================================================================
  // 경계조건 관리
  // ====================================================================

  /**
   * 현재 선택된 노드에 고정 BC 추가
   * 브러쉬 선택이 있으면 voxelIndices 기반, 없으면 기존 face 기반
   */
  addFixedBC(): BoundaryCondition | undefined {
    // 브러쉬 선택 우선
    if (this.getBrushSelectionCount() > 0) {
      const voxelIndices = new Map<string, Set<number>>();
      this.brushSelection.forEach((selSet, gridName) => {
        voxelIndices.set(gridName, new Set(selSet));
      });
      const bc: BoundaryCondition = {
        type: 'fixed',
        indices: new Set(),
        voxelIndices,
        values: [[0, 0, 0]],
        color: 0x00cc44,
      };
      this.boundaryConditions.push(bc);
      this._addBCVisual(bc);
      const count = this.getBrushSelectionCount();
      this.clearBrushSelection();
      console.log(`고정 BC 추가 (브러쉬): ${count}개 복셀`);
      return bc;
    }

    if (this.selectedNodeIndices.size === 0) {
      console.warn('선택된 노드가 없습니다');
      return undefined;
    }

    const indices = new Set(this.selectedNodeIndices);
    const bc: BoundaryCondition = {
      type: 'fixed',
      indices,
      values: [[0, 0, 0]],
      color: 0x00cc44,
    };

    this.boundaryConditions.push(bc);
    this._addBCVisual(bc);
    this.clearSelection();

    console.log(`고정 BC 추가: ${indices.size}개 노드`);
    return bc;
  }

  /**
   * 현재 선택된 노드에 하중 BC 추가
   */
  addForceBC(force: number[]): BoundaryCondition | undefined {
    // 브러쉬 선택 우선
    if (this.getBrushSelectionCount() > 0) {
      const voxelIndices = new Map<string, Set<number>>();
      this.brushSelection.forEach((selSet, gridName) => {
        voxelIndices.set(gridName, new Set(selSet));
      });
      const bc: BoundaryCondition = {
        type: 'force',
        indices: new Set(),
        voxelIndices,
        values: [force],
        color: 0xff2222,
      };
      this.boundaryConditions.push(bc);
      this._addBCVisual(bc);
      const count = this.getBrushSelectionCount();
      this.clearBrushSelection();
      console.log(`하중 BC 추가 (브러쉬): ${count}개 복셀, force=[${force}]`);
      return bc;
    }

    if (this.selectedNodeIndices.size === 0) {
      console.warn('선택된 노드가 없습니다');
      return undefined;
    }

    const indices = new Set(this.selectedNodeIndices);
    const bc: BoundaryCondition = {
      type: 'force',
      indices,
      values: [force],
      color: 0xff2222,
    };

    this.boundaryConditions.push(bc);
    this._addBCVisual(bc);
    this.clearSelection();

    console.log(`하중 BC 추가: ${indices.size}개 노드, force=[${force}]`);
    return bc;
  }

  /**
   * 마지막 BC 제거
   */
  removeLastBC(): void {
    if (this.boundaryConditions.length === 0) return;
    const bc = this.boundaryConditions.pop()!;
    this._removeBCVisual(bc);
    console.log('마지막 BC 제거');
  }

  /**
   * 모든 BC 제거
   */
  clearAllBC(): void {
    this._bcVisuals.forEach(v => {
      this.scene.remove(v);
      if ((v as THREE.Mesh).geometry) (v as THREE.Mesh).geometry.dispose();
      if ((v as THREE.Mesh).material) ((v as THREE.Mesh).material as THREE.Material).dispose();
    });
    this._bcVisuals = [];
    this.boundaryConditions = [];
    console.log('모든 BC 제거');
  }

  // ====================================================================
  // 재료 할당
  // ====================================================================

  /**
   * 메쉬에 재료 프리셋 할당
   */
  assignMaterial(meshName: string, presetKey: string): void {
    if (!MATERIAL_PRESETS[presetKey]) {
      console.warn(`알 수 없는 재료 프리셋: ${presetKey}`);
      return;
    }
    this.materialAssignments[meshName] = presetKey;
    console.log(`재료 할당: ${meshName} → ${MATERIAL_PRESETS[presetKey].label}`);
  }

  // ====================================================================
  // FEM 볼륨 메쉬 생성 (복셀 → HEX8)
  // ====================================================================

  /** 캐시된 FEM 메쉬 데이터 (영역별) */
  cachedFEMMeshes: Record<string, FEMMeshData> = {};

  /**
   * 복셀 그리드에서 FEM HEX8 볼륨 메쉬 생성
   *
   * 채워진 복셀 하나 = HEX8 요소 하나
   * 인접 복셀끼리 코너 노드를 공유
   * compact 노드 번호 부여 (사용되는 코너만)
   */
  buildFEMMesh(grid: VoxelGrid): FEMMeshData {
    const gsx = grid.gridSize!.x;
    const gsy = grid.gridSize!.y;
    const gsz = grid.gridSize!.z;
    const cs = grid.cellSize;
    const bmin = grid.bounds!.min;

    // 코너 좌표 → compact 노드 ID 매핑
    const cornerToNode = new Map<string, number>();
    const nodes: number[][] = [];
    let nodeCount = 0;

    /** 코너 노드 가져오기/생성 */
    const getOrCreateNode = (ix: number, iy: number, iz: number): number => {
      const key = `${ix},${iy},${iz}`;
      const existing = cornerToNode.get(key);
      if (existing !== undefined) return existing;
      const nodeId = nodeCount++;
      cornerToNode.set(key, nodeId);
      // 코너 좌표 = bounds.min + (ix * cellSize, iy * cellSize, iz * cellSize)
      nodes.push([
        bmin.x + ix * cs,
        bmin.y + iy * cs,
        bmin.z + iz * cs,
      ]);
      return nodeId;
    };

    const elements: number[][] = [];
    const voxelToElement = new Map<number, number>();

    for (let z = 0; z < gsz; z++) {
      for (let y = 0; y < gsy; y++) {
        for (let x = 0; x < gsx; x++) {
          if (!grid.get(x, y, z)) continue;

          const elemIdx = elements.length;
          const linearIdx = x + y * gsx + z * gsx * gsy;
          voxelToElement.set(linearIdx, elemIdx);

          // HEX8 요소의 8개 코너 노드
          // FEM 표준 순서: 하부면 반시계 → 상부면 반시계
          const n0 = getOrCreateNode(x,     y,     z);     // (-,-,-)
          const n1 = getOrCreateNode(x + 1, y,     z);     // (+,-,-)
          const n2 = getOrCreateNode(x + 1, y + 1, z);     // (+,+,-)
          const n3 = getOrCreateNode(x,     y + 1, z);     // (-,+,-)
          const n4 = getOrCreateNode(x,     y,     z + 1); // (-,-,+)
          const n5 = getOrCreateNode(x + 1, y,     z + 1); // (+,-,+)
          const n6 = getOrCreateNode(x + 1, y + 1, z + 1); // (+,+,+)
          const n7 = getOrCreateNode(x,     y + 1, z + 1); // (-,+,+)

          elements.push([n0, n1, n2, n3, n4, n5, n6, n7]);
        }
      }
    }

    console.log(`FEM 메쉬 생성: ${nodes.length}개 노드, ${elements.length}개 HEX8 요소`);

    return { nodes, elements, voxelToElement, cornerToNode };
  }

  // ====================================================================
  // 입자 데이터 추출 + 해석 요청 조립
  // ====================================================================

  /**
   * 복셀 그리드에서 입자 좌표/체적 추출 (PD/SPG용)
   */
  extractParticleData(): { positions: number[][]; volumes: number[] } {
    const positions: number[][] = [];
    const volumes: number[] = [];

    Object.entries(this.voxelGrids).forEach(([_name, grid]) => {
      const cellVolume = grid.cellSize ** 3;

      for (let z = 0; z < grid.gridSize!.z; z++) {
        for (let y = 0; y < grid.gridSize!.y; y++) {
          for (let x = 0; x < grid.gridSize!.x; x++) {
            if (grid.get(x, y, z)) {
              const world = grid.gridToWorld(x, y, z);
              positions.push([world.x, world.y, world.z]);
              volumes.push(cellVolume);
            }
          }
        }
      }
    });

    return { positions, volumes };
  }

  /**
   * 모델별 솔버 할당 (기본값: 'fem')
   * key: grid 이름, value: 솔버 메서드
   */
  solverAssignments: Record<string, string> = {};

  /**
   * 복셀 BC를 FEM 노드 인덱스로 변환
   * 선택된 복셀의 8개 코너 노드를 모두 포함
   */
  private _mapBCtoFEMNodes(
    bc: BoundaryCondition,
    gridName: string,
    femMesh: FEMMeshData,
  ): { type: string; node_indices: number[]; values: number[][] } | null {
    if (!bc.voxelIndices) return null;

    const selSet = bc.voxelIndices.get(gridName);
    if (!selSet || selSet.size === 0) return null;

    const nodeIndicesSet = new Set<number>();
    selSet.forEach(linearIdx => {
      const elemIdx = femMesh.voxelToElement.get(linearIdx);
      if (elemIdx === undefined) return;
      // HEX8 요소의 8개 코너 노드 추가
      const elem = femMesh.elements[elemIdx];
      elem.forEach(nodeIdx => nodeIndicesSet.add(nodeIdx));
    });

    if (nodeIndicesSet.size === 0) return null;

    return {
      type: bc.type,
      node_indices: [...nodeIndicesSet],
      values: bc.values,
    };
  }

  /**
   * 복셀 BC를 PD/SPG 입자 인덱스로 변환
   */
  private _mapBCtoParticles(
    bc: BoundaryCondition,
    gridName: string,
    voxelToParticle: Map<number, number>,
  ): { type: string; node_indices: number[]; values: number[][] } | null {
    if (!bc.voxelIndices) return null;

    const selSet = bc.voxelIndices.get(gridName);
    if (!selSet || selSet.size === 0) return null;

    const particleIndices: number[] = [];
    selSet.forEach(linearIdx => {
      const pIdx = voxelToParticle.get(linearIdx);
      if (pIdx !== undefined) particleIndices.push(pIdx);
    });

    if (particleIndices.length === 0) return null;

    return {
      type: bc.type,
      node_indices: particleIndices,
      values: bc.values,
    };
  }

  /**
   * AnalysisRequest 조립
   *
   * FEM 영역: 복셀 → HEX8 볼륨 메쉬 (nodes + elements) + 영역별 BC
   * PD/SPG 영역: 복셀 중심 → 입자 좌표 + 영역별 BC
   */
  buildAnalysisRequest(method: string): AnalysisRequest {
    // 전체 PD/SPG 입자 좌표 (positions 배열)
    const positions: number[][] = [];
    const volumes: number[] = [];
    const materials: MaterialRegionRequest[] = [];

    // FEM 메쉬 캐시 초기화
    this.cachedFEMMeshes = {};

    // 영역별 처리
    Object.entries(this.voxelGrids).forEach(([name, grid]) => {
      const presetKey = this.materialAssignments[name] || 'bone';
      const preset = MATERIAL_PRESETS[presetKey];
      const regionMethod = this.solverAssignments[name] || method;

      if (regionMethod === 'fem') {
        // ━━━ FEM 영역: HEX8 볼륨 메쉬 생성 ━━━
        const femMesh = this.buildFEMMesh(grid);
        this.cachedFEMMeshes[name] = femMesh;

        // 영역별 BC 변환 (복셀 → FEM 노드)
        const regionBCs: Array<{ type: string; node_indices: number[]; values: number[][] }> = [];
        for (const bc of this.boundaryConditions) {
          const mapped = this._mapBCtoFEMNodes(bc, name, femMesh);
          if (mapped) regionBCs.push(mapped);
        }

        materials.push({
          name: presetKey,
          method: 'fem',
          E: preset.E,
          nu: preset.nu,
          density: preset.density,
          node_indices: [],  // FEM은 nodes/elements 사용
          nodes: femMesh.nodes,
          elements: femMesh.elements,
          boundary_conditions: regionBCs,
        });
      } else {
        // ━━━ PD/SPG 영역: 입자 좌표 추출 ━━━
        const cellVolume = grid.cellSize ** 3;
        const gsx = grid.gridSize!.x;
        const gsy = grid.gridSize!.y;
        const gsz = grid.gridSize!.z;

        // 복셀 → 입자 인덱스 매핑
        const voxelToParticle = new Map<number, number>();
        const startIdx = positions.length;
        let localCount = 0;

        for (let z = 0; z < gsz; z++) {
          for (let y = 0; y < gsy; y++) {
            for (let x = 0; x < gsx; x++) {
              if (grid.get(x, y, z)) {
                const world = grid.gridToWorld(x, y, z);
                const globalIdx = positions.length;
                positions.push([world.x, world.y, world.z]);
                volumes.push(cellVolume);
                const linearIdx = x + y * gsx + z * gsx * gsy;
                voxelToParticle.set(linearIdx, globalIdx);
                localCount++;
              }
            }
          }
        }

        // 입자 인덱스 범위
        const indices: number[] = [];
        for (let i = startIdx; i < startIdx + localCount; i++) {
          indices.push(i);
        }

        // 영역별 BC 변환 (복셀 → 입자)
        const regionBCs: Array<{ type: string; node_indices: number[]; values: number[][] }> = [];
        for (const bc of this.boundaryConditions) {
          const mapped = this._mapBCtoParticles(bc, name, voxelToParticle);
          if (mapped) regionBCs.push(mapped);
        }

        materials.push({
          name: presetKey,
          method: regionMethod,
          E: preset.E,
          nu: preset.nu,
          density: preset.density,
          node_indices: indices,
          boundary_conditions: regionBCs,
        });
      }
    });

    // 글로벌 BC (face 기반 — 레거시 지원)
    const globalBCs = this.boundaryConditions
      .filter(bc => !bc.voxelIndices)
      .map(bc => ({
        type: bc.type,
        node_indices: Array.from(bc.indices),
        values: bc.values,
      }));

    return {
      positions,
      volumes,
      method,
      boundary_conditions: globalBCs,
      materials,
      options: {},
    };
  }

  // ====================================================================
  // 내부: 면 선택 알고리즘
  // ====================================================================

  private _getFaceNormal(posAttr: THREE.BufferAttribute, faceIndex: number): THREE.Vector3 {
    const i = faceIndex * 3;
    const vA = new THREE.Vector3().fromBufferAttribute(posAttr, i);
    const vB = new THREE.Vector3().fromBufferAttribute(posAttr, i + 1);
    const vC = new THREE.Vector3().fromBufferAttribute(posAttr, i + 2);

    const edge1 = new THREE.Vector3().subVectors(vB, vA);
    const edge2 = new THREE.Vector3().subVectors(vC, vA);
    return new THREE.Vector3().crossVectors(edge1, edge2).normalize();
  }

  private _bfsFaceSelect(
    posAttr: THREE.BufferAttribute,
    _normalAttr: THREE.BufferAttribute,
    startFace: number,
    refNormal: THREE.Vector3,
  ): number[] {
    const totalFaces = posAttr.count / 3;
    const visited = new Set<number>();
    const selected: number[] = [];
    const queue: number[] = [startFace];
    visited.add(startFace);

    const MAX_FACES = 100;

    while (queue.length > 0 && selected.length < MAX_FACES) {
      const fi = queue.shift()!;

      const normal = this._getFaceNormal(posAttr, fi);
      const dot = normal.dot(refNormal);

      if (dot < this.FACE_NORMAL_THRESHOLD) continue;

      selected.push(fi);

      // 인접 면 탐색 (±3 인덱스, 간소화)
      for (let delta = -3; delta <= 3; delta++) {
        const neighbor = fi + delta;
        if (neighbor >= 0 && neighbor < totalFaces && !visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push(neighbor);
        }
      }
    }

    return selected;
  }

  // ====================================================================
  // 내부: 시각화
  // ====================================================================

  private _updateSelectionVisual(mesh: THREE.Mesh): void {
    this._clearSelectionVisual();

    const posAttr = mesh.geometry.attributes.position as THREE.BufferAttribute;
    const positions: number[] = [];

    this.selectedFaceIndices.forEach(fi => {
      const i = fi * 3;
      for (let v = 0; v < 3; v++) {
        positions.push(
          posAttr.getX(i + v),
          posAttr.getY(i + v),
          posAttr.getZ(i + v),
        );
      }
    });

    if (positions.length === 0) return;

    // 선택 면을 반투명 노란색으로 오버레이
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geom.computeVertexNormals();

    const mat = new THREE.MeshBasicMaterial({
      color: 0xffff00,
      transparent: true,
      opacity: 0.5,
      side: THREE.DoubleSide,
      depthTest: false,
    });

    this._selectionHighlight = new THREE.Mesh(geom, mat);
    this._selectionHighlight.renderOrder = 999;
    this.scene.add(this._selectionHighlight);
  }

  private _clearSelectionVisual(): void {
    if (this._selectionHighlight) {
      this.scene.remove(this._selectionHighlight);
      this._selectionHighlight.geometry.dispose();
      (this._selectionHighlight.material as THREE.Material).dispose();
      this._selectionHighlight = null;
    }
  }

  private _addBCVisual(bc: BoundaryCondition): void {
    // voxelIndices가 있으면 InstancedMesh 큐브로 시각화
    if (bc.voxelIndices) {
      const worldPositions: Array<{ x: number; y: number; z: number }> = [];
      let cellSize = 1;
      bc.voxelIndices.forEach((selSet, gridName) => {
        const grid = this.voxelGrids[gridName];
        if (!grid) return;
        cellSize = grid.cellSize;
        const gsx = grid.gridSize!.x;
        const gsy = grid.gridSize!.y;
        selSet.forEach(linearIdx => {
          const x = linearIdx % gsx;
          const y = Math.floor(linearIdx / gsx) % gsy;
          const z = Math.floor(linearIdx / (gsx * gsy));
          const wp = grid.gridToWorld(x, y, z);
          worldPositions.push(wp);
        });
      });

      if (worldPositions.length === 0) return;

      const s = cellSize * 0.98;
      const boxGeom = new THREE.BoxGeometry(s, s, s);
      const mat = new THREE.MeshBasicMaterial({
        color: bc.color,
        transparent: true,
        opacity: 0.5,
        depthTest: false,
      });

      const count = Math.min(worldPositions.length, this.MAX_HIGHLIGHT);
      const instMesh = new THREE.InstancedMesh(boxGeom, mat, count);
      const matrix = new THREE.Matrix4();
      for (let i = 0; i < count; i++) {
        const wp = worldPositions[i];
        matrix.setPosition(wp.x, wp.y, wp.z);
        instMesh.setMatrixAt(i, matrix);
      }
      instMesh.instanceMatrix.needsUpdate = true;
      instMesh.renderOrder = 998;
      this.scene.add(instMesh);
      this._bcVisuals.push(instMesh);
      bc._visual = instMesh;
      return;
    }

    // 기존 face 기반: 포인트 시각화
    const positions: number[] = [];
    bc.indices.forEach(idx => {
      const meshList = Object.values(this.meshes);
      if (meshList.length === 0) return;
      const posAttr = meshList[0].geometry.attributes.position as THREE.BufferAttribute;
      if (idx < posAttr.count) {
        positions.push(posAttr.getX(idx), posAttr.getY(idx), posAttr.getZ(idx));
      }
    });

    if (positions.length === 0) return;

    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));

    const mat = new THREE.PointsMaterial({
      color: bc.color,
      size: 3,
      depthTest: false,
      sizeAttenuation: false,
    });

    const points = new THREE.Points(geom, mat);
    points.renderOrder = 998;
    this.scene.add(points);
    this._bcVisuals.push(points);
    bc._visual = points;
  }

  private _removeBCVisual(bc: BoundaryCondition): void {
    if (bc._visual) {
      this.scene.remove(bc._visual);
      if ((bc._visual as THREE.Mesh).geometry) (bc._visual as THREE.Mesh).geometry.dispose();
      if ((bc._visual as THREE.Mesh).material) ((bc._visual as THREE.Mesh).material as THREE.Material).dispose();
      const idx = this._bcVisuals.indexOf(bc._visual);
      if (idx >= 0) this._bcVisuals.splice(idx, 1);
    }
    // Force 화살표 제거
    if (bc._arrowVisual) {
      this.scene.remove(bc._arrowVisual);
      const arrow = bc._arrowVisual as THREE.Object3D & { line?: THREE.Line; cone?: THREE.Mesh };
      if (arrow.line) {
        arrow.line.geometry.dispose();
        (arrow.line.material as THREE.Material).dispose();
      }
      if (arrow.cone) {
        arrow.cone.geometry.dispose();
        (arrow.cone.material as THREE.Material).dispose();
      }
      const arrowIdx = this._bcVisuals.indexOf(bc._arrowVisual);
      if (arrowIdx >= 0) this._bcVisuals.splice(arrowIdx, 1);
      bc._arrowVisual = undefined;
    }
  }

  /**
   * 리소스 정리
   */
  dispose(): void {
    this.clearSelection();
    this.clearAllBC();
  }
}
