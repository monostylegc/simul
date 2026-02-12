/**
 * Jet 컬러맵 유틸리티 — 해석 결과 시각화용
 */

/**
 * Jet 컬러맵: t ∈ [0,1] → {r, g, b} (각 0~1)
 *
 *  t=0.00 파랑(0,0,1) → t=0.25 청록(0,1,1) → t=0.50 초록(0,1,0)
 *  → t=0.75 노랑(1,1,0) → t=1.00 빨강(1,0,0)
 */
function jetColormap(t) {
    t = Math.max(0, Math.min(1, t));
    let r, g, b;

    if (t < 0.25) {
        r = 0;
        g = t * 4;
        b = 1;
    } else if (t < 0.5) {
        r = 0;
        g = 1;
        b = 1 - (t - 0.25) * 4;
    } else if (t < 0.75) {
        r = (t - 0.5) * 4;
        g = 1;
        b = 0;
    } else {
        r = 1;
        g = 1 - (t - 0.75) * 4;
        b = 0;
    }

    return { r, g, b };
}

/**
 * 컬러바 DOM 요소 생성
 * @param {string} containerId - 컬러바를 넣을 컨테이너 ID
 * @param {number} minVal - 최소값
 * @param {number} maxVal - 최대값
 * @param {string} label - 라벨 (예: "Displacement [mm]")
 */
function createColorbar(containerId, minVal, maxVal, label) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = '';

    // 그라디언트 바
    const bar = document.createElement('div');
    bar.style.cssText = `
        width: 100%; height: 16px; border-radius: 3px;
        background: linear-gradient(to right,
            rgb(0,0,255), rgb(0,255,255), rgb(0,255,0),
            rgb(255,255,0), rgb(255,0,0));
    `;
    container.appendChild(bar);

    // 범위 라벨
    const labels = document.createElement('div');
    labels.style.cssText = 'display: flex; justify-content: space-between; font-size: 10px; color: #aaa; margin-top: 2px;';
    labels.innerHTML = `<span>${minVal.toExponential(2)}</span><span>${maxVal.toExponential(2)}</span>`;
    container.appendChild(labels);

    // 단위 라벨
    if (label) {
        const title = document.createElement('div');
        title.style.cssText = 'font-size: 10px; color: #888; text-align: center; margin-top: 2px;';
        title.textContent = label;
        container.appendChild(title);
    }
}

/**
 * 스칼라 배열에서 컬러 배열 생성 (Float32Array, 3채널)
 * @param {number[]} values - 스칼라 값 배열
 * @param {number} [minVal] - 최소값 (자동 계산)
 * @param {number} [maxVal] - 최대값 (자동 계산)
 * @returns {{colors: Float32Array, min: number, max: number}}
 */
function valuesToColors(values, minVal, maxVal) {
    if (minVal === undefined) minVal = Math.min(...values);
    if (maxVal === undefined) maxVal = Math.max(...values);

    const range = maxVal - minVal || 1e-10;
    const colors = new Float32Array(values.length * 3);

    for (let i = 0; i < values.length; i++) {
        const t = (values[i] - minVal) / range;
        const c = jetColormap(t);
        colors[i * 3] = c.r;
        colors[i * 3 + 1] = c.g;
        colors[i * 3 + 2] = c.b;
    }

    return { colors, min: minVal, max: maxVal };
}
