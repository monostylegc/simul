/**
 * 컬러맵 유틸리티 — ParaView 스타일 다중 컬러맵 지원.
 *
 * 지원 컬러맵:
 *   jet         — 클래식 과학 시각화 (파랑→청록→초록→노랑→빨강)
 *   coolToWarm  — ParaView 기본 발산 컬러맵 (파랑→흰→빨강)
 *   viridis     — 색맹 친화, 균일 밝기
 *   grayscale   — 흑백 (논문용)
 *   rainbow     — HSV 무지개
 *   turbo       — 개선된 Jet (Google)
 */

export interface RGB {
  r: number;
  g: number;
  b: number;
}

/** 컬러맵 이름 타입 */
export type ColormapName = 'jet' | 'coolToWarm' | 'viridis' | 'grayscale' | 'rainbow' | 'turbo';

/** 컬러맵 정보 */
export interface ColormapInfo {
  name: ColormapName;
  label: string;
  fn: (t: number) => RGB;
}

// ── 컬러맵 함수 ──

/**
 * Jet 컬러맵: t ∈ [0,1] → {r, g, b}
 */
export function jetColormap(t: number): RGB {
  t = Math.max(0, Math.min(1, t));
  let r: number, g: number, b: number;

  if (t < 0.25) {
    r = 0; g = t * 4; b = 1;
  } else if (t < 0.5) {
    r = 0; g = 1; b = 1 - (t - 0.25) * 4;
  } else if (t < 0.75) {
    r = (t - 0.5) * 4; g = 1; b = 0;
  } else {
    r = 1; g = 1 - (t - 0.75) * 4; b = 0;
  }

  return { r, g, b };
}

/**
 * Cool-to-Warm (파랑→흰→빨강, ParaView 기본 발산 맵)
 */
export function coolToWarmColormap(t: number): RGB {
  t = Math.max(0, Math.min(1, t));

  if (t < 0.5) {
    const s = t * 2; // 0→1
    return {
      r: 0.23 + s * 0.77,
      g: 0.30 + s * 0.70,
      b: 0.75 + s * 0.25,
    };
  } else {
    const s = (t - 0.5) * 2; // 0→1
    return {
      r: 1.0,
      g: 1.0 - s * 0.73,
      b: 1.0 - s * 0.77,
    };
  }
}

/**
 * Viridis — 색맹 친화, 균일 밝기 (간소화 5포인트 보간)
 */
export function viridisColormap(t: number): RGB {
  t = Math.max(0, Math.min(1, t));

  // 5개 키포인트 보간 (실제 viridis 근사)
  const keys: [number, number, number][] = [
    [0.267, 0.004, 0.329],  // t=0.0 진한 보라
    [0.282, 0.141, 0.458],  // t=0.25 보라
    [0.127, 0.566, 0.550],  // t=0.50 청록
    [0.544, 0.773, 0.247],  // t=0.75 연두
    [0.993, 0.906, 0.144],  // t=1.0 노랑
  ];

  const idx = t * 4;
  const i = Math.min(3, Math.floor(idx));
  const f = idx - i;

  return {
    r: keys[i][0] + f * (keys[i + 1][0] - keys[i][0]),
    g: keys[i][1] + f * (keys[i + 1][1] - keys[i][1]),
    b: keys[i][2] + f * (keys[i + 1][2] - keys[i][2]),
  };
}

/**
 * Grayscale — 흑백 (논문/인쇄용)
 */
export function grayscaleColormap(t: number): RGB {
  t = Math.max(0, Math.min(1, t));
  return { r: t, g: t, b: t };
}

/**
 * Rainbow — HSV 기반 무지개
 */
export function rainbowColormap(t: number): RGB {
  t = Math.max(0, Math.min(1, t));
  const h = (1 - t) * 240 / 360; // 파랑(240°)→빨강(0°)
  const s = 1, v = 1;

  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const u = v * (1 - (1 - f) * s);

  switch (i % 6) {
    case 0: return { r: v, g: u, b: p };
    case 1: return { r: q, g: v, b: p };
    case 2: return { r: p, g: v, b: u };
    case 3: return { r: p, g: q, b: v };
    case 4: return { r: u, g: p, b: v };
    case 5: return { r: v, g: p, b: q };
    default: return { r: 0, g: 0, b: 0 };
  }
}

/**
 * Turbo — 개선된 Jet (Google, 더 균일한 밝기)
 */
export function turboColormap(t: number): RGB {
  t = Math.max(0, Math.min(1, t));

  // 7포인트 보간 (실제 turbo 근사)
  const keys: [number, number, number][] = [
    [0.19, 0.07, 0.23],  // t=0.00
    [0.11, 0.34, 0.80],  // t=0.17
    [0.08, 0.67, 0.74],  // t=0.33
    [0.29, 0.87, 0.38],  // t=0.50
    [0.74, 0.90, 0.13],  // t=0.67
    [0.98, 0.60, 0.07],  // t=0.83
    [0.84, 0.15, 0.11],  // t=1.00
  ];

  const idx = t * 6;
  const i = Math.min(5, Math.floor(idx));
  const f = idx - i;

  return {
    r: keys[i][0] + f * (keys[i + 1][0] - keys[i][0]),
    g: keys[i][1] + f * (keys[i + 1][1] - keys[i][1]),
    b: keys[i][2] + f * (keys[i + 1][2] - keys[i][2]),
  };
}

// ── 컬러맵 레지스트리 ──

export const COLORMAPS: Record<ColormapName, ColormapInfo> = {
  jet:        { name: 'jet',        label: 'Jet',           fn: jetColormap },
  coolToWarm: { name: 'coolToWarm', label: 'Cool to Warm',  fn: coolToWarmColormap },
  viridis:    { name: 'viridis',    label: 'Viridis',       fn: viridisColormap },
  grayscale:  { name: 'grayscale',  label: 'Grayscale',     fn: grayscaleColormap },
  rainbow:    { name: 'rainbow',    label: 'Rainbow',       fn: rainbowColormap },
  turbo:      { name: 'turbo',      label: 'Turbo',         fn: turboColormap },
};

/** 컬러맵 이름 목록 */
export const COLORMAP_NAMES: ColormapName[] = Object.keys(COLORMAPS) as ColormapName[];

// ── 유틸 함수 ──

/**
 * 스칼라 배열에서 컬러 배열 생성 (Float32Array, 3채널).
 */
export function valuesToColors(
  values: number[],
  minVal?: number,
  maxVal?: number,
  colormapName: ColormapName = 'jet',
): { colors: Float32Array; min: number; max: number } {
  if (minVal === undefined) minVal = Math.min(...values);
  if (maxVal === undefined) maxVal = Math.max(...values);

  const range = maxVal - minVal || 1e-10;
  const colors = new Float32Array(values.length * 3);
  const cmFn = COLORMAPS[colormapName]?.fn ?? jetColormap;

  for (let i = 0; i < values.length; i++) {
    const t = (values[i] - minVal) / range;
    const c = cmFn(Math.max(0, Math.min(1, t)));
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;
  }

  return { colors, min: minVal, max: maxVal };
}

/**
 * CSS 그라디언트 문자열 생성 (컬러바 프리뷰용)
 */
export function colormapToCSS(name: ColormapName, steps = 10): string {
  const fn = COLORMAPS[name]?.fn ?? jetColormap;
  const stops: string[] = [];

  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const c = fn(t);
    const r = Math.round(c.r * 255);
    const g = Math.round(c.g * 255);
    const b = Math.round(c.b * 255);
    stops.push(`rgb(${r},${g},${b})`);
  }

  return `linear-gradient(to right, ${stops.join(', ')})`;
}

/**
 * 컬러바 DOM 요소 생성. (Svelte 컴포넌트로 대체 예정이지만 하위호환 유지)
 */
export function createColorbar(
  containerId: string,
  minVal: number,
  maxVal: number,
  label?: string,
  colormapName: ColormapName = 'jet',
): void {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = '';

  // 그라디언트 바
  const bar = document.createElement('div');
  bar.style.cssText = `
    width: 100%; height: 16px; border-radius: 3px;
    background: ${colormapToCSS(colormapName, 20)};
  `;
  container.appendChild(bar);

  // 범위 라벨
  const labels = document.createElement('div');
  labels.style.cssText =
    'display: flex; justify-content: space-between; font-size: 10px; color: #aaa; margin-top: 2px;';
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
