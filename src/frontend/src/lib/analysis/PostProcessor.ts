/**
 * 후처리기 (PostProcessor)
 * — FEM 볼륨 메쉬 표면 + PD/SPG 포인트 클라우드 시각화
 *
 * 기능:
 *  - FEM 결과: HEX8 표면 추출 → THREE.Mesh (vertex colors)
 *  - PD/SPG 결과: THREE.Points (포인트 클라우드)
 *  - 다중 컬러맵 (Jet, Cool-to-Warm, Viridis, Turbo 등)
 *  - 벡터 컴포넌트 선택 (Magnitude, X, Y, Z)
 *  - 커스텀 스칼라 범위 (min/max 클램핑)
 *  - 임계값 필터 (Threshold — 범위 밖 숨김)
 *  - 변위 워프 (Warp by Vector)
 *  - 불투명도
 *  - 클리핑 평면
 *
 * 분리된 모듈:
 *  - PostProcessorTypes.ts : 타입/인터페이스
 *  - HEX8Utils.ts          : HEX8 기하 유틸 (표면 추출)
 *  - ScalarMapper.ts       : 순수 함수 (스칼라 추출/통계/필터)
 */

import * as THREE from 'three';
import { valuesToColors, createColorbar, colormapToCSS } from './colormap';
import type { ColormapName } from './colormap';
import type { AnalysisResultData, FEMRegionResult, ParticleRegionResult } from '$lib/ws/types';

// ── 분리된 모듈에서 임포트 ──
import { extractSurfaceTriangles } from './HEX8Utils';
import {
  getFEMNodeScalars,
  getParticleScalars,
  getLegacyScalars,
  getAllScalars,
  computeStats,
  applyPointFilters,
  isTriangleVisible,
} from './ScalarMapper';

// ── 타입 re-export (하위 호환 — 기존 임포트 경로 유지) ──
export type {
  PostProcessMode,
  VectorComponent,
  RepresentationType,
  PostProcessStats,
  ThresholdConfig,
  ClipPlaneConfig,
} from './PostProcessorTypes';

// 로컬 사용을 위한 import
import type {
  PostProcessMode,
  VectorComponent,
  RepresentationType,
  PostProcessStats,
  ThresholdConfig,
  ClipPlaneConfig,
} from './PostProcessorTypes';

export class PostProcessor {
  private scene: THREE.Scene;

  // 결과 데이터
  data: AnalysisResultData | null = null;

  // 시각화 오브젝트
  private _points: THREE.Points | null = null;
  private _meshes: THREE.Mesh[] = [];
  private _geometry: THREE.BufferGeometry | null = null;

  // ── ParaView 스타일 설정 ──

  /** 시각화 모드 (변위/응력/손상) */
  mode: PostProcessMode = 'displacement';

  /** 벡터 컴포넌트 선택 */
  component: VectorComponent = 'magnitude';

  /** 컬러맵 */
  colormapName: ColormapName = 'jet';

  /** 변위 확대 배율 (Warp by Vector) */
  dispScale = 10.0;

  /** 포인트 크기 */
  particleSize = 3.0;

  /** 불투명도 */
  opacity = 1.0;

  /** 표현 타입 */
  representation: RepresentationType = 'points';

  /** 커스텀 스칼라 범위 (null이면 자동) */
  customRange: { min: number; max: number } | null = null;

  /** 임계값 필터 */
  threshold: ThresholdConfig = { enabled: false, lower: 0, upper: 1 };

  /** 클리핑 평면 */
  clipConfig: ClipPlaneConfig = {
    enabled: false,
    axis: 'x',
    position: 0,
    invert: false,
  };

  // 통계
  stats: PostProcessStats = {
    maxDisp: 0, maxStress: 0, maxDamage: 0,
    minDisp: 0, minStress: 0, minDamage: 0,
    currentMin: 0, currentMax: 0,
  };

  // 원본 좌표 캐시 (레거시 변형 좌표 계산용)
  private _cachedPositions: number[][] | null = null;

  /** 바운딩 박스 (클리핑 정규화용) */
  private _bbox: THREE.Box3 = new THREE.Box3();

  /** 보이는 입자 수 */
  visibleCount = 0;

  constructor(threeScene: THREE.Scene) {
    this.scene = threeScene;
  }

  /**
   * 해석 결과 로드
   */
  loadResults(resultData: AnalysisResultData): void {
    this.data = resultData;
    this.stats = computeStats(resultData, this.mode, this.component);
    this._computeBBox();

    // 임계값 범위를 현재 데이터 범위로 초기화
    this.threshold.lower = this.stats.currentMin;
    this.threshold.upper = this.stats.currentMax;

    this.updateVisualization();

    const hasFEM = resultData.fem_regions && resultData.fem_regions.length > 0;
    const hasParticles = resultData.particle_regions && resultData.particle_regions.length > 0;

    console.log('후처리 결과 로드:', {
      방법: resultData.info?.method,
      수렴: resultData.info?.converged,
      FEM영역: hasFEM ? resultData.fem_regions!.length : 0,
      입자영역: hasParticles ? resultData.particle_regions!.length : 0,
    });
  }

  /**
   * 시각화 모드 변경
   */
  setMode(mode: PostProcessMode): void {
    this.mode = mode;
    if (this.data) {
      this.stats = computeStats(this.data, this.mode, this.component);
    }

    // 모드 변경 시 임계값 범위 리셋
    this.threshold.lower = this.stats.currentMin;
    this.threshold.upper = this.stats.currentMax;
    this.customRange = null;

    if (this.data) this.updateVisualization();
  }

  /**
   * 컴포넌트 변경 (Magnitude, X, Y, Z)
   */
  setComponent(comp: VectorComponent): void {
    this.component = comp;
    if (this.data) {
      this.stats = computeStats(this.data, this.mode, this.component);
    }
    this.threshold.lower = this.stats.currentMin;
    this.threshold.upper = this.stats.currentMax;
    this.customRange = null;
    if (this.data) this.updateVisualization();
  }

  /**
   * 컬러맵 변경
   */
  setColormap(name: ColormapName): void {
    this.colormapName = name;
    if (this.data) this.updateVisualization();
  }

  /**
   * 변위 확대 배율 변경 (Warp by Vector)
   */
  setDisplacementScale(scale: number): void {
    this.dispScale = scale;
    if (this.data) this.updateVisualization();
  }

  /**
   * 포인트 크기 변경
   */
  setParticleSize(size: number): void {
    this.particleSize = size;
    if (this._points?.material) {
      (this._points.material as THREE.PointsMaterial).size = size;
    }
  }

  /**
   * 불투명도 변경
   */
  setOpacity(val: number): void {
    this.opacity = val;
    // Points
    if (this._points?.material) {
      const mat = this._points.material as THREE.PointsMaterial;
      mat.opacity = val;
      mat.transparent = val < 1.0;
    }
    // Meshes
    for (const mesh of this._meshes) {
      const mat = mesh.material as THREE.MeshPhongMaterial;
      mat.opacity = val;
      mat.transparent = val < 1.0;
    }
  }

  /**
   * 커스텀 범위 설정 (null이면 자동)
   */
  setCustomRange(min: number | null, max: number | null): void {
    if (min !== null && max !== null) {
      this.customRange = { min, max };
    } else {
      this.customRange = null;
    }
    if (this.data) this.updateVisualization();
  }

  /**
   * 임계값 필터 설정
   */
  setThreshold(enabled: boolean, lower?: number, upper?: number): void {
    this.threshold.enabled = enabled;
    if (lower !== undefined) this.threshold.lower = lower;
    if (upper !== undefined) this.threshold.upper = upper;
    if (this.data) this.updateVisualization();
  }

  /**
   * 클리핑 평면 설정
   */
  setClipPlane(config: Partial<ClipPlaneConfig>): void {
    Object.assign(this.clipConfig, config);
    if (this.data) this.updateVisualization();
  }

  /**
   * 시각화 업데이트 — FEM 메쉬 + PD/SPG 포인트 혼합 지원
   */
  updateVisualization(): void {
    if (!this.data) return;

    this.clear();

    // 전체 스칼라 범위 계산 (모든 영역 통합)
    const allScalars = getAllScalars(this.data, this.mode, this.component);
    const cMin = this.customRange?.min ?? (allScalars.length > 0 ? Math.min(...allScalars) : 0);
    const cMax = this.customRange?.max ?? (allScalars.length > 0 ? Math.max(...allScalars) : 1);

    let totalVisible = 0;

    // ━━━ FEM 영역: 메쉬 표면 렌더링 ━━━
    if (this.data.fem_regions) {
      for (const region of this.data.fem_regions) {
        const visible = this._renderFEMRegion(region, cMin, cMax);
        totalVisible += visible;
      }
    }

    // ━━━ PD/SPG 영역: 포인트 클라우드 렌더링 ━━━
    if (this.data.particle_regions) {
      for (const region of this.data.particle_regions) {
        const visible = this._renderParticleRegion(region, cMin, cMax);
        totalVisible += visible;
      }
    }

    // ━━━ 레거시 모드: fem_regions/particle_regions 없을 때 ━━━
    if (!this.data.fem_regions && !this.data.particle_regions) {
      totalVisible = this._renderLegacyPoints(cMin, cMax);
    }

    this.visibleCount = totalVisible;

    // 컬러바 업데이트
    const labels: Record<PostProcessMode, Record<VectorComponent, string>> = {
      displacement: {
        magnitude: 'Displacement Mag [mm]',
        x: 'Displacement X [mm]',
        y: 'Displacement Y [mm]',
        z: 'Displacement Z [mm]',
      },
      stress: {
        magnitude: 'von Mises Stress [Pa]',
        x: 'Stress X [Pa]',
        y: 'Stress Y [Pa]',
        z: 'Stress Z [Pa]',
      },
      damage: {
        magnitude: 'Damage [0-1]',
        x: 'Damage [0-1]',
        y: 'Damage [0-1]',
        z: 'Damage [0-1]',
      },
    };

    createColorbar(
      'analysis-colorbar',
      cMin,
      cMax,
      labels[this.mode][this.component],
      this.colormapName,
    );
  }

  // ====================================================================
  // FEM 메쉬 표면 렌더링
  // ====================================================================

  /**
   * FEM 영역을 THREE.Mesh로 렌더링
   * - HEX8 표면 추출 → 삼각형 메쉬 (HEX8Utils.extractSurfaceTriangles)
   * - 노드 변위로 워프 (Warp by Vector)
   * - 노드 스칼라로 vertex color (ScalarMapper.getFEMNodeScalars)
   * - ScalarMapper.isTriangleVisible 로 임계값/클리핑 필터
   */
  private _renderFEMRegion(
    region: FEMRegionResult,
    cMin: number,
    cMax: number,
  ): number {
    const { nodes, elements, displacements } = region;

    if (!nodes || !elements || nodes.length === 0) return 0;

    // 표면 삼각형 추출 (HEX8Utils)
    const surfaceTriangles = extractSurfaceTriangles(elements);
    if (surfaceTriangles.length === 0) return 0;

    // 노드별 스칼라 값 계산 (ScalarMapper)
    const nodeScalars = getFEMNodeScalars(region, this.mode, this.component);

    // 변형된 노드 좌표 계산 (Warp by Vector)
    const deformedNodes: number[][] = nodes.map((pos, i) => {
      const d = displacements[i] || [0, 0, 0];
      return [
        pos[0] + d[0] * this.dispScale,
        pos[1] + d[1] * this.dispScale,
        pos[2] + d[2] * this.dispScale,
      ];
    });

    // 삼각형 → BufferGeometry
    const nTris = surfaceTriangles.length;
    const posArray = new Float32Array(nTris * 3 * 3);
    const colorArray = new Float32Array(nTris * 3 * 3);
    const normalArray = new Float32Array(nTris * 3 * 3);

    // 노드 컬러 미리 계산
    const { colors: nodeColors } = valuesToColors(nodeScalars, cMin, cMax, this.colormapName);

    let visibleTris = 0;
    const v0 = new THREE.Vector3();
    const v1 = new THREE.Vector3();
    const v2 = new THREE.Vector3();
    const edge1 = new THREE.Vector3();
    const edge2 = new THREE.Vector3();
    const faceNormal = new THREE.Vector3();

    for (let t = 0; t < nTris; t++) {
      const tri = surfaceTriangles[t];

      // 임계값 + 클리핑 필터 (ScalarMapper)
      if (!isTriangleVisible(tri, deformedNodes, nodeScalars, this.threshold, this.clipConfig, this._bbox)) {
        continue;
      }

      const [ni0, ni1, ni2] = tri;
      const p0 = deformedNodes[ni0];
      const p1 = deformedNodes[ni1];
      const p2 = deformedNodes[ni2];

      const offset = visibleTris * 9;

      // 위치
      posArray[offset + 0] = p0[0]; posArray[offset + 1] = p0[1]; posArray[offset + 2] = p0[2];
      posArray[offset + 3] = p1[0]; posArray[offset + 4] = p1[1]; posArray[offset + 5] = p1[2];
      posArray[offset + 6] = p2[0]; posArray[offset + 7] = p2[1]; posArray[offset + 8] = p2[2];

      // 컬러 (노드별 vertex color)
      colorArray[offset + 0] = nodeColors[ni0 * 3];
      colorArray[offset + 1] = nodeColors[ni0 * 3 + 1];
      colorArray[offset + 2] = nodeColors[ni0 * 3 + 2];
      colorArray[offset + 3] = nodeColors[ni1 * 3];
      colorArray[offset + 4] = nodeColors[ni1 * 3 + 1];
      colorArray[offset + 5] = nodeColors[ni1 * 3 + 2];
      colorArray[offset + 6] = nodeColors[ni2 * 3];
      colorArray[offset + 7] = nodeColors[ni2 * 3 + 1];
      colorArray[offset + 8] = nodeColors[ni2 * 3 + 2];

      // 면 법선 계산
      v0.set(p0[0], p0[1], p0[2]);
      v1.set(p1[0], p1[1], p1[2]);
      v2.set(p2[0], p2[1], p2[2]);
      edge1.subVectors(v1, v0);
      edge2.subVectors(v2, v0);
      faceNormal.crossVectors(edge1, edge2).normalize();

      normalArray[offset + 0] = faceNormal.x; normalArray[offset + 1] = faceNormal.y; normalArray[offset + 2] = faceNormal.z;
      normalArray[offset + 3] = faceNormal.x; normalArray[offset + 4] = faceNormal.y; normalArray[offset + 5] = faceNormal.z;
      normalArray[offset + 6] = faceNormal.x; normalArray[offset + 7] = faceNormal.y; normalArray[offset + 8] = faceNormal.z;

      visibleTris++;
    }

    if (visibleTris === 0) return 0;

    // BufferGeometry 생성 (잘린 배열 사용)
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(posArray.slice(0, visibleTris * 9), 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colorArray.slice(0, visibleTris * 9), 3));
    geometry.setAttribute('normal', new THREE.BufferAttribute(normalArray.slice(0, visibleTris * 9), 3));

    // MeshPhongMaterial (조명 반응 + vertex colors)
    const material = new THREE.MeshPhongMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      flatShading: true,
      opacity: this.opacity,
      transparent: this.opacity < 1.0,
      shininess: 30,
    });

    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = `fem_result_${region.name}`;
    this.scene.add(mesh);
    this._meshes.push(mesh);

    console.log(`FEM 표면 렌더링 [${region.name}]: ${visibleTris}개 삼각형, ${nodes.length}개 노드`);

    return nodes.length;
  }

  // ====================================================================
  // PD/SPG 포인트 클라우드 렌더링
  // ====================================================================

  /**
   * PD/SPG 영역을 THREE.Points로 렌더링
   * - 스칼라 추출: ScalarMapper.getParticleScalars
   * - 필터: ScalarMapper.applyPointFilters
   */
  private _renderParticleRegion(
    region: ParticleRegionResult,
    cMin: number,
    cMax: number,
  ): number {
    const { positions, displacements } = region;

    if (!positions || positions.length === 0) return 0;

    // 변형 좌표 계산 (Warp by Vector)
    const deformed: number[][] = positions.map((pos, i) => {
      const d = displacements?.[i] || [0, 0, 0];
      return [
        pos[0] + d[0] * this.dispScale,
        pos[1] + d[1] * this.dispScale,
        pos[2] + d[2] * this.dispScale,
      ];
    });

    // 스칼라 값 계산 (ScalarMapper)
    const scalars = getParticleScalars(region, this.mode, this.component);

    // 필터 적용 (ScalarMapper)
    const { positions: filteredPos, scalars: filteredScl } =
      applyPointFilters(deformed, scalars, this.threshold, this.clipConfig, this._bbox);

    if (filteredPos.length === 0) return 0;

    // 컬러 계산
    const { colors } = valuesToColors(filteredScl, cMin, cMax, this.colormapName);

    // BufferGeometry
    const n = filteredPos.length;
    const posArray = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      posArray[i * 3] = filteredPos[i][0];
      posArray[i * 3 + 1] = filteredPos[i][1];
      posArray[i * 3 + 2] = filteredPos[i][2];
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
      size: this.particleSize,
      vertexColors: true,
      sizeAttenuation: true,
      depthTest: true,
      opacity: this.opacity,
      transparent: this.opacity < 1.0,
    });

    const points = new THREE.Points(geometry, material);
    points.name = `particle_result_${region.name}`;
    this.scene.add(points);

    // 첫 번째 포인트는 메인 _points에 저장
    if (!this._points) {
      this._points = points;
      this._geometry = geometry;
    }

    console.log(`입자 렌더링 [${region.name}]: ${n}개 입자`);

    return n;
  }

  // ====================================================================
  // 레거시 포인트 렌더링 (하위 호환)
  // ====================================================================

  /**
   * fem_regions/particle_regions 없을 때 기존 방식으로 렌더링
   */
  private _renderLegacyPoints(cMin: number, cMax: number): number {
    const allPositions = this.data!.displacements.length > 0
      ? this._getDeformedPositions()
      : [];

    if (allPositions.length === 0) return 0;

    const allScalars = getLegacyScalars(this.data!, this.mode, this.component);
    if (!allScalars || allScalars.length === 0) return 0;

    const { positions, scalars } = applyPointFilters(
      allPositions, allScalars, this.threshold, this.clipConfig, this._bbox,
    );

    if (positions.length === 0) return 0;

    const n = positions.length;
    const { colors } = valuesToColors(scalars, cMin, cMax, this.colormapName);

    this._geometry = new THREE.BufferGeometry();

    const posArray = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      posArray[i * 3] = positions[i][0];
      posArray[i * 3 + 1] = positions[i][1];
      posArray[i * 3 + 2] = positions[i][2];
    }

    this._geometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
    this._geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
      size: this.particleSize,
      vertexColors: true,
      sizeAttenuation: true,
      depthTest: true,
      opacity: this.opacity,
      transparent: this.opacity < 1.0,
    });

    this._points = new THREE.Points(this._geometry, material);
    this._points.name = 'analysis_result';
    this.scene.add(this._points);

    return n;
  }

  /**
   * 결과 시각화 제거
   */
  clear(): void {
    // Points 제거
    if (this._points) {
      this.scene.remove(this._points);
      this._points = null;
    }
    if (this._geometry) {
      this._geometry.dispose();
      this._geometry = null;
    }

    // FEM 메쉬 제거
    for (const mesh of this._meshes) {
      this.scene.remove(mesh);
      mesh.geometry.dispose();
      (mesh.material as THREE.Material).dispose();
    }
    this._meshes = [];

    // 이름으로도 정리 (안전장치)
    const toRemove: THREE.Object3D[] = [];
    this.scene.traverse(obj => {
      if (obj.name.startsWith('fem_result_') || obj.name.startsWith('particle_result_') || obj.name === 'analysis_result') {
        toRemove.push(obj);
      }
    });
    toRemove.forEach(obj => this.scene.remove(obj));
  }

  /**
   * 현재 스칼라 데이터의 범위 반환 (UI 범위 슬라이더용)
   */
  getDataRange(): { min: number; max: number } {
    return { min: this.stats.currentMin, max: this.stats.currentMax };
  }

  /**
   * CSS 컬러바 그라디언트 문자열
   */
  getColorbarCSS(): string {
    return colormapToCSS(this.colormapName, 20);
  }

  // ====================================================================
  // 내부 메서드
  // ====================================================================

  /**
   * 바운딩 박스 계산 (클리핑 정규화용)
   */
  private _computeBBox(): void {
    this._bbox.makeEmpty();

    // FEM 노드 좌표
    if (this.data?.fem_regions) {
      for (const r of this.data.fem_regions) {
        for (const p of r.nodes) {
          this._bbox.expandByPoint(new THREE.Vector3(p[0], p[1], p[2]));
        }
      }
    }

    // 입자 좌표
    if (this.data?.particle_regions) {
      for (const r of this.data.particle_regions) {
        for (const p of (r.positions || [])) {
          this._bbox.expandByPoint(new THREE.Vector3(p[0], p[1], p[2]));
        }
      }
    }

    // 캐시된 좌표 (레거시)
    if (this._cachedPositions) {
      for (const p of this._cachedPositions) {
        this._bbox.expandByPoint(new THREE.Vector3(p[0], p[1], p[2]));
      }
    }
  }

  /**
   * 레거시: 변형 좌표 계산 (ref + disp * scale)
   */
  private _getDeformedPositions(): number[][] {
    const disps = this.data!.displacements;
    const n = disps.length;

    if (this._cachedPositions) {
      const result: number[][] = [];
      for (let i = 0; i < Math.min(n, this._cachedPositions.length); i++) {
        const p = this._cachedPositions[i];
        const d = disps[i] || [0, 0, 0];
        result.push([
          p[0] + d[0] * this.dispScale,
          p[1] + d[1] * this.dispScale,
          p[2] + d[2] * this.dispScale,
        ]);
      }
      return result;
    }

    return disps;
  }

  /**
   * 해석 요청 시 원본 좌표를 캐시 (레거시 변형 좌표 계산용)
   */
  cachePositions(positions: number[][]): void {
    this._cachedPositions = positions;
    this._computeBBox();
  }

  /**
   * 수술 전 결과 저장
   */
  savePreOpResults(): AnalysisResultData | null {
    if (!this.data) return null;
    return JSON.parse(JSON.stringify(this.data));
  }

  /**
   * 수술 전/후 비교 (차이 컬러맵)
   */
  showComparison(preOpData: AnalysisResultData): void {
    if (!preOpData || !this.data) return;

    const preDisps = preOpData.displacements;
    const postDisps = this.data.displacements;
    const n = Math.min(preDisps.length, postDisps.length);

    const diffDisps: number[][] = [];
    for (let i = 0; i < n; i++) {
      diffDisps.push([
        (postDisps[i][0] || 0) - (preDisps[i][0] || 0),
        (postDisps[i][1] || 0) - (preDisps[i][1] || 0),
        (postDisps[i][2] || 0) - (preDisps[i][2] || 0),
      ]);
    }

    const diffData: AnalysisResultData = {
      ...this.data,
      displacements: diffDisps,
      info: { ...this.data.info, method: 'difference' },
    };
    this.loadResults(diffData);
  }

  /**
   * 임플란트 주변 필터 — 지정 중심/반경 내 입자만 표시
   */
  filterByRegion(center: THREE.Vector3, radius: number): void {
    if (!this._points || !this._geometry || radius <= 0) {
      if (this._points) this._points.visible = true;
      return;
    }

    const positions = this._geometry.attributes.position as THREE.BufferAttribute;
    const colors = this._geometry.attributes.color as THREE.BufferAttribute;
    if (!positions || !colors) return;

    const r2 = radius * radius;
    const cx = center.x, cy = center.y, cz = center.z;

    // 범위 밖 입자를 회색으로
    for (let i = 0; i < positions.count; i++) {
      const px = positions.getX(i);
      const py = positions.getY(i);
      const pz = positions.getZ(i);
      const dx = px - cx, dy = py - cy, dz = pz - cz;
      const dist2 = dx * dx + dy * dy + dz * dz;

      if (dist2 > r2) {
        colors.setXYZ(i, 0.5, 0.5, 0.5);
      }
    }

    colors.needsUpdate = true;
  }
}
