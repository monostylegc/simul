"""자동 재료 매핑 서비스 — SpineLabel 기반 기본값 제안.

자동 매핑 결과는 '제안'일 뿐, 사용자가 UI에서 E/nu/density를 직접 수정 가능.
"""

import numpy as np
from typing import Callable, Optional

from ..models import AutoMaterialRequest


# 척추 재료 데이터베이스 — 사용자가 수동 조정 가능한 기본값
SPINE_MATERIAL_DB = {
    "bone": {
        "E": 15e9,
        "nu": 0.3,
        "density": 1850,
        "description": "피질골 (Cortical bone)",
    },
    "cancellous_bone": {
        "E": 1e9,
        "nu": 0.3,
        "density": 1100,
        "description": "해면골 (Cancellous bone)",
    },
    "disc": {
        "E": 10e6,
        "nu": 0.45,
        "density": 1200,
        "description": "추간판 (Intervertebral disc)",
    },
    "soft_tissue": {
        "E": 1e6,
        "nu": 0.49,
        "density": 1050,
        "description": "연조직 (Soft tissue)",
    },
    "titanium": {
        "E": 110e9,
        "nu": 0.34,
        "density": 4500,
        "description": "티타늄 합금 (Ti-6Al-4V)",
    },
    "peek": {
        "E": 4e9,
        "nu": 0.38,
        "density": 1320,
        "description": "PEEK (Polyether ether ketone)",
    },
    "cobalt_chrome": {
        "E": 230e9,
        "nu": 0.30,
        "density": 8300,
        "description": "코발트-크롬 합금 (CoCr)",
    },
    "stainless_steel": {
        "E": 200e9,
        "nu": 0.30,
        "density": 7900,
        "description": "스테인리스 스틸 (316L)",
    },
    # ── 병리학적 변이 재료 ──
    "cortical_bone": {
        "E": 15e9,
        "nu": 0.3,
        "density": 1850,
        "description": "피질골 (Cortical bone)",
    },
    "osteoporotic_cortical": {
        "E": 8e9,
        "nu": 0.3,
        "density": 1400,
        "description": "골다공증 피질골 (Osteoporotic cortical, T-score ≤ -2.5)",
    },
    "osteoporotic_cancellous": {
        "E": 300e6,
        "nu": 0.3,
        "density": 600,
        "description": "골다공증 해면골 (Osteoporotic cancellous, T-score ≤ -2.5)",
    },
    "sclerotic_bone": {
        "E": 20e9,
        "nu": 0.3,
        "density": 2000,
        "description": "경화골 (Sclerotic bone)",
    },
    "disc_normal": {
        "E": 10e6,
        "nu": 0.45,
        "density": 1200,
        "description": "정상 추간판 (Normal disc)",
    },
    "disc_grade3": {
        "E": 20e6,
        "nu": 0.4,
        "density": 1150,
        "description": "퇴행 디스크 III (Pfirrmann Grade III)",
    },
    "disc_grade4": {
        "E": 40e6,
        "nu": 0.35,
        "density": 1100,
        "description": "퇴행 디스크 IV (Pfirrmann Grade IV)",
    },
    "disc_grade5": {
        "E": 80e6,
        "nu": 0.3,
        "density": 1050,
        "description": "퇴행 디스크 V (Pfirrmann Grade V)",
    },
    "ligament": {
        "E": 50e6,
        "nu": 0.4,
        "density": 1100,
        "description": "인대 (Ligament)",
    },
    "calcified_ligament": {
        "E": 200e6,
        "nu": 0.35,
        "density": 1300,
        "description": "석회화 인대 (Calcified ligament)",
    },
    "uhmwpe": {
        "E": 700e6,
        "nu": 0.46,
        "density": 930,
        "description": "초고분자량 폴리에틸렌 (UHMWPE)",
    },
}

# SpineLabel material_type → 기본 재료 매핑
_LABEL_TYPE_TO_MATERIAL = {
    "bone": "bone",
    "disc": "disc",
    "soft_tissue": "soft_tissue",
}


def auto_assign_materials(
    request: AutoMaterialRequest,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """SpineLabel 값 목록에서 자동 재료 매핑 생성.

    결과는 '제안'이며, 사용자가 UI에서 값을 수정할 수 있음.

    Args:
        request: 자동 재료 요청 (label_values, implant_materials)
        progress_callback: 진행률 콜백

    Returns:
        {materials: [{name, E, nu, density, description, node_indices}],
         material_db: {...}}
    """
    if progress_callback:
        progress_callback("material", {"message": "재료 자동 매핑 중..."})

    from backend.segmentation.labels import SpineLabel

    label_values = np.array(request.label_values, dtype=np.int32)

    # 라벨별 재료 그룹화
    groups = {}  # material_name → [node_indices]
    for i, lbl in enumerate(label_values):
        lbl_int = int(lbl)
        if lbl_int == 0:
            continue  # 배경 스킵

        mat_type = SpineLabel.to_material_type(lbl_int)
        type_name = {0: "empty", 1: "bone", 2: "disc", 3: "soft_tissue"}.get(mat_type, "empty")
        if type_name == "empty":
            continue

        mat_name = _LABEL_TYPE_TO_MATERIAL.get(type_name, type_name)
        if mat_name not in groups:
            groups[mat_name] = []
        groups[mat_name].append(i)

    # 재료 목록 생성
    materials = []
    for mat_name, indices in groups.items():
        if mat_name not in SPINE_MATERIAL_DB:
            continue
        db = SPINE_MATERIAL_DB[mat_name]
        materials.append({
            "name": mat_name,
            "E": db["E"],
            "nu": db["nu"],
            "density": db["density"],
            "description": db["description"],
            "node_indices": indices,
            "n_nodes": len(indices),
        })

    # 임플란트 재료 추가
    for impl_name, impl_mat in request.implant_materials.items():
        if impl_mat in SPINE_MATERIAL_DB:
            db = SPINE_MATERIAL_DB[impl_mat]
            materials.append({
                "name": f"{impl_name}_{impl_mat}",
                "E": db["E"],
                "nu": db["nu"],
                "density": db["density"],
                "description": f"{impl_name} — {db['description']}",
                "node_indices": [],  # 임플란트 인덱스는 별도 관리
                "n_nodes": 0,
            })

    if progress_callback:
        progress_callback("done", {"message": f"재료 매핑 완료: {len(materials)}종"})

    return {
        "materials": materials,
        "material_db": {
            k: {
                "E": v["E"],
                "nu": v["nu"],
                "density": v["density"],
                "description": v["description"],
            }
            for k, v in SPINE_MATERIAL_DB.items()
        },
    }
