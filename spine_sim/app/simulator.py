"""Main spine surgery simulator application."""

import taichi as ti
import numpy as np
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from ..core.mesh import TriangleMesh
from ..core.volume import VoxelVolume
from ..core.collision import CollisionDetector
from ..core.transform import Transform
from ..core.marching_cubes import MarchingCubes
from ..endoscope.instrument import Endoscope

from .gui import GUIManager, GUIState, ToolMode


@dataclass
class SceneObject:
    """씬 내 객체."""
    mesh: TriangleMesh
    color: tuple = (0.8, 0.8, 0.8)
    visible: bool = True
    selectable: bool = True


@ti.data_oriented
class SpineSimulator:
    """척추 수술 시뮬레이터 메인 애플리케이션.

    기능:
    - 3D 모델 로딩/표시 (STL/OBJ)
    - 척추 위치/방향 조절
    - 내시경 탐색 및 충돌 감지
    - 수술 드릴링 (복셀 제거)
    """

    def __init__(self, width: int = 1280, height: int = 720):
        """시뮬레이터 초기화.

        Args:
            width, height: 윈도우 크기
        """
        self.width = width
        self.height = height

        # 씬 객체
        self.objects: Dict[str, SceneObject] = {}

        # 충돌 감지기
        self.collision = CollisionDetector(max_triangles=500000)

        # 내시경
        self.endoscope = Endoscope()

        # 드릴링용 복셀 볼륨
        self.volume: Optional[VoxelVolume] = None
        self.marching_cubes: Optional[MarchingCubes] = None
        self.volume_mesh_dirty = False

        # 렌더링 버퍼
        self.vertices = ti.Vector.field(3, dtype=ti.f32, shape=100000)
        self.normals = ti.Vector.field(3, dtype=ti.f32, shape=100000)
        self.colors = ti.Vector.field(3, dtype=ti.f32, shape=100000)
        self.indices = ti.field(dtype=ti.i32, shape=300000)
        self.n_vertices = 0
        self.n_indices = 0

        # GUI 매니저
        self.gui_manager = GUIManager()
        self._register_callbacks()

    def _register_callbacks(self):
        """GUI 콜백 등록."""
        state = self.gui_manager.state

        state.register_callback("init_drilling_volume", self._on_init_drilling_volume)
        state.register_callback("perform_drilling", self._on_perform_drilling)
        state.register_callback("add_vertebra", self._on_add_vertebra)
        state.register_callback("update_render_data", self._update_render_data)

    def _on_init_drilling_volume(self):
        """드릴링 볼륨 초기화 콜백."""
        state = self.gui_manager.state
        self.init_drilling_volume(
            resolution=state.drill.volume_resolution,
            center=(0, 15, 0),
            size=state.drill.volume_size
        )

    def _on_perform_drilling(self, position, direction, radius, depth):
        """드릴링 수행 콜백."""
        self.perform_drilling(position, direction, radius, depth)

    def _on_add_vertebra(self):
        """척추 추가 콜백."""
        n = len([o for o in self.objects if o.startswith("L")])
        self.add_sample_vertebra(f"L{n+1}", position=(0, -30 * n, 0))

    # =========================================================================
    # 모델 관리
    # =========================================================================

    def load_model(self, filepath: str, name: Optional[str] = None,
                   color: tuple = (0.9, 0.85, 0.75)) -> str:
        """파일에서 3D 모델 로드.

        Args:
            filepath: STL 또는 OBJ 파일 경로
            name: 객체 이름 (None이면 파일명 사용)
            color: RGB 색상 튜플

        Returns:
            객체 이름
        """
        mesh = TriangleMesh.load(filepath, name)
        if name is None:
            name = mesh.name

        self.objects[name] = SceneObject(mesh=mesh, color=color)
        self._update_render_data()

        print(f"로드됨 '{name}': {mesh.n_vertices} 정점, {mesh.n_faces} 면")
        return name

    def load_volume(
        self,
        filepath: str,
        name: str = "CT",
        max_resolution: int = 64,
        is_labelmap: bool = False,
        isovalue: float = 0.5,
        color: tuple = (0.9, 0.85, 0.75)
    ) -> str:
        """NRRD/NIFTI 볼륨 파일 로드.

        3D Slicer에서 생성한 CT 볼륨 또는 세그멘테이션 labelmap을 로드합니다.

        Args:
            filepath: NRRD/NIFTI 파일 경로
            name: 객체 이름
            max_resolution: 최대 해상도 (다운샘플링)
            is_labelmap: True면 세그멘테이션 labelmap으로 로드
            isovalue: Marching Cubes 등위값
            color: RGB 색상 튜플

        Returns:
            객체 이름
        """
        from ..core.marching_cubes import MarchingCubes

        # 볼륨 로드
        if is_labelmap:
            volume = VoxelVolume.load_labelmap(filepath, max_resolution=max_resolution)
        else:
            volume = VoxelVolume.load(filepath, max_resolution=max_resolution)

        print(f"볼륨 로드됨: {volume.nx}x{volume.ny}x{volume.nz}, spacing={volume.spacing:.3f}")

        # 메쉬 추출
        marching_cubes = MarchingCubes(max_vertices=200000, max_triangles=200000)
        vertices, normals, faces = marching_cubes.extract(volume, isovalue=isovalue)

        if len(vertices) == 0:
            print(f"경고: '{name}' 볼륨에서 메쉬를 추출할 수 없습니다.")
            return name

        # TriangleMesh 생성
        mesh = TriangleMesh(vertices, faces, name=name)

        # 씬에 추가
        self.objects[name] = SceneObject(mesh=mesh, color=color)
        self._update_render_data()

        # 드릴링을 위해 볼륨 저장
        self.volume = volume
        self.marching_cubes = marching_cubes
        self.gui_manager.state.drill.volume_initialized = True

        print(f"'{name}': {mesh.n_vertices} 정점, {mesh.n_faces} 면 추출됨")
        return name

    def add_sample_vertebra(self, name: str = "L4", position: tuple = (0, 0, 0)):
        """샘플 척추 추가 (박스 플레이스홀더)."""
        mesh = TriangleMesh.create_box(size=(30, 25, 20))
        mesh.name = name
        mesh.transform.position = np.array(position, dtype=np.float32)

        self.objects[name] = SceneObject(
            mesh=mesh,
            color=(0.9, 0.85, 0.75)  # 뼈 색상
        )
        self._update_render_data()
        return name

    def set_object_position(self, name: str, position: tuple):
        """객체 위치 설정."""
        if name in self.objects:
            self.objects[name].mesh.transform.position = np.array(position, dtype=np.float32)
            self._update_render_data()

    def set_object_rotation(self, name: str, rx: float, ry: float, rz: float):
        """객체 회전 설정 (오일러 각도, 도 단위)."""
        if name in self.objects:
            t = Transform.from_euler(rx, ry, rz)
            self.objects[name].mesh.transform.rotation = t.rotation
            self._update_render_data()

    # =========================================================================
    # 드릴링
    # =========================================================================

    def init_drilling_volume(self, resolution: tuple = (64, 64, 64),
                             center: tuple = (0, 0, 0),
                             size: float = 50.0):
        """드릴링용 복셀 볼륨 초기화.

        Args:
            resolution: 복셀 해상도 (nx, ny, nz)
            center: 볼륨 중심 위치
            size: 볼륨 크기 (한 변의 길이)
        """
        spacing = size / resolution[0]
        origin = (
            center[0] - size / 2,
            center[1] - size / 2,
            center[2] - size / 2
        )

        self.volume = VoxelVolume(resolution=resolution, origin=origin, spacing=spacing)
        self.marching_cubes = MarchingCubes(max_vertices=200000, max_triangles=200000)

        # 기존 객체를 복셀로 변환 (단순 구 근사)
        for name, obj in self.objects.items():
            pos = obj.mesh.transform.position
            self.volume.fill_sphere(pos[0], pos[1], pos[2], 12.0, 1.0, 1)

        self.volume_mesh_dirty = True
        self.gui_manager.state.drill.volume_initialized = True
        print(f"드릴링 볼륨 초기화: {resolution}, spacing={spacing:.2f}")

    def perform_drilling(self, position: np.ndarray, direction: np.ndarray,
                         radius: float = None, depth: float = 5.0):
        """지정된 위치에서 드릴링 수행.

        Args:
            position: 드릴 팁 위치
            direction: 드릴 방향 (정규화됨)
            radius: 드릴 반지름
            depth: 드릴 깊이
        """
        if self.volume is None:
            print("경고: 드릴링 볼륨이 초기화되지 않음")
            return 0

        if radius is None:
            radius = self.gui_manager.state.drill.radius

        # 방향 정규화
        direction = direction / (np.linalg.norm(direction) + 1e-6)

        removed = self.volume.drill(
            position[0], position[1], position[2],
            direction[0], direction[1], direction[2],
            radius, depth
        )

        if removed > 0:
            self.volume_mesh_dirty = True

        return removed

    def _update_volume_mesh(self):
        """볼륨에서 메쉬 업데이트 (Marching Cubes)."""
        if self.volume is None or self.marching_cubes is None:
            return

        if not self.volume_mesh_dirty:
            return

        vertices, normals, faces = self.marching_cubes.extract(self.volume, isovalue=0.5)

        if len(vertices) > 0:
            mesh = TriangleMesh(vertices, faces, name="VoxelMesh")

            if "VoxelMesh" in self.objects:
                self.objects["VoxelMesh"].mesh = mesh
            else:
                self.objects["VoxelMesh"] = SceneObject(
                    mesh=mesh,
                    color=(0.95, 0.9, 0.8),
                    selectable=False
                )

            self._update_render_data()

        self.volume_mesh_dirty = False

    # =========================================================================
    # 렌더링
    # =========================================================================

    def _update_render_data(self):
        """렌더링 버퍼 업데이트."""
        all_verts = []
        all_norms = []
        all_colors = []
        all_indices = []

        vertex_offset = 0

        for name, obj in self.objects.items():
            if not obj.visible:
                continue

            mesh = obj.mesh
            verts = mesh.get_transformed_vertices()
            norms = mesh.get_transformed_normals()

            n_v = len(verts)
            all_verts.append(verts)
            all_norms.append(norms)
            all_colors.append(np.tile(obj.color, (n_v, 1)))
            all_indices.append(mesh.faces + vertex_offset)

            vertex_offset += n_v

        if all_verts:
            verts = np.vstack(all_verts).astype(np.float32)
            norms = np.vstack(all_norms).astype(np.float32)
            colors = np.vstack(all_colors).astype(np.float32)
            indices = np.vstack(all_indices).flatten().astype(np.int32)

            self.n_vertices = min(len(verts), 100000)
            self.n_indices = min(len(indices), 300000)

            verts = verts[:self.n_vertices]
            norms = norms[:self.n_vertices]
            colors = colors[:self.n_vertices]
            indices = indices[:self.n_indices]

            # 고정 크기로 패딩
            verts_padded = np.zeros((100000, 3), dtype=np.float32)
            norms_padded = np.zeros((100000, 3), dtype=np.float32)
            colors_padded = np.zeros((100000, 3), dtype=np.float32)
            indices_padded = np.zeros(300000, dtype=np.int32)

            verts_padded[:len(verts)] = verts
            norms_padded[:len(norms)] = norms
            colors_padded[:len(colors)] = colors
            indices_padded[:len(indices)] = indices

            self.vertices.from_numpy(verts_padded)
            self.normals.from_numpy(norms_padded)
            self.colors.from_numpy(colors_padded)
            self.indices.from_numpy(indices_padded)

            # 충돌 감지기 업데이트
            faces = np.vstack(all_indices).astype(np.int32)
            if len(faces) <= self.collision.max_triangles:
                self.collision.load_mesh(verts, faces)
        else:
            self.n_vertices = 0
            self.n_indices = 0

    # =========================================================================
    # 메인 루프
    # =========================================================================

    def run(self):
        """시뮬레이터 실행."""
        window = ti.ui.Window("Spine Surgery Simulator", (self.width, self.height), vsync=True)
        canvas = window.get_canvas()
        scene = window.get_scene()
        camera = ti.ui.Camera()
        gui = window.get_gui()

        while window.running:
            # 컨텍스트 구성
            context = self._build_context()

            # 입력 처리
            self.gui_manager.handle_input(window, context)

            # 볼륨 메쉬 업데이트
            self._update_volume_mesh()

            # 카메라 및 조명 설정 (뷰 모드에 따라)
            self.gui_manager.setup_camera(camera, self.endoscope)
            scene.set_camera(camera)
            self.gui_manager.setup_lighting(scene, self.endoscope)

            # 메쉬 렌더링
            if self.n_vertices > 0:
                scene.mesh(
                    self.vertices,
                    indices=self.indices,
                    normals=self.normals,
                    per_vertex_color=self.colors,
                    two_sided=True
                )

            canvas.scene(scene)

            # GUI 렌더링
            self.gui_manager.render(gui, context)

            window.show()

    def _build_context(self) -> Dict[str, Any]:
        """GUI용 컨텍스트 구성."""
        return {
            "objects": self.objects,
            "endoscope": self.endoscope,
            "collision": self.collision,
            "volume": self.volume,
            "n_vertices": self.n_vertices,
            "n_triangles": self.n_indices // 3,
            "fps": 60.0,  # TODO: 실제 FPS 측정
            "view_mode_name": self.gui_manager.get_view_mode_name(),
        }


def main():
    """시뮬레이터 실행."""
    ti.init(arch=ti.gpu)

    sim = SpineSimulator(width=1400, height=900)

    # 샘플 척추 추가
    sim.add_sample_vertebra("L5", position=(0, 0, 0))
    sim.add_sample_vertebra("L4", position=(0, 30, 0))
    sim.add_sample_vertebra("L3", position=(0, 60, 0))

    # 내시경 위치 설정
    sim.endoscope.set_position(np.array([50, 30, 50]))
    sim.endoscope.set_direction(np.array([-1, 0, -1]))

    sim.run()


if __name__ == "__main__":
    main()
