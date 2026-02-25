"""
임플란트 더미 STL 파일 생성 스크립트

Python 표준 라이브러리(struct, math, os)만 사용.
스크류 → 원기둥, 케이지 → 직육면체, 로드 → 가느다란 원기둥 형태의 바이너리 STL을 생성한다.

실행:
    uv run python scripts/gen_implant_stls.py
"""

import math
import os
import struct

# ── 출력 디렉터리 ──

BASE_DIR = os.path.join(
    os.path.dirname(__file__),
    '..', 'src', 'frontend', 'public', 'stl', 'implants',
)


# ── 바이너리 STL 쓰기 ──

def write_stl_binary(filepath: str, triangles: list) -> None:
    """
    바이너리 STL 파일 쓰기.

    :param filepath:  출력 파일 경로
    :param triangles: [(normal, v0, v1, v2), ...] — 각 항목은 4개의 (x, y, z) 튜플
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'wb') as f:
        # 헤더 80 바이트 (내용 무관)
        f.write(b'IMPLANT_DUMMY_STL' + b'\x00' * 63)
        # 삼각형 개수
        f.write(struct.pack('<I', len(triangles)))
        for normal, v0, v1, v2 in triangles:
            f.write(struct.pack('<3f', *normal))
            f.write(struct.pack('<3f', *v0))
            f.write(struct.pack('<3f', *v1))
            f.write(struct.pack('<3f', *v2))
            f.write(struct.pack('<H', 0))  # 속성 바이트 (미사용)


# ── 원기둥 삼각형 생성 (스크류용) ──

def make_cylinder_triangles(radius: float, height: float, segments: int = 20) -> list:
    """
    원기둥 삼각형 목록 생성.

    - Y축 방향으로 세워진 원기둥 (y=0 ~ y=height)
    - 측면 + 상/하단 캡 포함
    """
    tris = []
    angles = [2 * math.pi * i / segments for i in range(segments)]

    for i in range(segments):
        a0 = angles[i]
        a1 = angles[(i + 1) % segments]
        x0, z0 = math.cos(a0) * radius, math.sin(a0) * radius
        x1, z1 = math.cos(a1) * radius, math.sin(a1) * radius

        # 측면 법선 (바깥 방향, y=0)
        mid_a = (a0 + a1) / 2
        nx, nz = math.cos(mid_a), math.sin(mid_a)

        # 측면 사각형 → 2삼각형
        tris.append(((nx, 0, nz), (x0, 0, z0),      (x1, 0, z1),      (x0, height, z0)))
        tris.append(((nx, 0, nz), (x1, 0, z1),      (x1, height, z1), (x0, height, z0)))

        # 하단 캡 (-Y 법선)
        tris.append(((0, -1, 0), (0, 0, 0), (x1, 0, z1), (x0, 0, z0)))
        # 상단 캡 (+Y 법선)
        tris.append(((0, 1, 0),  (0, height, 0), (x0, height, z0), (x1, height, z1)))

    return tris


# ── 직육면체 삼각형 생성 (케이지용) ──

def make_box_triangles(w: float, h: float, d: float) -> list:
    """
    직육면체 삼각형 목록 생성.

    - 중심이 원점 (x: -w/2~w/2, y: -h/2~h/2, z: -d/2~d/2)
    - 6면 × 2삼각형 = 12개
    """
    hw, hh, hd = w / 2, h / 2, d / 2

    # 8 꼭지점
    p = [
        (-hw, -hh, -hd),  # 0 좌하전
        ( hw, -hh, -hd),  # 1 우하전
        ( hw,  hh, -hd),  # 2 우상전
        (-hw,  hh, -hd),  # 3 좌상전
        (-hw, -hh,  hd),  # 4 좌하후
        ( hw, -hh,  hd),  # 5 우하후
        ( hw,  hh,  hd),  # 6 우상후
        (-hw,  hh,  hd),  # 7 좌상후
    ]

    # 각 면: (법선, 꼭지점 인덱스 4개 → 2삼각형)
    faces = [
        ((0, 0, -1), [0, 3, 2, 1]),  # 전면 (-Z)
        ((0, 0,  1), [4, 5, 6, 7]),  # 후면 (+Z)
        ((-1, 0, 0), [0, 4, 7, 3]),  # 좌면 (-X)
        (( 1, 0, 0), [1, 2, 6, 5]),  # 우면 (+X)
        ((0, -1, 0), [0, 1, 5, 4]),  # 하면 (-Y)
        ((0,  1, 0), [3, 7, 6, 2]),  # 상면 (+Y)
    ]

    tris = []
    for normal, idx in faces:
        v0, v1, v2, v3 = p[idx[0]], p[idx[1]], p[idx[2]], p[idx[3]]
        tris.append((normal, v0, v1, v2))
        tris.append((normal, v0, v2, v3))

    return tris


# ── 규격 정의 ──

# 스크류: (반지름_mm, 길이_mm)
SCREW_SPECS: dict[str, tuple[float, float]] = {
    'M5x40': (2.5, 40.0),
    'M6x45': (3.0, 45.0),
    'M6x50': (3.0, 50.0),
    'M7x50': (3.5, 50.0),
    'M7x55': (3.5, 55.0),
}

# 케이지: (폭_mm, 높이_mm, 깊이_mm)
CAGE_SPECS: dict[str, tuple[float, float, float]] = {
    'cage_S':  (22.0,  8.0, 14.0),
    'cage_M':  (26.0, 10.0, 14.0),
    'cage_L':  (26.0, 12.0, 14.0),
    'cage_XL': (32.0, 14.0, 14.0),
}

# 로드: (반지름_mm, 길이_mm) — 척추경 나사 연결용 막대
ROD_SPECS: dict[str, tuple[float, float]] = {
    'rod_40':  (2.75, 40.0),
    'rod_50':  (2.75, 50.0),
    'rod_60':  (2.75, 60.0),
    'rod_80':  (2.75, 80.0),
    'rod_100': (2.75, 100.0),
}


# ── 메인 ──

def main() -> None:
    """스크류, 케이지, 로드 더미 STL 파일 일괄 생성."""
    count = 0

    # 스크류 생성
    for name, (radius, height) in SCREW_SPECS.items():
        path = os.path.join(BASE_DIR, 'screws', f'{name}.stl')
        tris = make_cylinder_triangles(radius, height)
        write_stl_binary(path, tris)
        print(f'  [스크류] {name} → {path}  ({len(tris)} tri)')
        count += 1

    # 케이지 생성
    for name, (w, h, d) in CAGE_SPECS.items():
        path = os.path.join(BASE_DIR, 'cages', f'{name}.stl')
        tris = make_box_triangles(w, h, d)
        write_stl_binary(path, tris)
        print(f'  [케이지] {name} → {path}  ({len(tris)} tri)')
        count += 1

    # 로드 생성 (가느다란 원기둥)
    for name, (radius, length) in ROD_SPECS.items():
        path = os.path.join(BASE_DIR, 'rods', f'{name}.stl')
        tris = make_cylinder_triangles(radius, length, segments=16)
        write_stl_binary(path, tris)
        print(f'  [로드]   {name} → {path}  ({len(tris)} tri)')
        count += 1

    print(f'\n총 {count}개 STL 파일 생성 완료.')
    print(f'경로: {os.path.abspath(BASE_DIR)}')


if __name__ == '__main__':
    main()
