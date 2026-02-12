/**
 * 전처리기 (PreProcessor)
 * — 면 선택, 경계조건 설정, 재료 할당, 해석 요청 조립
 */
class PreProcessor {
    constructor(threeScene, meshesRef, voxelGridsRef) {
        this.scene = threeScene;
        this.meshes = meshesRef;       // main.js의 meshes 참조
        this.voxelGrids = voxelGridsRef;

        // 선택 상태
        this.selectedFaceIndices = [];  // 선택된 face index 배열
        this.selectedNodeIndices = new Set(); // 매핑된 노드/복셀 인덱스

        // 경계조건 목록
        this.boundaryConditions = [];   // {type, indices: Set, values, mesh: InstancedMesh}

        // 재료 할당 (메쉬명 → 프리셋)
        this.materialAssignments = {};

        // 브러쉬 선택 (gridName → Set<linearIdx>)
        this.brushSelection = new Map();

        // 시각화 오브젝트
        this._selectionHighlight = null;  // InstancedMesh: 선택 하이라이트
        this._bcVisuals = [];              // 화살표/고정 표시

        // 설정
        this.FACE_NORMAL_THRESHOLD = Math.cos(30 * Math.PI / 180); // BFS 법선 유사도
        this.MAX_HIGHLIGHT = 5000;

        // 재료 프리셋
        this.MATERIAL_PRESETS = {
            bone:     { E: 15e9,  nu: 0.3,  density: 1850, label: 'Bone (15 GPa)' },
            disc:     { E: 10e6,  nu: 0.45, density: 1200, label: 'Disc (10 MPa)' },
            ligament: { E: 50e6,  nu: 0.4,  density: 1100, label: 'Ligament (50 MPa)' },
            titanium: { E: 110e9, nu: 0.34, density: 4500, label: 'Titanium (110 GPa)' },
        };
    }

    // ====================================================================
    // 면 선택 (Raycasting + BFS 인접 확장)
    // ====================================================================

    /**
     * 클릭한 면 + BFS 인접 면 선택
     * @param {Object} intersection - Three.js raycaster intersection
     * @param {boolean} additive - Shift 키 누른 상태 (추가 선택)
     */
    selectFace(intersection, additive = false) {
        if (!intersection || intersection.faceIndex === undefined) return;

        if (!additive) {
            this.clearSelection();
        }

        const mesh = intersection.object;
        const geometry = mesh.geometry;
        const faceIndex = intersection.faceIndex;

        // BufferGeometry에서 face 법선 가져오기
        const posAttr = geometry.attributes.position;
        const normalAttr = geometry.attributes.normal;

        if (!normalAttr) {
            geometry.computeVertexNormals();
        }

        // 클릭한 면의 법선 계산
        const clickedNormal = this._getFaceNormal(posAttr, faceIndex);

        // BFS로 인접 면 확장 (법선 유사도 기준)
        const selectedFaces = this._bfsFaceSelect(posAttr, normalAttr || geometry.attributes.normal, faceIndex, clickedNormal);

        // vertex 인덱스 수집
        selectedFaces.forEach(fi => {
            this.selectedFaceIndices.push(fi);
            // 각 face의 3개 vertex
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
    clearSelection() {
        this.selectedFaceIndices = [];
        this.selectedNodeIndices.clear();
        this._clearSelectionVisual();
    }

    // ====================================================================
    // 브러쉬 선택 (복셀 기반)
    // ====================================================================

    /**
     * 구체 브러쉬로 복셀 선택 (누적)
     * @param {THREE.Vector3} worldPos - 구체 중심 (월드 좌표)
     * @param {number} radius - 브러쉬 반경
     */
    brushSelectSphere(worldPos, radius) {
        Object.entries(this.voxelGrids).forEach(([name, grid]) => {
            const affected = grid.previewDrill(worldPos, radius);
            if (affected.length === 0) return;

            if (!this.brushSelection.has(name)) {
                this.brushSelection.set(name, new Set());
            }
            const selSet = this.brushSelection.get(name);
            const gsx = grid.gridSize.x;
            const gsy = grid.gridSize.y;
            affected.forEach(pos => {
                const linearIdx = pos.x + pos.y * gsx + pos.z * gsx * gsy;
                selSet.add(linearIdx);
            });
        });
    }

    /**
     * 브러쉬 선택 초기화
     */
    clearBrushSelection() {
        this.brushSelection.clear();
    }

    /**
     * 선택된 총 복셀 수
     */
    getBrushSelectionCount() {
        let count = 0;
        this.brushSelection.forEach(s => count += s.size);
        return count;
    }

    /**
     * 선택된 복셀의 월드 좌표 목록 반환 (시각화용)
     * @returns {Array<{x,y,z}>}
     */
    getBrushSelectionWorldPositions() {
        const positions = [];
        this.brushSelection.forEach((selSet, gridName) => {
            const grid = this.voxelGrids[gridName];
            if (!grid) return;
            const gsx = grid.gridSize.x;
            const gsy = grid.gridSize.y;
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
    addFixedBC() {
        // 브러쉬 선택 우선
        if (this.getBrushSelectionCount() > 0) {
            const voxelIndices = new Map();
            this.brushSelection.forEach((selSet, gridName) => {
                voxelIndices.set(gridName, new Set(selSet));
            });
            const bc = {
                type: 'fixed',
                indices: new Set(),  // 호환용 빈 Set
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
            return;
        }

        const indices = new Set(this.selectedNodeIndices);
        const bc = {
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
     * @param {number[]} force - [fx, fy, fz] 힘 벡터 [N]
     */
    addForceBC(force) {
        // 브러쉬 선택 우선
        if (this.getBrushSelectionCount() > 0) {
            const voxelIndices = new Map();
            this.brushSelection.forEach((selSet, gridName) => {
                voxelIndices.set(gridName, new Set(selSet));
            });
            const bc = {
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
            return;
        }

        const indices = new Set(this.selectedNodeIndices);
        const bc = {
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
    removeLastBC() {
        if (this.boundaryConditions.length === 0) return;
        const bc = this.boundaryConditions.pop();
        this._removeBCVisual(bc);
        console.log('마지막 BC 제거');
    }

    /**
     * 모든 BC 제거
     */
    clearAllBC() {
        this._bcVisuals.forEach(v => {
            this.scene.remove(v);
            if (v.geometry) v.geometry.dispose();
            if (v.material) v.material.dispose();
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
     * @param {string} meshName - 메쉬 이름
     * @param {string} presetKey - 프리셋 키 ('bone', 'disc', ...)
     */
    assignMaterial(meshName, presetKey) {
        if (!this.MATERIAL_PRESETS[presetKey]) {
            console.warn(`알 수 없는 재료 프리셋: ${presetKey}`);
            return;
        }
        this.materialAssignments[meshName] = presetKey;
        console.log(`재료 할당: ${meshName} → ${this.MATERIAL_PRESETS[presetKey].label}`);
    }

    // ====================================================================
    // 입자 데이터 추출 + 해석 요청 조립
    // ====================================================================

    /**
     * 복셀 그리드에서 입자 좌표/체적 추출
     * @returns {{positions: number[][], volumes: number[]}}
     */
    extractParticleData() {
        const positions = [];
        const volumes = [];

        Object.entries(this.voxelGrids).forEach(([name, grid]) => {
            const cellVolume = grid.cellSize ** 3;

            // 활성 복셀 순회
            for (let z = 0; z < grid.gridSize.z; z++) {
                for (let y = 0; y < grid.gridSize.y; y++) {
                    for (let x = 0; x < grid.gridSize.x; x++) {
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
     * AnalysisRequest 객체 조립
     * voxelIndices가 있는 BC는 복셀 linearIdx → particle index 매핑
     * @param {string} method - 'fem' | 'pd' | 'spg'
     * @returns {Object} 서버 전송용 요청 객체
     */
    buildAnalysisRequest(method) {
        // 복셀→입자 매핑 테이블 구축
        const positions = [];
        const volumes = [];
        // gridName → Map<linearIdx, particleIdx>
        const voxelToParticle = new Map();
        let particleIdx = 0;

        Object.entries(this.voxelGrids).forEach(([name, grid]) => {
            const cellVolume = grid.cellSize ** 3;
            const gsx = grid.gridSize.x;
            const gsy = grid.gridSize.y;
            const gsz = grid.gridSize.z;
            const indexMap = new Map();

            for (let z = 0; z < gsz; z++) {
                for (let y = 0; y < gsy; y++) {
                    for (let x = 0; x < gsx; x++) {
                        if (grid.get(x, y, z)) {
                            const world = grid.gridToWorld(x, y, z);
                            positions.push([world.x, world.y, world.z]);
                            volumes.push(cellVolume);
                            const linearIdx = x + y * gsx + z * gsx * gsy;
                            indexMap.set(linearIdx, particleIdx);
                            particleIdx++;
                        }
                    }
                }
            }

            voxelToParticle.set(name, indexMap);
        });

        // 경계조건 변환 (voxelIndices → particle indices 매핑)
        const bcs = this.boundaryConditions.map(bc => {
            if (bc.voxelIndices) {
                // 브러쉬 기반 BC: voxelIndices → particleIndices
                const particleIndices = [];
                bc.voxelIndices.forEach((selSet, gridName) => {
                    const indexMap = voxelToParticle.get(gridName);
                    if (!indexMap) return;
                    selSet.forEach(linearIdx => {
                        const pIdx = indexMap.get(linearIdx);
                        if (pIdx !== undefined) {
                            particleIndices.push(pIdx);
                        }
                    });
                });
                return {
                    type: bc.type,
                    node_indices: particleIndices,
                    values: bc.values,
                };
            }
            // 기존 face 기반 BC
            return {
                type: bc.type,
                node_indices: Array.from(bc.indices),
                values: bc.values,
            };
        });

        // 재료 변환 (메쉬별 프리셋 → MaterialRegion)
        const materials = [];
        let nodeOffset = 0;

        Object.entries(this.voxelGrids).forEach(([name, grid]) => {
            const presetKey = this.materialAssignments[name] || 'bone';
            const preset = this.MATERIAL_PRESETS[presetKey];

            // 이 그리드의 활성 복셀 수 계산
            let count = 0;
            for (let i = 0; i < grid.data.length; i++) {
                if (grid.data[i]) count++;
            }

            const indices = [];
            for (let i = nodeOffset; i < nodeOffset + count; i++) {
                indices.push(i);
            }

            materials.push({
                name: presetKey,
                E: preset.E,
                nu: preset.nu,
                density: preset.density,
                node_indices: indices,
            });

            nodeOffset += count;
        });

        return {
            positions,
            volumes,
            method,
            boundary_conditions: bcs,
            materials,
            options: {},
        };
    }

    // ====================================================================
    // 내부: 면 선택 알고리즘
    // ====================================================================

    _getFaceNormal(posAttr, faceIndex) {
        const i = faceIndex * 3;
        const vA = new THREE.Vector3().fromBufferAttribute(posAttr, i);
        const vB = new THREE.Vector3().fromBufferAttribute(posAttr, i + 1);
        const vC = new THREE.Vector3().fromBufferAttribute(posAttr, i + 2);

        const edge1 = new THREE.Vector3().subVectors(vB, vA);
        const edge2 = new THREE.Vector3().subVectors(vC, vA);
        return new THREE.Vector3().crossVectors(edge1, edge2).normalize();
    }

    _bfsFaceSelect(posAttr, normalAttr, startFace, refNormal) {
        const totalFaces = posAttr.count / 3;
        const visited = new Set();
        const selected = [];
        const queue = [startFace];
        visited.add(startFace);

        // 면 인접 맵 구축 (vertex 공유 기반, 간소화)
        // 성능 상 최대 100면까지만 확장
        const MAX_FACES = 100;

        while (queue.length > 0 && selected.length < MAX_FACES) {
            const fi = queue.shift();

            // 이 면의 법선 확인
            const normal = this._getFaceNormal(posAttr, fi);
            const dot = normal.dot(refNormal);

            if (dot < this.FACE_NORMAL_THRESHOLD) continue;

            selected.push(fi);

            // 인접 면 탐색 (±1 인덱스, 간소화)
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

    _updateSelectionVisual(mesh) {
        this._clearSelectionVisual();

        const posAttr = mesh.geometry.attributes.position;
        const positions = [];

        this.selectedFaceIndices.forEach(fi => {
            const i = fi * 3;
            for (let v = 0; v < 3; v++) {
                positions.push(
                    posAttr.getX(i + v),
                    posAttr.getY(i + v),
                    posAttr.getZ(i + v)
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

    _clearSelectionVisual() {
        if (this._selectionHighlight) {
            this.scene.remove(this._selectionHighlight);
            this._selectionHighlight.geometry.dispose();
            this._selectionHighlight.material.dispose();
            this._selectionHighlight = null;
        }
    }

    _addBCVisual(bc) {
        // voxelIndices가 있으면 InstancedMesh 큐브로 시각화
        if (bc.voxelIndices) {
            const worldPositions = [];
            let cellSize = 1;
            bc.voxelIndices.forEach((selSet, gridName) => {
                const grid = this.voxelGrids[gridName];
                if (!grid) return;
                cellSize = grid.cellSize;
                const gsx = grid.gridSize.x;
                const gsy = grid.gridSize.y;
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

            // Force BC 화살표는 main.js에서 관리 (createAppliedForceArrow)
            return;
        }

        // 기존 face 기반: 포인트 시각화 (고정=파랑, 하중=빨강)
        const positions = [];
        bc.indices.forEach(idx => {
            const meshList = Object.values(this.meshes);
            if (meshList.length === 0) return;
            const posAttr = meshList[0].geometry.attributes.position;
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

    _removeBCVisual(bc) {
        if (bc._visual) {
            this.scene.remove(bc._visual);
            bc._visual.geometry.dispose();
            bc._visual.material.dispose();
            const idx = this._bcVisuals.indexOf(bc._visual);
            if (idx >= 0) this._bcVisuals.splice(idx, 1);
        }
        // Force 화살표 제거
        if (bc._arrowVisual) {
            this.scene.remove(bc._arrowVisual);
            if (bc._arrowVisual.line) {
                bc._arrowVisual.line.geometry.dispose();
                bc._arrowVisual.line.material.dispose();
            }
            if (bc._arrowVisual.cone) {
                bc._arrowVisual.cone.geometry.dispose();
                bc._arrowVisual.cone.material.dispose();
            }
            const arrowIdx = this._bcVisuals.indexOf(bc._arrowVisual);
            if (arrowIdx >= 0) this._bcVisuals.splice(arrowIdx, 1);
            bc._arrowVisual = null;
        }
    }

    /**
     * 리소스 정리
     */
    dispose() {
        this.clearSelection();
        this.clearAllBC();
    }
}
