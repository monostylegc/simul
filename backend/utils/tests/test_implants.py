"""임플란트 모델 테스트."""

import pytest
import numpy as np
import tempfile
from pathlib import Path

from backend.utils.implants import (
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
