"""GUI 매니저 - 패널 관리 및 입력 처리."""

import taichi as ti
import numpy as np
from typing import List, Dict, Any, Optional

from .state import GUIState, ToolMode
from .panels import (
    Panel,
    ToolPanel,
    EndoscopePanel,
    DrillPanel,
    ObjectPanel,
    HelpPanel,
    StatsPanel,
    SelectedObjectPanel,
)
from .endoscope_view import DualViewRenderer, ViewMode


class GUIManager:
    """GUI 매니저 클래스.

    패널들을 관리하고, 입력을 처리하며, 시뮬레이터와 상호작용합니다.
    """

    def __init__(self):
        """GUI 매니저 초기화."""
        self.state = GUIState()
        self.panels: List[Panel] = []

        # 이중 뷰 렌더러 (메인 뷰 + 내시경 뷰)
        self.dual_view = DualViewRenderer()

        # 뷰 전환 쿨다운 (키 반복 방지)
        self._view_toggle_cooldown = 0

        # 기본 패널 등록
        self._init_default_panels()

    def _init_default_panels(self):
        """기본 패널들 초기화."""
        self.panels = [
            ToolPanel(),
            EndoscopePanel(),
            DrillPanel(),
            ObjectPanel(),
            HelpPanel(),
            StatsPanel(),
            SelectedObjectPanel(),
        ]

    def add_panel(self, panel: Panel):
        """패널 추가."""
        self.panels.append(panel)

    def remove_panel(self, name: str):
        """패널 제거."""
        self.panels = [p for p in self.panels if p.name != name]

    def get_panel(self, name: str) -> Optional[Panel]:
        """패널 검색."""
        for panel in self.panels:
            if panel.name == name:
                return panel
        return None

    def render(self, gui, context: Dict[str, Any]):
        """모든 패널 렌더링.

        Args:
            gui: Taichi GUI 객체
            context: 시뮬레이터 컨텍스트 (객체, 내시경 등)
        """
        for panel in self.panels:
            if panel.visible:
                panel.render(gui, self.state, context)

    def handle_mouse(self, window, context: Dict[str, Any]):
        """마우스 입력 처리.

        Args:
            window: Taichi 윈도우
            context: 시뮬레이터 컨텍스트
        """
        mouse = window.get_cursor_pos()

        if window.is_pressed(ti.ui.LMB):
            if self.state.mouse_down:
                # 드래그 중
                dx = (mouse[0] - self.state.last_mouse_x) * 200
                dy = (mouse[1] - self.state.last_mouse_y) * 200

                if self.state.tool_mode == ToolMode.NAVIGATE:
                    self.state.camera.rotate(-dx, dy)

            self.state.mouse_down = True
        else:
            self.state.mouse_down = False

        self.state.last_mouse_x = mouse[0]
        self.state.last_mouse_y = mouse[1]

    def handle_keyboard(self, window, context: Dict[str, Any]):
        """키보드 입력 처리.

        Args:
            window: Taichi 윈도우
            context: 시뮬레이터 컨텍스트
        """
        endoscope = context.get("endoscope")

        # 내시경 이동 (WASD)
        if endoscope is not None:
            speed = self.state.endoscope.move_speed
            rot_speed = self.state.endoscope.rotate_speed

            if window.is_pressed('w'):
                endoscope.move_forward(speed)
            if window.is_pressed('s'):
                endoscope.move_forward(-speed)
            if window.is_pressed('a'):
                endoscope.rotate_yaw(-rot_speed)
            if window.is_pressed('d'):
                endoscope.rotate_yaw(rot_speed)
            if window.is_pressed('q'):
                endoscope.rotate_pitch(-rot_speed)
            if window.is_pressed('e'):
                endoscope.rotate_pitch(rot_speed)

            # 충돌 검사
            collision = context.get("collision")
            if collision is not None:
                endoscope.check_collision(collision)

        # 드릴링 (Space)
        if self.state.tool_mode == ToolMode.DRILL:
            volume = context.get("volume")
            if volume is not None and endoscope is not None:
                if window.is_pressed(ti.ui.SPACE):
                    if not self.state.drill.active:
                        self.state.drill.active = True
                        self.state.trigger_callback(
                            "perform_drilling",
                            endoscope.tip_position,
                            endoscope.direction,
                            self.state.drill.radius,
                            self.state.drill.depth
                        )
                else:
                    self.state.drill.active = False

        # 줌 (+/-)
        if window.is_pressed('=') or window.is_pressed('+'):
            self.state.camera.zoom(-5)
        if window.is_pressed('-'):
            self.state.camera.zoom(5)

        # 도움말 토글 (H)
        if window.is_pressed('h'):
            self.state.show_help = not self.state.show_help

        # 통계 토글 (Tab)
        if window.is_pressed(ti.ui.TAB):
            self.state.show_stats = not self.state.show_stats

        # 뷰 모드 전환 (V)
        if self._view_toggle_cooldown > 0:
            self._view_toggle_cooldown -= 1
        if window.is_pressed('v') and self._view_toggle_cooldown == 0:
            self.dual_view.toggle_view()
            self._view_toggle_cooldown = 15  # 쿨다운 프레임

    def handle_input(self, window, context: Dict[str, Any]):
        """모든 입력 처리.

        Args:
            window: Taichi 윈도우
            context: 시뮬레이터 컨텍스트
        """
        self.handle_mouse(window, context)
        self.handle_keyboard(window, context)

    def get_camera_position(self) -> np.ndarray:
        """카메라 위치 계산."""
        cam = self.state.camera
        theta = np.radians(cam.theta)
        phi = np.radians(cam.phi)

        x = cam.distance * np.cos(phi) * np.sin(theta)
        y = cam.distance * np.sin(phi)
        z = cam.distance * np.cos(phi) * np.cos(theta)

        target = np.array([cam.target_x, cam.target_y, cam.target_z])
        return target + np.array([x, y, z])

    def get_camera_target(self) -> np.ndarray:
        """카메라 타겟 위치."""
        cam = self.state.camera
        return np.array([cam.target_x, cam.target_y, cam.target_z])

    def setup_camera(self, camera: ti.ui.Camera, endoscope=None):
        """Taichi 카메라 설정.

        Args:
            camera: Taichi UI 카메라
            endoscope: 내시경 객체 (내시경 뷰용)
        """
        cam_pos = self.get_camera_position()
        cam_target = self.get_camera_target()

        if endoscope is not None:
            self.dual_view.setup_camera(
                camera,
                cam_pos,
                cam_target,
                endoscope,
                self.state.camera.fov
            )
        else:
            camera.position(*cam_pos)
            camera.lookat(*cam_target)
            camera.up(0, 1, 0)
            camera.fov(self.state.camera.fov)

    def setup_lighting(self, scene: ti.ui.Scene, endoscope=None):
        """씬 조명 설정.

        Args:
            scene: Taichi 씬
            endoscope: 내시경 객체 (내시경 뷰용)
        """
        cam_pos = self.get_camera_position()
        light_pos = cam_pos + np.array([50, 100, 50])

        if endoscope is not None:
            self.dual_view.setup_lighting(scene, light_pos, endoscope)
        else:
            scene.ambient_light((0.3, 0.3, 0.3))
            scene.point_light(pos=tuple(light_pos), color=(1, 1, 1))

    def get_view_mode_name(self) -> str:
        """현재 뷰 모드 이름."""
        return self.dual_view.endoscope_view.get_view_mode_name()
