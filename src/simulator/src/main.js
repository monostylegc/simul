/**
 * Spine Surgery Simulator - Three.js Frontend
 * 복셀 기반 드릴링 시스템 + 탭 기반 데스크탑 CAE 스타일 UI
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
let currentTool = null;    // null=도구 없음, 'drill'=드릴, 'bc_brush'=BC 브러쉬
let currentPanel = 'file'; // 현재 활성 탭/패널
let isMouseDown = false;
let isDrillInitialized = false;
let gridHelper = null;     // 그리드 헬퍼 (모델 크기에 맞게 동적 조절)
let axesHelper = null;     // 축 헬퍼
let drillHighlight = null;         // 드릴 영향 범위 하이라이트 (InstancedMesh)
let bcBrushHighlight = null;       // BC 브러쉬 프리뷰 하이라이트 (시안, InstancedMesh)
let bcSelectionHighlight = null;   // BC 확정 선택 하이라이트 (노란, InstancedMesh)
const MAX_PREVIEW_VOXELS = 5000;   // 최대 프리뷰 복셀 수
const bcBrushSettings = { radius: 5 };

// Analysis (전처리/후처리) 관련
let wsClient = null;               // WebSocket 클라이언트
let preProcessor = null;           // 전처리기
let postProcessor = null;          // 후처리기
let analysisMode = 'pre';          // 'pre' | 'post'

// Force 방향/화살표 관련
let forceDirection = new THREE.Vector3(0, -1, 0);  // Force 방향 벡터
let forceMagnitude = 100;                           // Force 크기 (N)
let forceArrowPreview = null;                       // ArrowHelper 프리뷰
let appliedForceArrows = [];                        // 적용된 Force BC 화살표 [{arrow, bc, origin}]
let isRotatingArrow = false;                        // Ctrl+드래그 회전 중 플래그
let arrowOrigin = new THREE.Vector3();              // 화살표 원점 캐시
let rotatingForceEntry = null;                      // Ctrl+드래그 중인 적용 화살표 엔트리

// NRRD 관련
let pendingNRRD = null;    // 로딩된 NRRD 데이터 (적용 전)

// Undo/Redo 히스토리
const historyStack = [];   // Undo 스택
const redoStack = [];      // Redo 스택
const MAX_HISTORY = 30;    // 최대 히스토리 개수
let isUndoing = false;     // Undo 중인지 여부

// 조명 참조 (View 탭에서 조절용)
let ambientLight = null;
let dirLight = null;

// Up 축 설정
let currentUpAxis = 'y';

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
    scene.background = new THREE.Color(0xe8e8e8);

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
    // CAD 스타일 네비게이션: 우클릭=회전, 중클릭=팬, 휠=줌 (좌클릭은 도구 전용)
    controls.mouseButtons = {
        MIDDLE: THREE.MOUSE.PAN,
        RIGHT: THREE.MOUSE.ROTATE
    };

    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    setupLights();

    // Grid (초기 그리드 - 모델 로드 후 크기 자동 조절됨)
    gridHelper = new THREE.GridHelper(300, 30, 0xbbbbbb, 0xcccccc);
    scene.add(gridHelper);

    // Axes
    axesHelper = new THREE.AxesHelper(50);
    scene.add(axesHelper);

    createDrillPreview();
    setupEventListeners();
    setupAnalysisListeners();
    setupViewListeners();

    // 자동으로 샘플 STL 로드
    loadSampleSTL();

    animate();

    console.log('Three.js initialized (Voxel mode + Tab UI)');
}

// ============================================================================
// 조명
// ============================================================================
function setupLights() {
    ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    dirLight = new THREE.DirectionalLight(0xffffff, 0.7);
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
    const radius = currentTool === 'bc_brush' ? bcBrushSettings.radius : drillSettings.radius;

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

    gridHelper = new THREE.GridHelper(gridSize, divisions, 0xbbbbbb, 0xcccccc);
    // Z-up이면 그리드를 XY 평면으로 회전
    if (currentUpAxis === 'z') {
        gridHelper.rotation.x = Math.PI / 2;
    }
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
        <div style="padding: 8px; background: #e3f2fd; border: 1px solid #bbdefb; border-radius: 4px; margin-top: 8px;">
            <div style="color: #1565c0; font-size: 11px; font-weight: bold; margin-bottom: 4px;">Model Info</div>
            <div style="font-size: 11px; color: #444;">크기: ${size.x.toFixed(1)} x ${size.y.toFixed(1)} x ${size.z.toFixed(1)} mm</div>
            <div style="font-size: 11px; color: #444;">중심: (${center.x.toFixed(1)}, ${center.y.toFixed(1)}, ${center.z.toFixed(1)})</div>
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
    updateMaterialTargetList();
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
    clearBCHighlights();

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
// BC 타입별 색상 헬퍼
// ============================================================================

/**
 * 브러쉬 선택 색상 반환 (중립 색상 - 타입 무관)
 * @returns {{preview: number, selection: number, confirmed: number}}
 */
function getCurrentBCColor() {
    return { preview: 0x66ccff, selection: 0xffcc00, confirmed: 0x1976d2 };
}

// ============================================================================
// BC 브러쉬 하이라이트 (InstancedMesh)
// ============================================================================

/**
 * BC 브러쉬 프리뷰 InstancedMesh 생성 (BC 타입별 색상)
 */
function createBCBrushHighlight() {
    clearBCBrushHighlight();

    const firstGrid = Object.values(voxelGrids)[0];
    if (!firstGrid) return;

    const colors = getCurrentBCColor();
    const s = firstGrid.cellSize * 0.96;
    const boxGeom = new THREE.BoxGeometry(s, s, s);
    const mat = new THREE.MeshBasicMaterial({
        color: colors.preview,
        transparent: true,
        opacity: 0.45,
        depthTest: false
    });

    bcBrushHighlight = new THREE.InstancedMesh(boxGeom, mat, MAX_PREVIEW_VOXELS);
    bcBrushHighlight.count = 0;
    bcBrushHighlight.visible = false;
    bcBrushHighlight.renderOrder = 998;
    scene.add(bcBrushHighlight);
}

/**
 * BC 브러쉬 프리뷰 업데이트 (호버 시 시안 하이라이트)
 */
function updateBCBrushPreview(intersection) {
    if (!isDrillInitialized || !intersection) {
        if (bcBrushHighlight) bcBrushHighlight.visible = false;
        return;
    }

    // 지연 생성 (initializeVoxels 비동기 완료 후 첫 호버 시)
    if (!bcBrushHighlight) {
        createBCBrushHighlight();
        if (!bcBrushHighlight) return;
    }

    const point = intersection.point;
    const matrix = new THREE.Matrix4();
    let count = 0;

    Object.values(voxelGrids).forEach(grid => {
        const affected = grid.previewDrill(point, bcBrushSettings.radius);
        affected.forEach(pos => {
            if (count >= MAX_PREVIEW_VOXELS) return;
            const worldPos = grid.gridToWorld(pos.x, pos.y, pos.z);
            matrix.setPosition(worldPos.x, worldPos.y, worldPos.z);
            bcBrushHighlight.setMatrixAt(count, matrix);
            count++;
        });
    });

    bcBrushHighlight.count = count;
    bcBrushHighlight.instanceMatrix.needsUpdate = true;
    bcBrushHighlight.visible = count > 0;
}

/**
 * BC 확정 선택 영역 시각화 업데이트 (BC 타입별 색상)
 */
function updateBCSelectionVisual() {
    if (!preProcessor) return;

    // 기존 하이라이트 제거
    clearBCSelectionHighlight();

    const positions = preProcessor.getBrushSelectionWorldPositions();
    if (positions.length === 0) {
        // 선택 없으면 화살표도 제거
        clearForceArrowPreview();
        const countEl = document.getElementById('bc-selection-count');
        if (countEl) countEl.textContent = '0';
        return;
    }

    const firstGrid = Object.values(voxelGrids)[0];
    if (!firstGrid) return;

    const colors = getCurrentBCColor();
    const s = firstGrid.cellSize * 0.96;
    const boxGeom = new THREE.BoxGeometry(s, s, s);
    const mat = new THREE.MeshBasicMaterial({
        color: colors.selection,
        transparent: true,
        opacity: 0.5,
        depthTest: false
    });

    const count = Math.min(positions.length, MAX_PREVIEW_VOXELS);
    bcSelectionHighlight = new THREE.InstancedMesh(boxGeom, mat, count);
    const matrix = new THREE.Matrix4();
    for (let i = 0; i < count; i++) {
        const wp = positions[i];
        matrix.setPosition(wp.x, wp.y, wp.z);
        bcSelectionHighlight.setMatrixAt(i, matrix);
    }
    bcSelectionHighlight.instanceMatrix.needsUpdate = true;
    bcSelectionHighlight.renderOrder = 997;
    scene.add(bcSelectionHighlight);

    // 선택 카운트 UI 업데이트
    const countEl = document.getElementById('bc-selection-count');
    if (countEl) countEl.textContent = preProcessor.getBrushSelectionCount();
}

/**
 * BC 브러쉬 프리뷰 하이라이트 제거
 */
function clearBCBrushHighlight() {
    if (bcBrushHighlight) {
        scene.remove(bcBrushHighlight);
        if (bcBrushHighlight.geometry) bcBrushHighlight.geometry.dispose();
        if (bcBrushHighlight.material) bcBrushHighlight.material.dispose();
        bcBrushHighlight = null;
    }
}

/**
 * BC 확정 선택 하이라이트 제거
 */
function clearBCSelectionHighlight() {
    if (bcSelectionHighlight) {
        scene.remove(bcSelectionHighlight);
        if (bcSelectionHighlight.geometry) bcSelectionHighlight.geometry.dispose();
        if (bcSelectionHighlight.material) bcSelectionHighlight.material.dispose();
        bcSelectionHighlight = null;
    }
}

/**
 * BC 관련 하이라이트 모두 정리
 */
function clearBCHighlights() {
    clearBCBrushHighlight();
    clearBCSelectionHighlight();
    clearForceArrowPreview();
    clearAppliedForceArrows();
}

// ============================================================================
// Force 화살표 프리뷰
// ============================================================================

/**
 * Force 화살표 프리뷰 업데이트
 * 선택 영역 중심에서 forceDirection 방향으로 화살표 표시
 */
function updateForceArrowPreview() {
    if (!preProcessor) return;

    const positions = preProcessor.getBrushSelectionWorldPositions();
    if (positions.length === 0) {
        clearForceArrowPreview();
        return;
    }

    // 선택 영역 중심 계산
    const center = new THREE.Vector3();
    positions.forEach(wp => { center.x += wp.x; center.y += wp.y; center.z += wp.z; });
    center.divideScalar(positions.length);
    arrowOrigin.copy(center);

    // 모델 바운딩박스 대각선의 20%를 화살표 길이로
    const box = new THREE.Box3();
    const targetMeshes = isDrillInitialized ? voxelMeshes : meshes;
    Object.values(targetMeshes).forEach(m => { if (m.visible !== false) box.expandByObject(m); });
    const diag = box.isEmpty() ? 50 : box.getSize(new THREE.Vector3()).length();
    const arrowLength = diag * 0.2;
    const headLength = arrowLength * 0.2;
    const headWidth = headLength * 0.5;

    // 기존 화살표 제거 후 재생성
    clearForceArrowPreview();

    const dir = forceDirection.clone().normalize();
    forceArrowPreview = new THREE.ArrowHelper(dir, center, arrowLength, 0xff2222, headLength, headWidth);
    forceArrowPreview.renderOrder = 999;
    // 물체에 가려지지 않도록 depthTest 비활성화
    forceArrowPreview.line.material.depthTest = false;
    forceArrowPreview.cone.material.depthTest = false;
    scene.add(forceArrowPreview);
}

/**
 * Force 화살표 프리뷰 제거
 */
function clearForceArrowPreview() {
    if (forceArrowPreview) {
        scene.remove(forceArrowPreview);
        // ArrowHelper는 내부 line/cone 가지므로 dispose
        if (forceArrowPreview.line) {
            forceArrowPreview.line.geometry.dispose();
            forceArrowPreview.line.material.dispose();
        }
        if (forceArrowPreview.cone) {
            forceArrowPreview.cone.geometry.dispose();
            forceArrowPreview.cone.material.dispose();
        }
        forceArrowPreview = null;
    }
}

/**
 * 적용된 Force BC 화살표 생성
 * 적용면 중심에 방향/크기를 나타내는 확정 화살표 표시
 */
function createAppliedForceArrow(positions, direction, magnitude, bc) {
    // 적용면 중심 계산
    const center = new THREE.Vector3();
    positions.forEach(wp => { center.x += wp.x; center.y += wp.y; center.z += wp.z; });
    center.divideScalar(positions.length);

    // 모델 바운딩박스 기준 화살표 크기
    const box = new THREE.Box3();
    const targetMeshes = isDrillInitialized ? voxelMeshes : meshes;
    Object.values(targetMeshes).forEach(m => { if (m.visible !== false) box.expandByObject(m); });
    const diag = box.isEmpty() ? 50 : box.getSize(new THREE.Vector3()).length();
    const arrowLength = diag * 0.2;
    const headLength = arrowLength * 0.2;
    const headWidth = headLength * 0.5;

    const dir = direction.clone().normalize();
    const arrow = new THREE.ArrowHelper(dir, center, arrowLength, 0xff2222, headLength, headWidth);
    arrow.renderOrder = 998;
    // 물체에 가려지지 않도록 depthTest 비활성화
    arrow.line.material.depthTest = false;
    arrow.cone.material.depthTest = false;
    scene.add(arrow);
    appliedForceArrows.push({ arrow, bc, origin: center.clone(), magnitude });
}

/**
 * 적용된 Force BC 화살표 모두 제거
 */
function clearAppliedForceArrows() {
    appliedForceArrows.forEach(entry => {
        scene.remove(entry.arrow);
        if (entry.arrow.line) {
            entry.arrow.line.geometry.dispose();
            entry.arrow.line.material.dispose();
        }
        if (entry.arrow.cone) {
            entry.arrow.cone.geometry.dispose();
            entry.arrow.cone.material.dispose();
        }
    });
    appliedForceArrows = [];
    rotatingForceEntry = null;
}

/**
 * 적용된 Force 화살표 방향 업데이트
 * Ctrl+드래그로 방향 변경 시 화살표 재생성 + BC 데이터 갱신
 */
function updateAppliedForceArrowDirection(entry, newDir) {
    const dir = newDir.clone().normalize();
    // 화살표 방향 업데이트
    entry.arrow.setDirection(dir);
    // BC 데이터의 force 벡터도 갱신
    if (entry.bc && entry.bc.values && entry.bc.values.length > 0) {
        const mag = entry.magnitude;
        entry.bc.values[0] = [dir.x * mag, dir.y * mag, dir.z * mag];
    }
}

/**
 * Force 방향 표시 UI 갱신
 */
function updateForceDirectionDisplay() {
    const el = document.getElementById('force-direction-display');
    if (el) {
        el.textContent = `(${forceDirection.x.toFixed(2)}, ${forceDirection.y.toFixed(2)}, ${forceDirection.z.toFixed(2)})`;
    }
}

/**
 * 재료 대상 목록 갱신
 * 로드된 메쉬/복셀 이름으로 <option> 동적 생성
 */
function updateMaterialTargetList() {
    const sel = document.getElementById('material-target');
    if (!sel) return;

    // 기존 옵션 제거 (전체 옵션 유지)
    while (sel.options.length > 1) sel.remove(1);

    // 복셀 그리드 이름 추가
    const names = Object.keys(voxelGrids).length > 0
        ? Object.keys(voxelGrids)
        : Object.keys(meshes);

    names.forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        sel.appendChild(opt);
    });
}

// ============================================================================
// 복셀화 - 드릴 모드 진입 시 초기화
// ============================================================================
function initializeVoxels() {
    if (isDrillInitialized) return;
    isDrillInitialized = true; // setTimeout 전에 설정하여 이중 호출 방지

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
        // 현재 도구에 맞게 상태바 + 프리뷰 업데이트
        const toolNames = { drill: 'Drill', bc_brush: 'BC Brush' };
        document.getElementById('current-tool').textContent = toolNames[currentTool] || currentTool || 'None';
        updateDrillPreviewSize();
        updateModelList();
        updateMaterialTargetList();
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
 * Undo/Redo 버튼 상태 업데이트 (사이드바 + 상단 아이콘)
 */
function updateUndoRedoButtons() {
    const undoBtn = document.getElementById('btn-undo');
    const redoBtn = document.getElementById('btn-redo');
    const undoCount = document.getElementById('undo-count');
    const redoCount = document.getElementById('redo-count');

    // 사이드바 버튼
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

    // 상단 아이콘 버튼
    const undoTop = document.getElementById('btn-undo-top');
    const redoTop = document.getElementById('btn-redo-top');
    if (undoTop) undoTop.disabled = historyStack.length === 0;
    if (redoTop) redoTop.disabled = redoStack.length === 0;
}

// ============================================================================
// 탭 전환 시스템
// ============================================================================

/**
 * 탭 전환 - 핵심 함수
 * @param {string} tabName - 'file'|'modeling'|'preprocess'|'solve'|'postprocess'|'view'
 */
function switchTab(tabName) {
    // 탭 버튼 active 상태 업데이트
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    // 패널 전환
    document.querySelectorAll('.prop-panel').forEach(p => p.style.display = 'none');
    const panel = document.getElementById('panel-' + tabName);
    if (panel) panel.style.display = 'block';
    currentPanel = tabName;

    // 탭별 도구/모드 전환
    switch (tabName) {
        case 'file':
        case 'view':
            setTool(null, true);
            exitPostMode();
            break;
        case 'modeling':
            exitPostMode();
            setTool('drill', true);
            // 드릴 토글 버튼 상태 동기화
            updateDrillToggleButton();
            break;
        case 'preprocess':
            exitPostMode();
            setTool('bc_brush', true);
            initAnalysis();
            if (isDrillInitialized && !bcBrushHighlight) {
                createBCBrushHighlight();
            }
            break;
        case 'solve':
            setTool(null, true);
            exitPostMode();
            initAnalysis();
            break;
        case 'postprocess':
            setTool(null, true);
            enterPostMode();
            break;
    }
}

/**
 * 후처리 모드 진입 (메쉬 숨기고 결과 시각화)
 */
function enterPostMode() {
    analysisMode = 'post';
    if (postProcessor && postProcessor.data) {
        Object.values(voxelMeshes).forEach(m => m.visible = false);
        Object.values(meshes).forEach(m => m.visible = false);
        postProcessor.updateVisualization();
    }
}

/**
 * 후처리 모드 해제 (메쉬 복원)
 */
function exitPostMode() {
    if (analysisMode !== 'post') return;
    analysisMode = 'pre';
    if (isDrillInitialized) {
        Object.values(voxelMeshes).forEach(m => m.visible = true);
    } else {
        Object.values(meshes).forEach(m => m.visible = true);
    }
    if (postProcessor) postProcessor.clear();
}

/**
 * 드릴 토글 버튼 시각적 상태 업데이트
 */
function updateDrillToggleButton() {
    const btn = document.getElementById('btn-toggle-drill');
    if (!btn) return;
    btn.classList.toggle('active', currentTool === 'drill');
    btn.textContent = currentTool === 'drill' ? 'Drill: ON' : 'Drill: OFF';
}

// ============================================================================
// 우측 속성 패널 전환 (레거시 호환 + 탭 동기화)
// ============================================================================

/**
 * 우측 사이드바 패널 전환
 * @param {string} panel - 레거시: 'default'|'drill'|'bc'|'analysis'|'nrrd' → 새: 'file'|'modeling'|'preprocess'|'solve'|'postprocess'|'view'
 */
function setToolPanel(panel) {
    // 레거시 패널명 매핑
    const mapping = {
        'default': 'file',
        'drill': 'modeling',
        'bc': 'preprocess',
        'analysis': 'solve',
        'nrrd': 'file'
    };
    const tabName = mapping[panel] || panel;

    currentPanel = tabName;

    // 모든 패널 숨기기
    document.querySelectorAll('.prop-panel').forEach(p => p.style.display = 'none');

    // 선택된 패널 표시
    const target = document.getElementById('panel-' + tabName);
    if (target) target.style.display = 'block';

    // 탭 버튼 active 상태 동기화
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
}

// ============================================================================
// BC 모드 진입/해제
// ============================================================================

/**
 * BC 면 선택 모드 활성화
 */
function activateBCMode() {
    setTool('bc_brush', true);
    initAnalysis();

    // 복셀 초기화 완료 후 브러쉬 하이라이트 생성
    if (isDrillInitialized && !bcBrushHighlight) {
        createBCBrushHighlight();
    }
}

// ============================================================================
// Re-voxelize 헬퍼
// ============================================================================

/**
 * 현재 해상도로 복셀 재생성
 */
function revoxelize() {
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
}

// ============================================================================
// 재료 적용 헬퍼
// ============================================================================

/**
 * 선택된 재료 프리셋 적용 (대상 오브젝트 선택 지원)
 */
function applyMaterial() {
    if (!preProcessor) return;
    const preset = document.getElementById('material-preset').value;
    const targetSel = document.getElementById('material-target');
    const target = targetSel ? targetSel.value : '__all__';

    if (target === '__all__') {
        // 전체에 적용
        const names = Object.keys(voxelGrids).length > 0
            ? Object.keys(voxelGrids)
            : Object.keys(meshes);
        names.forEach(name => preProcessor.assignMaterial(name, preset));
    } else {
        // 선택된 오브젝트에만 적용
        preProcessor.assignMaterial(target, preset);
    }
}

// ============================================================================
// 카메라 프리셋 (View 탭)
// ============================================================================

/**
 * 카메라를 지정 방향 프리셋으로 이동
 * @param {string} direction - 'front'|'back'|'top'|'bottom'|'left'|'right'
 */
function setCameraPreset(direction) {
    const box = new THREE.Box3();
    const targetMeshes = isDrillInitialized ? voxelMeshes : meshes;
    Object.values(targetMeshes).forEach(m => {
        if (m.visible !== false) box.expandByObject(m);
    });
    Object.values(meshes).forEach(m => {
        if (m.visible !== false) box.expandByObject(m);
    });

    if (box.isEmpty()) return;

    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * (Math.PI / 180);
    const dist = maxDim / (2 * Math.tan(fov / 2)) * 1.8;

    const positions = {
        front:  [center.x, center.y, center.z + dist],
        back:   [center.x, center.y, center.z - dist],
        top:    [center.x, center.y + dist, center.z + 0.01],
        bottom: [center.x, center.y - dist, center.z + 0.01],
        left:   [center.x - dist, center.y, center.z],
        right:  [center.x + dist, center.y, center.z]
    };

    const pos = positions[direction];
    if (!pos) return;

    camera.position.set(pos[0], pos[1], pos[2]);
    camera.lookAt(center);
    controls.target.copy(center);
    controls.update();
}

// ============================================================================
// 이벤트
// ============================================================================
function setupEventListeners() {
    const container = document.getElementById('canvas-container');

    // ── 포인터 이벤트 (캔버스) ──
    container.addEventListener('pointermove', onMouseMove);
    container.addEventListener('pointerdown', onMouseDown);
    container.addEventListener('pointerup', onMouseUp);
    window.addEventListener('resize', onWindowResize);

    // ── 캔버스에 STL 드래그 앤 드롭 ──
    container.addEventListener('dragover', (e) => {
        e.preventDefault();
    });
    container.addEventListener('drop', (e) => {
        e.preventDefault();
        const files = Array.from(e.dataTransfer.files).filter(
            f => f.name.toLowerCase().endsWith('.stl')
        );
        if (files.length === 0) return;
        if (files.length === 1) {
            loadSTLFile(files[0]);
        } else {
            loadMultipleSTLFiles(files);
        }
    });

    // ── 탭 버튼 클릭 ──
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            switchTab(btn.dataset.tab);
        });
    });

    // ── File 패널 버튼들 ──
    document.getElementById('btn-load-sample').addEventListener('click', () => {
        loadSampleSTL();
    });
    document.getElementById('btn-load-stl').addEventListener('click', () => {
        document.getElementById('file-input').click();
    });
    document.getElementById('btn-load-nrrd').addEventListener('click', () => {
        document.getElementById('nrrd-input').click();
    });
    document.getElementById('btn-clear-all').addEventListener('click', () => {
        clearAllMeshes();
    });

    // ── Modeling 패널: 드릴 토글 ──
    document.getElementById('btn-toggle-drill').addEventListener('click', () => {
        setTool('drill');  // 토글 (force 없이)
        updateDrillToggleButton();
    });

    // ── 상단 Undo/Redo 아이콘 ──
    document.getElementById('btn-undo-top').addEventListener('click', undo);
    document.getElementById('btn-redo-top').addEventListener('click', redo);

    // ── 사이드바 슬라이더/입력 ──

    // 드릴 반경
    document.getElementById('drill-radius').addEventListener('input', (e) => {
        drillSettings.radius = parseFloat(e.target.value);
        document.getElementById('drill-radius-value').textContent = drillSettings.radius;
        updateDrillPreviewSize();
        updateDrillStatus();
    });

    // 복셀 해상도
    document.getElementById('voxel-resolution').addEventListener('input', (e) => {
        drillSettings.resolution = parseInt(e.target.value);
        document.getElementById('voxel-resolution-value').textContent = drillSettings.resolution;
    });

    // Re-voxelize 버튼 (사이드바)
    document.getElementById('btn-revoxelize').addEventListener('click', revoxelize);

    // BC 브러쉬 반경 슬라이더
    const bcBrushRadiusSlider = document.getElementById('bc-brush-radius');
    if (bcBrushRadiusSlider) {
        bcBrushRadiusSlider.addEventListener('input', (e) => {
            bcBrushSettings.radius = parseFloat(e.target.value);
            document.getElementById('bc-brush-radius-value').textContent = bcBrushSettings.radius;
            // 프리뷰 구체 크기 업데이트
            if (currentTool === 'bc_brush') {
                updateDrillPreviewSize();
            }
        });
    }

    // STL 파일 입력
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

    // NRRD 파일 입력
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

    // Undo/Redo 버튼 (사이드바)
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
 * @param {string|null} tool - null=해제, 'drill'=드릴, 'bc_brush'=BC 브러쉬
 * @param {boolean} force - true면 토글 없이 강제 설정 (탭 전환 시 사용)
 */
function setTool(tool, force) {
    if (force) {
        // 강제 설정 (탭 전환 시)
        currentTool = tool;
    } else {
        // 일반 토글
        if (tool !== null && currentTool === tool) {
            currentTool = null;
        } else {
            currentTool = tool;
        }
    }

    // 상태바 업데이트
    const toolNames = { drill: 'Drill', bc_select: 'BC Select', bc_brush: 'BC Brush' };
    document.getElementById('current-tool').textContent = currentTool
        ? (toolNames[currentTool] || currentTool)
        : 'None';

    // 드릴 상태바
    const drillStatus = document.getElementById('drill-status');
    if (drillStatus) {
        drillStatus.style.display = (currentTool === 'drill' || currentTool === 'bc_brush') ? 'inline' : 'none';
        updateDrillStatus();
    }

    // 네비게이션 (우클릭=회전, 중클릭=팬, 휠=줌, 좌클릭=도구 전용)
    controls.enabled = true;
    controls.mouseButtons = {
        MIDDLE: THREE.MOUSE.PAN,
        RIGHT: THREE.MOUSE.ROTATE
    };

    drillPreview.visible = false;
    if (drillHighlight) drillHighlight.visible = false;
    if (bcBrushHighlight) bcBrushHighlight.visible = false;

    // 드릴/브러쉬 모드 진입 시 복셀 초기화
    if ((currentTool === 'drill' || currentTool === 'bc_brush') && !isDrillInitialized) {
        initializeVoxels();
    }

    // 도구 전환 시 프리뷰 구체 크기 갱신 (드릴 ↔ 브러쉬 반경 다름)
    if (currentTool === 'drill' || currentTool === 'bc_brush') {
        updateDrillPreviewSize();
    }

    // 드릴 토글 버튼 동기화
    updateDrillToggleButton();
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

    // Ctrl+드래그: 적용된 Force 화살표 방향 조정
    if (isRotatingArrow && rotatingForceEntry) {
        raycaster.setFromCamera(mouse, camera);
        const camDir = camera.getWorldDirection(new THREE.Vector3());
        const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(camDir, arrowOrigin);
        const target = new THREE.Vector3();
        raycaster.ray.intersectPlane(plane, target);
        if (target) {
            const newDir = target.sub(arrowOrigin).normalize();
            forceDirection.copy(newDir);
            updateAppliedForceArrowDirection(rotatingForceEntry, newDir);
            updateForceDirectionDisplay();
        }
        return;
    }

    if (currentTool === 'drill') {
        updateDrillPreview();
        if (isMouseDown) {
            const intersection = getIntersection();
            if (intersection) {
                performDrill(intersection);
            }
        }
    } else if (currentTool === 'bc_brush') {
        // BC 브러쉬: 드릴과 동일한 프리뷰 패턴
        const intersection = getIntersection();
        if (intersection) {
            drillPreview.position.copy(intersection.point);
            drillPreview.visible = true;

            // 호버 프리뷰 (BC 타입별 색상)
            if (!isMouseDown) {
                updateBCBrushPreview(intersection);
            }

            // 드래그 중 선택 누적 (Ctrl 시 화살표 조정이므로 제외)
            if (isMouseDown && preProcessor && !isRotatingArrow) {
                preProcessor.brushSelectSphere(intersection.point, bcBrushSettings.radius);
                updateBCSelectionVisual();
            }
        } else {
            drillPreview.visible = false;
            if (bcBrushHighlight) bcBrushHighlight.visible = false;
        }
    }
}

function onMouseDown(event) {
    if (event.button !== 0) return;
    isMouseDown = true;

    // Ctrl+좌클릭: Force 화살표 회전 시작 (선택 영역 있을 때 항상 가능)
    if (event.ctrlKey && currentTool === 'bc_brush' && appliedForceArrows.length > 0) {
        // 마지막 적용된 Force 화살표 방향 조정
        rotatingForceEntry = appliedForceArrows[appliedForceArrows.length - 1];
        arrowOrigin.copy(rotatingForceEntry.origin);
        isRotatingArrow = true;
        controls.enabled = false;  // 회전 중 OrbitControls 비활성
        return;
    }

    if (currentTool === 'drill') {
        // 드릴링 시작 시 스냅샷 저장 (Undo용)
        if (isDrillInitialized) {
            saveSnapshot();
        }

        const intersection = getIntersection();
        if (intersection) {
            performDrill(intersection);
        }
    } else if (currentTool === 'bc_brush' && preProcessor && !event.ctrlKey) {
        // BC 브러쉬: 클릭으로 선택 누적 (Ctrl 시 화살표 조정이므로 제외)
        const intersection = getIntersection();
        if (intersection) {
            preProcessor.brushSelectSphere(intersection.point, bcBrushSettings.radius);
            updateBCSelectionVisual();
            if (bcBrushHighlight) bcBrushHighlight.visible = false;
        }
    } else if (currentTool === 'bc_select' && preProcessor) {
        // BC 모드: 면 선택 (레거시)
        const intersection = getIntersection();
        if (intersection) {
            preProcessor.selectFace(intersection, event.shiftKey);
        }
    }
}

function onMouseUp() {
    isMouseDown = false;

    // 화살표 회전 종료
    if (isRotatingArrow) {
        isRotatingArrow = false;
        controls.enabled = true;
        rotatingForceEntry = null;
    }
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
            return `<div style="padding: 5px; color: #1565c0;">• ${name} (${count} tris, ${voxelCount} voxels)</div>`;
        });
    } else {
        // 원본 메쉬 정보 표시
        items = Object.entries(meshes).map(([name, mesh]) => {
            const count = mesh.geometry.attributes.position.count / 3;
            return `<div style="padding: 5px; color: #555;">• ${name} (${count} tris)</div>`;
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

            // File 탭으로 전환 + NRRD 설정 섹션 표시
            switchTab('file');
            const nrrdSection = document.getElementById('nrrd-settings-section');
            if (nrrdSection) nrrdSection.style.display = 'block';

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
            document.getElementById('current-tool').textContent = 'None';
        }
    };

    reader.onerror = () => {
        alert('파일 읽기 실패');
        document.getElementById('current-tool').textContent = 'None';
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

            // File 탭 유지
            switchTab('file');

            // 카메라 맞추기
            fitCameraToSceneFromVoxels();

            updateModelList();
            document.getElementById('current-tool').textContent = 'None';

            console.log('NRRD 메쉬 생성 완료');

        } catch (error) {
            console.error('NRRD 적용 실패:', error);
            alert('NRRD 적용 실패: ' + error.message);
            document.getElementById('current-tool').textContent = 'None';
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
// Analysis (전처리/후처리) 시스템
// ============================================================================

/**
 * Analysis 모드 초기화
 */
function initAnalysis() {
    // 복셀이 아직 초기화 안 됐으면 복셀화 실행
    if (!isDrillInitialized && Object.keys(meshes).length > 0) {
        initializeVoxels();
    }

    // PreProcessor 초기화
    if (!preProcessor) {
        const targetMeshes = isDrillInitialized ? voxelMeshes : meshes;
        preProcessor = new PreProcessor(scene, targetMeshes, voxelGrids);
    }

    // PostProcessor 초기화
    if (!postProcessor) {
        postProcessor = new PostProcessor(scene);
    }

    // WebSocket 연결
    if (!wsClient) {
        wsClient = new WSClient();
        wsClient.onConnect(() => {
            // Solve 패널 내 상태
            const el = document.getElementById('ws-status');
            if (el) { el.textContent = '연결됨'; el.style.color = '#27ae60'; }
            // 상태바 WS 표시
            const bar = document.getElementById('ws-status-bar');
            if (bar) { bar.textContent = '연결됨'; bar.style.color = '#27ae60'; }
        });
        wsClient.onDisconnect(() => {
            const el = document.getElementById('ws-status');
            if (el) { el.textContent = '미연결'; el.style.color = '#ff4444'; }
            const bar = document.getElementById('ws-status-bar');
            if (bar) { bar.textContent = '미연결'; bar.style.color = '#ff4444'; }
        });
        wsClient.onProgress((data) => {
            updateAnalysisProgress(data);
        });
        wsClient.onResult((data) => {
            onAnalysisResult(data);
        });
        wsClient.onError((data) => {
            onAnalysisError(data);
        });
        wsClient.connect();
    }
}

/**
 * 해석 실행
 */
function runAnalysis() {
    if (!preProcessor || !wsClient) {
        alert('Analysis 모드를 먼저 활성화하세요');
        return;
    }

    if (!wsClient.connected) {
        alert('서버에 연결되지 않았습니다.\nuv run python -m src.server.app 으로 서버를 시작하세요.');
        return;
    }

    const method = document.getElementById('solver-method').value;
    const request = preProcessor.buildAnalysisRequest(method);

    if (request.positions.length === 0) {
        alert('복셀 데이터가 없습니다. 먼저 STL을 로드하세요.');
        return;
    }

    // 원본 좌표 캐시 (후처리용)
    postProcessor.cachePositions(request.positions);

    // 진행률 표시
    const progressDiv = document.getElementById('analysis-progress');
    if (progressDiv) progressDiv.style.display = 'block';
    updateAnalysisProgress({ step: 'sending', message: '요청 전송 중...' });

    // 해석 요청 전송
    wsClient.send('run_analysis', request);

    console.log('해석 요청:', { method, particles: request.positions.length, bcs: request.boundary_conditions.length });
}

/**
 * 해석 진행률 업데이트
 */
function updateAnalysisProgress(data) {
    const textEl = document.getElementById('progress-text');
    const barEl = document.getElementById('progress-bar');

    if (textEl) textEl.textContent = data.message || data.step || '';

    // 단계별 진행률 추정
    const stepProgress = {
        sending: 5, init: 10, setup: 20, bc: 30,
        material: 40, solving: 70, postprocess: 90, done: 100,
    };
    const pct = stepProgress[data.step] || 50;
    if (barEl) barEl.style.width = pct + '%';
}

/**
 * 해석 결과 수신
 */
function onAnalysisResult(data) {
    console.log('해석 결과 수신:', data.info);

    // 진행률 완료
    updateAnalysisProgress({ step: 'done', message: `완료 (${data.info?.elapsed_time?.toFixed(2) || '?'}초)` });

    // 후처리기에 결과 로드
    postProcessor.loadResults(data);

    // 통계 표시
    const statsEl = document.getElementById('analysis-stats');
    if (statsEl && data.info) {
        statsEl.innerHTML = `
            <div>입자: ${data.info.n_particles || '?'}</div>
            <div>방법: ${data.info.method || '?'}</div>
            <div>수렴: ${data.info.converged ? '예' : '아니오'}</div>
            <div>반복: ${data.info.iterations || '?'}</div>
            <div>백엔드: ${data.info.backend || '?'}</div>
            <div>최대 변위: ${postProcessor.stats.maxDisp.toExponential(3)}</div>
        `;
    }

    // Post-process 탭으로 자동 전환
    switchTab('postprocess');
}

/**
 * 해석 에러 처리
 */
function onAnalysisError(data) {
    console.error('해석 에러:', data.message);
    updateAnalysisProgress({ step: 'error', message: `에러: ${data.message}` });
    alert('해석 실패: ' + data.message);
}

/**
 * Analysis 이벤트 리스너 설정 (사이드바 패널 내부 요소)
 */
function setupAnalysisListeners() {
    // 선택 해제 (사이드바 버튼)
    const clearSelBtn = document.getElementById('btn-clear-selection');
    if (clearSelBtn) clearSelBtn.addEventListener('click', () => {
        if (preProcessor) {
            preProcessor.clearSelection();
            preProcessor.clearBrushSelection();
        }
        clearBCSelectionHighlight();
        const countEl = document.getElementById('bc-selection-count');
        if (countEl) countEl.textContent = '0';
    });

    // Force 크기 슬라이더
    const forceMagSlider = document.getElementById('force-magnitude');
    if (forceMagSlider) {
        forceMagSlider.addEventListener('input', (e) => {
            forceMagnitude = parseFloat(e.target.value);
            document.getElementById('force-magnitude-value').textContent = forceMagnitude;
        });
    }

    // Force 방향 리셋 (-Y)
    const resetForceDirBtn = document.getElementById('btn-reset-force-dir');
    if (resetForceDirBtn) {
        resetForceDirBtn.addEventListener('click', () => {
            forceDirection.set(0, -1, 0);
            updateForceDirectionDisplay();
            // 적용된 Force 화살표가 있으면 마지막 것의 방향도 리셋
            if (appliedForceArrows.length > 0) {
                const entry = appliedForceArrows[appliedForceArrows.length - 1];
                updateAppliedForceArrowDirection(entry, forceDirection);
            }
        });
    }

    // Step 1: Fixed BC 적용
    const applyFixedBtn = document.getElementById('btn-apply-fixed');
    if (applyFixedBtn) applyFixedBtn.addEventListener('click', () => {
        if (!preProcessor) return;
        preProcessor.addFixedBC();
        // 적용 후 선택 정리
        clearBCSelectionHighlight();
        clearForceArrowPreview();
        const countEl = document.getElementById('bc-selection-count');
        if (countEl) countEl.textContent = '0';
    });

    // Step 2: Force BC 적용
    const applyForceBtn = document.getElementById('btn-apply-force');
    if (applyForceBtn) applyForceBtn.addEventListener('click', () => {
        if (!preProcessor) return;
        if (preProcessor.getBrushSelectionCount() === 0) return;
        // 적용 전 선택 위치 캡처 (적용 후 brushSelection이 비워지므로)
        const selectedPositions = preProcessor.getBrushSelectionWorldPositions();
        // 방향 × 크기로 Force 벡터 계산
        const dir = forceDirection.clone().normalize();
        const force = [dir.x * forceMagnitude, dir.y * forceMagnitude, dir.z * forceMagnitude];
        const bc = preProcessor.addForceBC(force);
        // 적용면 중심에 확정 화살표 생성
        createAppliedForceArrow(selectedPositions, forceDirection, forceMagnitude, bc);
        // 적용 후 선택 정리
        clearBCSelectionHighlight();
        clearForceArrowPreview();
        const countEl = document.getElementById('bc-selection-count');
        if (countEl) countEl.textContent = '0';
    });

    // BC 제거 (사이드바 버튼)
    const clearBcBtn = document.getElementById('btn-clear-bc');
    if (clearBcBtn) clearBcBtn.addEventListener('click', () => {
        if (preProcessor) {
            preProcessor.clearAllBC();
            preProcessor.clearBrushSelection();
        }
        clearBCHighlights();  // 브러쉬/선택/화살표 모두 정리
        const countEl = document.getElementById('bc-selection-count');
        if (countEl) countEl.textContent = '0';
    });

    // 재료 적용 (사이드바 버튼)
    const assignMatBtn = document.getElementById('btn-assign-material');
    if (assignMatBtn) assignMatBtn.addEventListener('click', () => {
        if (!preProcessor) return;
        applyMaterial();
    });

    // 해석 실행 (사이드바 버튼)
    const runBtn = document.getElementById('btn-run-analysis');
    if (runBtn) runBtn.addEventListener('click', () => {
        initAnalysis();
        runAnalysis();
    });

    // 후처리 슬라이더
    const vizMode = document.getElementById('viz-mode');
    if (vizMode) vizMode.addEventListener('change', (e) => {
        if (postProcessor) postProcessor.setMode(e.target.value);
    });

    const dispScale = document.getElementById('disp-scale');
    if (dispScale) dispScale.addEventListener('input', (e) => {
        document.getElementById('disp-scale-value').textContent = e.target.value;
        if (postProcessor) postProcessor.setDisplacementScale(parseFloat(e.target.value));
    });

    const particleSize = document.getElementById('particle-size');
    if (particleSize) particleSize.addEventListener('input', (e) => {
        document.getElementById('particle-size-value').textContent = parseFloat(e.target.value).toFixed(1);
        if (postProcessor) postProcessor.setParticleSize(parseFloat(e.target.value));
    });
}

// ============================================================================
// View 탭 이벤트 리스너
// ============================================================================
function setupViewListeners() {
    // 카메라 프리셋 버튼들
    document.getElementById('btn-cam-reset').addEventListener('click', fitCameraToScene);
    document.getElementById('btn-cam-front').addEventListener('click', () => setCameraPreset('front'));
    document.getElementById('btn-cam-back').addEventListener('click', () => setCameraPreset('back'));
    document.getElementById('btn-cam-top').addEventListener('click', () => setCameraPreset('top'));
    document.getElementById('btn-cam-bottom').addEventListener('click', () => setCameraPreset('bottom'));
    document.getElementById('btn-cam-left').addEventListener('click', () => setCameraPreset('left'));
    document.getElementById('btn-cam-right').addEventListener('click', () => setCameraPreset('right'));

    // Up 축 라디오 변경
    document.querySelectorAll('input[name="up-axis"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            currentUpAxis = e.target.value;
            if (currentUpAxis === 'z') {
                camera.up.set(0, 0, 1);
            } else {
                camera.up.set(0, 1, 0);
            }
            controls.update();
            // GridHelper 재생성
            updateGridToModel();
        });
    });

    // Ambient 밝기 슬라이더
    document.getElementById('ambient-intensity').addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        document.getElementById('ambient-intensity-value').textContent = val.toFixed(2);
        if (ambientLight) ambientLight.intensity = val;
    });

    // Directional 밝기 슬라이더
    document.getElementById('dir-intensity').addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        document.getElementById('dir-intensity-value').textContent = val.toFixed(2);
        if (dirLight) dirLight.intensity = val;
    });

    // 그림자 체크박스
    document.getElementById('chk-shadow').addEventListener('change', (e) => {
        renderer.shadowMap.enabled = e.target.checked;
        if (dirLight) dirLight.castShadow = e.target.checked;
        // 그림자 맵 변경 시 재렌더 필요
        renderer.shadowMap.needsUpdate = true;
    });

    // 배경색 선택
    document.getElementById('bg-color').addEventListener('change', (e) => {
        scene.background = new THREE.Color(e.target.value);
    });

    // Grid 표시 체크박스
    document.getElementById('chk-grid').addEventListener('change', (e) => {
        if (gridHelper) gridHelper.visible = e.target.checked;
    });

    // Axes 표시 체크박스
    document.getElementById('chk-axes').addEventListener('change', (e) => {
        if (axesHelper) axesHelper.visible = e.target.checked;
    });
}

// ============================================================================
// 임플란트 매니저
// ============================================================================
let implantManager = null;

/**
 * 임플란트 매니저 초기화 (지연 초기화)
 */
function initImplantManager() {
    if (implantManager) return;
    implantManager = new ImplantManager(scene, camera, renderer);
}

/**
 * 임플란트 목록 UI 업데이트
 */
function updateImplantList() {
    const listEl = document.getElementById('implant-list');
    if (!listEl || !implantManager) { if (listEl) listEl.innerHTML = ''; return; }

    const names = implantManager.getImplantNames();
    if (names.length === 0) {
        listEl.innerHTML = '<div style="color: #888;">임플란트 없음</div>';
        return;
    }

    listEl.innerHTML = names.map(name => `
        <div style="display: flex; align-items: center; gap: 4px; padding: 2px 0;">
            <span style="flex: 1; cursor: pointer; color: ${implantManager.selectedImplant === name ? '#1976d2' : '#444'};"
                  onclick="selectImplantUI('${name}')">${name}</span>
            <button onclick="removeImplantUI('${name}')" style="background: none; border: none; color: #e53935; cursor: pointer; font-size: 14px;" title="제거">✕</button>
        </div>
    `).join('');
}

function selectImplantUI(name) {
    initImplantManager();
    implantManager.selectImplant(name);
    updateImplantList();
}

function removeImplantUI(name) {
    if (!implantManager) return;
    implantManager.removeImplant(name);
    updateImplantList();
}

// ============================================================================
// CT/MRI 파이프라인 — 업로드 + 세그멘테이션 + 메쉬 추출
// ============================================================================
let uploadedNiftiPath = null;   // 업로드된 NIfTI 경로
let segLabelsPath = null;       // 세그멘테이션 라벨맵 경로
let segLabelInfo = null;        // 라벨 정보 배열

/**
 * NIfTI 파일 업로드 (REST)
 */
async function uploadNiftiFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const statusEl = document.getElementById('upload-status');
    const fnameEl = document.getElementById('upload-filename');
    const sizeEl = document.getElementById('upload-size');

    try {
        const resp = await fetch('/api/upload', { method: 'POST', body: formData });
        if (!resp.ok) throw new Error('업로드 실패: ' + resp.status);
        const data = await resp.json();

        uploadedNiftiPath = data.path;
        if (fnameEl) fnameEl.textContent = data.filename;
        if (sizeEl) sizeEl.textContent = (data.size / 1024 / 1024).toFixed(1) + ' MB';
        if (statusEl) statusEl.style.display = 'block';

        // 세그멘테이션 버튼 활성화
        const segBtn = document.getElementById('btn-run-segment');
        if (segBtn) segBtn.disabled = false;

        console.log('NIfTI 업로드 완료:', data.path);
    } catch (err) {
        alert('파일 업로드 실패: ' + err.message);
    }
}

/**
 * 세그멘테이션 실행 (WS)
 */
function runSegmentation() {
    if (!uploadedNiftiPath || !wsClient || !wsClient.connected) {
        alert('NIfTI를 먼저 업로드하고 서버에 연결하세요.');
        return;
    }

    const engine = document.getElementById('seg-engine').value;
    const fast = document.getElementById('seg-fast').checked;

    const progressEl = document.getElementById('seg-progress');
    if (progressEl) progressEl.style.display = 'block';

    // 세그멘테이션 요청 데이터 구성
    const segData = {
        input_path: uploadedNiftiPath,
        engine: engine,
        device: 'gpu',
        fast: fast,
    };

    // SpineUnified 엔진일 때 모달리티 추가
    if (engine === 'spine_unified') {
        const modalityEl = document.getElementById('seg-modality');
        const modality = modalityEl ? modalityEl.value : 'auto';
        if (modality !== 'auto') {
            segData.modality = modality;
        }
    }

    wsClient.send('segment', segData);
}

/**
 * 메쉬 추출 실행 (WS)
 */
function runExtractMeshes() {
    if (!segLabelsPath || !wsClient || !wsClient.connected) {
        alert('세그멘테이션을 먼저 실행하세요.');
        return;
    }

    wsClient.send('extract_meshes', {
        labels_path: segLabelsPath,
        resolution: 64,
        smooth: true,
    });
}

/**
 * 세그멘테이션 결과 수신 처리
 */
function onSegmentResult(data) {
    console.log('세그멘테이션 완료:', data);
    segLabelsPath = data.labels_path;
    segLabelInfo = data.label_info || [];

    // 라벨 목록 표시
    const labelsEl = document.getElementById('seg-labels');
    if (labelsEl) {
        labelsEl.style.display = 'block';
        labelsEl.innerHTML = '<div style="font-weight: bold; margin-bottom: 4px;">검출 라벨 (' + data.n_labels + '개):</div>' +
            segLabelInfo.map(l =>
                `<div style="padding: 1px 0;">• ${l.name} (${l.material_type}, ${l.voxel_count} voxels)</div>`
            ).join('');
    }

    // 진행률 완료
    const pEl = document.getElementById('seg-progress-text');
    if (pEl) pEl.textContent = '세그멘테이션 완료!';

    // 메쉬 추출 버튼 활성화
    const meshBtn = document.getElementById('btn-extract-meshes');
    if (meshBtn) meshBtn.disabled = false;
}

/**
 * 메쉬 추출 결과 수신 — 씬에 메쉬 추가
 */
function onMeshesExtracted(data) {
    console.log('메쉬 추출 완료:', data.meshes?.length, '개');

    if (!data.meshes || data.meshes.length === 0) {
        alert('추출된 메쉬가 없습니다.');
        return;
    }

    clearAllMeshes();

    data.meshes.forEach(m => {
        const vertices = new Float32Array(m.vertices.flat());
        const indices = new Uint32Array(m.faces.flat());

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
        geometry.setIndex(new THREE.BufferAttribute(indices, 1));
        geometry.computeVertexNormals();
        geometry.computeBoundingBox();

        // 색상 파싱
        const color = new THREE.Color(m.color || '#888888');
        const material = new THREE.MeshPhongMaterial({
            color: color,
            flatShading: false,
            side: THREE.DoubleSide,
            shininess: 30,
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.name = m.name;
        mesh.userData.drillable = true;
        mesh.userData.color = color.getHex();
        mesh.userData.labelValue = m.label;
        mesh.userData.materialType = m.material_type;
        mesh.castShadow = true;
        mesh.receiveShadow = true;

        scene.add(mesh);
        meshes[m.name] = mesh;
    });

    onAllLoaded();
    fitCameraToScene();
    console.log('CT/MRI 메쉬 로드 완료:', Object.keys(meshes).length, '개');
}

// ============================================================================
// DICOM 원클릭 파이프라인
// ============================================================================

/**
 * DICOM 파이프라인 진행률 UI 업데이트
 */
function updatePipelineStep(stepId, status) {
    const el = document.getElementById(stepId);
    if (!el) return;
    const icon = el.querySelector('.ps-icon');
    if (status === 'active') {
        el.style.color = '#7c4dff';
        el.style.fontWeight = 'bold';
        if (icon) icon.textContent = '◉';
    } else if (status === 'done') {
        el.style.color = '#4caf50';
        el.style.fontWeight = 'normal';
        if (icon) icon.textContent = '✓';
    } else if (status === 'error') {
        el.style.color = '#e53935';
        el.style.fontWeight = 'normal';
        if (icon) icon.textContent = '✗';
    }
}

function updatePipelineStepText(text) {
    const el = document.getElementById('dicom-pipeline-detail');
    if (el) el.textContent = text;
}

/**
 * DICOM 폴더 파일들을 REST 업로드 후 WS 파이프라인 실행
 */
async function runDicomPipeline(files) {
    if (!files || files.length === 0) return;

    // WS 연결 확인/초기화
    initAnalysis();
    if (!wsClient || !wsClient.connected) {
        alert('서버에 연결되지 않았습니다. 잠시 후 다시 시도하세요.');
        return;
    }

    // 진행률 UI 표시
    const progressEl = document.getElementById('dicom-pipeline-progress');
    if (progressEl) progressEl.style.display = 'block';
    const titleEl = document.getElementById('dicom-pipeline-title');
    if (titleEl) titleEl.textContent = '처리 중...';

    // 모든 스텝 초기화
    ['ps-upload', 'ps-convert', 'ps-segment', 'ps-mesh'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.style.color = '#888';
            el.style.fontWeight = 'normal';
            const icon = el.querySelector('.ps-icon');
            if (icon) icon.textContent = '○';
        }
    });

    // 1단계: 업로드
    updatePipelineStep('ps-upload', 'active');
    updatePipelineStepText(`${files.length}개 파일 업로드 중...`);

    const formData = new FormData();
    for (const f of files) {
        formData.append('files', f);
    }

    let uploadData;
    try {
        const resp = await fetch('/api/upload_dicom', { method: 'POST', body: formData });
        if (!resp.ok) {
            const errText = await resp.text();
            throw new Error(`업로드 실패 (${resp.status}): ${errText}`);
        }
        uploadData = await resp.json();
        updatePipelineStep('ps-upload', 'done');
        updatePipelineStepText(`${uploadData.n_files}개 파일 업로드 완료 (${(uploadData.total_size / 1024 / 1024).toFixed(1)} MB)`);
    } catch (err) {
        updatePipelineStep('ps-upload', 'error');
        updatePipelineStepText('업로드 실패: ' + err.message);
        if (titleEl) titleEl.textContent = '실패';
        alert('DICOM 업로드 실패: ' + err.message);
        return;
    }

    // 2단계: WS로 파이프라인 실행 요청
    updatePipelineStep('ps-convert', 'active');
    updatePipelineStepText('DICOM 변환 시작...');

    const engine = document.getElementById('dicom-engine')?.value || 'totalseg';
    const fast = document.getElementById('dicom-fast')?.checked || false;
    const smooth = document.getElementById('dicom-smooth')?.checked ?? true;

    wsClient.send('run_dicom_pipeline', {
        dicom_dir: uploadData.dicom_dir,
        engine: engine,
        device: 'gpu',
        fast: fast,
        smooth: smooth,
        resolution: 64,
    });
}

/**
 * 파이프라인 중간 단계 수신 처리
 */
function onPipelineStep(data) {
    console.log('파이프라인 단계:', data.step, data.message);
    updatePipelineStepText(data.message || '');

    const step = data.step;
    if (step === 'dicom_convert') {
        updatePipelineStep('ps-convert', 'active');
    } else if (step === 'dicom_convert_done') {
        updatePipelineStep('ps-convert', 'done');
        // NIfTI 경로 저장 (수동 워크플로우와 호환)
        if (data.nifti_path) uploadedNiftiPath = data.nifti_path;
    } else if (step === 'segmentation' || step === 'segment') {
        updatePipelineStep('ps-segment', 'active');
    } else if (step === 'segmentation_done') {
        updatePipelineStep('ps-segment', 'done');
        if (data.labels_path) segLabelsPath = data.labels_path;
        if (data.label_info) segLabelInfo = data.label_info;
    } else if (step === 'mesh_extract') {
        updatePipelineStep('ps-mesh', 'active');
    } else if (step === 'done') {
        // 개별 하위 단계 완료 메시지
    }
}

/**
 * 파이프라인 최종 결과 수신 — 메쉬 표시
 */
function onPipelineResult(data) {
    console.log('DICOM 파이프라인 완료:', data.meshes?.length, '개 메쉬');

    updatePipelineStep('ps-mesh', 'done');
    const titleEl = document.getElementById('dicom-pipeline-title');
    if (titleEl) titleEl.textContent = '완료!';
    updatePipelineStepText(`${data.meshes?.length || 0}개 3D 모델 생성됨`);

    // NIfTI/라벨 경로 저장 (수동 워크플로우 호환)
    if (data.nifti_path) uploadedNiftiPath = data.nifti_path;
    if (data.labels_path) segLabelsPath = data.labels_path;
    if (data.seg_info) segLabelInfo = data.seg_info;

    // 기존 onMeshesExtracted 재사용
    onMeshesExtracted({ meshes: data.meshes });
}

// ============================================================================
// 후처리 확장 — 수술 전/후 비교
// ============================================================================
let preOpResults = null;  // 수술 전 결과 캐시

function savePreOpResults() {
    if (!postProcessor || !postProcessor.data) {
        alert('해석 결과가 없습니다.');
        return;
    }
    preOpResults = JSON.parse(JSON.stringify(postProcessor.data));
    const compareBtn = document.getElementById('btn-compare');
    if (compareBtn) compareBtn.disabled = false;
    alert('수술 전 결과 저장 완료');
}

function showComparison() {
    if (!preOpResults || !postProcessor || !postProcessor.data) {
        alert('수술 전/후 결과가 모두 필요합니다.');
        return;
    }
    // 차이 계산: 현재 - 수술 전
    const preDisps = preOpResults.displacements;
    const postDisps = postProcessor.data.displacements;
    const n = Math.min(preDisps.length, postDisps.length);

    const diffDisps = [];
    for (let i = 0; i < n; i++) {
        diffDisps.push([
            (postDisps[i][0] || 0) - (preDisps[i][0] || 0),
            (postDisps[i][1] || 0) - (preDisps[i][1] || 0),
            (postDisps[i][2] || 0) - (preDisps[i][2] || 0),
        ]);
    }

    // 차이 데이터로 시각화
    const diffData = { ...postProcessor.data, displacements: diffDisps, info: { ...postProcessor.data.info, method: 'difference' } };
    postProcessor.loadResults(diffData);
}

// ============================================================================
// 재료 프리셋 → 수동 편집 동기화
// ============================================================================
const MATERIAL_PRESETS = {
    bone:             { E: 15e9,  nu: 0.3,  density: 1850 },
    cancellous_bone:  { E: 1e9,   nu: 0.3,  density: 1100 },
    disc:             { E: 10e6,  nu: 0.45, density: 1200 },
    soft_tissue:      { E: 1e6,   nu: 0.49, density: 1050 },
    titanium:         { E: 110e9, nu: 0.34, density: 4500 },
    peek:             { E: 4e9,   nu: 0.38, density: 1320 },
    cobalt_chrome:    { E: 230e9, nu: 0.30, density: 8300 },
    stainless_steel:  { E: 200e9, nu: 0.30, density: 7900 },
};

function syncMaterialPreset() {
    const preset = document.getElementById('material-preset').value;
    if (preset === 'custom') return;  // 사용자 직접 입력

    const p = MATERIAL_PRESETS[preset];
    if (!p) return;

    const eInput = document.getElementById('mat-E');
    const nuInput = document.getElementById('mat-nu');
    const densInput = document.getElementById('mat-density');
    if (eInput) eInput.value = p.E;
    if (nuInput) nuInput.value = p.nu;
    if (densInput) densInput.value = p.density;
}

// ============================================================================
// 확장 이벤트 리스너 — CT/MRI + 임플란트 + 비교
// ============================================================================
function setupExtendedListeners() {
    // DICOM 원클릭 파이프라인
    const dicomInput = document.getElementById('dicom-input');
    const dicomBtn = document.getElementById('btn-dicom-pipeline');
    if (dicomBtn && dicomInput) {
        dicomBtn.addEventListener('click', () => dicomInput.click());
        dicomInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                runDicomPipeline(e.target.files);
            }
            e.target.value = '';  // 같은 폴더 재선택 가능
        });
    }

    // NIfTI 업로드
    const niftiInput = document.getElementById('nifti-input');
    const uploadBtn = document.getElementById('btn-upload-nifti');
    if (uploadBtn && niftiInput) {
        uploadBtn.addEventListener('click', () => niftiInput.click());
        niftiInput.addEventListener('change', (e) => {
            if (e.target.files[0]) uploadNiftiFile(e.target.files[0]);
        });
    }

    // 세그멘테이션 실행
    const segBtn = document.getElementById('btn-run-segment');
    if (segBtn) segBtn.addEventListener('click', () => {
        initAnalysis();
        runSegmentation();
    });

    // 엔진 선택 → 모달리티 섹션 토글
    const segEngineSelect = document.getElementById('seg-engine');
    const modalitySection = document.getElementById('modality-section');
    if (segEngineSelect && modalitySection) {
        segEngineSelect.addEventListener('change', () => {
            modalitySection.style.display =
                segEngineSelect.value === 'spine_unified' ? 'block' : 'none';
        });
    }

    // 메쉬 추출
    const meshBtn = document.getElementById('btn-extract-meshes');
    if (meshBtn) meshBtn.addEventListener('click', () => {
        initAnalysis();
        runExtractMeshes();
    });

    // 임플란트 Import
    const implantInput = document.getElementById('implant-input');
    const implantBtn = document.getElementById('btn-import-implant');
    if (implantBtn && implantInput) {
        implantBtn.addEventListener('click', () => implantInput.click());
        implantInput.addEventListener('change', async (e) => {
            if (!e.target.files[0]) return;
            initImplantManager();
            const matType = document.getElementById('implant-material').value;
            try {
                await implantManager.loadImplantSTL(e.target.files[0], null, matType);
                updateImplantList();
            } catch (err) {
                alert('임플란트 로드 실패: ' + err.message);
            }
            e.target.value = '';  // 같은 파일 재선택 가능
        });
    }

    // 임플란트 TransformControls 모드
    const trBtn = document.getElementById('btn-impl-translate');
    const roBtn = document.getElementById('btn-impl-rotate');
    const scBtn = document.getElementById('btn-impl-scale');
    if (trBtn) trBtn.addEventListener('click', () => { if (implantManager) implantManager.setTransformMode('translate'); });
    if (roBtn) roBtn.addEventListener('click', () => { if (implantManager) implantManager.setTransformMode('rotate'); });
    if (scBtn) scBtn.addEventListener('click', () => { if (implantManager) implantManager.setTransformMode('scale'); });

    // 수술 계획 저장
    const savePlanBtn = document.getElementById('btn-save-plan');
    if (savePlanBtn) savePlanBtn.addEventListener('click', () => {
        if (!implantManager) { alert('임플란트가 없습니다.'); return; }
        const plan = implantManager.exportPlan();
        // BC/재료 정보도 추가
        if (preProcessor) {
            plan.boundary_conditions = preProcessor.getAllBC ? preProcessor.getAllBC() : [];
        }
        const blob = new Blob([JSON.stringify(plan, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'surgical_plan.json';
        a.click();
        URL.revokeObjectURL(url);
    });

    // 수술 계획 로드
    const planInput = document.getElementById('plan-input');
    const loadPlanBtn = document.getElementById('btn-load-plan');
    if (loadPlanBtn && planInput) {
        loadPlanBtn.addEventListener('click', () => planInput.click());
        planInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = (ev) => {
                try {
                    const plan = JSON.parse(ev.target.result);
                    initImplantManager();
                    implantManager.importPlan(plan);
                    updateImplantList();
                    console.log('수술 계획 로드 완료');
                } catch (err) {
                    alert('계획 파일 파싱 실패: ' + err.message);
                }
            };
            reader.readAsText(file);
            e.target.value = '';
        });
    }

    // 자동 재료 할당
    const autoMatBtn = document.getElementById('btn-auto-material');
    if (autoMatBtn) autoMatBtn.addEventListener('click', () => {
        if (!wsClient || !wsClient.connected) {
            alert('서버에 연결되지 않았습니다.');
            return;
        }
        // 라벨 값 수집 (현재 메쉬의 userData.labelValue)
        const labelValues = [];
        Object.values(meshes).forEach(mesh => {
            const lbl = mesh.userData.labelValue || 0;
            const positions = mesh.geometry.attributes.position;
            for (let i = 0; i < positions.count; i++) {
                labelValues.push(lbl);
            }
        });
        if (labelValues.length === 0) {
            alert('라벨 데이터가 없습니다. CT/MRI 파이프라인을 먼저 실행하세요.');
            return;
        }
        wsClient.send('auto_material', { label_values: labelValues });
    });

    // 재료 프리셋 변경 → 수동 편집 필드 동기화
    const presetSel = document.getElementById('material-preset');
    if (presetSel) presetSel.addEventListener('change', syncMaterialPreset);

    // 후처리 비교
    const savePreOpBtn = document.getElementById('btn-save-preop');
    if (savePreOpBtn) savePreOpBtn.addEventListener('click', savePreOpResults);
    const compareBtn = document.getElementById('btn-compare');
    if (compareBtn) compareBtn.addEventListener('click', showComparison);

    // 필터 반경 슬라이더
    const filterRadius = document.getElementById('filter-radius');
    if (filterRadius) filterRadius.addEventListener('input', (e) => {
        document.getElementById('filter-radius-value').textContent = e.target.value;
        // 필터 기능은 향후 확장
    });

    // WS 확장 콜백 등록
    if (wsClient) {
        wsClient.onSegmentResult(onSegmentResult);
        wsClient.onMeshesResult(onMeshesExtracted);
        wsClient.onMaterialResult((data) => {
            console.log('자동 재료 매핑:', data);
            alert(`재료 매핑 완료: ${data.materials?.length || 0}종\n수동 조정은 Pre-process 탭에서 가능합니다.`);
        });
        wsClient.onPipelineStep(onPipelineStep);
        wsClient.onPipelineResult(onPipelineResult);
    }
}

// ============================================================================
// initAnalysis 확장 — WS 콜백 등록
// ============================================================================
const _origInitAnalysis = initAnalysis;
initAnalysis = function() {
    _origInitAnalysis();
    // WS 확장 콜백 등록 (initAnalysis 호출 시 wsClient가 생성된 후)
    if (wsClient) {
        if (!wsClient._onSegmentResult) {
            wsClient.onSegmentResult(onSegmentResult);
            wsClient.onMeshesResult(onMeshesExtracted);
            wsClient.onMaterialResult((data) => {
                console.log('자동 재료 매핑:', data);
                alert(`재료 매핑 완료: ${data.materials?.length || 0}종`);
            });
            wsClient.onPipelineStep(onPipelineStep);
            wsClient.onPipelineResult(onPipelineResult);
        }
    }
};

// ============================================================================
// 시작
// ============================================================================
init();
setupExtendedListeners();
