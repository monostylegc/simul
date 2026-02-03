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
let currentTool = 'navigate';
let isMouseDown = false;
let isDrillInitialized = false;

// NRRD 관련
let pendingNRRD = null;    // 로딩된 NRRD 데이터 (적용 전)

// Undo/Redo 히스토리
const historyStack = [];   // Undo 스택
const redoStack = [];      // Redo 스택
const MAX_HISTORY = 30;    // 최대 히스토리 개수
let isUndoing = false;     // Undo 중인지 여부

// 단면 뷰 (Slice)
let sliceMode = false;
let slicePlanes = {};      // THREE.Mesh for slice planes
let clippingPlane = null;  // THREE.Plane
const sliceSettings = {
    axis: 'z',             // 'x', 'y', 'z'
    position: 0.5,         // 0~1 (normalized)
    visible: false
};

const drillSettings = {
    radius: 5,
    depth: 10,
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

    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    setupLights();

    // Grid
    const grid = new THREE.GridHelper(300, 30, 0x444444, 0x333333);
    scene.add(grid);

    // Axes
    const axes = new THREE.AxesHelper(50);
    scene.add(axes);

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
// 드릴 프리뷰 (빨간 구)
// ============================================================================
function createDrillPreview() {
    const geometry = new THREE.SphereGeometry(drillSettings.radius, 32, 32);
    const material = new THREE.MeshBasicMaterial({
        color: 0xff4444,
        transparent: true,
        opacity: 0.6,
        depthTest: false
    });
    drillPreview = new THREE.Mesh(geometry, material);
    drillPreview.visible = false;
    drillPreview.renderOrder = 999;
    scene.add(drillPreview);
}

function updateDrillPreviewSize() {
    if (drillPreview) {
        drillPreview.geometry.dispose();
        drillPreview.geometry = new THREE.SphereGeometry(drillSettings.radius, 32, 32);
    }
}

// ============================================================================
// STL 로딩 설정
// ============================================================================
const loadSettings = {
    keepOriginalPosition: true,  // 원본 좌표 유지 (3D Slicer 등에서 내보낸 파일용)
    centerToOrigin: false        // 전체 모델을 원점 중심으로 이동
};

// ============================================================================
// STL 로딩
// ============================================================================
function loadSampleSTL() {
    clearAllMeshes();

    const loader = new THREE.STLLoader();
    let loadedCount = 0;
    const totalFiles = 2;
    const geometries = {};

    console.log('Loading STL files...');

    // L5 (아래쪽 척추)
    loader.load('stl/L5.stl',
        (geometry) => {
            console.log('L5 loaded:', geometry.attributes.position.count, 'vertices');
            geometries.L5 = geometry;
            loadedCount++;
            if (loadedCount >= totalFiles) processLoadedGeometries(geometries);
        },
        (progress) => console.log('L5 progress:', Math.round(progress.loaded/progress.total*100) + '%'),
        (error) => console.error('L5 error:', error)
    );

    // L4 (위쪽 척추)
    loader.load('stl/L4.stl',
        (geometry) => {
            console.log('L4 loaded:', geometry.attributes.position.count, 'vertices');
            geometries.L4 = geometry;
            loadedCount++;
            if (loadedCount >= totalFiles) processLoadedGeometries(geometries);
        },
        (progress) => console.log('L4 progress:', Math.round(progress.loaded/progress.total*100) + '%'),
        (error) => console.error('L4 error:', error)
    );
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
 */
function centerAllMeshes() {
    // 전체 바운딩 박스 계산
    const box = new THREE.Box3();
    Object.values(meshes).forEach(mesh => {
        box.expandByObject(mesh);
    });

    if (box.isEmpty()) return;

    // 중심 계산
    const center = box.getCenter(new THREE.Vector3());

    // 모든 메쉬 이동
    Object.values(meshes).forEach(mesh => {
        mesh.position.sub(center);
    });

    console.log(`모든 메쉬를 원점으로 이동 (오프셋: ${center.x.toFixed(1)}, ${center.y.toFixed(1)}, ${center.z.toFixed(1)})`);
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

    isDrillInitialized = false;
    updateModelList();
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
        document.getElementById('current-tool').textContent = 'Drill';
        updateModelList();
        console.log('Voxel initialization complete');
    }, 50);
}

// ============================================================================
// 드릴링 - 복셀 제거 후 메쉬 재생성
// ============================================================================
function performDrill(point, normal) {
    if (!isDrillInitialized) return;

    const radius = drillSettings.radius;
    let totalRemoved = 0;

    Object.entries(voxelGrids).forEach(([name, grid]) => {
        // 복셀 드릴링
        const removed = grid.drillSphere(point, radius);
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
        console.log(`Drilled: removed ${totalRemoved} voxels`);
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
// 단면 뷰 (Slice View)
// ============================================================================

/**
 * 단면 뷰 토글
 */
function toggleSliceView() {
    sliceSettings.visible = !sliceSettings.visible;

    if (sliceSettings.visible) {
        enableSliceView();
    } else {
        disableSliceView();
    }

    document.getElementById('slice-panel').style.display =
        sliceSettings.visible ? 'block' : 'none';
}

/**
 * 단면 뷰 활성화
 */
function enableSliceView() {
    // Clipping plane 생성
    updateClippingPlane();

    // 모든 복셀 메쉬에 클리핑 적용
    Object.values(voxelMeshes).forEach(mesh => {
        mesh.material.clippingPlanes = [clippingPlane];
        mesh.material.clipShadows = true;
        mesh.material.needsUpdate = true;
    });

    // 렌더러에 클리핑 활성화
    renderer.localClippingEnabled = true;

    // 단면 평면 시각화 생성
    createSlicePlaneHelper();

    console.log('단면 뷰 활성화');
}

/**
 * 단면 뷰 비활성화
 */
function disableSliceView() {
    // 클리핑 제거
    Object.values(voxelMeshes).forEach(mesh => {
        mesh.material.clippingPlanes = [];
        mesh.material.needsUpdate = true;
    });

    renderer.localClippingEnabled = false;

    // 헬퍼 제거
    if (slicePlanes.helper) {
        scene.remove(slicePlanes.helper);
        slicePlanes.helper.geometry.dispose();
        slicePlanes.helper.material.dispose();
        slicePlanes.helper = null;
    }

    console.log('단면 뷰 비활성화');
}

/**
 * 클리핑 평면 업데이트
 */
function updateClippingPlane() {
    if (!isDrillInitialized) return;

    // 바운딩 박스 계산
    const box = new THREE.Box3();
    Object.values(voxelMeshes).forEach(mesh => {
        box.expandByObject(mesh);
    });

    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());

    // 축에 따른 법선 및 위치 계산
    let normal, position;
    const t = sliceSettings.position;

    switch (sliceSettings.axis) {
        case 'x': // Sagittal
            normal = new THREE.Vector3(-1, 0, 0);
            position = box.min.x + size.x * t;
            break;
        case 'y': // Coronal
            normal = new THREE.Vector3(0, -1, 0);
            position = box.min.y + size.y * t;
            break;
        case 'z': // Axial
        default:
            normal = new THREE.Vector3(0, 0, -1);
            position = box.min.z + size.z * t;
            break;
    }

    // 클리핑 평면 생성/업데이트
    if (!clippingPlane) {
        clippingPlane = new THREE.Plane();
    }

    clippingPlane.normal.copy(normal);
    clippingPlane.constant = -position * normal.x - position * normal.y - position * normal.z;

    // 축에 따른 constant 계산
    if (sliceSettings.axis === 'x') {
        clippingPlane.constant = position;
    } else if (sliceSettings.axis === 'y') {
        clippingPlane.constant = position;
    } else {
        clippingPlane.constant = position;
    }

    // 헬퍼 업데이트
    updateSlicePlaneHelper(center, size);
}

/**
 * 단면 평면 헬퍼 생성
 */
function createSlicePlaneHelper() {
    if (slicePlanes.helper) {
        scene.remove(slicePlanes.helper);
        slicePlanes.helper.geometry.dispose();
        slicePlanes.helper.material.dispose();
    }

    const box = new THREE.Box3();
    Object.values(voxelMeshes).forEach(mesh => {
        box.expandByObject(mesh);
    });

    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());

    // 반투명 평면 생성
    let planeSize, planeGeom;
    switch (sliceSettings.axis) {
        case 'x':
            planeGeom = new THREE.PlaneGeometry(size.y * 1.2, size.z * 1.2);
            break;
        case 'y':
            planeGeom = new THREE.PlaneGeometry(size.x * 1.2, size.z * 1.2);
            break;
        case 'z':
        default:
            planeGeom = new THREE.PlaneGeometry(size.x * 1.2, size.y * 1.2);
            break;
    }

    const planeMat = new THREE.MeshBasicMaterial({
        color: 0x4fc3f7,
        transparent: true,
        opacity: 0.3,
        side: THREE.DoubleSide,
        depthWrite: false
    });

    slicePlanes.helper = new THREE.Mesh(planeGeom, planeMat);
    slicePlanes.helper.renderOrder = 1;
    scene.add(slicePlanes.helper);

    updateSlicePlaneHelper(center, size);
}

/**
 * 단면 평면 헬퍼 위치 업데이트
 */
function updateSlicePlaneHelper(center, size) {
    if (!slicePlanes.helper) return;

    const t = sliceSettings.position;
    const box = new THREE.Box3();
    Object.values(voxelMeshes).forEach(mesh => {
        box.expandByObject(mesh);
    });

    switch (sliceSettings.axis) {
        case 'x':
            slicePlanes.helper.position.set(
                box.min.x + size.x * t,
                center.y,
                center.z
            );
            slicePlanes.helper.rotation.set(0, Math.PI / 2, 0);
            break;
        case 'y':
            slicePlanes.helper.position.set(
                center.x,
                box.min.y + size.y * t,
                center.z
            );
            slicePlanes.helper.rotation.set(Math.PI / 2, 0, 0);
            break;
        case 'z':
        default:
            slicePlanes.helper.position.set(
                center.x,
                center.y,
                box.min.z + size.z * t
            );
            slicePlanes.helper.rotation.set(0, 0, 0);
            break;
    }
}

/**
 * 단면 축 변경
 */
function setSliceAxis(axis) {
    sliceSettings.axis = axis;

    // 버튼 상태 업데이트
    document.querySelectorAll('[data-slice-axis]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.sliceAxis === axis);
    });

    if (sliceSettings.visible) {
        // 헬퍼 재생성 (크기가 다름)
        createSlicePlaneHelper();
        updateClippingPlane();
    }
}

/**
 * 단면 위치 변경
 */
function setSlicePosition(position) {
    sliceSettings.position = position;

    if (sliceSettings.visible) {
        updateClippingPlane();
    }
}

// ============================================================================
// 이벤트
// ============================================================================
function setupEventListeners() {
    const container = document.getElementById('canvas-container');

    container.addEventListener('mousemove', onMouseMove);
    container.addEventListener('mousedown', onMouseDown);
    container.addEventListener('mouseup', onMouseUp);
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
    });

    document.getElementById('drill-depth').addEventListener('input', (e) => {
        drillSettings.depth = parseFloat(e.target.value);
        document.getElementById('drill-depth-value').textContent = drillSettings.depth;
    });

    // 버튼
    document.getElementById('btn-load-sample').addEventListener('click', loadSampleSTL);

    document.getElementById('btn-load-stl').addEventListener('click', () => {
        document.getElementById('file-input').click();
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

    // 단면 뷰 버튼
    const sliceBtn = document.getElementById('btn-slice-view');
    if (sliceBtn) sliceBtn.addEventListener('click', toggleSliceView);

    // 단면 축 버튼
    document.querySelectorAll('[data-slice-axis]').forEach(btn => {
        btn.addEventListener('click', () => setSliceAxis(btn.dataset.sliceAxis));
    });

    // 단면 위치 슬라이더
    const sliceSlider = document.getElementById('slice-position');
    if (sliceSlider) {
        sliceSlider.addEventListener('input', (e) => {
            const pos = parseFloat(e.target.value);
            setSlicePosition(pos);
            document.getElementById('slice-position-value').textContent = Math.round(pos * 100) + '%';
        });
    }
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

function setTool(tool) {
    currentTool = tool;

    document.querySelectorAll('.tool-btn[data-tool]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tool === tool);
    });
    document.getElementById('current-tool').textContent = tool.charAt(0).toUpperCase() + tool.slice(1);
    document.getElementById('drill-panel').style.display = tool === 'drill' ? 'block' : 'none';

    controls.enabled = (tool === 'navigate');
    drillPreview.visible = false;

    // 드릴 모드 진입 시 복셀 초기화
    if (tool === 'drill' && !isDrillInitialized) {
        initializeVoxels();
    }

    // Navigate 모드에서는 원본 메쉬 표시
    if (tool === 'navigate' && isDrillInitialized) {
        // 복셀 메쉬 유지 (드릴링 결과 보존)
    }
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
                performDrill(intersection.point, intersection.face.normal);
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
            performDrill(intersection.point, intersection.face.normal);
        }
    }
}

function onMouseUp() {
    isMouseDown = false;
}

function updateDrillPreview() {
    const intersection = getIntersection();
    if (intersection) {
        drillPreview.position.copy(intersection.point);
        drillPreview.visible = true;
    } else {
        drillPreview.visible = false;
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
