"""임플란트 3D 메쉬 생성 서비스.

guideline.py / implants.py (core 계층) → JSON 직렬화 가능 딕셔너리로 변환.
"""

from ..models.surgical import ImplantMeshRequest


def generate_implant_mesh(request: ImplantMeshRequest, progress_callback=None) -> dict:
    """임플란트 규격 → 3D 메쉬 생성 → JSON 직렬화 딕셔너리 반환.

    반환 형식::

        {
            "name": "PedicleScrew",
            "implant_type": "screw",
            "vertices": [[x, y, z], ...],   # float list
            "faces": [[i, j, k], ...],       # int list
            "color": [r, g, b],              # 0~1 범위 RGB
        }
    """
    from src.core.implants import (
        ScrewSpec, CageSpec,
        create_pedicle_screw, create_interbody_cage, create_rod,
        create_standard_screw, create_standard_cage,
    )

    implant_type = request.implant_type

    if implant_type == "screw":
        if request.size:
            # 표준 규격 문자열 사용 (예: "M6x45")
            mesh = create_standard_screw(request.size)
        else:
            spec = None
            if request.screw_spec:
                spec = ScrewSpec(**request.screw_spec.model_dump())
            mesh = create_pedicle_screw(spec)
        color = [0.80, 0.80, 0.85]  # 티타늄 실버

    elif implant_type == "cage":
        if request.size:
            # 표준 규격 문자열 사용 (예: "L")
            mesh = create_standard_cage(request.size)
        else:
            spec = None
            if request.cage_spec:
                spec = CageSpec(**request.cage_spec.model_dump())
            mesh = create_interbody_cage(spec)
        color = [0.85, 0.85, 0.70]  # PEEK 크림색

    elif implant_type == "rod":
        mesh = create_rod(
            length=request.rod_length,
            diameter=request.rod_diameter,
        )
        color = [0.75, 0.75, 0.80]  # 티타늄 로드

    else:
        raise ValueError(f"알 수 없는 임플란트 타입: {implant_type}")

    return {
        "name": mesh.name,
        "implant_type": implant_type,
        "vertices": mesh.vertices.tolist(),
        "faces": mesh.faces.tolist(),
        "color": color,
    }
