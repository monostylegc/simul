/**
 * 후처리기 (PostProcessor)
 * — 해석 결과를 컬러맵으로 시각화 (변위/응력/손상)
 */
class PostProcessor {
    constructor(threeScene) {
        this.scene = threeScene;

        // 결과 데이터
        this.data = null;  // {positions, displacements, stress, damage, info}

        // 시각화 오브젝트
        this._points = null;
        this._geometry = null;

        // 설정
        this.mode = 'displacement';  // 'displacement' | 'stress' | 'damage'
        this.dispScale = 10.0;       // 변위 확대 배율
        this.particleSize = 2.0;     // 포인트 크기

        // 통계
        this.stats = { maxDisp: 0, maxStress: 0, maxDamage: 0 };
    }

    /**
     * 해석 결과 로드
     * @param {Object} resultData - 서버에서 받은 결과
     *   {displacements: [[dx,dy,dz],...], stress: [...], damage: [...], info: {...}}
     */
    loadResults(resultData) {
        this.data = resultData;
        this._computeStats();
        this.updateVisualization();

        console.log('후처리 결과 로드:', {
            입자수: resultData.info?.n_particles,
            방법: resultData.info?.method,
            수렴: resultData.info?.converged,
        });
    }

    /**
     * 시각화 모드 변경
     * @param {string} mode - 'displacement' | 'stress' | 'damage'
     */
    setMode(mode) {
        this.mode = mode;
        if (this.data) this.updateVisualization();
    }

    /**
     * 변위 확대 배율 변경
     */
    setDisplacementScale(scale) {
        this.dispScale = scale;
        if (this.data && this.mode === 'displacement') {
            this.updateVisualization();
        }
    }

    /**
     * 포인트 크기 변경
     */
    setParticleSize(size) {
        this.particleSize = size;
        if (this._points && this._points.material) {
            this._points.material.size = size;
        }
    }

    /**
     * 시각화 업데이트 (현재 모드에 맞게)
     */
    updateVisualization() {
        if (!this.data) return;

        this.clear();

        const positions = this.data.displacements.length > 0
            ? this._getDeformedPositions()
            : [];

        if (positions.length === 0) return;

        const n = positions.length;

        // 스칼라 값 추출 (모드별)
        const scalars = this._getScalars();
        if (!scalars || scalars.length === 0) return;

        // 컬러 계산
        const { colors, min: cMin, max: cMax } = valuesToColors(scalars);

        // BufferGeometry 생성
        this._geometry = new THREE.BufferGeometry();

        const posArray = new Float32Array(n * 3);
        for (let i = 0; i < n; i++) {
            posArray[i * 3] = positions[i][0];
            posArray[i * 3 + 1] = positions[i][1];
            posArray[i * 3 + 2] = positions[i][2];
        }

        this._geometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
        this._geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        // PointsMaterial
        const material = new THREE.PointsMaterial({
            size: this.particleSize,
            vertexColors: true,
            sizeAttenuation: true,
            depthTest: true,
        });

        this._points = new THREE.Points(this._geometry, material);
        this._points.name = 'analysis_result';
        this.scene.add(this._points);

        // 컬러바 업데이트
        const labels = {
            displacement: 'Displacement [mm]',
            stress: 'von Mises Stress [Pa]',
            damage: 'Damage [0-1]',
        };
        createColorbar('analysis-colorbar', cMin, cMax, labels[this.mode] || '');
    }

    /**
     * 컬러바 업데이트
     */
    updateColorbar() {
        if (!this.data) return;
        const scalars = this._getScalars();
        if (!scalars || scalars.length === 0) return;
        const minVal = Math.min(...scalars);
        const maxVal = Math.max(...scalars);
        const labels = {
            displacement: 'Displacement [mm]',
            stress: 'von Mises Stress [Pa]',
            damage: 'Damage [0-1]',
        };
        createColorbar('analysis-colorbar', minVal, maxVal, labels[this.mode] || '');
    }

    /**
     * 결과 시각화 제거
     */
    clear() {
        if (this._points) {
            this.scene.remove(this._points);
            this._points = null;
        }
        if (this._geometry) {
            this._geometry.dispose();
            this._geometry = null;
        }
    }

    // ====================================================================
    // 내부 메서드
    // ====================================================================

    _computeStats() {
        if (!this.data) return;

        const { displacements, stress, damage } = this.data;

        // 최대 변위 크기
        this.stats.maxDisp = 0;
        if (displacements && displacements.length > 0) {
            for (const d of displacements) {
                const mag = Math.sqrt(d[0] ** 2 + d[1] ** 2 + (d[2] || 0) ** 2);
                if (mag > this.stats.maxDisp) this.stats.maxDisp = mag;
            }
        }

        // 최대 응력
        this.stats.maxStress = 0;
        if (stress && stress.length > 0) {
            if (typeof stress[0] === 'number') {
                // 스칼라 (von Mises)
                this.stats.maxStress = Math.max(...stress);
            } else {
                // 텐서 → von Mises 크기
                for (const s of stress) {
                    const mag = Math.sqrt(s.reduce((sum, v) => sum + v * v, 0));
                    if (mag > this.stats.maxStress) this.stats.maxStress = mag;
                }
            }
        }

        // 최대 손상
        this.stats.maxDamage = 0;
        if (damage && damage.length > 0) {
            this.stats.maxDamage = Math.max(...damage);
        }
    }

    /**
     * 변형 좌표 계산 (ref + disp * scale)
     */
    _getDeformedPositions() {
        // 서버에서 positions 정보가 없으면 displacements에서 유추
        // 실제로는 원본 위치 + 변위 * 스케일
        const disps = this.data.displacements;
        const n = disps.length;

        // info에서 원본 positions 참조 (별도 전송 필요할 수 있음)
        // MVP: displacements를 positions로 사용 (서버에서 positions도 보내야 함)
        // 서버가 positions 정보를 따로 보내지 않으므로
        // domain의 positions를 사용해야 하지만 현재 구조상 없으므로
        // request 시 보낸 positions를 로컬에 캐싱해둔다
        if (this._cachedPositions) {
            const result = [];
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

        // 폴백: 변위를 직접 좌표로 사용 (임시)
        return disps;
    }

    /**
     * 현재 모드에 맞는 스칼라 배열 반환
     */
    _getScalars() {
        if (!this.data) return null;

        switch (this.mode) {
            case 'displacement': {
                const disps = this.data.displacements;
                return disps.map(d =>
                    Math.sqrt(d[0] ** 2 + d[1] ** 2 + (d[2] || 0) ** 2)
                );
            }
            case 'stress': {
                const stress = this.data.stress;
                if (!stress || stress.length === 0) return null;
                if (typeof stress[0] === 'number') return stress;
                // 텐서 → von Mises 크기
                return stress.map(s =>
                    Math.sqrt(s.reduce((sum, v) => sum + v * v, 0))
                );
            }
            case 'damage': {
                return this.data.damage || [];
            }
            default:
                return null;
        }
    }

    /**
     * 해석 요청 시 원본 좌표를 캐시 (변형 좌표 계산용)
     */
    cachePositions(positions) {
        this._cachedPositions = positions;
    }

    /**
     * 수술 전 결과 저장
     */
    savePreOpResults() {
        if (!this.data) return null;
        return JSON.parse(JSON.stringify(this.data));
    }

    /**
     * 수술 전/후 비교 (차이 컬러맵)
     * @param {Object} preOpData - 수술 전 결과
     */
    showComparison(preOpData) {
        if (!preOpData || !this.data) return;

        const preDisps = preOpData.displacements;
        const postDisps = this.data.displacements;
        const n = Math.min(preDisps.length, postDisps.length);

        const diffDisps = [];
        for (let i = 0; i < n; i++) {
            diffDisps.push([
                (postDisps[i][0] || 0) - (preDisps[i][0] || 0),
                (postDisps[i][1] || 0) - (preDisps[i][1] || 0),
                (postDisps[i][2] || 0) - (preDisps[i][2] || 0),
            ]);
        }

        const diffData = {
            ...this.data,
            displacements: diffDisps,
            info: { ...this.data.info, method: 'difference' },
        };
        this.loadResults(diffData);
    }

    /**
     * 임플란트 주변 필터 — 지정 중심/반경 내 입자만 표시
     * @param {THREE.Vector3} center - 필터 중심
     * @param {number} radius - 반경 (mm), 0이면 전체 표시
     */
    filterByRegion(center, radius) {
        if (!this._points || !this._geometry || radius <= 0) {
            // 반경 0이면 전체 표시
            if (this._points) this._points.visible = true;
            return;
        }

        const positions = this._geometry.attributes.position;
        const colors = this._geometry.attributes.color;
        if (!positions || !colors) return;

        const r2 = radius * radius;
        const cx = center.x, cy = center.y, cz = center.z;

        // 범위 밖 입자를 투명하게 (색상을 회색으로)
        for (let i = 0; i < positions.count; i++) {
            const px = positions.getX(i);
            const py = positions.getY(i);
            const pz = positions.getZ(i);
            const dx = px - cx, dy = py - cy, dz = pz - cz;
            const dist2 = dx * dx + dy * dy + dz * dz;

            if (dist2 > r2) {
                colors.setXYZ(i, 0.5, 0.5, 0.5);  // 회색
            }
        }

        colors.needsUpdate = true;
    }
}
