/**
 * Material Library 스토어 (Svelte 5 runes).
 *
 * ANSYS/Abaqus 스타일 재료 라이브러리:
 * - 카테고리별 분류 (Bone, Disc, Implant, Soft Tissue, Custom)
 * - 병리학적 변이 프리셋 (골다공증, 디스크 퇴행, 경화골 등)
 * - 속성 미세 조정 (E, nu, density)
 * - 커스텀 재료 localStorage 저장/복원
 */

// ── 타입 정의 ──

/** 재료 카테고리 */
export type MaterialCategory = 'bone' | 'disc' | 'implant' | 'soft_tissue' | 'custom';

/** 구성 모델 타입 */
export type ConstitutiveModel = 'linear_elastic' | 'neo_hookean' | 'mooney_rivlin' | 'ogden';

/** 구성 모델 메타정보 */
export const CONSTITUTIVE_MODELS: Record<ConstitutiveModel, {
  label: string;
  labelKo: string;
  description: string;
  params: string[];   // 이 모델에서 편집 가능한 파라미터
  femOnly: boolean;   // FEM 전용 여부
}> = {
  linear_elastic: {
    label: 'Linear Elastic', labelKo: '선형 탄성',
    description: '소변형 선형 탄성 — 모든 솔버 지원',
    params: ['E', 'nu', 'density'], femOnly: false,
  },
  neo_hookean: {
    label: 'Neo-Hookean', labelKo: 'Neo-Hookean',
    description: '대변형 압축성 초탄성 — FEM 전용',
    params: ['E', 'nu', 'density'], femOnly: true,
  },
  mooney_rivlin: {
    label: 'Mooney-Rivlin', labelKo: 'Mooney-Rivlin',
    description: '2-파라미터 초탄성 — 연조직/디스크에 적합, FEM 전용',
    params: ['C10', 'C01', 'D1', 'density'], femOnly: true,
  },
  ogden: {
    label: 'Ogden', labelKo: 'Ogden',
    description: 'N-항 초탄성 — 생체 조직 대변형, FEM 전용',
    params: ['mu_ogden', 'alpha_ogden', 'D1', 'density'], femOnly: true,
  },
};

/** 재료 항목 */
export interface MaterialEntry {
  key: string;                // 고유 식별자
  category: MaterialCategory;
  label: string;              // 영문 라벨
  labelKo: string;            // 한글 라벨
  E: number;                  // Young's modulus [Pa]
  nu: number;                 // Poisson's ratio
  density: number;            // [kg/m³]
  description: string;        // 한글 설명
  isCustom: boolean;
  isPathological: boolean;    // 병리학적 변이 여부
  // 구성 모델 (기본값: linear_elastic)
  constitutiveModel: ConstitutiveModel;
  // 초탄성 파라미터 (선택적)
  C10?: number;               // Mooney-Rivlin 제1상수 [Pa]
  C01?: number;               // Mooney-Rivlin 제2상수 [Pa]
  D1?: number;                // 비압축성 파라미터 [1/Pa]
  mu_ogden?: number;          // Ogden 전단 계수 [Pa]
  alpha_ogden?: number;       // Ogden 지수
}

/** 카테고리 라벨 (한글) */
export const CATEGORY_LABELS_KO: Record<MaterialCategory | 'all', string> = {
  all: '전체',
  bone: '뼈',
  disc: '디스크',
  implant: '임플란트',
  soft_tissue: '연조직',
  custom: '커스텀',
};

// ── 빌트인 재료 데이터베이스 (17종) ──

const BUILTIN_MATERIALS: MaterialEntry[] = [
  // ━━━ 뼈 (Bone) ━━━
  {
    key: 'cortical_bone', category: 'bone',
    label: 'Cortical Bone', labelKo: '피질골',
    E: 15e9, nu: 0.3, density: 1850,
    description: '건강한 피질골 (Cortical bone)',
    isCustom: false, isPathological: false, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'cancellous_bone', category: 'bone',
    label: 'Cancellous Bone', labelKo: '해면골',
    E: 1e9, nu: 0.3, density: 1100,
    description: '건강한 해면골 (Cancellous/Trabecular bone)',
    isCustom: false, isPathological: false, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'osteoporotic_cortical', category: 'bone',
    label: 'Osteoporotic Cortical', labelKo: '골다공증 피질골',
    E: 8e9, nu: 0.3, density: 1400,
    description: '골다공증 피질골 (T-score ≤ -2.5)',
    isCustom: false, isPathological: true, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'osteoporotic_cancellous', category: 'bone',
    label: 'Osteoporotic Cancellous', labelKo: '골다공증 해면골',
    E: 0.3e9, nu: 0.3, density: 600,
    description: '골다공증 해면골 — 골밀도 현저 감소',
    isCustom: false, isPathological: true, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'sclerotic_bone', category: 'bone',
    label: 'Sclerotic Bone', labelKo: '경화골',
    E: 20e9, nu: 0.3, density: 2000,
    description: '경화골 (Sclerotic bone) — 골밀도 비정상 증가',
    isCustom: false, isPathological: true, constitutiveModel: 'linear_elastic',
  },

  // ━━━ 디스크 (Disc) ━━━
  {
    key: 'disc_normal', category: 'disc',
    label: 'Normal Disc', labelKo: '정상 디스크',
    E: 10e6, nu: 0.45, density: 1200,
    description: '건강한 추간판 (Intervertebral disc)',
    isCustom: false, isPathological: false, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'disc_grade3', category: 'disc',
    label: 'Degenerated Disc III', labelKo: '퇴행 디스크 III',
    E: 20e6, nu: 0.4, density: 1150,
    description: '퇴행성 디스크 Pfirrmann Grade III — 수핵 불균질화',
    isCustom: false, isPathological: true, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'disc_grade4', category: 'disc',
    label: 'Degenerated Disc IV', labelKo: '퇴행 디스크 IV',
    E: 40e6, nu: 0.35, density: 1100,
    description: '퇴행성 디스크 Pfirrmann Grade IV — 높이 감소, 수핵 소실',
    isCustom: false, isPathological: true, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'disc_grade5', category: 'disc',
    label: 'Degenerated Disc V', labelKo: '퇴행 디스크 V',
    E: 80e6, nu: 0.3, density: 1050,
    description: '퇴행성 디스크 Pfirrmann Grade V — 완전 붕괴, 섬유화',
    isCustom: false, isPathological: true, constitutiveModel: 'linear_elastic',
  },

  // ━━━ 연조직 (Soft Tissue) ━━━
  {
    key: 'ligament', category: 'soft_tissue',
    label: 'Ligament', labelKo: '인대',
    E: 50e6, nu: 0.4, density: 1100,
    description: '척추 인대 (Spinal ligament)',
    isCustom: false, isPathological: false, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'calcified_ligament', category: 'soft_tissue',
    label: 'Calcified Ligament', labelKo: '석회화 인대',
    E: 200e6, nu: 0.35, density: 1300,
    description: '석회화 인대 — 비정상 경직, 황색인대 비후 등',
    isCustom: false, isPathological: true, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'soft_tissue', category: 'soft_tissue',
    label: 'Soft Tissue', labelKo: '연조직',
    E: 1e6, nu: 0.49, density: 1050,
    description: '일반 연조직 (근육, 지방 등)',
    isCustom: false, isPathological: false, constitutiveModel: 'linear_elastic',
  },

  // ━━━ 임플란트 (Implant) ━━━
  {
    key: 'titanium', category: 'implant',
    label: 'Ti-6Al-4V', labelKo: '티타늄 합금',
    E: 110e9, nu: 0.34, density: 4500,
    description: 'Ti-6Al-4V — 척추 나사/로드 표준 재질',
    isCustom: false, isPathological: false, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'peek', category: 'implant',
    label: 'PEEK', labelKo: 'PEEK',
    E: 4e9, nu: 0.38, density: 1320,
    description: 'Polyether-ether-ketone — 추간체 케이지 재질',
    isCustom: false, isPathological: false, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'cobalt_chrome', category: 'implant',
    label: 'CoCr Alloy', labelKo: '코발트-크롬',
    E: 230e9, nu: 0.30, density: 8300,
    description: 'CoCr 합금 — 고강도 임플란트',
    isCustom: false, isPathological: false, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'stainless_steel', category: 'implant',
    label: '316L SS', labelKo: '스테인리스강 316L',
    E: 200e9, nu: 0.30, density: 7900,
    description: '316L 스테인리스강 — 경제적 임플란트',
    isCustom: false, isPathological: false, constitutiveModel: 'linear_elastic',
  },
  {
    key: 'uhmwpe', category: 'implant',
    label: 'UHMWPE', labelKo: '초고분자 PE',
    E: 0.7e9, nu: 0.46, density: 930,
    description: '초고분자량 폴리에틸렌 — 베어링면 재질',
    isCustom: false, isPathological: false, constitutiveModel: 'linear_elastic',
  },
];

// ── localStorage 키 ──

const STORAGE_KEY = 'pysim-custom-materials';

// ── 스토어 클래스 ──

class MaterialLibraryState {
  /** 전체 재료 목록 (빌트인 + 커스텀) */
  entries = $state<MaterialEntry[]>([...BUILTIN_MATERIALS]);

  /** 활성 카테고리 필터 */
  activeCategory = $state<MaterialCategory | 'all'>('all');

  /** 검색 쿼리 */
  searchQuery = $state('');

  constructor() {
    this._loadCustomFromStorage();
  }

  /** 필터링된 목록 (카테고리 + 검색) */
  get filtered(): MaterialEntry[] {
    let list = this.entries;

    // 카테고리 필터
    if (this.activeCategory !== 'all') {
      list = list.filter(m => m.category === this.activeCategory);
    }

    // 검색 필터
    const q = this.searchQuery.trim().toLowerCase();
    if (q) {
      list = list.filter(m =>
        m.label.toLowerCase().includes(q) ||
        m.labelKo.includes(q) ||
        m.description.includes(q) ||
        m.key.includes(q)
      );
    }

    return list;
  }

  /** 카테고리별 재료 목록 */
  getByCategory(cat: MaterialCategory): MaterialEntry[] {
    return this.entries.filter(m => m.category === cat);
  }

  /** 키로 재료 조회 */
  getByKey(key: string): MaterialEntry | undefined {
    return this.entries.find(m => m.key === key);
  }

  /** 커스텀 재료 추가 → localStorage 저장 */
  addCustom(partial: {
    label: string;
    labelKo: string;
    E: number;
    nu: number;
    density: number;
    description?: string;
    constitutiveModel?: ConstitutiveModel;
    C10?: number;
    C01?: number;
    D1?: number;
    mu_ogden?: number;
    alpha_ogden?: number;
  }): string {
    const key = `custom_${Date.now()}`;
    const entry: MaterialEntry = {
      key,
      category: 'custom',
      label: partial.label,
      labelKo: partial.labelKo,
      E: partial.E,
      nu: partial.nu,
      density: partial.density,
      description: partial.description ?? `사용자 정의 재료: ${partial.labelKo}`,
      isCustom: true,
      isPathological: false,
      constitutiveModel: partial.constitutiveModel ?? 'linear_elastic',
      C10: partial.C10,
      C01: partial.C01,
      D1: partial.D1,
      mu_ogden: partial.mu_ogden,
      alpha_ogden: partial.alpha_ogden,
    };
    this.entries = [...this.entries, entry];
    this._saveCustomToStorage();
    return key;
  }

  /** 커스텀 재료 삭제 */
  removeCustom(key: string): void {
    this.entries = this.entries.filter(m => m.key !== key || !m.isCustom);
    this._saveCustomToStorage();
  }

  /** localStorage에 커스텀 재료 저장 */
  private _saveCustomToStorage(): void {
    try {
      const customs = this.entries.filter(m => m.isCustom);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(customs));
    } catch {
      // localStorage 접근 실패 무시 (SSR 등)
    }
  }

  /** localStorage에서 커스텀 재료 복원 */
  private _loadCustomFromStorage(): void {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const customs: MaterialEntry[] = JSON.parse(raw);
      if (Array.isArray(customs) && customs.length > 0) {
        // 빌트인과 합침 (중복 키 제거)
        const existingKeys = new Set(this.entries.map(m => m.key));
        const newCustoms = customs
          .filter(c => !existingKeys.has(c.key))
          .map(c => ({ ...c, isCustom: true, category: 'custom' as MaterialCategory }));
        this.entries = [...this.entries, ...newCustoms];
      }
    } catch {
      // 파싱 실패 무시
    }
  }
}

export const materialLibrary = new MaterialLibraryState();

// ── 유틸리티 함수 ──

/**
 * E 값을 사람이 읽기 쉬운 문자열로 변환.
 * 예: 15e9 → "15 GPa", 10e6 → "10 MPa"
 */
export function formatE(E: number): string {
  if (E >= 1e9) {
    const val = E / 1e9;
    return `${val >= 10 ? val.toFixed(0) : val.toFixed(1)} GPa`;
  }
  const val = E / 1e6;
  return `${val >= 10 ? val.toFixed(0) : val.toFixed(1)} MPa`;
}

/**
 * 대수 슬라이더 위치(0~1000) → E 값(Pa) 변환.
 * 범위: 10⁵ Pa (0.1 MPa) ~ 10¹¹·⁴ Pa (~250 GPa)
 */
export function sliderToE(pos: number): number {
  const logMin = 5;    // log10(100,000) = 10⁵ Pa
  const logMax = 11.4; // log10(~250 GPa)
  return Math.pow(10, logMin + (pos / 1000) * (logMax - logMin));
}

/**
 * E 값(Pa) → 대수 슬라이더 위치(0~1000) 변환.
 */
export function eToSlider(E: number): number {
  const logMin = 5;
  const logMax = 11.4;
  const logE = Math.log10(Math.max(E, 1e5));
  return Math.round(((logE - logMin) / (logMax - logMin)) * 1000);
}

// ── 초탄성 파라미터 변환 유틸리티 ──

/**
 * E/ν → Mooney-Rivlin (C10, C01, D1) 변환.
 * beta: C10/C01 비율 (0~1, 기본 0.5 = 균등 분배)
 */
export function enuToMooneyRivlin(E: number, nu: number, beta = 0.5): { C10: number; C01: number; D1: number } {
  const mu = E / (2 * (1 + nu));
  const K = E / (3 * (1 - 2 * nu));
  return {
    C10: (mu / 2) * beta,
    C01: (mu / 2) * (1 - beta),
    D1: K > 0 ? 2 / K : 0,
  };
}

/**
 * E/ν → Ogden (mu, alpha, D1) 변환.
 * alpha 기본값 2.0 → Neo-Hookean 동치
 */
export function enuToOgden(E: number, nu: number, alpha = 2.0): { mu_ogden: number; alpha_ogden: number; D1: number } {
  const mu = E / (2 * (1 + nu));
  const K = E / (3 * (1 - 2 * nu));
  return {
    mu_ogden: mu,
    alpha_ogden: alpha,
    D1: K > 0 ? 2 / K : 0,
  };
}

/** 구성 모델 짧은 라벨 (Solve 패널 요약용) */
export function constitutiveModelShort(model: ConstitutiveModel): string {
  switch (model) {
    case 'linear_elastic': return 'Linear';
    case 'neo_hookean': return 'NeoHook';
    case 'mooney_rivlin': return 'M-R';
    case 'ogden': return 'Ogden';
    default: return 'Linear';
  }
}
