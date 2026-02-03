/**
 * 복셀 시스템 - 메쉬를 복셀로 변환하고 드릴링 후 다시 메쉬로
 */

class VoxelGrid {
    constructor(resolution = 64) {
        this.resolution = resolution;
        this.data = null;  // Uint8Array
        this.bounds = null;  // { min: Vector3, max: Vector3 }
        this.cellSize = 0;
        this.gridSize = null;
    }

    /**
     * 현재 복셀 데이터의 스냅샷 생성 (Undo용)
     */
    createSnapshot() {
        if (!this.data) return null;
        return new Uint8Array(this.data);
    }

    /**
     * 스냅샷에서 복셀 데이터 복원 (Undo용)
     */
    restoreSnapshot(snapshot) {
        if (!snapshot || !this.data) return;
        this.data.set(snapshot);
    }

    /**
     * 특정 축의 단면 데이터 가져오기 (Slice 뷰용)
     * @param {string} axis - 'x', 'y', 'z'
     * @param {number} index - 단면 인덱스
     * @returns {Object} 단면 정보 { width, height, data }
     */
    getSlice(axis, index) {
        if (!this.data || !this.gridSize) return null;

        let width, height, sliceData;

        if (axis === 'z') {
            // Axial (위에서 본 단면)
            width = this.gridSize.x;
            height = this.gridSize.y;
            sliceData = new Uint8Array(width * height);
            for (let y = 0; y < height; y++) {
                for (let x = 0; x < width; x++) {
                    sliceData[x + y * width] = this.get(x, y, index);
                }
            }
        } else if (axis === 'y') {
            // Coronal (앞에서 본 단면)
            width = this.gridSize.x;
            height = this.gridSize.z;
            sliceData = new Uint8Array(width * height);
            for (let z = 0; z < height; z++) {
                for (let x = 0; x < width; x++) {
                    sliceData[x + z * width] = this.get(x, index, z);
                }
            }
        } else {
            // Sagittal (옆에서 본 단면)
            width = this.gridSize.y;
            height = this.gridSize.z;
            sliceData = new Uint8Array(width * height);
            for (let z = 0; z < height; z++) {
                for (let y = 0; y < width; y++) {
                    sliceData[y + z * width] = this.get(index, y, z);
                }
            }
        }

        return { width, height, data: sliceData };
    }

    /**
     * NRRD 데이터에서 VoxelGrid 생성
     * @param {Object} nrrdData - NRRDLoader.parse() 결과 { header, data }
     * @param {number} threshold - 복셀 활성화 임계값 (기본: 0.5)
     * @param {number} targetResolution - 목표 해상도 (0이면 원본 사용, 원본보다 크면 업샘플링)
     */
    fromNRRD(nrrdData, threshold = 0.5, targetResolution = 0) {
        console.time('NRRD to Voxel');

        const { header, data } = nrrdData;
        const [sizeX, sizeY, sizeZ] = header.sizes;
        const spacing = header.spacing || [1, 1, 1];

        console.log(`NRRD 크기: ${sizeX} x ${sizeY} x ${sizeZ}`);
        console.log(`NRRD spacing: ${spacing.join(', ')}`);

        // 데이터 정규화 (0~1 범위로)
        let minVal = Infinity, maxVal = -Infinity;
        for (let i = 0; i < data.length; i++) {
            if (data[i] < minVal) minVal = data[i];
            if (data[i] > maxVal) maxVal = data[i];
        }

        // labelmap인 경우 (세그멘테이션)
        const isLabelmap = (minVal >= 0 && maxVal <= 255 && Number.isInteger(maxVal));

        console.log(`데이터 범위: ${minVal} ~ ${maxVal}, labelmap: ${isLabelmap}`);

        // 리샘플링 (다운샘플링 또는 업샘플링)
        let finalSizeX = sizeX, finalSizeY = sizeY, finalSizeZ = sizeZ;
        let finalSpacing = [...spacing];
        let scale = 1;
        let isUpsampling = false;

        if (targetResolution > 0) {
            const maxDim = Math.max(sizeX, sizeY, sizeZ);
            scale = maxDim / targetResolution;

            if (scale > 1) {
                // 다운샘플링
                finalSizeX = Math.ceil(sizeX / scale);
                finalSizeY = Math.ceil(sizeY / scale);
                finalSizeZ = Math.ceil(sizeZ / scale);
                finalSpacing = spacing.map(s => s * scale);
                console.log(`다운샘플링: ${scale.toFixed(2)}x → ${finalSizeX} x ${finalSizeY} x ${finalSizeZ}`);
            } else if (scale < 1) {
                // 업샘플링
                isUpsampling = true;
                finalSizeX = Math.ceil(sizeX / scale);
                finalSizeY = Math.ceil(sizeY / scale);
                finalSizeZ = Math.ceil(sizeZ / scale);
                finalSpacing = spacing.map(s => s * scale);
                console.log(`업샘플링: ${(1/scale).toFixed(2)}x → ${finalSizeX} x ${finalSizeY} x ${finalSizeZ}`);
            }
        }

        // VoxelGrid 설정
        this.gridSize = {
            x: finalSizeX,
            y: finalSizeY,
            z: finalSizeZ
        };

        // 물리적 크기 계산 (원본과 동일하게 유지)
        const physicalSize = {
            x: sizeX * spacing[0],
            y: sizeY * spacing[1],
            z: sizeZ * spacing[2]
        };

        // 원점 (3D Slicer의 space origin 사용)
        const origin = header.spaceOrigin || [0, 0, 0];

        this.bounds = {
            min: new THREE.Vector3(origin[0], origin[1], origin[2]),
            max: new THREE.Vector3(
                origin[0] + physicalSize.x,
                origin[1] + physicalSize.y,
                origin[2] + physicalSize.z
            )
        };

        this.cellSize = Math.max(
            physicalSize.x / finalSizeX,
            physicalSize.y / finalSizeY,
            physicalSize.z / finalSizeZ
        );
        this.resolution = Math.max(finalSizeX, finalSizeY, finalSizeZ);

        // 복셀 데이터 할당
        const totalCells = finalSizeX * finalSizeY * finalSizeZ;
        this.data = new Uint8Array(totalCells);

        // 원본 데이터에서 값을 가져오는 헬퍼 함수
        const getSrcValue = (sx, sy, sz) => {
            sx = Math.max(0, Math.min(sizeX - 1, sx));
            sy = Math.max(0, Math.min(sizeY - 1, sy));
            sz = Math.max(0, Math.min(sizeZ - 1, sz));
            return data[sx + sy * sizeX + sz * sizeX * sizeY];
        };

        // Trilinear 보간 (업샘플링용)
        const trilinearInterpolate = (fx, fy, fz) => {
            const x0 = Math.floor(fx), x1 = Math.min(x0 + 1, sizeX - 1);
            const y0 = Math.floor(fy), y1 = Math.min(y0 + 1, sizeY - 1);
            const z0 = Math.floor(fz), z1 = Math.min(z0 + 1, sizeZ - 1);

            const xd = fx - x0, yd = fy - y0, zd = fz - z0;

            // 8개 코너 값
            const c000 = getSrcValue(x0, y0, z0);
            const c100 = getSrcValue(x1, y0, z0);
            const c010 = getSrcValue(x0, y1, z0);
            const c110 = getSrcValue(x1, y1, z0);
            const c001 = getSrcValue(x0, y0, z1);
            const c101 = getSrcValue(x1, y0, z1);
            const c011 = getSrcValue(x0, y1, z1);
            const c111 = getSrcValue(x1, y1, z1);

            // Trilinear 보간
            const c00 = c000 * (1 - xd) + c100 * xd;
            const c01 = c001 * (1 - xd) + c101 * xd;
            const c10 = c010 * (1 - xd) + c110 * xd;
            const c11 = c011 * (1 - xd) + c111 * xd;

            const c0 = c00 * (1 - yd) + c10 * yd;
            const c1 = c01 * (1 - yd) + c11 * yd;

            return c0 * (1 - zd) + c1 * zd;
        };

        // 데이터 복사 (리샘플링 포함)
        let filledCount = 0;

        for (let z = 0; z < finalSizeZ; z++) {
            for (let y = 0; y < finalSizeY; y++) {
                for (let x = 0; x < finalSizeX; x++) {
                    // 원본 좌표 (부동소수점)
                    const srcX = x * scale;
                    const srcY = y * scale;
                    const srcZ = z * scale;

                    const dstIdx = x + y * finalSizeX + z * finalSizeX * finalSizeY;

                    let value;
                    if (isLabelmap) {
                        // labelmap: nearest neighbor (보간 시 경계가 흐려지는 것 방지)
                        const nearestVal = getSrcValue(
                            Math.round(srcX),
                            Math.round(srcY),
                            Math.round(srcZ)
                        );
                        value = nearestVal > 0 ? 1 : 0;
                    } else {
                        // CT 등: trilinear 보간 후 threshold 적용
                        let rawValue;
                        if (isUpsampling) {
                            rawValue = trilinearInterpolate(srcX, srcY, srcZ);
                        } else {
                            rawValue = getSrcValue(
                                Math.floor(srcX),
                                Math.floor(srcY),
                                Math.floor(srcZ)
                            );
                        }
                        const normalized = (rawValue - minVal) / (maxVal - minVal);
                        value = normalized > threshold ? 1 : 0;
                    }

                    this.data[dstIdx] = value;
                    if (value > 0) filledCount++;
                }
            }
        }

        console.timeEnd('NRRD to Voxel');
        console.log(`채워진 복셀: ${filledCount} / ${totalCells} (${(filledCount/totalCells*100).toFixed(1)}%)`);

        return this;
    }

    /**
     * 메쉬를 복셀 그리드로 변환
     */
    fromMesh(mesh) {
        console.time('Voxelization');

        // 1. Bounding box 계산
        const geometry = mesh.geometry;
        geometry.computeBoundingBox();

        // 월드 좌표로 변환
        const box = geometry.boundingBox.clone();
        box.applyMatrix4(mesh.matrixWorld);

        // 약간의 여유 추가
        const padding = 2;
        box.min.subScalar(padding);
        box.max.addScalar(padding);

        this.bounds = {
            min: box.min.clone(),
            max: box.max.clone()
        };

        // 2. 셀 크기 계산
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        this.cellSize = maxDim / this.resolution;

        // 3. 그리드 크기 계산
        this.gridSize = {
            x: Math.ceil(size.x / this.cellSize),
            y: Math.ceil(size.y / this.cellSize),
            z: Math.ceil(size.z / this.cellSize)
        };

        console.log(`Grid size: ${this.gridSize.x} x ${this.gridSize.y} x ${this.gridSize.z}`);
        console.log(`Cell size: ${this.cellSize.toFixed(2)}`);

        // 4. 복셀 데이터 초기화
        const totalCells = this.gridSize.x * this.gridSize.y * this.gridSize.z;
        this.data = new Uint8Array(totalCells);

        // 5. 메쉬 내부 복셀 채우기 (ray casting 방식)
        this._voxelizeMesh(mesh);

        console.timeEnd('Voxelization');

        const filledCount = this.data.reduce((a, b) => a + b, 0);
        console.log(`Filled voxels: ${filledCount} / ${totalCells}`);

        return this;
    }

    /**
     * Ray casting으로 메쉬 내부 복셀 채우기
     */
    _voxelizeMesh(mesh) {
        const geometry = mesh.geometry;
        const posAttr = geometry.attributes.position;

        // 삼각형 목록 추출
        const triangles = [];
        for (let i = 0; i < posAttr.count; i += 3) {
            const v0 = new THREE.Vector3(posAttr.getX(i), posAttr.getY(i), posAttr.getZ(i));
            const v1 = new THREE.Vector3(posAttr.getX(i+1), posAttr.getY(i+1), posAttr.getZ(i+1));
            const v2 = new THREE.Vector3(posAttr.getX(i+2), posAttr.getY(i+2), posAttr.getZ(i+2));

            // 월드 좌표로 변환
            v0.applyMatrix4(mesh.matrixWorld);
            v1.applyMatrix4(mesh.matrixWorld);
            v2.applyMatrix4(mesh.matrixWorld);

            triangles.push({ v0, v1, v2 });
        }

        // 각 복셀 중심에서 ray casting
        const raycaster = new THREE.Raycaster();
        const direction = new THREE.Vector3(1, 0, 0);  // X 방향으로 발사

        for (let z = 0; z < this.gridSize.z; z++) {
            for (let y = 0; y < this.gridSize.y; y++) {
                // 이 줄(row)의 모든 교차점 찾기
                const origin = this.gridToWorld(0, y, z);
                origin.x = this.bounds.min.x - 1;  // 바운드 밖에서 시작

                raycaster.set(origin, direction);
                const intersects = raycaster.intersectObject(mesh);

                // 교차점 X 좌표 정렬
                const xPoints = intersects.map(i => i.point.x).sort((a, b) => a - b);

                // 짝수번째 교차 후 = 내부
                for (let x = 0; x < this.gridSize.x; x++) {
                    const worldPos = this.gridToWorld(x, y, z);

                    // 이 X 좌표가 몇 번째 교차점 뒤에 있는지 카운트
                    let crossCount = 0;
                    for (const xp of xPoints) {
                        if (worldPos.x > xp) crossCount++;
                        else break;
                    }

                    // 홀수 개의 교차점 뒤 = 내부
                    if (crossCount % 2 === 1) {
                        this.set(x, y, z, 1);
                    }
                }
            }
        }
    }

    /**
     * 그리드 인덱스 계산
     */
    index(x, y, z) {
        return x + y * this.gridSize.x + z * this.gridSize.x * this.gridSize.y;
    }

    /**
     * 복셀 값 가져오기
     */
    get(x, y, z) {
        if (x < 0 || x >= this.gridSize.x ||
            y < 0 || y >= this.gridSize.y ||
            z < 0 || z >= this.gridSize.z) {
            return 0;
        }
        return this.data[this.index(x, y, z)];
    }

    /**
     * 복셀 값 설정
     */
    set(x, y, z, value) {
        if (x < 0 || x >= this.gridSize.x ||
            y < 0 || y >= this.gridSize.y ||
            z < 0 || z >= this.gridSize.z) {
            return;
        }
        this.data[this.index(x, y, z)] = value;
    }

    /**
     * 월드 좌표 → 그리드 좌표
     */
    worldToGrid(worldPos) {
        return {
            x: Math.floor((worldPos.x - this.bounds.min.x) / this.cellSize),
            y: Math.floor((worldPos.y - this.bounds.min.y) / this.cellSize),
            z: Math.floor((worldPos.z - this.bounds.min.z) / this.cellSize)
        };
    }

    /**
     * 그리드 좌표 → 월드 좌표 (셀 중심)
     */
    gridToWorld(x, y, z) {
        return new THREE.Vector3(
            this.bounds.min.x + (x + 0.5) * this.cellSize,
            this.bounds.min.y + (y + 0.5) * this.cellSize,
            this.bounds.min.z + (z + 0.5) * this.cellSize
        );
    }

    /**
     * 구 형태로 드릴링 (복셀 제거)
     */
    drillSphere(worldPos, radius) {
        const gridPos = this.worldToGrid(worldPos);
        const gridRadius = Math.ceil(radius / this.cellSize);

        let removed = 0;

        for (let dz = -gridRadius; dz <= gridRadius; dz++) {
            for (let dy = -gridRadius; dy <= gridRadius; dy++) {
                for (let dx = -gridRadius; dx <= gridRadius; dx++) {
                    const gx = gridPos.x + dx;
                    const gy = gridPos.y + dy;
                    const gz = gridPos.z + dz;

                    // 구 내부인지 확인
                    const cellCenter = this.gridToWorld(gx, gy, gz);
                    const dist = cellCenter.distanceTo(worldPos);

                    if (dist <= radius && this.get(gx, gy, gz) === 1) {
                        this.set(gx, gy, gz, 0);
                        removed++;
                    }
                }
            }
        }

        return removed;
    }

    /**
     * Marching Cubes로 메쉬 생성
     */
    toMesh() {
        console.time('Marching Cubes');

        const positions = [];
        const normals = [];

        // 각 큐브 처리
        for (let z = 0; z < this.gridSize.z - 1; z++) {
            for (let y = 0; y < this.gridSize.y - 1; y++) {
                for (let x = 0; x < this.gridSize.x - 1; x++) {
                    this._processCube(x, y, z, positions, normals);
                }
            }
        }

        console.timeEnd('Marching Cubes');
        console.log(`Generated ${positions.length / 9} triangles`);

        // Three.js geometry 생성
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));

        if (normals.length > 0) {
            geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
        } else {
            geometry.computeVertexNormals();
        }

        return geometry;
    }

    /**
     * 단일 큐브 처리 (Marching Cubes)
     */
    _processCube(x, y, z, positions, normals) {
        // 8개 코너의 값
        const corners = [
            this.get(x, y, z),
            this.get(x+1, y, z),
            this.get(x+1, y, z+1),
            this.get(x, y, z+1),
            this.get(x, y+1, z),
            this.get(x+1, y+1, z),
            this.get(x+1, y+1, z+1),
            this.get(x, y+1, z+1)
        ];

        // 큐브 인덱스 계산
        let cubeIndex = 0;
        for (let i = 0; i < 8; i++) {
            if (corners[i] > 0) cubeIndex |= (1 << i);
        }

        // 완전히 내부이거나 외부이면 스킵
        if (cubeIndex === 0 || cubeIndex === 255) return;

        // 엣지 테이블에서 교차하는 엣지 찾기
        const edges = EDGE_TABLE[cubeIndex];
        if (edges === 0) return;

        // 코너 월드 좌표
        const cornerPositions = [
            this.gridToWorld(x, y, z),
            this.gridToWorld(x+1, y, z),
            this.gridToWorld(x+1, y, z+1),
            this.gridToWorld(x, y, z+1),
            this.gridToWorld(x, y+1, z),
            this.gridToWorld(x+1, y+1, z),
            this.gridToWorld(x+1, y+1, z+1),
            this.gridToWorld(x, y+1, z+1)
        ];

        // 엣지 중점 계산
        const vertList = new Array(12);
        const edgeVertices = [
            [0, 1], [1, 2], [2, 3], [3, 0],
            [4, 5], [5, 6], [6, 7], [7, 4],
            [0, 4], [1, 5], [2, 6], [3, 7]
        ];

        for (let i = 0; i < 12; i++) {
            if (edges & (1 << i)) {
                const [a, b] = edgeVertices[i];
                vertList[i] = cornerPositions[a].clone().lerp(cornerPositions[b], 0.5);
            }
        }

        // 삼각형 생성
        const tris = TRI_TABLE[cubeIndex];
        for (let i = 0; tris[i] !== -1; i += 3) {
            const v0 = vertList[tris[i]];
            const v1 = vertList[tris[i + 1]];
            const v2 = vertList[tris[i + 2]];

            if (v0 && v1 && v2) {
                positions.push(v0.x, v0.y, v0.z);
                positions.push(v1.x, v1.y, v1.z);
                positions.push(v2.x, v2.y, v2.z);
            }
        }
    }
}

// Marching Cubes 룩업 테이블
const EDGE_TABLE = [
    0x0, 0x109, 0x203, 0x30a, 0x406, 0x50f, 0x605, 0x70c,
    0x80c, 0x905, 0xa0f, 0xb06, 0xc0a, 0xd03, 0xe09, 0xf00,
    0x190, 0x99, 0x393, 0x29a, 0x596, 0x49f, 0x795, 0x69c,
    0x99c, 0x895, 0xb9f, 0xa96, 0xd9a, 0xc93, 0xf99, 0xe90,
    0x230, 0x339, 0x33, 0x13a, 0x636, 0x73f, 0x435, 0x53c,
    0xa3c, 0xb35, 0x83f, 0x936, 0xe3a, 0xf33, 0xc39, 0xd30,
    0x3a0, 0x2a9, 0x1a3, 0xaa, 0x7a6, 0x6af, 0x5a5, 0x4ac,
    0xbac, 0xaa5, 0x9af, 0x8a6, 0xfaa, 0xea3, 0xda9, 0xca0,
    0x460, 0x569, 0x663, 0x76a, 0x66, 0x16f, 0x265, 0x36c,
    0xc6c, 0xd65, 0xe6f, 0xf66, 0x86a, 0x963, 0xa69, 0xb60,
    0x5f0, 0x4f9, 0x7f3, 0x6fa, 0x1f6, 0xff, 0x3f5, 0x2fc,
    0xdfc, 0xcf5, 0xfff, 0xef6, 0x9fa, 0x8f3, 0xbf9, 0xaf0,
    0x650, 0x759, 0x453, 0x55a, 0x256, 0x35f, 0x55, 0x15c,
    0xe5c, 0xf55, 0xc5f, 0xd56, 0xa5a, 0xb53, 0x859, 0x950,
    0x7c0, 0x6c9, 0x5c3, 0x4ca, 0x3c6, 0x2cf, 0x1c5, 0xcc,
    0xfcc, 0xec5, 0xdcf, 0xcc6, 0xbca, 0xac3, 0x9c9, 0x8c0,
    0x8c0, 0x9c9, 0xac3, 0xbca, 0xcc6, 0xdcf, 0xec5, 0xfcc,
    0xcc, 0x1c5, 0x2cf, 0x3c6, 0x4ca, 0x5c3, 0x6c9, 0x7c0,
    0x950, 0x859, 0xb53, 0xa5a, 0xd56, 0xc5f, 0xf55, 0xe5c,
    0x15c, 0x55, 0x35f, 0x256, 0x55a, 0x453, 0x759, 0x650,
    0xaf0, 0xbf9, 0x8f3, 0x9fa, 0xef6, 0xfff, 0xcf5, 0xdfc,
    0x2fc, 0x3f5, 0xff, 0x1f6, 0x6fa, 0x7f3, 0x4f9, 0x5f0,
    0xb60, 0xa69, 0x963, 0x86a, 0xf66, 0xe6f, 0xd65, 0xc6c,
    0x36c, 0x265, 0x16f, 0x66, 0x76a, 0x663, 0x569, 0x460,
    0xca0, 0xda9, 0xea3, 0xfaa, 0x8a6, 0x9af, 0xaa5, 0xbac,
    0x4ac, 0x5a5, 0x6af, 0x7a6, 0xaa, 0x1a3, 0x2a9, 0x3a0,
    0xd30, 0xc39, 0xf33, 0xe3a, 0x936, 0x83f, 0xb35, 0xa3c,
    0x53c, 0x435, 0x73f, 0x636, 0x13a, 0x33, 0x339, 0x230,
    0xe90, 0xf99, 0xc93, 0xd9a, 0xa96, 0xb9f, 0x895, 0x99c,
    0x69c, 0x795, 0x49f, 0x596, 0x29a, 0x393, 0x99, 0x190,
    0xf00, 0xe09, 0xd03, 0xc0a, 0xb06, 0xa0f, 0x905, 0x80c,
    0x70c, 0x605, 0x50f, 0x406, 0x30a, 0x203, 0x109, 0x0
];

const TRI_TABLE = [
    [-1],
    [0, 8, 3, -1],
    [0, 1, 9, -1],
    [1, 8, 3, 9, 8, 1, -1],
    [1, 2, 10, -1],
    [0, 8, 3, 1, 2, 10, -1],
    [9, 2, 10, 0, 2, 9, -1],
    [2, 8, 3, 2, 10, 8, 10, 9, 8, -1],
    [3, 11, 2, -1],
    [0, 11, 2, 8, 11, 0, -1],
    [1, 9, 0, 2, 3, 11, -1],
    [1, 11, 2, 1, 9, 11, 9, 8, 11, -1],
    [3, 10, 1, 11, 10, 3, -1],
    [0, 10, 1, 0, 8, 10, 8, 11, 10, -1],
    [3, 9, 0, 3, 11, 9, 11, 10, 9, -1],
    [9, 8, 10, 10, 8, 11, -1],
    [4, 7, 8, -1],
    [4, 3, 0, 7, 3, 4, -1],
    [0, 1, 9, 8, 4, 7, -1],
    [4, 1, 9, 4, 7, 1, 7, 3, 1, -1],
    [1, 2, 10, 8, 4, 7, -1],
    [3, 4, 7, 3, 0, 4, 1, 2, 10, -1],
    [9, 2, 10, 9, 0, 2, 8, 4, 7, -1],
    [2, 10, 9, 2, 9, 7, 2, 7, 3, 7, 9, 4, -1],
    [8, 4, 7, 3, 11, 2, -1],
    [11, 4, 7, 11, 2, 4, 2, 0, 4, -1],
    [9, 0, 1, 8, 4, 7, 2, 3, 11, -1],
    [4, 7, 11, 9, 4, 11, 9, 11, 2, 9, 2, 1, -1],
    [3, 10, 1, 3, 11, 10, 7, 8, 4, -1],
    [1, 11, 10, 1, 4, 11, 1, 0, 4, 7, 11, 4, -1],
    [4, 7, 8, 9, 0, 11, 9, 11, 10, 11, 0, 3, -1],
    [4, 7, 11, 4, 11, 9, 9, 11, 10, -1],
    [9, 5, 4, -1],
    [9, 5, 4, 0, 8, 3, -1],
    [0, 5, 4, 1, 5, 0, -1],
    [8, 5, 4, 8, 3, 5, 3, 1, 5, -1],
    [1, 2, 10, 9, 5, 4, -1],
    [3, 0, 8, 1, 2, 10, 4, 9, 5, -1],
    [5, 2, 10, 5, 4, 2, 4, 0, 2, -1],
    [2, 10, 5, 3, 2, 5, 3, 5, 4, 3, 4, 8, -1],
    [9, 5, 4, 2, 3, 11, -1],
    [0, 11, 2, 0, 8, 11, 4, 9, 5, -1],
    [0, 5, 4, 0, 1, 5, 2, 3, 11, -1],
    [2, 1, 5, 2, 5, 8, 2, 8, 11, 4, 8, 5, -1],
    [10, 3, 11, 10, 1, 3, 9, 5, 4, -1],
    [4, 9, 5, 0, 8, 1, 8, 10, 1, 8, 11, 10, -1],
    [5, 4, 0, 5, 0, 11, 5, 11, 10, 11, 0, 3, -1],
    [5, 4, 8, 5, 8, 10, 10, 8, 11, -1],
    [9, 7, 8, 5, 7, 9, -1],
    [9, 3, 0, 9, 5, 3, 5, 7, 3, -1],
    [0, 7, 8, 0, 1, 7, 1, 5, 7, -1],
    [1, 5, 3, 3, 5, 7, -1],
    [9, 7, 8, 9, 5, 7, 10, 1, 2, -1],
    [10, 1, 2, 9, 5, 0, 5, 3, 0, 5, 7, 3, -1],
    [8, 0, 2, 8, 2, 5, 8, 5, 7, 10, 5, 2, -1],
    [2, 10, 5, 2, 5, 3, 3, 5, 7, -1],
    [7, 9, 5, 7, 8, 9, 3, 11, 2, -1],
    [9, 5, 7, 9, 7, 2, 9, 2, 0, 2, 7, 11, -1],
    [2, 3, 11, 0, 1, 8, 1, 7, 8, 1, 5, 7, -1],
    [11, 2, 1, 11, 1, 7, 7, 1, 5, -1],
    [9, 5, 8, 8, 5, 7, 10, 1, 3, 10, 3, 11, -1],
    [5, 7, 0, 5, 0, 9, 7, 11, 0, 1, 0, 10, 11, 10, 0, -1],
    [11, 10, 0, 11, 0, 3, 10, 5, 0, 8, 0, 7, 5, 7, 0, -1],
    [11, 10, 5, 7, 11, 5, -1],
    [10, 6, 5, -1],
    [0, 8, 3, 5, 10, 6, -1],
    [9, 0, 1, 5, 10, 6, -1],
    [1, 8, 3, 1, 9, 8, 5, 10, 6, -1],
    [1, 6, 5, 2, 6, 1, -1],
    [1, 6, 5, 1, 2, 6, 3, 0, 8, -1],
    [9, 6, 5, 9, 0, 6, 0, 2, 6, -1],
    [5, 9, 8, 5, 8, 2, 5, 2, 6, 3, 2, 8, -1],
    [2, 3, 11, 10, 6, 5, -1],
    [11, 0, 8, 11, 2, 0, 10, 6, 5, -1],
    [0, 1, 9, 2, 3, 11, 5, 10, 6, -1],
    [5, 10, 6, 1, 9, 2, 9, 11, 2, 9, 8, 11, -1],
    [6, 3, 11, 6, 5, 3, 5, 1, 3, -1],
    [0, 8, 11, 0, 11, 5, 0, 5, 1, 5, 11, 6, -1],
    [3, 11, 6, 0, 3, 6, 0, 6, 5, 0, 5, 9, -1],
    [6, 5, 9, 6, 9, 11, 11, 9, 8, -1],
    [5, 10, 6, 4, 7, 8, -1],
    [4, 3, 0, 4, 7, 3, 6, 5, 10, -1],
    [1, 9, 0, 5, 10, 6, 8, 4, 7, -1],
    [10, 6, 5, 1, 9, 7, 1, 7, 3, 7, 9, 4, -1],
    [6, 1, 2, 6, 5, 1, 4, 7, 8, -1],
    [1, 2, 5, 5, 2, 6, 3, 0, 4, 3, 4, 7, -1],
    [8, 4, 7, 9, 0, 5, 0, 6, 5, 0, 2, 6, -1],
    [7, 3, 9, 7, 9, 4, 3, 2, 9, 5, 9, 6, 2, 6, 9, -1],
    [3, 11, 2, 7, 8, 4, 10, 6, 5, -1],
    [5, 10, 6, 4, 7, 2, 4, 2, 0, 2, 7, 11, -1],
    [0, 1, 9, 4, 7, 8, 2, 3, 11, 5, 10, 6, -1],
    [9, 2, 1, 9, 11, 2, 9, 4, 11, 7, 11, 4, 5, 10, 6, -1],
    [8, 4, 7, 3, 11, 5, 3, 5, 1, 5, 11, 6, -1],
    [5, 1, 11, 5, 11, 6, 1, 0, 11, 7, 11, 4, 0, 4, 11, -1],
    [0, 5, 9, 0, 6, 5, 0, 3, 6, 11, 6, 3, 8, 4, 7, -1],
    [6, 5, 9, 6, 9, 11, 4, 7, 9, 7, 11, 9, -1],
    [10, 4, 9, 6, 4, 10, -1],
    [4, 10, 6, 4, 9, 10, 0, 8, 3, -1],
    [10, 0, 1, 10, 6, 0, 6, 4, 0, -1],
    [8, 3, 1, 8, 1, 6, 8, 6, 4, 6, 1, 10, -1],
    [1, 4, 9, 1, 2, 4, 2, 6, 4, -1],
    [3, 0, 8, 1, 2, 9, 2, 4, 9, 2, 6, 4, -1],
    [0, 2, 4, 4, 2, 6, -1],
    [8, 3, 2, 8, 2, 4, 4, 2, 6, -1],
    [10, 4, 9, 10, 6, 4, 11, 2, 3, -1],
    [0, 8, 2, 2, 8, 11, 4, 9, 10, 4, 10, 6, -1],
    [3, 11, 2, 0, 1, 6, 0, 6, 4, 6, 1, 10, -1],
    [6, 4, 1, 6, 1, 10, 4, 8, 1, 2, 1, 11, 8, 11, 1, -1],
    [9, 6, 4, 9, 3, 6, 9, 1, 3, 11, 6, 3, -1],
    [8, 11, 1, 8, 1, 0, 11, 6, 1, 9, 1, 4, 6, 4, 1, -1],
    [3, 11, 6, 3, 6, 0, 0, 6, 4, -1],
    [6, 4, 8, 11, 6, 8, -1],
    [7, 10, 6, 7, 8, 10, 8, 9, 10, -1],
    [0, 7, 3, 0, 10, 7, 0, 9, 10, 6, 7, 10, -1],
    [10, 6, 7, 1, 10, 7, 1, 7, 8, 1, 8, 0, -1],
    [10, 6, 7, 10, 7, 1, 1, 7, 3, -1],
    [1, 2, 6, 1, 6, 8, 1, 8, 9, 8, 6, 7, -1],
    [2, 6, 9, 2, 9, 1, 6, 7, 9, 0, 9, 3, 7, 3, 9, -1],
    [7, 8, 0, 7, 0, 6, 6, 0, 2, -1],
    [7, 3, 2, 6, 7, 2, -1],
    [2, 3, 11, 10, 6, 8, 10, 8, 9, 8, 6, 7, -1],
    [2, 0, 7, 2, 7, 11, 0, 9, 7, 6, 7, 10, 9, 10, 7, -1],
    [1, 8, 0, 1, 7, 8, 1, 10, 7, 6, 7, 10, 2, 3, 11, -1],
    [11, 2, 1, 11, 1, 7, 10, 6, 1, 6, 7, 1, -1],
    [8, 9, 6, 8, 6, 7, 9, 1, 6, 11, 6, 3, 1, 3, 6, -1],
    [0, 9, 1, 11, 6, 7, -1],
    [7, 8, 0, 7, 0, 6, 3, 11, 0, 11, 6, 0, -1],
    [7, 11, 6, -1],
    [7, 6, 11, -1],
    [3, 0, 8, 11, 7, 6, -1],
    [0, 1, 9, 11, 7, 6, -1],
    [8, 1, 9, 8, 3, 1, 11, 7, 6, -1],
    [10, 1, 2, 6, 11, 7, -1],
    [1, 2, 10, 3, 0, 8, 6, 11, 7, -1],
    [2, 9, 0, 2, 10, 9, 6, 11, 7, -1],
    [6, 11, 7, 2, 10, 3, 10, 8, 3, 10, 9, 8, -1],
    [7, 2, 3, 6, 2, 7, -1],
    [7, 0, 8, 7, 6, 0, 6, 2, 0, -1],
    [2, 7, 6, 2, 3, 7, 0, 1, 9, -1],
    [1, 6, 2, 1, 8, 6, 1, 9, 8, 8, 7, 6, -1],
    [10, 7, 6, 10, 1, 7, 1, 3, 7, -1],
    [10, 7, 6, 1, 7, 10, 1, 8, 7, 1, 0, 8, -1],
    [0, 3, 7, 0, 7, 10, 0, 10, 9, 6, 10, 7, -1],
    [7, 6, 10, 7, 10, 8, 8, 10, 9, -1],
    [6, 8, 4, 11, 8, 6, -1],
    [3, 6, 11, 3, 0, 6, 0, 4, 6, -1],
    [8, 6, 11, 8, 4, 6, 9, 0, 1, -1],
    [9, 4, 6, 9, 6, 3, 9, 3, 1, 11, 3, 6, -1],
    [6, 8, 4, 6, 11, 8, 2, 10, 1, -1],
    [1, 2, 10, 3, 0, 11, 0, 6, 11, 0, 4, 6, -1],
    [4, 11, 8, 4, 6, 11, 0, 2, 9, 2, 10, 9, -1],
    [10, 9, 3, 10, 3, 2, 9, 4, 3, 11, 3, 6, 4, 6, 3, -1],
    [8, 2, 3, 8, 4, 2, 4, 6, 2, -1],
    [0, 4, 2, 4, 6, 2, -1],
    [1, 9, 0, 2, 3, 4, 2, 4, 6, 4, 3, 8, -1],
    [1, 9, 4, 1, 4, 2, 2, 4, 6, -1],
    [8, 1, 3, 8, 6, 1, 8, 4, 6, 6, 10, 1, -1],
    [10, 1, 0, 10, 0, 6, 6, 0, 4, -1],
    [4, 6, 3, 4, 3, 8, 6, 10, 3, 0, 3, 9, 10, 9, 3, -1],
    [10, 9, 4, 6, 10, 4, -1],
    [4, 9, 5, 7, 6, 11, -1],
    [0, 8, 3, 4, 9, 5, 11, 7, 6, -1],
    [5, 0, 1, 5, 4, 0, 7, 6, 11, -1],
    [11, 7, 6, 8, 3, 4, 3, 5, 4, 3, 1, 5, -1],
    [9, 5, 4, 10, 1, 2, 7, 6, 11, -1],
    [6, 11, 7, 1, 2, 10, 0, 8, 3, 4, 9, 5, -1],
    [7, 6, 11, 5, 4, 10, 4, 2, 10, 4, 0, 2, -1],
    [3, 4, 8, 3, 5, 4, 3, 2, 5, 10, 5, 2, 11, 7, 6, -1],
    [7, 2, 3, 7, 6, 2, 5, 4, 9, -1],
    [9, 5, 4, 0, 8, 6, 0, 6, 2, 6, 8, 7, -1],
    [3, 6, 2, 3, 7, 6, 1, 5, 0, 5, 4, 0, -1],
    [6, 2, 8, 6, 8, 7, 2, 1, 8, 4, 8, 5, 1, 5, 8, -1],
    [9, 5, 4, 10, 1, 6, 1, 7, 6, 1, 3, 7, -1],
    [1, 6, 10, 1, 7, 6, 1, 0, 7, 8, 7, 0, 9, 5, 4, -1],
    [4, 0, 10, 4, 10, 5, 0, 3, 10, 6, 10, 7, 3, 7, 10, -1],
    [7, 6, 10, 7, 10, 8, 5, 4, 10, 4, 8, 10, -1],
    [6, 9, 5, 6, 11, 9, 11, 8, 9, -1],
    [3, 6, 11, 0, 6, 3, 0, 5, 6, 0, 9, 5, -1],
    [0, 11, 8, 0, 5, 11, 0, 1, 5, 5, 6, 11, -1],
    [6, 11, 3, 6, 3, 5, 5, 3, 1, -1],
    [1, 2, 10, 9, 5, 11, 9, 11, 8, 11, 5, 6, -1],
    [0, 11, 3, 0, 6, 11, 0, 9, 6, 5, 6, 9, 1, 2, 10, -1],
    [11, 8, 5, 11, 5, 6, 8, 0, 5, 10, 5, 2, 0, 2, 5, -1],
    [6, 11, 3, 6, 3, 5, 2, 10, 3, 10, 5, 3, -1],
    [5, 8, 9, 5, 2, 8, 5, 6, 2, 3, 8, 2, -1],
    [9, 5, 6, 9, 6, 0, 0, 6, 2, -1],
    [1, 5, 8, 1, 8, 0, 5, 6, 8, 3, 8, 2, 6, 2, 8, -1],
    [1, 5, 6, 2, 1, 6, -1],
    [1, 3, 6, 1, 6, 10, 3, 8, 6, 5, 6, 9, 8, 9, 6, -1],
    [10, 1, 0, 10, 0, 6, 9, 5, 0, 5, 6, 0, -1],
    [0, 3, 8, 5, 6, 10, -1],
    [10, 5, 6, -1],
    [11, 5, 10, 7, 5, 11, -1],
    [11, 5, 10, 11, 7, 5, 8, 3, 0, -1],
    [5, 11, 7, 5, 10, 11, 1, 9, 0, -1],
    [10, 7, 5, 10, 11, 7, 9, 8, 1, 8, 3, 1, -1],
    [11, 1, 2, 11, 7, 1, 7, 5, 1, -1],
    [0, 8, 3, 1, 2, 7, 1, 7, 5, 7, 2, 11, -1],
    [9, 7, 5, 9, 2, 7, 9, 0, 2, 2, 11, 7, -1],
    [7, 5, 2, 7, 2, 11, 5, 9, 2, 3, 2, 8, 9, 8, 2, -1],
    [2, 5, 10, 2, 3, 5, 3, 7, 5, -1],
    [8, 2, 0, 8, 5, 2, 8, 7, 5, 10, 2, 5, -1],
    [9, 0, 1, 5, 10, 3, 5, 3, 7, 3, 10, 2, -1],
    [9, 8, 2, 9, 2, 1, 8, 7, 2, 10, 2, 5, 7, 5, 2, -1],
    [1, 3, 5, 3, 7, 5, -1],
    [0, 8, 7, 0, 7, 1, 1, 7, 5, -1],
    [9, 0, 3, 9, 3, 5, 5, 3, 7, -1],
    [9, 8, 7, 5, 9, 7, -1],
    [5, 8, 4, 5, 10, 8, 10, 11, 8, -1],
    [5, 0, 4, 5, 11, 0, 5, 10, 11, 11, 3, 0, -1],
    [0, 1, 9, 8, 4, 10, 8, 10, 11, 10, 4, 5, -1],
    [10, 11, 4, 10, 4, 5, 11, 3, 4, 9, 4, 1, 3, 1, 4, -1],
    [2, 5, 1, 2, 8, 5, 2, 11, 8, 4, 5, 8, -1],
    [0, 4, 11, 0, 11, 3, 4, 5, 11, 2, 11, 1, 5, 1, 11, -1],
    [0, 2, 5, 0, 5, 9, 2, 11, 5, 4, 5, 8, 11, 8, 5, -1],
    [9, 4, 5, 2, 11, 3, -1],
    [2, 5, 10, 3, 5, 2, 3, 4, 5, 3, 8, 4, -1],
    [5, 10, 2, 5, 2, 4, 4, 2, 0, -1],
    [3, 10, 2, 3, 5, 10, 3, 8, 5, 4, 5, 8, 0, 1, 9, -1],
    [5, 10, 2, 5, 2, 4, 1, 9, 2, 9, 4, 2, -1],
    [8, 4, 5, 8, 5, 3, 3, 5, 1, -1],
    [0, 4, 5, 1, 0, 5, -1],
    [8, 4, 5, 8, 5, 3, 9, 0, 5, 0, 3, 5, -1],
    [9, 4, 5, -1],
    [4, 11, 7, 4, 9, 11, 9, 10, 11, -1],
    [0, 8, 3, 4, 9, 7, 9, 11, 7, 9, 10, 11, -1],
    [1, 10, 11, 1, 11, 4, 1, 4, 0, 7, 4, 11, -1],
    [3, 1, 4, 3, 4, 8, 1, 10, 4, 7, 4, 11, 10, 11, 4, -1],
    [4, 11, 7, 9, 11, 4, 9, 2, 11, 9, 1, 2, -1],
    [9, 7, 4, 9, 11, 7, 9, 1, 11, 2, 11, 1, 0, 8, 3, -1],
    [11, 7, 4, 11, 4, 2, 2, 4, 0, -1],
    [11, 7, 4, 11, 4, 2, 8, 3, 4, 3, 2, 4, -1],
    [2, 9, 10, 2, 7, 9, 2, 3, 7, 7, 4, 9, -1],
    [9, 10, 7, 9, 7, 4, 10, 2, 7, 8, 7, 0, 2, 0, 7, -1],
    [3, 7, 10, 3, 10, 2, 7, 4, 10, 1, 10, 0, 4, 0, 10, -1],
    [1, 10, 2, 8, 7, 4, -1],
    [4, 9, 1, 4, 1, 7, 7, 1, 3, -1],
    [4, 9, 1, 4, 1, 7, 0, 8, 1, 8, 7, 1, -1],
    [4, 0, 3, 7, 4, 3, -1],
    [4, 8, 7, -1],
    [9, 10, 8, 10, 11, 8, -1],
    [3, 0, 9, 3, 9, 11, 11, 9, 10, -1],
    [0, 1, 10, 0, 10, 8, 8, 10, 11, -1],
    [3, 1, 10, 11, 3, 10, -1],
    [1, 2, 11, 1, 11, 9, 9, 11, 8, -1],
    [3, 0, 9, 3, 9, 11, 1, 2, 9, 2, 11, 9, -1],
    [0, 2, 11, 8, 0, 11, -1],
    [3, 2, 11, -1],
    [2, 3, 8, 2, 8, 10, 10, 8, 9, -1],
    [9, 10, 2, 0, 9, 2, -1],
    [2, 3, 8, 2, 8, 10, 0, 1, 8, 1, 10, 8, -1],
    [1, 10, 2, -1],
    [1, 3, 8, 9, 1, 8, -1],
    [0, 9, 1, -1],
    [0, 3, 8, -1],
    [-1]
];

// 전역으로 내보내기
window.VoxelGrid = VoxelGrid;
