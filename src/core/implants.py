"""척추 수술용 임플란트 모델."""

import numpy as np
from typing import Tuple, Optional
from dataclasses import dataclass

from .mesh import TriangleMesh


@dataclass
class ScrewSpec:
    """Pedicle Screw 규격.

    실제 수술에서 사용되는 나사 규격 기반.
    """
    diameter: float = 6.0      # 직경 (mm), 일반적으로 4.5~7.5mm
    length: float = 45.0       # 길이 (mm), 일반적으로 30~55mm
    head_diameter: float = 10.0  # 헤드 직경 (mm)
    head_height: float = 5.0   # 헤드 높이 (mm)
    thread_pitch: float = 2.5  # 나사산 피치 (mm)
    thread_depth: float = 0.5  # 나사산 깊이 (mm)


@dataclass
class CageSpec:
    """Interbody Cage 규격.

    추간판 대체용 케이지 규격.
    """
    width: float = 26.0        # 폭 (mm), 일반적으로 22~32mm
    depth: float = 10.0        # 깊이 (mm), 일반적으로 8~14mm
    height: float = 12.0       # 높이 (mm), 일반적으로 8~16mm
    angle: float = 6.0         # 전만각 (도), 일반적으로 0~12도
    porous: bool = False       # 다공성 여부


def create_pedicle_screw(
    spec: Optional[ScrewSpec] = None,
    segments: int = 16,
    thread_segments: int = 4
) -> TriangleMesh:
    """Pedicle Screw 메쉬 생성.

    척추경 나사 (Pedicle Screw) 3D 모델을 생성합니다.
    실제 수술에서 사용되는 나사 형태를 단순화하여 표현합니다.

    Args:
        spec: 나사 규격 (None이면 기본값 사용)
        segments: 원형 단면 세그먼트 수
        thread_segments: 나사산 세그먼트 수 (per pitch)

    Returns:
        생성된 메쉬
    """
    if spec is None:
        spec = ScrewSpec()

    vertices = []
    faces = []

    # === 헤드 (다각형 실린더 - tulip head 형태) ===
    head_r = spec.head_diameter / 2
    head_h = spec.head_height

    # 헤드 상단 정점
    for i in range(segments):
        angle = 2 * np.pi * i / segments
        x = head_r * np.cos(angle)
        z = head_r * np.sin(angle)
        vertices.append([x, head_h, z])

    # 헤드 하단 정점
    for i in range(segments):
        angle = 2 * np.pi * i / segments
        x = head_r * 0.8 * np.cos(angle)  # 살짝 좁아짐
        z = head_r * 0.8 * np.sin(angle)
        vertices.append([x, 0, z])

    # 헤드 상단 면 (중심에서 방사형)
    head_top_center = len(vertices)
    vertices.append([0, head_h, 0])
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.append([head_top_center, i, next_i])

    # 헤드 측면
    for i in range(segments):
        i0 = i
        i1 = (i + 1) % segments
        i2 = i + segments
        i3 = (i + 1) % segments + segments
        faces.append([i0, i2, i1])
        faces.append([i1, i2, i3])

    # === 샤프트 (원기둥 + 나사산) ===
    shaft_r = spec.diameter / 2
    shaft_length = spec.length - head_h

    # 나사산 포함 샤프트
    n_threads = int(shaft_length / spec.thread_pitch)
    thread_r = shaft_r + spec.thread_depth

    shaft_start = len(vertices)

    # 각 피치마다 나사산 정점 추가
    for t in range(n_threads + 1):
        y = -t * spec.thread_pitch

        for i in range(segments):
            angle = 2 * np.pi * i / segments
            # 나사산 프로파일 (삼각파)
            thread_offset = (t + i / segments) % 1
            if thread_offset < 0.5:
                r = shaft_r + spec.thread_depth * (thread_offset * 2)
            else:
                r = shaft_r + spec.thread_depth * (2 - thread_offset * 2)

            x = r * np.cos(angle)
            z = r * np.sin(angle)
            vertices.append([x, y, z])

    # 샤프트 면
    for t in range(n_threads):
        for i in range(segments):
            i0 = shaft_start + t * segments + i
            i1 = shaft_start + t * segments + (i + 1) % segments
            i2 = shaft_start + (t + 1) * segments + i
            i3 = shaft_start + (t + 1) * segments + (i + 1) % segments
            faces.append([i0, i2, i1])
            faces.append([i1, i2, i3])

    # 헤드-샤프트 연결
    for i in range(segments):
        i0 = i + segments  # 헤드 하단
        i1 = (i + 1) % segments + segments
        i2 = shaft_start + i  # 샤프트 상단
        i3 = shaft_start + (i + 1) % segments
        faces.append([i0, i2, i1])
        faces.append([i1, i2, i3])

    # === 팁 (뾰족한 끝) ===
    tip_start = len(vertices)
    tip_y = -n_threads * spec.thread_pitch

    # 팁 측면 정점
    for i in range(segments):
        angle = 2 * np.pi * i / segments
        x = shaft_r * 0.3 * np.cos(angle)
        z = shaft_r * 0.3 * np.sin(angle)
        vertices.append([x, tip_y - spec.thread_pitch, z])

    # 팁 중심
    tip_center = len(vertices)
    vertices.append([0, tip_y - spec.thread_pitch * 1.5, 0])

    # 팁 면
    shaft_end = shaft_start + n_threads * segments
    for i in range(segments):
        i0 = shaft_end + i
        i1 = shaft_end + (i + 1) % segments
        i2 = tip_start + i
        i3 = tip_start + (i + 1) % segments
        faces.append([i0, i2, i1])
        faces.append([i1, i2, i3])

    # 팁 끝
    for i in range(segments):
        i0 = tip_start + i
        i1 = tip_start + (i + 1) % segments
        faces.append([tip_center, i1, i0])

    mesh = TriangleMesh(
        vertices=np.array(vertices, dtype=np.float32),
        faces=np.array(faces, dtype=np.int32),
        name="PedicleScrew"
    )

    return mesh


def create_interbody_cage(
    spec: Optional[CageSpec] = None,
    segments: int = 8
) -> TriangleMesh:
    """Interbody Cage 메쉬 생성.

    추간판 대체용 케이지 3D 모델을 생성합니다.
    PLIF/TLIF 수술에서 사용되는 형태를 표현합니다.

    Args:
        spec: 케이지 규격 (None이면 기본값 사용)
        segments: 모서리 둥글기 세그먼트 수

    Returns:
        생성된 메쉬
    """
    if spec is None:
        spec = CageSpec()

    # 전만각 적용
    angle_rad = np.radians(spec.angle)
    front_h = spec.height
    back_h = spec.height + spec.depth * np.tan(angle_rad)

    w, d, h = spec.width / 2, spec.depth / 2, spec.height

    # 케이지 정점 (박스 + 전만각)
    vertices = np.array([
        # 하단 (y=0)
        [-w, 0, -d],
        [w, 0, -d],
        [w, 0, d],
        [-w, 0, d],
        # 상단 (전만각 적용)
        [-w, front_h, -d],
        [w, front_h, -d],
        [w, back_h, d],
        [-w, back_h, d],
    ], dtype=np.float32)

    # 면 (박스)
    faces = np.array([
        # 하단
        [0, 2, 1],
        [0, 3, 2],
        # 상단
        [4, 5, 6],
        [4, 6, 7],
        # 전면
        [0, 1, 5],
        [0, 5, 4],
        # 후면
        [2, 3, 7],
        [2, 7, 6],
        # 좌측
        [0, 4, 7],
        [0, 7, 3],
        # 우측
        [1, 2, 6],
        [1, 6, 5],
    ], dtype=np.int32)

    mesh = TriangleMesh(
        vertices=vertices,
        faces=faces,
        name="InterbodyCage"
    )

    return mesh


def create_rod(
    length: float = 100.0,
    diameter: float = 5.5,
    segments: int = 16
) -> TriangleMesh:
    """연결 로드 메쉬 생성.

    Pedicle Screw들을 연결하는 로드를 생성합니다.

    Args:
        length: 로드 길이 (mm)
        diameter: 로드 직경 (mm), 일반적으로 5.5mm
        segments: 원형 단면 세그먼트 수

    Returns:
        생성된 메쉬
    """
    return TriangleMesh.create_cylinder(
        radius=diameter / 2,
        height=length,
        segments=segments
    )


# === 팩토리 함수들 ===

def create_standard_screw(size: str = "M6x45") -> TriangleMesh:
    """표준 규격 나사 생성.

    Args:
        size: 규격 문자열 (예: "M5x40", "M6x45", "M7x50")

    Returns:
        생성된 메쉬
    """
    # 규격 파싱
    parts = size.upper().replace("M", "").split("X")
    diameter = float(parts[0])
    length = float(parts[1]) if len(parts) > 1 else 45.0

    spec = ScrewSpec(
        diameter=diameter,
        length=length,
        head_diameter=diameter + 4,
        head_height=diameter * 0.8
    )

    return create_pedicle_screw(spec)


def create_standard_cage(size: str = "L") -> TriangleMesh:
    """표준 규격 케이지 생성.

    Args:
        size: 규격 ("S", "M", "L", "XL")

    Returns:
        생성된 메쉬
    """
    sizes = {
        "S": CageSpec(width=22, depth=8, height=8),
        "M": CageSpec(width=26, depth=10, height=10),
        "L": CageSpec(width=26, depth=10, height=12),
        "XL": CageSpec(width=32, depth=12, height=14),
    }

    spec = sizes.get(size.upper(), sizes["M"])
    return create_interbody_cage(spec)
