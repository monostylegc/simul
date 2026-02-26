"""수술 가이드라인 - 임플란트 배치 경로 시각화."""

import numpy as np
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

from .mesh import TriangleMesh


@dataclass
class PedicleEntryPoint:
    """척추경 진입점 정보.

    Pedicle Screw 삽입을 위한 진입점과 권장 각도 정보.
    """
    position: np.ndarray          # 진입점 위치 (mm)
    medial_angle: float = 10.0    # 내측각 (도), 일반적으로 5-15도
    caudal_angle: float = 0.0     # 두측각 (도), 일반적으로 0-10도
    depth: float = 45.0           # 권장 삽입 깊이 (mm)
    safe_zone_radius: float = 3.0 # 안전 영역 반경 (mm)

    def get_direction(self) -> np.ndarray:
        """삽입 방향 벡터 계산.

        Returns:
            정규화된 방향 벡터
        """
        # 기본 방향: -Z (전방으로)
        medial_rad = np.radians(self.medial_angle)
        caudal_rad = np.radians(self.caudal_angle)

        # 내측각 적용 (Y축 회전)
        x = -np.sin(medial_rad)
        z = -np.cos(medial_rad)

        # 두측각 적용 (X축 회전)
        y = -np.sin(caudal_rad) * np.cos(medial_rad)
        z = -np.cos(caudal_rad) * np.cos(medial_rad)

        direction = np.array([x, y, z], dtype=np.float32)
        return direction / (np.linalg.norm(direction) + 1e-8)


@dataclass
class ScrewGuideline:
    """Pedicle Screw 삽입 가이드라인."""
    entry_point: PedicleEntryPoint
    vertebra_name: str = ""
    side: str = "left"  # "left" or "right"

    # 시각화 설정
    show_trajectory: bool = True
    show_safe_zone: bool = True
    show_depth_marker: bool = True

    # 색상 설정
    trajectory_color: tuple = (0.0, 1.0, 0.0)  # 녹색
    safe_zone_color: tuple = (0.0, 0.5, 0.0)   # 진한 녹색
    danger_color: tuple = (1.0, 0.0, 0.0)      # 빨간색


def create_trajectory_mesh(
    start: np.ndarray,
    direction: np.ndarray,
    length: float,
    radius: float = 1.0,
    segments: int = 8
) -> TriangleMesh:
    """삽입 경로 메쉬 생성 (원뿔 형태).

    Args:
        start: 시작점
        direction: 방향 (정규화됨)
        length: 길이
        radius: 시작점 반경
        segments: 원형 세그먼트 수

    Returns:
        경로 메쉬
    """
    direction = direction / (np.linalg.norm(direction) + 1e-8)
    end = start + direction * length

    # 직교 기저 벡터 생성
    if abs(direction[0]) < 0.9:
        up = np.array([1, 0, 0])
    else:
        up = np.array([0, 1, 0])

    right = np.cross(direction, up)
    right = right / (np.linalg.norm(right) + 1e-8)
    up = np.cross(right, direction)

    vertices = []
    faces = []

    # 시작점 원형 정점
    for i in range(segments):
        angle = 2 * np.pi * i / segments
        offset = radius * (np.cos(angle) * right + np.sin(angle) * up)
        vertices.append(start + offset)

    # 끝점 (뾰족한 원뿔)
    tip_idx = len(vertices)
    vertices.append(end)

    # 원뿔 측면
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.append([i, next_i, tip_idx])

    # 시작점 캡
    center_idx = len(vertices)
    vertices.append(start)
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.append([center_idx, next_i, i])

    return TriangleMesh(
        vertices=np.array(vertices, dtype=np.float32),
        faces=np.array(faces, dtype=np.int32),
        name="trajectory"
    )


def create_safe_zone_mesh(
    center: np.ndarray,
    normal: np.ndarray,
    radius: float,
    segments: int = 16
) -> TriangleMesh:
    """안전 영역 원형 메쉬 생성.

    Args:
        center: 원 중심
        normal: 원 법선
        radius: 반경
        segments: 세그먼트 수

    Returns:
        안전 영역 메쉬
    """
    normal = normal / (np.linalg.norm(normal) + 1e-8)

    # 직교 기저 벡터
    if abs(normal[0]) < 0.9:
        up = np.array([1, 0, 0])
    else:
        up = np.array([0, 1, 0])

    right = np.cross(normal, up)
    right = right / (np.linalg.norm(right) + 1e-8)
    up = np.cross(right, normal)

    vertices = [center]  # 중심점
    faces = []

    # 원형 정점
    for i in range(segments):
        angle = 2 * np.pi * i / segments
        offset = radius * (np.cos(angle) * right + np.sin(angle) * up)
        vertices.append(center + offset)

    # 삼각형 면
    for i in range(segments):
        next_i = (i % segments) + 1
        next_next = ((i + 1) % segments) + 1
        faces.append([0, next_i, next_next])

    return TriangleMesh(
        vertices=np.array(vertices, dtype=np.float32),
        faces=np.array(faces, dtype=np.int32),
        name="safe_zone"
    )


def create_depth_marker_mesh(
    start: np.ndarray,
    direction: np.ndarray,
    depth: float,
    marker_interval: float = 10.0,
    marker_radius: float = 0.5,
    segments: int = 8
) -> TriangleMesh:
    """깊이 표시 마커 메쉬 생성.

    Args:
        start: 시작점
        direction: 방향
        depth: 총 깊이
        marker_interval: 마커 간격 (mm)
        marker_radius: 마커 반경
        segments: 세그먼트 수

    Returns:
        깊이 마커 메쉬
    """
    direction = direction / (np.linalg.norm(direction) + 1e-8)

    all_vertices = []
    all_faces = []
    vertex_offset = 0

    n_markers = int(depth / marker_interval)

    for m in range(1, n_markers + 1):
        d = m * marker_interval
        center = start + direction * d

        # 작은 원형 마커
        marker = create_safe_zone_mesh(center, direction, marker_radius, segments)

        all_vertices.append(marker.vertices)
        all_faces.append(marker.faces + vertex_offset)
        vertex_offset += len(marker.vertices)

    if not all_vertices:
        return TriangleMesh(
            vertices=np.zeros((0, 3), dtype=np.float32),
            faces=np.zeros((0, 3), dtype=np.int32),
            name="depth_markers"
        )

    return TriangleMesh(
        vertices=np.vstack(all_vertices).astype(np.float32),
        faces=np.vstack(all_faces).astype(np.int32),
        name="depth_markers"
    )


class GuidelineManager:
    """가이드라인 관리자.

    여러 가이드라인을 관리하고 시각화 메쉬를 생성합니다.
    """

    def __init__(self):
        """관리자 초기화."""
        self.guidelines: List[ScrewGuideline] = []

    def add_guideline(self, guideline: ScrewGuideline):
        """가이드라인 추가."""
        self.guidelines.append(guideline)

    def remove_guideline(self, index: int):
        """가이드라인 제거."""
        if 0 <= index < len(self.guidelines):
            self.guidelines.pop(index)

    def clear(self):
        """모든 가이드라인 제거."""
        self.guidelines.clear()

    def create_standard_bilateral_guidelines(
        self,
        vertebra_position: np.ndarray,
        vertebra_name: str = "L4",
        pedicle_offset: float = 15.0,
        medial_angle: float = 10.0,
        caudal_angle: float = 0.0,
        depth: float = 45.0
    ):
        """양측 표준 가이드라인 생성.

        Args:
            vertebra_position: 척추 중심 위치
            vertebra_name: 척추 이름
            pedicle_offset: 척추경 좌우 오프셋 (mm)
            medial_angle: 내측각 (도)
            caudal_angle: 두측각 (도)
            depth: 삽입 깊이 (mm)
        """
        # 좌측 가이드라인
        left_pos = vertebra_position + np.array([-pedicle_offset, 0, 0])
        left_entry = PedicleEntryPoint(
            position=left_pos,
            medial_angle=medial_angle,
            caudal_angle=caudal_angle,
            depth=depth
        )
        self.guidelines.append(ScrewGuideline(
            entry_point=left_entry,
            vertebra_name=vertebra_name,
            side="left"
        ))

        # 우측 가이드라인 (내측각 반대)
        right_pos = vertebra_position + np.array([pedicle_offset, 0, 0])
        right_entry = PedicleEntryPoint(
            position=right_pos,
            medial_angle=-medial_angle,  # 반대 방향
            caudal_angle=caudal_angle,
            depth=depth
        )
        self.guidelines.append(ScrewGuideline(
            entry_point=right_entry,
            vertebra_name=vertebra_name,
            side="right"
        ))

    def get_visualization_meshes(self) -> List[Tuple[TriangleMesh, tuple]]:
        """시각화용 메쉬 리스트 생성.

        Returns:
            (mesh, color) 튜플 리스트
        """
        meshes = []

        for guideline in self.guidelines:
            entry = guideline.entry_point
            direction = entry.get_direction()

            # 삽입 경로 (원뿔)
            if guideline.show_trajectory:
                trajectory = create_trajectory_mesh(
                    start=entry.position,
                    direction=direction,
                    length=entry.depth,
                    radius=entry.safe_zone_radius * 0.5
                )
                meshes.append((trajectory, guideline.trajectory_color))

            # 안전 영역 (원)
            if guideline.show_safe_zone:
                # 진입점에서 법선 방향으로 약간 들어간 위치
                safe_zone_pos = entry.position + direction * 2
                safe_zone = create_safe_zone_mesh(
                    center=safe_zone_pos,
                    normal=-direction,  # 바깥쪽을 향함
                    radius=entry.safe_zone_radius
                )
                meshes.append((safe_zone, guideline.safe_zone_color))

            # 깊이 마커
            if guideline.show_depth_marker:
                markers = create_depth_marker_mesh(
                    start=entry.position,
                    direction=direction,
                    depth=entry.depth
                )
                if markers.n_vertices > 0:
                    meshes.append((markers, (1.0, 1.0, 0.0)))  # 노란색

        return meshes
