"""수술 가이드라인 메쉬 생성 서비스.

guideline.py (core 계층) → JSON 직렬화 가능 딕셔너리 목록으로 변환.
"""

import numpy as np
from ..models.surgical import GuidelineRequest


def generate_guideline_meshes(request: GuidelineRequest, progress_callback=None) -> dict:
    """Pedicle Screw 가이드라인 시각화 메쉬 생성 → JSON 직렬화 딕셔너리 반환.

    GuidelineManager를 사용하여 양측(좌/우) 가이드라인을 생성한다.

    반환 형식::

        {
            "vertebra_name": "L4",
            "meshes": [
                {
                    "name": "trajectory",
                    "vertices": [[x, y, z], ...],
                    "faces": [[i, j, k], ...],
                    "color": [r, g, b],
                },
                ...
            ]
        }
    """
    from src.core.guideline import GuidelineManager

    manager = GuidelineManager()

    # 척추 중심 위치 numpy 배열로 변환
    vertebra_pos = np.array(request.vertebra_position, dtype=np.float32)

    # 양측 표준 가이드라인 생성
    manager.create_standard_bilateral_guidelines(
        vertebra_position=vertebra_pos,
        vertebra_name=request.vertebra_name,
        pedicle_offset=request.pedicle_offset,
        medial_angle=request.medial_angle,
        caudal_angle=request.caudal_angle,
        depth=request.depth,
    )

    # show_* 플래그 사후 적용 (create_standard_bilateral_guidelines는 플래그 인자 없음)
    for gl in manager.guidelines:
        gl.show_trajectory = request.show_trajectory
        gl.show_safe_zone = request.show_safe_zone
        gl.show_depth_marker = request.show_depth_marker

    # 시각화 메쉬 목록 직렬화
    vis_meshes = manager.get_visualization_meshes()
    meshes_out = []
    for mesh, color in vis_meshes:
        if mesh.n_vertices == 0:
            continue
        meshes_out.append({
            "name": mesh.name,
            "vertices": mesh.vertices.tolist(),
            "faces": mesh.faces.tolist(),
            "color": list(color),
        })

    return {
        "vertebra_name": request.vertebra_name,
        "meshes": meshes_out,
    }
