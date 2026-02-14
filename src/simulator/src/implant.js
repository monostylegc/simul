/**
 * 임플란트 매니저 (ImplantManager)
 * — 외부 STL 임플란트 로드, TransformControls 기반 배치, 수술 계획 JSON 관리
 */
class ImplantManager {
    constructor(threeScene, threeCamera, threeRenderer) {
        this.scene = threeScene;
        this.camera = threeCamera;
        this.renderer = threeRenderer;

        // 임플란트 목록: { name → { mesh, stlPath, material } }
        this.implants = {};

        // TransformControls
        this.transformControls = null;
        this.selectedImplant = null;
        this._transformMode = 'translate';

        this._initTransformControls();
    }

    /**
     * TransformControls 초기화
     */
    _initTransformControls() {
        if (typeof THREE.TransformControls === 'undefined') {
            console.warn('TransformControls 미로드 — 임플란트 배치 불가');
            return;
        }

        this.transformControls = new THREE.TransformControls(this.camera, this.renderer.domElement);
        this.transformControls.setSize(0.8);
        this.scene.add(this.transformControls);

        // TransformControls 드래그 중 OrbitControls 비활성화
        this.transformControls.addEventListener('dragging-changed', (event) => {
            if (typeof controls !== 'undefined' && controls) {
                controls.enabled = !event.value;
            }
        });
    }

    /**
     * 외부 STL 파일 로드
     * @param {File} file - STL 파일 객체
     * @param {string} [name] - 임플란트 이름 (없으면 파일명)
     * @param {string} [materialType='titanium'] - 재료 타입
     */
    loadImplantSTL(file, name, materialType = 'titanium') {
        return new Promise((resolve, reject) => {
            if (!name) {
                name = file.name.replace(/\.[^/.]+$/, '');
            }

            // 중복 이름 처리
            if (this.implants[name]) {
                let i = 2;
                while (this.implants[`${name}_${i}`]) i++;
                name = `${name}_${i}`;
            }

            const reader = new FileReader();
            reader.onload = (e) => {
                const loader = new THREE.STLLoader();
                try {
                    const geometry = loader.parse(e.target.result);
                    geometry.computeVertexNormals();
                    geometry.computeBoundingBox();

                    // 임플란트 색상 (재료별)
                    const color = this._materialColor(materialType);
                    const material = new THREE.MeshPhongMaterial({
                        color: color,
                        flatShading: false,
                        side: THREE.DoubleSide,
                        shininess: 60,
                        transparent: true,
                        opacity: 0.85,
                    });

                    const mesh = new THREE.Mesh(geometry, material);
                    mesh.name = 'implant_' + name;
                    mesh.userData.isImplant = true;
                    mesh.userData.implantName = name;
                    mesh.userData.materialType = materialType;
                    mesh.castShadow = true;

                    // 씬의 중심에 배치
                    const box = new THREE.Box3();
                    this.scene.traverse(obj => {
                        if (obj.isMesh && !obj.userData.isImplant) {
                            box.expandByObject(obj);
                        }
                    });
                    if (!box.isEmpty()) {
                        const center = box.getCenter(new THREE.Vector3());
                        mesh.position.copy(center);
                    }

                    this.scene.add(mesh);
                    this.implants[name] = {
                        mesh: mesh,
                        stlPath: file.name,
                        material: materialType,
                    };

                    console.log(`임플란트 로드: ${name} (${materialType})`);
                    resolve(name);
                } catch (err) {
                    reject(err);
                }
            };
            reader.onerror = reject;
            reader.readAsArrayBuffer(file);
        });
    }

    /**
     * 임플란트 선택 (TransformControls 바인딩)
     */
    selectImplant(name) {
        if (!this.implants[name]) {
            console.warn(`임플란트 없음: ${name}`);
            return;
        }

        this.selectedImplant = name;
        const mesh = this.implants[name].mesh;

        if (this.transformControls) {
            this.transformControls.attach(mesh);
        }
    }

    /**
     * 선택 해제
     */
    deselectImplant() {
        this.selectedImplant = null;
        if (this.transformControls) {
            this.transformControls.detach();
        }
    }

    /**
     * TransformControls 모드 설정
     * @param {'translate'|'rotate'|'scale'} mode
     */
    setTransformMode(mode) {
        this._transformMode = mode;
        if (this.transformControls) {
            this.transformControls.setMode(mode);
        }
    }

    /**
     * 임플란트 변환 정보 반환
     */
    getImplantTransform(name) {
        const entry = this.implants[name];
        if (!entry) return null;

        const mesh = entry.mesh;
        return {
            position: [mesh.position.x, mesh.position.y, mesh.position.z],
            rotation: [mesh.rotation.x, mesh.rotation.y, mesh.rotation.z],
            scale: [mesh.scale.x, mesh.scale.y, mesh.scale.z],
        };
    }

    /**
     * 임플란트 제거
     */
    removeImplant(name) {
        const entry = this.implants[name];
        if (!entry) return;

        if (this.selectedImplant === name) {
            this.deselectImplant();
        }

        this.scene.remove(entry.mesh);
        if (entry.mesh.geometry) entry.mesh.geometry.dispose();
        if (entry.mesh.material) entry.mesh.material.dispose();

        delete this.implants[name];
        console.log(`임플란트 제거: ${name}`);
    }

    /**
     * 모든 임플란트 이름 목록
     */
    getImplantNames() {
        return Object.keys(this.implants);
    }

    /**
     * 수술 계획 JSON 내보내기
     */
    exportPlan() {
        const implants = [];
        for (const [name, entry] of Object.entries(this.implants)) {
            const transform = this.getImplantTransform(name);
            implants.push({
                name: name,
                stl_path: entry.stlPath,
                position: transform.position,
                rotation: transform.rotation,
                scale: transform.scale,
                material: entry.material,
            });
        }

        return {
            implants: implants,
            bone_modifications: {},  // 드릴 히스토리는 별도
        };
    }

    /**
     * 수술 계획 JSON에서 복원
     */
    importPlan(planData) {
        if (!planData || !planData.implants) return;

        // 임플란트 위치/회전 복원 (STL은 이미 로드된 상태 가정)
        for (const impl of planData.implants) {
            const entry = this.implants[impl.name];
            if (!entry) continue;

            const mesh = entry.mesh;
            if (impl.position) mesh.position.set(...impl.position);
            if (impl.rotation) mesh.rotation.set(...impl.rotation);
            if (impl.scale) mesh.scale.set(...impl.scale);
            if (impl.material) entry.material = impl.material;
        }
    }

    /**
     * 정리
     */
    dispose() {
        this.deselectImplant();
        for (const name of Object.keys(this.implants)) {
            this.removeImplant(name);
        }
        if (this.transformControls) {
            this.scene.remove(this.transformControls);
            this.transformControls.dispose();
            this.transformControls = null;
        }
    }

    // ── 내부 메서드 ──

    _materialColor(materialType) {
        const colors = {
            titanium: 0x8899aa,
            peek: 0xccbb88,
            cobalt_chrome: 0x99aacc,
            stainless_steel: 0xaaaaaa,
        };
        return colors[materialType] || 0x8899aa;
    }
}
