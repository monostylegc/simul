"""가이드라인 테스트."""

import pytest
import numpy as np

from spine_sim.core.guideline import (
    PedicleEntryPoint,
    ScrewGuideline,
    GuidelineManager,
    create_trajectory_mesh,
    create_safe_zone_mesh,
    create_depth_marker_mesh,
)


class TestPedicleEntryPoint:
    """PedicleEntryPoint 테스트."""

    def test_default_direction(self):
        """기본 방향 (내측각=0, 두측각=0) 테스트."""
        entry = PedicleEntryPoint(
            position=np.array([0, 0, 0]),
            medial_angle=0.0,
            caudal_angle=0.0
        )

        direction = entry.get_direction()

        # 기본 방향: -Z (전방)
        assert direction[2] < 0  # Z가 음수

    def test_medial_angle(self):
        """내측각 테스트."""
        entry = PedicleEntryPoint(
            position=np.array([0, 0, 0]),
            medial_angle=15.0,  # 15도 내측
            caudal_angle=0.0
        )

        direction = entry.get_direction()

        # 내측각이 있으면 X 방향 성분이 있어야 함
        assert direction[0] < 0  # 좌측으로 기울어짐

    def test_direction_normalized(self):
        """방향 벡터 정규화 테스트."""
        entry = PedicleEntryPoint(
            position=np.array([0, 0, 0]),
            medial_angle=10.0,
            caudal_angle=5.0
        )

        direction = entry.get_direction()
        length = np.linalg.norm(direction)

        assert abs(length - 1.0) < 0.001


class TestTrajectoryMesh:
    """궤적 메쉬 테스트."""

    def test_creation(self):
        """궤적 메쉬 생성 테스트."""
        mesh = create_trajectory_mesh(
            start=np.array([0, 0, 0]),
            direction=np.array([0, 0, -1]),
            length=45.0
        )

        assert mesh.n_vertices > 0
        assert mesh.n_faces > 0

    def test_length(self):
        """궤적 길이 테스트."""
        length = 50.0
        mesh = create_trajectory_mesh(
            start=np.array([0, 0, 0]),
            direction=np.array([0, 0, -1]),
            length=length
        )

        # 바운딩 박스로 길이 확인
        min_b, max_b = mesh.get_bounds()
        actual_length = max_b[2] - min_b[2]

        assert actual_length >= length * 0.9


class TestSafeZoneMesh:
    """안전 영역 메쉬 테스트."""

    def test_creation(self):
        """안전 영역 생성 테스트."""
        mesh = create_safe_zone_mesh(
            center=np.array([0, 0, 0]),
            normal=np.array([0, 0, 1]),
            radius=3.0
        )

        assert mesh.n_vertices > 0
        assert mesh.n_faces > 0

    def test_radius(self):
        """반경 테스트."""
        radius = 5.0
        mesh = create_safe_zone_mesh(
            center=np.array([0, 0, 0]),
            normal=np.array([0, 0, 1]),
            radius=radius
        )

        # 바운딩 박스로 반경 확인
        min_b, max_b = mesh.get_bounds()
        actual_radius = (max_b[0] - min_b[0]) / 2

        assert abs(actual_radius - radius) < 0.5


class TestDepthMarkerMesh:
    """깊이 마커 테스트."""

    def test_creation(self):
        """깊이 마커 생성 테스트."""
        mesh = create_depth_marker_mesh(
            start=np.array([0, 0, 0]),
            direction=np.array([0, 0, -1]),
            depth=45.0,
            marker_interval=10.0
        )

        assert mesh.n_vertices > 0

    def test_marker_count(self):
        """마커 개수 테스트."""
        depth = 50.0
        interval = 10.0

        mesh = create_depth_marker_mesh(
            start=np.array([0, 0, 0]),
            direction=np.array([0, 0, -1]),
            depth=depth,
            marker_interval=interval
        )

        expected_markers = int(depth / interval)
        # 각 마커는 여러 정점을 가짐
        assert mesh.n_vertices >= expected_markers


class TestGuidelineManager:
    """GuidelineManager 테스트."""

    def test_add_guideline(self):
        """가이드라인 추가 테스트."""
        manager = GuidelineManager()

        entry = PedicleEntryPoint(position=np.array([0, 0, 0]))
        guideline = ScrewGuideline(entry_point=entry)

        manager.add_guideline(guideline)

        assert len(manager.guidelines) == 1

    def test_bilateral_creation(self):
        """양측 가이드라인 생성 테스트."""
        manager = GuidelineManager()

        manager.create_standard_bilateral_guidelines(
            vertebra_position=np.array([0, 0, 0]),
            vertebra_name="L4"
        )

        assert len(manager.guidelines) == 2
        assert manager.guidelines[0].side == "left"
        assert manager.guidelines[1].side == "right"

    def test_visualization_meshes(self):
        """시각화 메쉬 생성 테스트."""
        manager = GuidelineManager()

        manager.create_standard_bilateral_guidelines(
            vertebra_position=np.array([0, 0, 0])
        )

        meshes = manager.get_visualization_meshes()

        # 각 가이드라인당 여러 메쉬 (궤적, 안전 영역, 마커)
        assert len(meshes) > 0

    def test_clear(self):
        """가이드라인 제거 테스트."""
        manager = GuidelineManager()

        manager.create_standard_bilateral_guidelines(
            vertebra_position=np.array([0, 0, 0])
        )

        assert len(manager.guidelines) > 0

        manager.clear()

        assert len(manager.guidelines) == 0


class TestSimulatorIntegration:
    """시뮬레이터 통합 테스트."""

    def test_add_guideline(self):
        """시뮬레이터에서 가이드라인 추가."""
        import taichi as ti
        ti.init(arch=ti.cpu, offline_cache=True)

        from spine_sim.app.simulator import SpineSimulator

        sim = SpineSimulator(width=800, height=600)
        sim.add_sample_vertebra("L4", position=(0, 30, 0))

        sim.add_screw_guideline("L4", side="left")

        assert len(sim.guideline_manager.guidelines) == 1

    def test_bilateral_guidelines(self):
        """양측 가이드라인 추가."""
        import taichi as ti
        ti.init(arch=ti.cpu, offline_cache=True)

        from spine_sim.app.simulator import SpineSimulator

        sim = SpineSimulator(width=800, height=600)
        sim.add_sample_vertebra("L4", position=(0, 30, 0))

        sim.add_bilateral_guidelines("L4")

        assert len(sim.guideline_manager.guidelines) == 2

    def test_toggle_guidelines(self):
        """가이드라인 토글 테스트."""
        import taichi as ti
        ti.init(arch=ti.cpu, offline_cache=True)

        from spine_sim.app.simulator import SpineSimulator

        sim = SpineSimulator(width=800, height=600)

        initial = sim.show_guidelines
        toggled = sim.toggle_guidelines()

        assert toggled != initial
