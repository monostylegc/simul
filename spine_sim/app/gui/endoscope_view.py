"""내시경 뷰 렌더링 모듈.

PIP(Picture-in-Picture) 또는 전체 화면 내시경 뷰를 제공합니다.
"""

import taichi as ti
import numpy as np
from typing import Optional, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum, auto

if TYPE_CHECKING:
    from ...endoscope.instrument import Endoscope


class ViewMode(Enum):
    """뷰 모드 열거형."""
    MAIN_ONLY = auto()       # 메인 뷰만
    ENDOSCOPE_ONLY = auto()  # 내시경 뷰만
    PIP_BOTTOM_RIGHT = auto()  # 메인 + 우하단 PIP
    SPLIT_HORIZONTAL = auto()  # 좌우 분할


@dataclass
class EndoscopeViewConfig:
    """내시경 뷰 설정."""
    # PIP 위치 및 크기 (화면 비율)
    pip_x: float = 0.70
    pip_y: float = 0.02
    pip_width: float = 0.28
    pip_height: float = 0.35

    # 내시경 광원 설정
    light_intensity: float = 1.0
    light_color: tuple = (1.0, 0.95, 0.9)  # 따뜻한 백색
    light_range: float = 50.0  # mm

    # 뷰 설정
    fov: float = 70.0
    vignette_strength: float = 0.3  # 비네팅 효과 강도


@ti.data_oriented
class EndoscopeViewRenderer:
    """내시경 뷰 렌더러.

    내시경 시점에서의 씬 렌더링을 담당합니다.
    """

    def __init__(self, width: int = 400, height: int = 300):
        """렌더러 초기화.

        Args:
            width, height: PIP 뷰 해상도
        """
        self.width = width
        self.height = height
        self.config = EndoscopeViewConfig()

        # 현재 뷰 모드
        self.view_mode = ViewMode.MAIN_ONLY

        # 내시경 뷰 프레임버퍼 (RGBA)
        self.framebuffer = ti.Vector.field(3, dtype=ti.f32, shape=(width, height))

        # 비네팅 마스크 (원형 감쇠)
        self.vignette_mask = ti.field(dtype=ti.f32, shape=(width, height))
        self._init_vignette_mask()

    @ti.kernel
    def _init_vignette_mask(self):
        """비네팅 마스크 초기화 (내시경 특유의 원형 뷰)."""
        cx = self.width / 2.0
        cy = self.height / 2.0
        max_r = ti.min(cx, cy)

        for i, j in self.vignette_mask:
            dx = i - cx
            dy = j - cy
            r = ti.sqrt(dx * dx + dy * dy)

            # 원형 마스크 + 가장자리 감쇠
            if r < max_r * 0.85:
                self.vignette_mask[i, j] = 1.0
            elif r < max_r:
                # 부드러운 가장자리
                t = (r - max_r * 0.85) / (max_r * 0.15)
                self.vignette_mask[i, j] = 1.0 - t * t
            else:
                self.vignette_mask[i, j] = 0.0

    def toggle_view_mode(self):
        """뷰 모드 순환."""
        modes = list(ViewMode)
        current_idx = modes.index(self.view_mode)
        next_idx = (current_idx + 1) % len(modes)
        self.view_mode = modes[next_idx]
        return self.view_mode

    def set_view_mode(self, mode: ViewMode):
        """뷰 모드 설정."""
        self.view_mode = mode

    def setup_endoscope_camera(self, camera: ti.ui.Camera, endoscope: "Endoscope"):
        """Taichi 카메라를 내시경 시점으로 설정.

        Args:
            camera: Taichi UI 카메라
            endoscope: 내시경 객체
        """
        params = endoscope.get_camera_params()

        camera.position(*params['position'])
        camera.lookat(*params['lookat'])
        camera.up(*params['up'])
        camera.fov(params['fov'])

    def setup_endoscope_lighting(self, scene: ti.ui.Scene, endoscope: "Endoscope"):
        """내시경 조명 설정 (팁에서 발광).

        Args:
            scene: Taichi 씬
            endoscope: 내시경 객체
        """
        tip_pos = endoscope.tip_position
        direction = endoscope.direction

        # 내시경 팁 바로 앞에 포인트 라이트
        light_pos = tip_pos + direction * 2.0

        scene.point_light(
            pos=tuple(light_pos),
            color=self.config.light_color
        )

        # 주변광 낮추기 (내시경 내부는 어두움)
        scene.ambient_light((0.1, 0.1, 0.1))

    def get_pip_rect(self, window_width: int, window_height: int) -> tuple:
        """PIP 영역의 픽셀 좌표 반환.

        Returns:
            (x, y, width, height) 픽셀 단위
        """
        cfg = self.config
        x = int(cfg.pip_x * window_width)
        y = int(cfg.pip_y * window_height)
        w = int(cfg.pip_width * window_width)
        h = int(cfg.pip_height * window_height)
        return (x, y, w, h)

    def render_pip_frame(self, gui, window_width: int, window_height: int):
        """PIP 프레임 테두리 렌더링.

        Args:
            gui: Taichi GUI
            window_width, window_height: 윈도우 크기
        """
        if self.view_mode != ViewMode.PIP_BOTTOM_RIGHT:
            return

        cfg = self.config

        # PIP 영역 테두리
        with gui.sub_window("Endoscope View",
                           cfg.pip_x - 0.01,
                           cfg.pip_y - 0.02,
                           cfg.pip_width + 0.02,
                           cfg.pip_height + 0.04) as w:
            w.text("Endoscope")

    def get_view_mode_name(self) -> str:
        """현재 뷰 모드 이름 반환."""
        names = {
            ViewMode.MAIN_ONLY: "Main View",
            ViewMode.ENDOSCOPE_ONLY: "Endoscope View",
            ViewMode.PIP_BOTTOM_RIGHT: "Main + PIP",
            ViewMode.SPLIT_HORIZONTAL: "Split View",
        }
        return names.get(self.view_mode, "Unknown")


class DualViewRenderer:
    """이중 뷰 렌더러.

    메인 뷰와 내시경 뷰를 동시에 렌더링합니다.
    Taichi GGUI의 제한으로 완전한 동시 렌더링은 어렵지만,
    뷰 전환과 시각적 피드백을 제공합니다.
    """

    def __init__(self):
        """렌더러 초기화."""
        self.endoscope_view = EndoscopeViewRenderer()
        self._is_endoscope_view_active = False

    @property
    def current_view_mode(self) -> ViewMode:
        """현재 뷰 모드."""
        return self.endoscope_view.view_mode

    def toggle_view(self):
        """뷰 모드 전환."""
        mode = self.endoscope_view.toggle_view_mode()
        self._is_endoscope_view_active = (mode == ViewMode.ENDOSCOPE_ONLY)
        return mode

    def is_endoscope_active(self) -> bool:
        """내시경 뷰가 활성화되어 있는지."""
        return self.current_view_mode in [
            ViewMode.ENDOSCOPE_ONLY,
            ViewMode.PIP_BOTTOM_RIGHT,
            ViewMode.SPLIT_HORIZONTAL
        ]

    def setup_camera(self, camera: ti.ui.Camera,
                     main_cam_pos: np.ndarray,
                     main_cam_target: np.ndarray,
                     endoscope: "Endoscope",
                     fov: float = 60.0):
        """현재 뷰 모드에 따라 카메라 설정.

        Args:
            camera: Taichi 카메라
            main_cam_pos: 메인 카메라 위치
            main_cam_target: 메인 카메라 타겟
            endoscope: 내시경 객체
            fov: 메인 카메라 FOV
        """
        mode = self.current_view_mode

        if mode == ViewMode.ENDOSCOPE_ONLY:
            # 내시경 뷰
            self.endoscope_view.setup_endoscope_camera(camera, endoscope)
        else:
            # 메인 뷰 (MAIN_ONLY, PIP_BOTTOM_RIGHT, SPLIT_HORIZONTAL)
            camera.position(*main_cam_pos)
            camera.lookat(*main_cam_target)
            camera.up(0, 1, 0)
            camera.fov(fov)

    def setup_lighting(self, scene: ti.ui.Scene,
                       main_light_pos: np.ndarray,
                       endoscope: "Endoscope"):
        """현재 뷰 모드에 따라 조명 설정.

        Args:
            scene: Taichi 씬
            main_light_pos: 메인 조명 위치
            endoscope: 내시경 객체
        """
        mode = self.current_view_mode

        if mode == ViewMode.ENDOSCOPE_ONLY:
            # 내시경 조명 (팁에서 발광)
            self.endoscope_view.setup_endoscope_lighting(scene, endoscope)
        else:
            # 메인 조명
            scene.ambient_light((0.3, 0.3, 0.3))
            scene.point_light(pos=tuple(main_light_pos), color=(1, 1, 1))

    def render_overlay(self, gui, window_width: int, window_height: int):
        """오버레이 UI 렌더링 (PIP 프레임 등).

        Args:
            gui: Taichi GUI
            window_width, window_height: 윈도우 크기
        """
        self.endoscope_view.render_pip_frame(gui, window_width, window_height)
