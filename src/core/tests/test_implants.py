"""임플란트 모델 테스트."""

import pytest
import numpy as np
import tempfile
from pathlib import Path

from spine_sim.core.implants import (
    create_pedicle_screw,
    create_interbody_cage,
    create_rod,
    create_standard_screw,
    create_standard_cage,
    ScrewSpec,
    CageSpec,
)


class TestPedicleScrew:
    """Pedicle Screw 테스트."""

    def test_default_screw(self):
        """기본 나사 생성 테스트."""
        screw = create_pedicle_screw()

        assert screw.n_vertices > 0
        assert screw.n_faces > 0
        assert screw.name == "PedicleScrew"

    def test_custom_spec(self):
        """커스텀 규격 테스트."""
        spec = ScrewSpec(diameter=7.0, length=50.0)
        screw = create_pedicle_screw(spec)

        # 바운딩 박스 확인
        min_b, max_b = screw.get_bounds()

        # 직경 확인 (x, z 방향)
        assert max_b[0] - min_b[0] <= spec.head_diameter + 2  # 헤드 포함
        assert max_b[2] - min_b[2] <= spec.head_diameter + 2

        # 길이 확인 (y 방향)
        assert max_b[1] - min_b[1] >= spec.length * 0.8

    def test_standard_sizes(self):
        """표준 규격 테스트."""
        sizes = ["M5x40", "M6x45", "M7x50"]

        for size in sizes:
            screw = create_standard_screw(size)
            assert screw.n_vertices > 0

    def test_screw_save(self):
        """나사 저장 테스트."""
        screw = create_pedicle_screw()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "screw.stl"
            screw.save_stl(str(path))
            assert path.exists()
            assert path.stat().st_size > 1000  # 적어도 1KB


class TestInterbodyCage:
    """Interbody Cage 테스트."""

    def test_default_cage(self):
        """기본 케이지 생성 테스트."""
        cage = create_interbody_cage()

        assert cage.n_vertices == 8  # 박스 정점
        assert cage.n_faces == 12    # 박스 면
        assert cage.name == "InterbodyCage"

    def test_lordosis_angle(self):
        """전만각 테스트."""
        spec = CageSpec(angle=10.0)
        cage = create_interbody_cage(spec)

        # 상단 정점의 y 값 확인 (뒤쪽이 더 높아야 함)
        vertices = cage.vertices
        top_verts = vertices[vertices[:, 1] > 5]  # 상단 정점

        # z 좌표가 양수인 것(뒤쪽)이 더 높아야 함
        front_y = top_verts[top_verts[:, 2] < 0, 1].mean()
        back_y = top_verts[top_verts[:, 2] > 0, 1].mean()

        assert back_y > front_y

    def test_standard_sizes(self):
        """표준 규격 테스트."""
        sizes = ["S", "M", "L", "XL"]

        for size in sizes:
            cage = create_standard_cage(size)
            assert cage.n_vertices > 0


class TestRod:
    """Connection Rod 테스트."""

    def test_default_rod(self):
        """기본 로드 생성 테스트."""
        rod = create_rod()

        assert rod.n_vertices > 0
        assert rod.n_faces > 0

    def test_rod_dimensions(self):
        """로드 치수 테스트."""
        length = 80.0
        diameter = 5.5

        rod = create_rod(length=length, diameter=diameter)

        min_b, max_b = rod.get_bounds()

        # 길이 확인 (z 방향)
        actual_length = max_b[2] - min_b[2]
        assert abs(actual_length - length) < 1.0

        # 직경 확인 (x 방향)
        actual_diameter = max_b[0] - min_b[0]
        assert abs(actual_diameter - diameter) < 0.5


class TestSimulatorIntegration:
    """시뮬레이터 임플란트 통합 테스트."""

    def test_add_screw(self):
        """나사 추가 테스트."""
        import taichi as ti
        ti.init(arch=ti.cpu, offline_cache=True)

        from spine_sim.app.simulator import SpineSimulator

        sim = SpineSimulator(width=800, height=600)
        name = sim.add_pedicle_screw(position=(10, 20, 30))

        assert "Screw" in name
        assert name in sim.objects

    def test_add_cage(self):
        """케이지 추가 테스트."""
        import taichi as ti
        ti.init(arch=ti.cpu, offline_cache=True)

        from spine_sim.app.simulator import SpineSimulator

        sim = SpineSimulator(width=800, height=600)
        name = sim.add_interbody_cage(position=(0, 15, 0))

        assert "Cage" in name
        assert name in sim.objects

    def test_add_rod(self):
        """로드 추가 테스트."""
        import taichi as ti
        ti.init(arch=ti.cpu, offline_cache=True)

        from spine_sim.app.simulator import SpineSimulator

        sim = SpineSimulator(width=800, height=600)
        name = sim.add_rod(start=(0, 0, 0), end=(0, 60, 0))

        assert "Rod" in name
        assert name in sim.objects

    def test_surgical_setup(self):
        """수술 셋업 테스트 (척추 + 임플란트)."""
        import taichi as ti
        ti.init(arch=ti.cpu, offline_cache=True)

        from spine_sim.app.simulator import SpineSimulator

        sim = SpineSimulator(width=800, height=600)

        # 척추 추가
        sim.add_sample_vertebra("L4", position=(0, 30, 0))
        sim.add_sample_vertebra("L5", position=(0, 0, 0))

        # 나사 추가 (양측)
        sim.add_pedicle_screw(name="L4_Left", position=(-15, 30, 0))
        sim.add_pedicle_screw(name="L4_Right", position=(15, 30, 0))
        sim.add_pedicle_screw(name="L5_Left", position=(-15, 0, 0))
        sim.add_pedicle_screw(name="L5_Right", position=(15, 0, 0))

        # 로드 추가
        sim.add_rod(name="Rod_Left", start=(-15, 30, 0), end=(-15, 0, 0))
        sim.add_rod(name="Rod_Right", start=(15, 30, 0), end=(15, 0, 0))

        # 케이지 추가
        sim.add_interbody_cage(name="Cage_L4L5", position=(0, 15, 0))

        # 총 9개 객체
        assert len(sim.objects) == 9
