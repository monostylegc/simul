/**
 * FEA 결과 시각화 메인 스크립트
 *
 * Three.js 기반 입자 시각화
 * - 변위 (displacement)
 * - von Mises 변형률 (strain)
 * - 손상도 (damage)
 */

// ============================================================================
// 전역 변수
// ============================================================================
let scene, camera, renderer, controls;
let particleSystem = null;
let feaData = null;

// 시각화 설정
const config = {
    mode: 'displacement',  // displacement, strain, damage, original
    particleSize: 1.0,
    dispScale: 10.0,
    colorMax: 0.02
};

// ============================================================================
// 초기화
// ============================================================================
function init() {
    // 씬 생성
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);

    // 캔버스 컨테이너
    const container = document.getElementById('canvas-container');
    const width = container.clientWidth;
    const height = container.clientHeight;

    // 카메라
    camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 10000);
    camera.position.set(200, 200, 200);
    camera.lookAt(0, 0, 0);

    // 렌더러
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // 컨트롤
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;

    // 조명
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(100, 200, 100);
    scene.add(directionalLight);

    // 그리드
    const gridHelper = new THREE.GridHelper(200, 20, 0x444444, 0x333333);
    scene.add(gridHelper);

    // 축 헬퍼
    const axesHelper = new THREE.AxesHelper(50);
    scene.add(axesHelper);

    // 이벤트 리스너
    setupEventListeners();

    // 리사이즈 핸들러
    window.addEventListener('resize', onWindowResize);

    // 애니메이션 시작
    animate();

    console.log('FEA Viewer 초기화 완료');
}

// ============================================================================
// 이벤트 리스너 설정
// ============================================================================
function setupEventListeners() {
    // 파일 로드
    document.getElementById('btn-load').addEventListener('click', () => {
        document.getElementById('file-input').click();
    });

    document.getElementById('file-input').addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            loadJSONFile(e.target.files[0]);
        }
    });

    document.getElementById('btn-load-sample').addEventListener('click', loadSampleData);

    // 시각화 모드
    document.querySelectorAll('[data-mode]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-mode]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            config.mode = btn.dataset.mode;
            document.getElementById('current-mode').textContent =
                btn.textContent.charAt(0).toUpperCase() + btn.textContent.slice(1);
            updateVisualization();
        });
    });

    // 슬라이더
    document.getElementById('particle-size').addEventListener('input', (e) => {
        config.particleSize = parseFloat(e.target.value);
        document.getElementById('particle-size-value').textContent = config.particleSize.toFixed(1);
        updateVisualization();
    });

    document.getElementById('disp-scale').addEventListener('input', (e) => {
        config.dispScale = parseFloat(e.target.value);
        document.getElementById('disp-scale-value').textContent = config.dispScale.toFixed(0);
        updateVisualization();
    });

    document.getElementById('color-max').addEventListener('input', (e) => {
        config.colorMax = parseFloat(e.target.value);
        document.getElementById('color-max-value').textContent = config.colorMax.toFixed(3);
        updateColorbar();
        updateVisualization();
    });

    // 뷰 버튼
    document.getElementById('btn-reset-view').addEventListener('click', () => {
        if (feaData) {
            fitCameraToData();
        } else {
            camera.position.set(200, 200, 200);
            camera.lookAt(0, 0, 0);
        }
    });

    document.getElementById('btn-top-view').addEventListener('click', () => {
        const center = getDataCenter();
        camera.position.set(center.x, center.y + 300, center.z);
        camera.lookAt(center.x, center.y, center.z);
    });

    document.getElementById('btn-front-view').addEventListener('click', () => {
        const center = getDataCenter();
        camera.position.set(center.x, center.y, center.z + 300);
        camera.lookAt(center.x, center.y, center.z);
    });

    document.getElementById('btn-side-view').addEventListener('click', () => {
        const center = getDataCenter();
        camera.position.set(center.x + 300, center.y, center.z);
        camera.lookAt(center.x, center.y, center.z);
    });

    // 스크린샷
    document.getElementById('btn-screenshot').addEventListener('click', takeScreenshot);
}

// ============================================================================
// 데이터 로드
// ============================================================================
function loadJSONFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const data = JSON.parse(e.target.result);
            loadData(data);
            document.getElementById('file-info').textContent = `Loaded: ${file.name}`;
        } catch (err) {
            alert('JSON 파싱 오류: ' + err.message);
        }
    };
    reader.readAsText(file);
}

function loadSampleData() {
    // 샘플 데이터 생성 (구 형태)
    const n = 500;
    const positions = [];
    const displacements = [];
    const strains = [];
    const damages = [];

    // 구 형태로 입자 배치
    const radius = 50;
    for (let i = 0; i < n; i++) {
        // 피보나치 격자로 구 표면에 균일 분포
        const phi = Math.acos(1 - 2 * (i + 0.5) / n);
        const theta = Math.PI * (1 + Math.sqrt(5)) * i;

        const r = radius * Math.cbrt(Math.random() * 0.8 + 0.2);  // 내부까지 채움
        const x = r * Math.sin(phi) * Math.cos(theta);
        const y = r * Math.sin(phi) * Math.sin(theta);
        const z = r * Math.cos(phi);

        positions.push([x, y, z]);

        // 변위: z 방향 압축 + 측면 팽창
        const compressZ = -0.01 * z;
        const expandXY = 0.003 * Math.sqrt(x*x + y*y) * Math.sign(z);
        displacements.push([
            expandXY * x / (Math.sqrt(x*x + y*y) + 0.001),
            expandXY * y / (Math.sqrt(x*x + y*y) + 0.001),
            compressZ
        ]);

        // 변형률: 중심에서 멀수록 높음
        const dist = Math.sqrt(x*x + y*y + z*z);
        strains.push(0.02 * dist / radius);

        // 손상도: 상단/하단 가장자리에서 높음
        const edgeDist = Math.abs(z) / radius;
        damages.push(edgeDist > 0.8 ? (edgeDist - 0.8) * 2 : 0);
    }

    const data = {
        positions: positions,
        displacements: displacements,
        von_mises_strain: strains,
        damage: damages
    };

    loadData(data);
    document.getElementById('file-info').textContent = 'Sample data loaded';
}

function loadData(data) {
    feaData = {
        positions: data.positions,
        displacements: data.displacements || data.positions.map(() => [0, 0, 0]),
        strains: data.von_mises_strain || data.strains || data.positions.map(() => 0),
        damages: data.damage || data.positions.map(() => 0)
    };

    // 통계 업데이트
    updateStatistics();

    // 시각화 업데이트
    updateVisualization();

    // 카메라 맞춤
    fitCameraToData();

    console.log(`데이터 로드 완료: ${feaData.positions.length} 입자`);
}

// ============================================================================
// 시각화 업데이트
// ============================================================================
function updateVisualization() {
    if (!feaData) return;

    // 기존 파티클 시스템 제거
    if (particleSystem) {
        scene.remove(particleSystem);
        particleSystem.geometry.dispose();
        particleSystem.material.dispose();
    }

    const n = feaData.positions.length;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(n * 3);
    const colors = new Float32Array(n * 3);

    for (let i = 0; i < n; i++) {
        // 위치 계산
        let x = feaData.positions[i][0];
        let y = feaData.positions[i][1];
        let z = feaData.positions[i][2];

        // 변위 모드일 때 변위 적용
        if (config.mode === 'displacement' || config.mode === 'strain' || config.mode === 'damage') {
            x += feaData.displacements[i][0] * config.dispScale;
            y += feaData.displacements[i][1] * config.dispScale;
            z += feaData.displacements[i][2] * config.dispScale;
        }

        positions[i * 3] = x;
        positions[i * 3 + 1] = y;
        positions[i * 3 + 2] = z;

        // 색상 계산
        let value = 0;
        if (config.mode === 'displacement') {
            const dx = feaData.displacements[i][0];
            const dy = feaData.displacements[i][1];
            const dz = feaData.displacements[i][2];
            value = Math.sqrt(dx*dx + dy*dy + dz*dz);
        } else if (config.mode === 'strain') {
            value = feaData.strains[i];
        } else if (config.mode === 'damage') {
            value = feaData.damages[i];
        } else {
            value = 0;  // original - 회색
        }

        const color = valueToColor(value, config.colorMax);
        colors[i * 3] = color.r;
        colors[i * 3 + 1] = color.g;
        colors[i * 3 + 2] = color.b;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    // 포인트 재질
    const material = new THREE.PointsMaterial({
        size: 5 * config.particleSize,
        vertexColors: true,
        sizeAttenuation: true
    });

    particleSystem = new THREE.Points(geometry, material);
    scene.add(particleSystem);
}

// ============================================================================
// 컬러맵
// ============================================================================
function valueToColor(value, maxValue) {
    // 0 ~ maxValue를 0 ~ 1로 정규화
    const t = Math.min(1, Math.max(0, value / maxValue));

    // Jet 컬러맵 (파랑 → 청록 → 초록 → 노랑 → 빨강)
    let r, g, b;

    if (t < 0.25) {
        // 파랑 → 청록
        r = 0;
        g = t * 4;
        b = 1;
    } else if (t < 0.5) {
        // 청록 → 초록
        r = 0;
        g = 1;
        b = 1 - (t - 0.25) * 4;
    } else if (t < 0.75) {
        // 초록 → 노랑
        r = (t - 0.5) * 4;
        g = 1;
        b = 0;
    } else {
        // 노랑 → 빨강
        r = 1;
        g = 1 - (t - 0.75) * 4;
        b = 0;
    }

    return { r, g, b };
}

function updateColorbar() {
    document.getElementById('colorbar-max').textContent = config.colorMax.toFixed(3);
    document.getElementById('colorbar-mid').textContent = (config.colorMax / 2).toFixed(3);
    document.getElementById('colorbar-min').textContent = '0.000';
}

// ============================================================================
// 통계 업데이트
// ============================================================================
function updateStatistics() {
    if (!feaData) return;

    const n = feaData.positions.length;
    document.getElementById('stat-particles').textContent = n;

    // 최대 변위
    let maxDisp = 0;
    for (let i = 0; i < n; i++) {
        const dx = feaData.displacements[i][0];
        const dy = feaData.displacements[i][1];
        const dz = feaData.displacements[i][2];
        const disp = Math.sqrt(dx*dx + dy*dy + dz*dz);
        if (disp > maxDisp) maxDisp = disp;
    }
    document.getElementById('stat-max-disp').textContent = maxDisp.toExponential(3);

    // 최대 변형률
    const maxStrain = Math.max(...feaData.strains);
    document.getElementById('stat-max-strain').textContent = maxStrain.toExponential(3);

    // 최대 손상도
    const maxDamage = Math.max(...feaData.damages);
    document.getElementById('stat-max-damage').textContent = maxDamage.toFixed(4);
}

// ============================================================================
// 카메라 유틸리티
// ============================================================================
function getDataCenter() {
    if (!feaData) return new THREE.Vector3(0, 0, 0);

    let cx = 0, cy = 0, cz = 0;
    const n = feaData.positions.length;
    for (let i = 0; i < n; i++) {
        cx += feaData.positions[i][0];
        cy += feaData.positions[i][1];
        cz += feaData.positions[i][2];
    }
    return new THREE.Vector3(cx / n, cy / n, cz / n);
}

function fitCameraToData() {
    if (!feaData) return;

    const center = getDataCenter();

    // 바운딩 박스 계산
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;

    for (const pos of feaData.positions) {
        minX = Math.min(minX, pos[0]);
        minY = Math.min(minY, pos[1]);
        minZ = Math.min(minZ, pos[2]);
        maxX = Math.max(maxX, pos[0]);
        maxY = Math.max(maxY, pos[1]);
        maxZ = Math.max(maxZ, pos[2]);
    }

    const size = Math.max(maxX - minX, maxY - minY, maxZ - minZ);
    const dist = size * 2;

    camera.position.set(center.x + dist, center.y + dist * 0.5, center.z + dist);
    camera.lookAt(center.x, center.y, center.z);
    controls.target.set(center.x, center.y, center.z);
}

// ============================================================================
// 스크린샷
// ============================================================================
function takeScreenshot() {
    renderer.render(scene, camera);
    const dataURL = renderer.domElement.toDataURL('image/png');

    const link = document.createElement('a');
    link.download = 'fea_result.png';
    link.href = dataURL;
    link.click();
}

// ============================================================================
// 렌더 루프
// ============================================================================
let lastTime = 0;
let frameCount = 0;

function animate(time) {
    requestAnimationFrame(animate);

    controls.update();
    renderer.render(scene, camera);

    // FPS 계산
    frameCount++;
    if (time - lastTime >= 1000) {
        document.getElementById('fps').textContent = frameCount;
        frameCount = 0;
        lastTime = time;
    }
}

function onWindowResize() {
    const container = document.getElementById('canvas-container');
    const width = container.clientWidth;
    const height = container.clientHeight;

    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
}

// ============================================================================
// 시작
// ============================================================================
init();
