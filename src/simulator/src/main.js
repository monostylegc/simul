/**
 * Spine Surgery Simulator - Three.js Frontend
 * 복셀 기반 드릴링 시스템
 */

// ============================================================================
// 전역 변수
// ============================================================================
let scene, camera, renderer, controls;
let raycaster, mouse;
let meshes = {};           // 원본 STL 메쉬 (표시용)
let voxelMeshes = {};      // 복셀화된 메쉬 (드릴링용)
let voxelGrids = {};       // VoxelGrid 인스턴스
let drillPreview = null;
let currentTool = null;  // null=도구 없음, 'drill'=드릴 등
let isMouseDown = false;
let isDrillInitialized = false;
let gridHelper = null;     // 그리드 헬퍼 (모델 크기에 맞게 동적 조절)
let axesHelper = null;     // 축 헬퍼
let drillHighlight = null;         // 드릴 영향 범위 하이라이트 (InstancedMesh)
const MAX_PREVIEW_VOXELS = 5000;   // 최대 프리뷰 복셀 수

// NRRD 관련
let pendingNRRD = null;    // 로딩된 NRRD 데이터 (적용 전)

// Undo/Redo 히스토리
const historyStack = [];   // Undo 스택
const redoStack = [];      // Redo 스택
const MAX_HISTORY = 30;    // 최대 히스토리 개수
let isUndoing = false;     // Undo 중인지 여부


const drillSettings = {
    radius: 5,
    resolution: 64  // 복셀 해상도 (기본값 상향)
};

const nrrdSettings = {
    resolution: 128,
    threshold: 0.3
};

let frameCount = 0;
let lastTime = performance.now();

// ============================================================================
// 초기화
// ============================================================================
function init() {
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);

    const container = document.getElementById('canvas-container');
    const width = container.clientWidth;
    const height = container.clientHeight;

    camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 2000);
    camera.position.set(150, 150, 150);
    camera.lookAt(0, 0, 0);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    container.appendChild(renderer.domElement);

    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    // CAD 스타일 네비게이션: 우클릭=회전, 중클릭=팬, 휠=줌, 좌클릭=회전(도구 없을 때)
    controls.mouseButtons = {
        LEFT: THREE.MOUSE.ROTATE,
        MIDDLE: THREE.MOUSE.PAN,
        RIGHT: THREE.MOUSE.ROTATE
    };

    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    setupLights();

    // Grid (초기 그리드 - 모델 로드 후 크기 자동 조절됨)
    gridHelper = new THREE.GridHelper(300, 30, 0x444444, 0x333333);
    scene.add(gridHelper);

    // Axes
    axesHelper = new THREE.AxesHelper(50);
    scene.add(axesHelper);

    createDrillPreview();
    setupEventListeners();

    // 자동으로 샘플 STL 로드
    loadSampleSTL();

    animate();

    console.log('Three.js initialized (Voxel mode)');
}

// ============================================================================
// 조명
// ============================================================================
function setupLights() {
    const ambient = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambient);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(100, 200, 100);
    dirLight.castShadow = true;
    scene.add(dirLight);

    const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.3);
    dirLight2.position.set(-100, 50, -100);
    scene.add(dirLight2);
}

// ============================================================================
// 드릴 프리뷰 (구체)
// ============================================================================
function createDrillPreview() {
    drillPreview = new THREE.Group();
    drillPreview.visible = false;
    drillPreview.renderOrder = 999;
    buildDrillPreviewComponents();
    scene.add(drillPreview);
}

/**
 * 드릴 프리뷰 구성요소 생성 (회색 반투명 구체)
 */
function buildDrillPreviewComponents() {
    const radius = drillSettings.radius;

    // 회색 반투명 구체
    const geom = new THREE.SphereGeometry(radius, 24, 16);
    const mat = new THREE.MeshBasicMaterial({
        color: 0xaaaaaa,
        transparent: true,
        opacity: 0.35,
        depthTest: false
    });
    const sphere = new THREE.Mesh(geom, mat);
    sphere.renderOrder = 999;
    drillPreview.add(sphere);
}

function updateDrillPreviewSize() {
    if (!drillPreview) return;

    // 기존 구성요소 제거
    while (drillPreview.children.length > 0) {
        const child = drillPreview.children[0];
        drillPreview.remove(child);
        if (child.geometry) child.geometry.dispose();
        if (child.material) child.material.dispose();
    }

    // 새 구성요소 생성
    buildDrillPreviewComponents();
}

// ============================================================================
// STL 로딩 설정
// ============================================================================
const loadSettings = {
    keepOriginalPosition: true,  // 원본 좌표 유지 (3D Slicer 등에서 내보낸 파일용)
    centerToOrigin: true         // 전체 모델을 원점 중심으로 이동
};

// ============================================================================
// STL 로딩
// ============================================================================
function loadSampleSTL() {
    clearAllMeshes();

    console.log('Loading STL manifest...');

    // manifest.json에서 파일 목록 로드
    fetch('stl/manifest.json')
        .then(response => {
            if (!response.ok) {
                throw new Error('manifest.json not found');
            }
            return response.json();
        })
        .then(manifest => {
            console.log('Manifest loaded:', manifest);
            loadSTLFilesFromList(manifest.files);
        })
        .catch(error => {
            console.error('Manifest load failed:', error);
            // 폴백: 기본 파일 로드
            console.log('Fallback: loading default files...');
            loadSTLFilesFromList(['L5.stl', 'L4.stl', 'disc.stl']);
        });
}

/**
 * STL 파일 목록에서 모든 파일 로드
 * @param {string[]} fileList - STL 파일명 배열
 */
function loadSTLFilesFromList(fileList) {
    const loader = new THREE.STLLoader();
    let loadedCount = 0;
    const totalFiles = fileList.length;
    const geometries = {};

    console.log(`Loading ${totalFiles} STL files...`);

    fileList.forEach(filename => {
        const name = filename.replace(/\.[^/.]+$/, '');  // 확장자 제거

        loader.load(`stl/${filename}`,
            (geometry) => {
                console.log(`${name} loaded:`, geometry.attributes.position.count, 'vertices');
                geometries[name] = geometry;
                loadedCount++;
                if (loadedCount >= totalFiles) processLoadedGeometries(geometries);
            },
            (progress) => {
                if (progress.total) {
                    console.log(`${name} progress:`, Math.round(progress.loaded/progress.total*100) + '%');
                }
            },
            (error) => console.error(`${name} error:`, error)
        );
    });
}

/**
 * 로드된 geometry들을 처리
 * - keepOriginalPosition: true면 원본 좌표 유지
 * - centerToOrigin: true면 전체 모델 중심을 원점으로 이동
 */
function processLoadedGeometries(geometries) {
    if (loadSettings.keepOriginalPosition) {
        // 원본 좌표 유지 - 3D Slicer 등에서 내보낸 파일
        Object.entries(geometries).forEach(([name, geometry]) => {
            addSTLMesh(geometry, name, getColorForName(name), null);
        });

        // 전체 모델을 원점 중심으로 이동 (선택적)
        if (loadSettings.centerToOrigin) {
            centerAllMeshes();
        }
    } else {
        // 기존 방식: 강제 재배치
        arrangeVertebrae(geometries);
    }

    onAllLoaded();
}

/**
 * 이름에 따른 색상 반환
 */
function getColorForName(name) {
    const colorMap = {
        'L1': 0xe6d5c3, 'L2': 0xe6d5c3, 'L3': 0xe6d5c3,
        'L4': 0xd4c4b0, 'L5': 0xe6d5c3, 'S1': 0xc9b8a5,
        'disc': 0x6ba3d6,      // 디스크: 파란색 계열
        'ligament': 0xd4a574,  // 인대: 갈색 계열
        'nerve': 0xf5d67a,     // 신경: 노란색 계열
        'default': 0xe6d5c3
    };

    // 이름에서 키워드 찾기
    const lowerName = name.toLowerCase();
    for (const [key, color] of Object.entries(colorMap)) {
        if (lowerName.includes(key.toLowerCase())) {
            return color;
        }
    }
    return colorMap.default;
}

/**
 * 모든 메쉬를 전체 중심 기준으로 원점에 배치
 * geometry 정점 자체를 이동하여 정확한 좌표 변환 보장
 */
function centerAllMeshes() {
    // 전체 바운딩 박스 계산
    const box = new THREE.Box3();
    Object.values(meshes).forEach(mesh => {
        box.expandByObject(mesh);
    });

    if (box.isEmpty()) return;

    // 전체 모델 중심 계산
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());

    // geometry 정점을 직접 이동하여 원점 중심 배치
    // (mesh.position 대신 vertex를 이동해야 복셀화/레이캐스트 정확도 보장)
    Object.values(meshes).forEach(mesh => {
        const worldOffset = center.clone().sub(mesh.position);
        mesh.geometry.translate(-worldOffset.x, -worldOffset.y, -worldOffset.z);
        mesh.position.set(0, 0, 0);
        mesh.geometry.computeBoundingBox();
    });

    // 그리드/축 헬퍼를 모델 크기에 맞게 업데이트
    updateGridToModel();

    console.log(`모델 중심을 원점으로 이동 (오프셋: ${center.x.toFixed(1)}, ${center.y.toFixed(1)}, ${center.z.toFixed(1)})`);
    console.log(`모델 크기: ${size.x.toFixed(1)} x ${size.y.toFixed(1)} x ${size.z.toFixed(1)} mm`);
}

/**
 * 모델 크기에 맞게 그리드와 축 헬퍼 동적 업데이트
 */
function updateGridToModel() {
    const box = new THREE.Box3();
    Object.values(meshes).forEach(mesh => {
        box.expandByObject(mesh);
    });

    if (box.isEmpty()) return;

    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);

    // 기존 그리드/축 제거
    if (gridHelper) {
        scene.remove(gridHelper);
        gridHelper.geometry.dispose();
    }
    if (axesHelper) {
        scene.remove(axesHelper);
        axesHelper.geometry.dispose();
    }

    // 모델 크기에 맞는 그리드 생성 (모델의 2배 크기)
    const gridSize = Math.ceil(maxDim * 2 / 10) * 10;
    const step = gridSize <= 100 ? 5 : 10;
    const divisions = Math.round(gridSize / step);

    gridHelper = new THREE.GridHelper(gridSize, divisions, 0x444444, 0x333333);
    scene.add(gridHelper);

    // 축 헬퍼도 모델에 비례
    axesHelper = new THREE.AxesHelper(maxDim * 0.4);
    scene.add(axesHelper);

    console.log(`그리드: ${gridSize}mm (${step}mm 간격, ${divisions} 분할)`);
}

/**
 * 모델 좌표/크기 정보를 사이드바에 표시
 */
function updateModelInfo() {
    const infoDiv = document.getElementById('model-info');
    if (!infoDiv) return;

    const box = new THREE.Box3();
    const targetMeshes = isDrillInitialized ? voxelMeshes : meshes;
    Object.values(targetMeshes).forEach(mesh => {
        if (mesh.visible !== false) box.expandByObject(mesh);
    });

    if (box.isEmpty()) {
        infoDiv.innerHTML = '';
        return;
    }

    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const min = box.min;
    const max = box.max;

    infoDiv.innerHTML = `
        <div style="padding: 8px; background: rgba(79, 195, 247, 0.1); border: 1px solid rgba(79, 195, 247, 0.3); border-radius: 4px; margin-top: 8px;">
            <div style="color: #4fc3f7; font-size: 11px; font-weight: bold; margin-bottom: 4px;">Model Info</div>
            <div style="font-size: 11px; color: #ccc;">크기: ${size.x.toFixed(1)} x ${size.y.toFixed(1)} x ${size.z.toFixed(1)} mm</div>
            <div style="font-size: 11px; color: #ccc;">중심: (${center.x.toFixed(1)}, ${center.y.toFixed(1)}, ${center.z.toFixed(1)})</div>
            <div style="font-size: 10px; color: #888; margin-top: 2px;">
                min: (${min.x.toFixed(1)}, ${min.y.toFixed(1)}, ${min.z.toFixed(1)})<br>
                max: (${max.x.toFixed(1)}, ${max.y.toFixed(1)}, ${max.z.toFixed(1)})
            </div>
        </div>
    `;
}

/**
 * 기존 방식: L4, L5를 강제 재배치 (레거시)
 */
function arrangeVertebrae(geometries) {
    // 각 geometry의 bounding box 계산
    geometries.L5.computeBoundingBox();
    geometries.L4.computeBoundingBox();

    const l5Box = geometries.L5.boundingBox;
    const l4Box = geometries.L4.boundingBox;

    // L5 중심 계산
    const l5Center = new THREE.Vector3();
    l5Box.getCenter(l5Center);

    // L4 중심 계산
    const l4Center = new THREE.Vector3();
    l4Box.getCenter(l4Center);

    // L5를 원점에 배치 (중심 기준)
    const l5Offset = { x: -l5Center.x, y: -l5Center.y, z: -l5Center.z };

    // L4를 L5 위에 배치 (Y축으로 분리)
    const l5Height = l5Box.max.y - l5Box.min.y;
    const gap = 5;
    const l4Offset = {
        x: -l4Center.x,
        y: -l5Center.y + l5Height / 2 + gap + (l4Box.max.y - l4Box.min.y) / 2,
        z: -l4Center.z
    };

    // 메쉬 추가
    addSTLMesh(geometries.L5, 'L5', 0xe6d5c3, l5Offset);
    addSTLMesh(geometries.L4, 'L4', 0xd4c4b0, l4Offset);
}

function onAllLoaded() {
    console.log('All STL files loaded');
    updateGridToModel();
    fitCameraToScene();
    updateModelList();
    isDrillInitialized = false;  // 새로 로드되면 복셀 초기화 필요
}

function addSTLMesh(geometry, name, color, offset = null) {
    // 법선 계산
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();

    const material = new THREE.MeshPhongMaterial({
        color: color,
        flatShading: false,
        side: THREE.DoubleSide,
        shininess: 30
    });

    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = name;
    mesh.userData.drillable = true;
    mesh.userData.color = color;
    mesh.castShadow = true;
    mesh.receiveShadow = true;

    // offset이 주어지면 사용, 아니면 원점에 배치
    if (offset) {
        mesh.position.set(offset.x, offset.y, offset.z);
    }

    scene.add(mesh);
    meshes[name] = mesh;

    console.log(`Added mesh: ${name} at position (${mesh.position.x}, ${mesh.position.y}, ${mesh.position.z})`);
}

function fitCameraToScene() {
    const box = new THREE.Box3();
    Object.values(meshes).forEach(mesh => {
        box.expandByObject(mesh);
    });

    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());

    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * (Math.PI / 180);
    const cameraDistance = maxDim / (2 * Math.tan(fov / 2)) * 2;

    camera.position.set(
        center.x + cameraDistance * 0.7,
        center.y + cameraDistance * 0.5,
        center.z + cameraDistance * 0.7
    );
    camera.lookAt(center);
    controls.target.copy(center);
    controls.update();
}

function clearAllMeshes() {
    // 원본 메쉬 제거
    Object.keys(meshes).forEach(key => {
        scene.remove(meshes[key]);
        if (meshes[key].geometry) meshes[key].geometry.dispose();
        if (meshes[key].material) meshes[key].material.dispose();
    });
    meshes = {};

    // 복셀 메쉬 제거
    Object.keys(voxelMeshes).forEach(key => {
        scene.remove(voxelMeshes[key]);
        if (voxelMeshes[key].geometry) voxelMeshes[key].geometry.dispose();
        if (voxelMeshes[key].material) voxelMeshes[key].material.dispose();
    });
    voxelMeshes = {};
    voxelGrids = {};
    clearDrillHighlight();

    isDrillInitialized = false;
    updateModelList();
}

// ============================================================================
// 드릴 영향 범위 하이라이트 (InstancedMesh)
// ============================================================================

/**
 * 드릴 하이라이트 InstancedMesh 생성 (복셀 초기화 후 호출)
 */
function createDrillHighlight() {
    clearDrillHighlight();

    const firstGrid = Object.values(voxelGrids)[0];
    if (!firstGrid) return;

    const s = firstGrid.cellSize * 0.96;
    const boxGeom = new THREE.BoxGeometry(s, s, s);
    const material = new THREE.MeshBasicMaterial({
        color: 0xff2222,
        transparent: true,
        opacity: 0.45,
        depthTest: false
    });

    drillHighlight = new THREE.InstancedMesh(boxGeom, material, MAX_PREVIEW_VOXELS);
    drillHighlight.count = 0;
    drillHighlight.visible = false;
    drillHighlight.renderOrder = 998;
    scene.add(drillHighlight);
}

/**
 * 마우스 위치에서 드릴 영향 범위 복셀 하이라이트 업데이트
 */
function updateDrillHighlight(intersection) {
    if (!isDrillInitialized || !intersection || !drillHighlight) {
        if (drillHighlight) drillHighlight.visible = false;
        return;
    }

    const point = intersection.point;

    const matrix = new THREE.Matrix4();
    let count = 0;

    Object.values(voxelGrids).forEach(grid => {
        const affected = grid.previewDrill(point, drillSettings.radius);
        affected.forEach(pos => {
            if (count >= MAX_PREVIEW_VOXELS) return;
            const worldPos = grid.gridToWorld(pos.x, pos.y, pos.z);
            matrix.setPosition(worldPos.x, worldPos.y, worldPos.z);
            drillHighlight.setMatrixAt(count, matrix);
            count++;
        });
    });

    drillHighlight.count = count;
    drillHighlight.instanceMatrix.needsUpdate = true;
    drillHighlight.visible = count > 0;

    // 상태바에 영향 복셀 수 표시
    const dInfo = document.getElementById('drill-d-info');
    if (dInfo) dInfo.textContent = `${count} voxels`;
}

/**
 * 드릴 하이라이트 제거
 */
function clearDrillHighlight() {
    if (drillHighlight) {
        scene.remove(drillHighlight);
        if (drillHighlight.geometry) drillHighlight.geometry.dispose();
        if (drillHighlight.material) drillHighlight.material.dispose();
        drillHighlight = null;
    }
}

// ============================================================================
// 복셀화 - 드릴 모드 진입 시 초기화
// ============================================================================
function initializeVoxels() {
    if (isDrillInitialized) return;

    console.log('Initializing voxels...');
    document.getElementById('current-tool').textContent = 'Drill (초기화 중...)';

    // 약간의 지연 후 실행 (UI 업데이트를 위해)
    setTimeout(() => {
        Object.entries(meshes).forEach(([name, mesh]) => {
            if (!mesh.userData.drillable) return;

            console.log(`Voxelizing ${name}...`);

            // VoxelGrid 생성
            const grid = new VoxelGrid(drillSettings.resolution);
            grid.fromMesh(mesh);
            voxelGrids[name] = grid;

            // 복셀 메쉬 생성
            const voxelGeometry = grid.toMesh();
            const material = new THREE.MeshPhongMaterial({
                color: mesh.userData.color,
                flatShading: false,
                side: THREE.DoubleSide,
                shininess: 30
            });

            const voxelMesh = new THREE.Mesh(voxelGeometry, material);
            voxelMesh.name = name + '_voxel';
            voxelMesh.userData.gridName = name;
            voxelMesh.castShadow = true;
            voxelMesh.receiveShadow = true;

            scene.add(voxelMesh);
            voxelMeshes[name] = voxelMesh;

            // 원본 메쉬 숨기기
            mesh.visible = false;

            console.log(`${name} voxelized`);
        });

        isDrillInitialized = true;
        createDrillHighlight();
        document.getElementById('current-tool').textContent = 'Drill';
        updateModelList();
        console.log('Voxel initialization complete');
    }, 50);
}

// ============================================================================
// 드릴링 - 복셀 제거 후 메쉬 재생성
// ============================================================================
function performDrill(intersection) {
    if (!isDrillInitialized) return;

    const radius = drillSettings.radius;
    const point = intersection.point;

    let totalRemoved = 0;

    Object.entries(voxelGrids).forEach(([name, grid]) => {
        // 구체 드릴링
        const removed = grid.drillWithSphere(point, radius);
        totalRemoved += removed;

        if (removed > 0) {
            // 메쉬 재생성
            const newGeometry = grid.toMesh();

            // 기존 메쉬 교체
            const oldMesh = voxelMeshes[name];
            oldMesh.geometry.dispose();
            oldMesh.geometry = newGeometry;
        }
    });

    if (totalRemoved > 0) {
        console.log(`Drilled: ${totalRemoved} voxels (R=${radius}mm, sphere)`);
        // 드릴 후 하이라이트 숨김 (다음 마우스 이동 시 재계산)
        if (drillHighlight) drillHighlight.visible = false;
        updateModelList();
    }
}

/**
 * 드릴링 전 스냅샷 저장 (Undo용)
 */
function saveSnapshot() {
    const snapshot = {};
    Object.entries(voxelGrids).forEach(([name, grid]) => {
        snapshot[name] = grid.createSnapshot();
    });

    historyStack.push(snapshot);

    // 최대 개수 초과 시 오래된 것 제거
    if (historyStack.length > MAX_HISTORY) {
        historyStack.shift();
    }

    // 새 동작 시 Redo 스택 초기화
    if (!isUndoing) {
        redoStack.length = 0;
    }

    updateUndoRedoButtons();
}

/**
 * Undo - 이전 상태로 복원
 */
function undo() {
    if (historyStack.length === 0) return;

    isUndoing = true;

    // 현재 상태를 Redo 스택에 저장
    const currentSnapshot = {};
    Object.entries(voxelGrids).forEach(([name, grid]) => {
        currentSnapshot[name] = grid.createSnapshot();
    });
    redoStack.push(currentSnapshot);

    // 이전 상태 복원
    const prevSnapshot = historyStack.pop();
    Object.entries(prevSnapshot).forEach(([name, data]) => {
        if (voxelGrids[name]) {
            voxelGrids[name].restoreSnapshot(data);
            // 메쉬 재생성
            const newGeometry = voxelGrids[name].toMesh();
            voxelMeshes[name].geometry.dispose();
            voxelMeshes[name].geometry = newGeometry;
        }
    });

    isUndoing = false;
    updateModelList();
    updateUndoRedoButtons();
    console.log('Undo 완료');
}

/**
 * Redo - 다시 실행
 */
function redo() {
    if (redoStack.length === 0) return;

    // 현재 상태를 History 스택에 저장
    const currentSnapshot = {};
    Object.entries(voxelGrids).forEach(([name, grid]) => {
        currentSnapshot[name] = grid.createSnapshot();
    });
    historyStack.push(currentSnapshot);

    // Redo 상태 복원
    const nextSnapshot = redoStack.pop();
    Object.entries(nextSnapshot).forEach(([name, data]) => {
        if (voxelGrids[name]) {
            voxelGrids[name].restoreSnapshot(data);
            // 메쉬 재생성
            const newGeometry = voxelGrids[name].toMesh();
            voxelMeshes[name].geometry.dispose();
            voxelMeshes[name].geometry = newGeometry;
        }
    });

    updateModelList();
    updateUndoRedoButtons();
    console.log('Redo 완료');
}

/**
 * Undo/Redo 버튼 상태 업데이트
 */
function updateUndoRedoButtons() {
    const undoBtn = document.getElementById('btn-undo');
    const redoBtn = document.getElementById('btn-redo');
    const undoCount = document.getElementById('undo-count');
    const redoCount = document.getElementById('redo-count');

    if (undoBtn) {
        undoBtn.disabled = historyStack.length === 0;
        undoBtn.style.opacity = historyStack.length === 0 ? 0.5 : 1;
    }
    if (redoBtn) {
        redoBtn.disabled = redoStack.length === 0;
        redoBtn.style.opacity = redoStack.length === 0 ? 0.5 : 1;
    }
    if (undoCount) {
        undoCount.textContent = historyStack.length;
    }
    if (redoCount) {
        redoCount.textContent = redoStack.length;
    }
}


// ============================================================================
// 이벤트
// ============================================================================
function setupEventListeners() {
    const container = document.getElementById('canvas-container');

    // pointer events 사용 (OrbitControls가 pointerdown에서 preventDefault 호출하여 mousedown 차단)
    container.addEventListener('pointermove', onMouseMove);
    container.addEventListener('pointerdown', onMouseDown);
    container.addEventListener('pointerup', onMouseUp);
    window.addEventListener('resize', onWindowResize);

    // 도구 버튼
    document.querySelectorAll('.tool-btn[data-tool]').forEach(btn => {
        btn.addEventListener('click', () => setTool(btn.dataset.tool));
    });

    // 슬라이더
    document.getElementById('voxel-resolution').addEventListener('input', (e) => {
        drillSettings.resolution = parseInt(e.target.value);
        document.getElementById('voxel-resolution-value').textContent = drillSettings.resolution;
    });

    document.getElementById('btn-revoxelize').addEventListener('click', () => {
        if (Object.keys(meshes).length === 0) {
            alert('먼저 STL 파일을 로드하세요');
            return;
        }
        // 기존 복셀 메쉬 제거
        Object.keys(voxelMeshes).forEach(key => {
            scene.remove(voxelMeshes[key]);
            if (voxelMeshes[key].geometry) voxelMeshes[key].geometry.dispose();
            if (voxelMeshes[key].material) voxelMeshes[key].material.dispose();
        });
        voxelMeshes = {};
        voxelGrids = {};
        isDrillInitialized = false;

        // 원본 메쉬 다시 표시
        Object.values(meshes).forEach(m => m.visible = true);

        // 재복셀화
        initializeVoxels();
    });

    document.getElementById('drill-radius').addEventListener('input', (e) => {
        drillSettings.radius = parseFloat(e.target.value);
        document.getElementById('drill-radius-value').textContent = drillSettings.radius;
        updateDrillPreviewSize();
        updateDrillStatus();
    });

    // 버튼
    document.getElementById('btn-load-sample').addEventListener('click', loadSampleSTL);

    // 드래그 앤 드롭 영역
    const dropZone = document.getElementById('drop-zone');

    dropZone.addEventListener('click', () => {
        document.getElementById('file-input').click();
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#e94560';
        dropZone.style.background = 'rgba(233, 69, 96, 0.1)';
    });

    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#4fc3f7';
        dropZone.style.background = 'transparent';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#4fc3f7';
        dropZone.style.background = 'transparent';

        const files = Array.from(e.dataTransfer.files).filter(
            f => f.name.toLowerCase().endsWith('.stl')
        );

        if (files.length === 0) {
            alert('STL 파일만 지원됩니다');
            return;
        }

        if (files.length === 1) {
            loadSTLFile(files[0]);
        } else {
            loadMultipleSTLFiles(files);
        }
    });

    document.getElementById('file-input').addEventListener('change', (e) => {
        const files = e.target.files;
        if (files.length === 1) {
            loadSTLFile(files[0]);
        } else if (files.length > 1) {
            loadMultipleSTLFiles(files);
        }
        // 같은 파일 다시 선택 가능하도록 초기화
        e.target.value = '';
    });

    // 좌표 설정 체크박스
    const keepPosCheckbox = document.getElementById('chk-keep-position');
    const centerOriginCheckbox = document.getElementById('chk-center-origin');

    if (keepPosCheckbox) {
        keepPosCheckbox.addEventListener('change', (e) => {
            loadSettings.keepOriginalPosition = e.target.checked;
            console.log('원본 좌표 유지:', loadSettings.keepOriginalPosition);
        });
    }

    if (centerOriginCheckbox) {
        centerOriginCheckbox.addEventListener('change', (e) => {
            loadSettings.centerToOrigin = e.target.checked;
            console.log('원점 중심 이동:', loadSettings.centerToOrigin);
        });
    }

    document.getElementById('btn-clear-all').addEventListener('click', clearAllMeshes);

    // NRRD 로딩
    document.getElementById('btn-load-nrrd').addEventListener('click', () => {
        document.getElementById('nrrd-input').click();
    });

    document.getElementById('nrrd-input').addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) loadNRRDFile(file);
    });

    document.getElementById('nrrd-resolution').addEventListener('input', (e) => {
        nrrdSettings.resolution = parseInt(e.target.value);
        document.getElementById('nrrd-resolution-value').textContent =
            nrrdSettings.resolution === 0 ? 'Original' : nrrdSettings.resolution;
    });

    document.getElementById('nrrd-threshold').addEventListener('input', (e) => {
        nrrdSettings.threshold = parseFloat(e.target.value);
        document.getElementById('nrrd-threshold-value').textContent = nrrdSettings.threshold.toFixed(2);
    });

    document.getElementById('btn-apply-nrrd').addEventListener('click', applyNRRD);

    document.getElementById('btn-reset-view').addEventListener('click', () => {
        fitCameraToScene();
    });

    document.getElementById('btn-top-view').addEventListener('click', () => {
        const center = controls.target.clone();
        camera.position.set(center.x, center.y + 300, center.z);
        camera.lookAt(center);
    });

    document.getElementById('btn-front-view').addEventListener('click', () => {
        const center = controls.target.clone();
        camera.position.set(center.x, center.y, center.z + 300);
        camera.lookAt(center);
    });

    // Undo/Redo 버튼
    const undoBtn = document.getElementById('btn-undo');
    const redoBtn = document.getElementById('btn-redo');
    if (undoBtn) undoBtn.addEventListener('click', undo);
    if (redoBtn) redoBtn.addEventListener('click', redo);

    // 키보드 단축키 (Ctrl+Z, Ctrl+Y)
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'z') {
            e.preventDefault();
            undo();
        } else if (e.ctrlKey && e.key === 'y') {
            e.preventDefault();
            redo();
        }
    });

}

function loadSTLFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        const loader = new THREE.STLLoader();
        const geometry = loader.parse(e.target.result);
        const name = file.name.replace(/\.[^/.]+$/, '');

        // 원본 좌표 유지 (offset = null)
        addSTLMesh(geometry, name, getColorForName(name), null);

        // centerToOrigin 옵션이 켜져 있으면 중심 이동
        if (loadSettings.centerToOrigin) {
            centerAllMeshes();
        }

        fitCameraToScene();
        updateModelList();
        isDrillInitialized = false;  // 새 메쉬 추가시 복셀 재초기화 필요
    };
    reader.readAsArrayBuffer(file);
}

/**
 * 여러 STL 파일 동시 로드 (폴더 선택 또는 다중 선택용)
 */
function loadMultipleSTLFiles(files) {
    const loader = new THREE.STLLoader();
    let loadedCount = 0;
    const totalFiles = files.length;

    console.log(`Loading ${totalFiles} STL files...`);

    Array.from(files).forEach(file => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const geometry = loader.parse(e.target.result);
            const name = file.name.replace(/\.[^/.]+$/, '');

            // 원본 좌표 유지
            addSTLMesh(geometry, name, getColorForName(name), null);

            loadedCount++;
            console.log(`Loaded ${name} (${loadedCount}/${totalFiles})`);

            if (loadedCount >= totalFiles) {
                // 모든 파일 로드 완료
                if (loadSettings.centerToOrigin) {
                    centerAllMeshes();
                }
                fitCameraToScene();
                updateModelList();
                isDrillInitialized = false;
                console.log('All files loaded');
            }
        };
        reader.readAsArrayBuffer(file);
    });
}

/**
 * 도구 설정 (CAD 스타일: 네비게이션은 항상 활성)
 * - 우클릭 드래그: 회전
 * - 휠: 줌
 * - 중클릭 드래그: 팬
 * - 좌클릭: 활성 도구 사용 (도구 없으면 무시)
 */
function setTool(tool) {
    // 같은 도구 다시 클릭 → 토글 (해제)
    if (currentTool === tool) {
        currentTool = null;
    } else {
        currentTool = tool;
    }

    // 버튼 활성 상태 업데이트
    document.querySelectorAll('.tool-btn[data-tool]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tool === currentTool);
    });

    // 상태바 업데이트
    document.getElementById('current-tool').textContent = currentTool
        ? currentTool.charAt(0).toUpperCase() + currentTool.slice(1)
        : 'None';
    document.getElementById('drill-panel').style.display = currentTool === 'drill' ? 'block' : 'none';

    const drillStatus = document.getElementById('drill-status');
    if (drillStatus) {
        drillStatus.style.display = currentTool === 'drill' ? 'block' : 'none';
        updateDrillStatus();
    }

    // 네비게이션은 항상 활성 (CAD 스타일: 우클릭=회전, 중클릭=팬, 휠=줌)
    controls.enabled = true;
    if (currentTool) {
        // 도구 활성: 좌클릭은 도구용 (OrbitControls에서 제외)
        controls.mouseButtons = {
            MIDDLE: THREE.MOUSE.PAN,
            RIGHT: THREE.MOUSE.ROTATE
        };
    } else {
        // 도구 없음: 좌클릭도 회전
        controls.mouseButtons = {
            LEFT: THREE.MOUSE.ROTATE,
            MIDDLE: THREE.MOUSE.PAN,
            RIGHT: THREE.MOUSE.ROTATE
        };
    }

    drillPreview.visible = false;
    if (drillHighlight) drillHighlight.visible = false;

    // 드릴 모드 진입 시 복셀 초기화
    if (currentTool === 'drill' && !isDrillInitialized) {
        initializeVoxels();
    }
}

/**
 * 드릴 상태바 정보 업데이트
 */
function updateDrillStatus() {
    const rInfo = document.getElementById('drill-r-info');
    if (rInfo) rInfo.textContent = drillSettings.radius;
}

function onMouseMove(event) {
    const container = document.getElementById('canvas-container');
    const rect = container.getBoundingClientRect();

    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    if (currentTool === 'drill') {
        updateDrillPreview();
        if (isMouseDown) {
            const intersection = getIntersection();
            if (intersection) {
                performDrill(intersection);
            }
        }
    }
}

function onMouseDown(event) {
    if (event.button !== 0) return;
    isMouseDown = true;

    if (currentTool === 'drill') {
        // 드릴링 시작 시 스냅샷 저장 (Undo용)
        if (isDrillInitialized) {
            saveSnapshot();
        }

        const intersection = getIntersection();
        if (intersection) {
            performDrill(intersection);
        }
    }
}

function onMouseUp() {
    isMouseDown = false;
}

function updateDrillPreview() {
    const intersection = getIntersection();
    if (intersection) {
        // 구체는 방향 무관 - 위치만 설정
        drillPreview.position.copy(intersection.point);
        drillPreview.visible = true;

        // 드릴 영향 범위 복셀 하이라이트 (마우스 버튼 안 누른 상태에서만)
        if (!isMouseDown) {
            updateDrillHighlight(intersection);
        }
    } else {
        drillPreview.visible = false;
        if (drillHighlight) drillHighlight.visible = false;
    }
}

function getIntersection() {
    raycaster.setFromCamera(mouse, camera);

    // 드릴 초기화 후에는 복셀 메쉬에서 교차 검사
    let objects;
    if (isDrillInitialized) {
        objects = Object.values(voxelMeshes);
    } else {
        objects = Object.values(meshes).filter(m => m.userData.drillable);
    }

    const intersects = raycaster.intersectObjects(objects);
    return intersects.length > 0 ? intersects[0] : null;
}

function onWindowResize() {
    const container = document.getElementById('canvas-container');
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
}

function updateModelList() {
    const list = document.getElementById('model-list');
    let items = [];

    if (isDrillInitialized) {
        // 복셀 메쉬 정보 표시
        items = Object.entries(voxelMeshes).map(([name, mesh]) => {
            const count = mesh.geometry.attributes.position.count / 3;
            const voxelCount = voxelGrids[name] ?
                voxelGrids[name].data.reduce((a, b) => a + b, 0) : 0;
            return `<div style="padding: 5px; color: #4fc3f7;">• ${name} (${count} tris, ${voxelCount} voxels)</div>`;
        });
    } else {
        // 원본 메쉬 정보 표시
        items = Object.entries(meshes).map(([name, mesh]) => {
            const count = mesh.geometry.attributes.position.count / 3;
            return `<div style="padding: 5px; color: #888;">• ${name} (${count} tris)</div>`;
        });
    }

    list.innerHTML = items.join('');

    // 모델 좌표 정보 업데이트
    updateModelInfo();
}

// ============================================================================
// 렌더 루프
// ============================================================================
function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);

    frameCount++;
    const now = performance.now();
    if (now - lastTime >= 1000) {
        document.getElementById('fps').textContent = frameCount;
        frameCount = 0;
        lastTime = now;
    }
}

// ============================================================================
// NRRD 로딩
// ============================================================================
function loadNRRDFile(file) {
    console.log(`Loading NRRD: ${file.name}`);
    document.getElementById('current-tool').textContent = 'NRRD 로딩 중...';

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            pendingNRRD = NRRDLoader.parse(e.target.result);
            pendingNRRD.fileName = file.name.replace(/\.[^/.]+$/, '');

            // NRRD 정보 표시
            const { header } = pendingNRRD;
            console.log('NRRD 로딩 완료:', header);

            // NRRD 설정 패널 표시
            document.getElementById('nrrd-panel').style.display = 'block';
            document.getElementById('current-tool').textContent = 'NRRD 로드됨 - 설정 조절 후 Apply';

            // NRRD 정보 표시
            const maxDim = Math.max(...header.sizes);
            const infoDiv = document.getElementById('nrrd-info');
            infoDiv.innerHTML = `원본: ${header.sizes.join(' × ')}<br>최대 차원: ${maxDim}`;

            // 해상도 슬라이더 설정 (업샘플링 허용)
            const resSlider = document.getElementById('nrrd-resolution');
            resSlider.min = 32;
            resSlider.max = 256;  // 원본보다 높게 설정 가능 (업샘플링)
            resSlider.value = Math.max(64, Math.min(128, maxDim));
            nrrdSettings.resolution = parseInt(resSlider.value);
            document.getElementById('nrrd-resolution-value').textContent = nrrdSettings.resolution;

        } catch (error) {
            console.error('NRRD 파싱 실패:', error);
            alert('NRRD 파일 로딩 실패: ' + error.message);
            document.getElementById('current-tool').textContent = 'Navigate';
        }
    };

    reader.onerror = () => {
        alert('파일 읽기 실패');
        document.getElementById('current-tool').textContent = 'Navigate';
    };

    reader.readAsArrayBuffer(file);
}

function applyNRRD() {
    if (!pendingNRRD) {
        alert('먼저 NRRD 파일을 로드하세요');
        return;
    }

    console.log('NRRD 적용 중...', nrrdSettings);
    document.getElementById('current-tool').textContent = '복셀화 중...';

    // 기존 메쉬 정리
    clearAllMeshes();

    setTimeout(() => {
        try {
            // VoxelGrid 생성
            const grid = new VoxelGrid();
            grid.fromNRRD(pendingNRRD, nrrdSettings.threshold, nrrdSettings.resolution);

            const name = pendingNRRD.fileName || 'NRRD';
            voxelGrids[name] = grid;

            // Marching Cubes로 메쉬 생성
            console.log('Marching Cubes 실행 중...');
            const geometry = grid.toMesh();

            if (geometry.attributes.position.count === 0) {
                throw new Error('생성된 메쉬가 비어있음 - threshold를 조절하세요');
            }

            const material = new THREE.MeshPhongMaterial({
                color: 0xe6d5c3,
                flatShading: false,
                side: THREE.DoubleSide,
                shininess: 30
            });

            const mesh = new THREE.Mesh(geometry, material);
            mesh.name = name;
            mesh.castShadow = true;
            mesh.receiveShadow = true;

            scene.add(mesh);
            voxelMeshes[name] = mesh;

            // 복셀 시스템 초기화 완료 상태로 설정
            isDrillInitialized = true;

            // NRRD 패널 숨기기
            document.getElementById('nrrd-panel').style.display = 'none';

            // 카메라 맞추기
            fitCameraToSceneFromVoxels();

            updateModelList();
            document.getElementById('current-tool').textContent = 'Navigate';

            console.log('NRRD 메쉬 생성 완료');

        } catch (error) {
            console.error('NRRD 적용 실패:', error);
            alert('NRRD 적용 실패: ' + error.message);
            document.getElementById('current-tool').textContent = 'Navigate';
        }
    }, 50);
}

function fitCameraToSceneFromVoxels() {
    const box = new THREE.Box3();

    // 복셀 메쉬에서 바운딩 박스 계산
    Object.values(voxelMeshes).forEach(mesh => {
        box.expandByObject(mesh);
    });

    // 원본 메쉬도 포함
    Object.values(meshes).forEach(mesh => {
        if (mesh.visible) box.expandByObject(mesh);
    });

    if (box.isEmpty()) return;

    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());

    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * (Math.PI / 180);
    const cameraDistance = maxDim / (2 * Math.tan(fov / 2)) * 2;

    camera.position.set(
        center.x + cameraDistance * 0.7,
        center.y + cameraDistance * 0.5,
        center.z + cameraDistance * 0.7
    );
    camera.lookAt(center);
    controls.target.copy(center);
    controls.update();
}

// ============================================================================
// 시작
// ============================================================================
init();
