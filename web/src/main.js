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

const drillSettings = {
    radius: 5,
    depth: 10,
    resolution: 48  // 복셀 해상도
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
            if (loadedCount >= totalFiles) arrangeVertebrae(geometries);
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
            if (loadedCount >= totalFiles) arrangeVertebrae(geometries);
        },
        (progress) => console.log('L4 progress:', Math.round(progress.loaded/progress.total*100) + '%'),
        (error) => console.error('L4 error:', error)
    );
}

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
    // L5의 높이 + 약간의 간격
    const l5Height = l5Box.max.y - l5Box.min.y;
    const gap = 5;  // 척추 사이 간격
    const l4Offset = {
        x: -l4Center.x,
        y: -l5Center.y + l5Height / 2 + gap + (l4Box.max.y - l4Box.min.y) / 2,
        z: -l4Center.z
    };

    // 메쉬 추가
    addSTLMesh(geometries.L5, 'L5', 0xe6d5c3, l5Offset);
    addSTLMesh(geometries.L4, 'L4', 0xd4c4b0, l4Offset);

    onAllLoaded();
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
        const file = e.target.files[0];
        if (file) loadSTLFile(file);
    });

    document.getElementById('btn-clear-all').addEventListener('click', clearAllMeshes);

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
}

function loadSTLFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        const loader = new THREE.STLLoader();
        const geometry = loader.parse(e.target.result);
        const name = file.name.replace(/\.[^/.]+$/, '');
        addSTLMesh(geometry, name, 0xe6d5c3);
        fitCameraToScene();
        updateModelList();
        isDrillInitialized = false;  // 새 메쉬 추가시 복셀 재초기화 필요
    };
    reader.readAsArrayBuffer(file);
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
// 시작
// ============================================================================
init();
