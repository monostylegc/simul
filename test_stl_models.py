#!/usr/bin/env python
"""STL 모델 로드 및 테스트 스크립트.

L4, L5, disc STL 파일을 로드하여 메쉬 정보를 확인하고
시뮬레이터에서 시각화합니다.

실행: uv run python test_stl_models.py
"""

import taichi as ti
import numpy as np
from pathlib import Path

# Taichi 초기화
ti.init(arch=ti.gpu)

from spine_sim.core.mesh import TriangleMesh
from spine_sim.app.simulator import SpineSimulator, SceneObject


def load_and_center_models():
    """STL 모델 로드 및 중심 정렬."""
    stl_dir = Path("stl")

    meshes = {}
    all_verts = []

    # 모든 모델 로드
    for filename in ["L4.stl", "L5.stl", "disc.stl"]:
        filepath = stl_dir / filename
        if filepath.exists():
            mesh = TriangleMesh.load(str(filepath))
            name = filename.replace(".stl", "")
            meshes[name] = mesh
            all_verts.append(mesh.vertices)

    # 전체 모델의 중심 계산
    all_verts = np.vstack(all_verts)
    global_center = (all_verts.min(axis=0) + all_verts.max(axis=0)) / 2

    print(f"전체 모델 중심: ({global_center[0]:.1f}, {global_center[1]:.1f}, {global_center[2]:.1f})")

    # 각 모델의 정점을 중심으로 이동
    for name, mesh in meshes.items():
        mesh.vertices = mesh.vertices - global_center
        mesh.compute_normals()

        # 이동 후 범위 확인
        min_c = mesh.vertices.min(axis=0)
        max_c = mesh.vertices.max(axis=0)
        print(f"{name}: 범위 X({min_c[0]:.1f}~{max_c[0]:.1f}), "
              f"Y({min_c[1]:.1f}~{max_c[1]:.1f}), Z({min_c[2]:.1f}~{max_c[2]:.1f})")

    return meshes


def run_simulator():
    """시뮬레이터 실행."""
    print("\n" + "=" * 60)
    print("시뮬레이터 실행")
    print("=" * 60)

    # 모델 로드 및 중심 정렬
    meshes = load_and_center_models()

    sim = SpineSimulator(width=1400, height=900)

    # 색상 설정
    colors = {
        "L4": (0.95, 0.90, 0.80),   # 밝은 뼈색
        "L5": (0.90, 0.85, 0.75),   # 뼈색
        "disc": (0.8, 0.4, 0.4),    # 붉은 디스크
    }

    # 모델 추가
    for name, mesh in meshes.items():
        color = colors.get(name, (0.8, 0.8, 0.8))
        sim.objects[name] = SceneObject(mesh=mesh, color=color)

    sim._update_render_data()

    # 내시경 위치 (측면에서 바라보도록)
    sim.endoscope.set_position(np.array([80, 0, 0]))
    sim.endoscope.set_direction(np.array([-1, 0, 0]))

    # 카메라 설정
    sim.gui_manager.state.camera.distance = 200.0
    sim.gui_manager.state.camera.phi = 20.0

    print("\n조작법:")
    print("  마우스 드래그: 카메라 회전")
    print("  +/-: 줌")
    print("  WASD: 내시경 이동")
    print("  Q/E: 내시경 회전")
    print("  V: 뷰 전환 (메인 ↔ 내시경)")
    print("  Drill 모드 → Init Volume → Space: 드릴링")
    print("\n모델 정보:")
    print(f"  L4: {meshes['L4'].n_vertices:,} 정점, {meshes['L4'].n_faces:,} 삼각형")
    print(f"  L5: {meshes['L5'].n_vertices:,} 정점, {meshes['L5'].n_faces:,} 삼각형")
    print(f"  disc: {meshes['disc'].n_vertices:,} 정점, {meshes['disc'].n_faces:,} 삼각형")

    sim.run()


if __name__ == "__main__":
    run_simulator()
