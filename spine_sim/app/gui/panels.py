"""GUI 패널 컴포넌트."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING
from .state import GUIState, ToolMode

if TYPE_CHECKING:
    pass  # 타입 힌트용 임포트


class Panel(ABC):
    """패널 베이스 클래스."""

    def __init__(self, name: str, x: float, y: float, width: float, height: float):
        """패널 초기화.

        Args:
            name: 패널 제목
            x, y: 화면 내 위치 (0~1 비율)
            width, height: 크기 (0~1 비율)
        """
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.visible = True

    @abstractmethod
    def render(self, gui, state: GUIState, context: Dict[str, Any]):
        """패널 렌더링.

        Args:
            gui: Taichi GUI 객체
            state: GUI 상태
            context: 추가 컨텍스트 (시뮬레이터 데이터 등)
        """
        pass


class ToolPanel(Panel):
    """도구 선택 패널."""

    def __init__(self):
        super().__init__("Tools", x=0.01, y=0.01, width=0.18, height=0.20)

    def render(self, gui, state: GUIState, context: Dict[str, Any]):
        with gui.sub_window(self.name, self.x, self.y, self.width, self.height) as w:
            w.text("Tool Mode")
            w.text("")

            # 도구 버튼들
            tools = [
                (ToolMode.NAVIGATE, "Navigate", "View navigation"),
                (ToolMode.POSITION, "Position", "Object placement"),
                (ToolMode.DRILL, "Drill", "Surgical drilling"),
            ]

            for mode, label, tooltip in tools:
                is_active = state.tool_mode == mode
                button_label = f"[{label}]" if is_active else f" {label} "
                if w.button(button_label):
                    state.set_tool_mode(mode)

            w.text("")
            w.text(f"Active: {state.tool_mode.name}")


class EndoscopePanel(Panel):
    """내시경 정보 패널."""

    def __init__(self):
        super().__init__("Endoscope", x=0.01, y=0.22, width=0.18, height=0.20)

    def render(self, gui, state: GUIState, context: Dict[str, Any]):
        endoscope = context.get("endoscope")
        if endoscope is None:
            return

        view_mode_name = context.get("view_mode_name", "Main View")

        with gui.sub_window(self.name, self.x, self.y, self.width, self.height) as w:
            w.text("Endoscope")
            w.text("")

            # 위치 표시
            pos = endoscope.tip_position
            w.text(f"X: {pos[0]:.1f}")
            w.text(f"Y: {pos[1]:.1f}")
            w.text(f"Z: {pos[2]:.1f}")

            # 충돌 상태
            if endoscope.is_colliding:
                w.text("!! COLLISION !!")

            # 현재 뷰 모드
            w.text("")
            w.text(f"View: {view_mode_name}")
            w.text("Press V to toggle")


class DrillPanel(Panel):
    """드릴링 설정 패널."""

    def __init__(self):
        super().__init__("Drilling", x=0.01, y=0.41, width=0.18, height=0.22)

    def render(self, gui, state: GUIState, context: Dict[str, Any]):
        # 드릴 모드일 때만 표시
        if state.tool_mode != ToolMode.DRILL:
            return

        volume = context.get("volume")

        with gui.sub_window(self.name, self.x, self.y, self.width, self.height) as w:
            w.text("Drill Settings")
            w.text("")

            # 드릴 반지름
            state.drill.radius = w.slider_float(
                "Radius",
                state.drill.radius,
                0.5, 5.0
            )

            # 드릴 깊이
            state.drill.depth = w.slider_float(
                "Depth",
                state.drill.depth,
                1.0, 10.0
            )

            w.text("")

            # 볼륨 초기화
            if volume is None:
                if w.button("Init Volume"):
                    state.trigger_callback("init_drilling_volume")
            else:
                res = state.drill.volume_resolution
                w.text(f"Volume: {res[0]}x{res[1]}x{res[2]}")

                # 드릴링 상태
                if state.drill.active:
                    w.text(">> DRILLING <<")
                else:
                    w.text("Press SPACE to drill")


class ObjectPanel(Panel):
    """씬 객체 목록 패널."""

    def __init__(self):
        super().__init__("Objects", x=0.01, y=0.64, width=0.18, height=0.20)

    def render(self, gui, state: GUIState, context: Dict[str, Any]):
        objects = context.get("objects", {})

        with gui.sub_window(self.name, self.x, self.y, self.width, self.height) as w:
            w.text("Scene Objects")
            w.text("")

            # 객체 목록
            for name, obj in objects.items():
                is_selected = name == state.selected_object
                prefix = ">" if is_selected else " "
                visible_mark = "O" if obj.visible else "X"

                if w.button(f"{prefix} [{visible_mark}] {name}"):
                    if state.selected_object == name:
                        # 이미 선택된 경우 가시성 토글
                        obj.visible = not obj.visible
                    else:
                        state.selected_object = name

            w.text("")

            # 객체 추가 버튼
            if w.button("+ Add Vertebra"):
                state.trigger_callback("add_vertebra")


class HelpPanel(Panel):
    """도움말 패널."""

    def __init__(self):
        super().__init__("Help", x=0.01, y=0.85, width=0.18, height=0.14)

    def render(self, gui, state: GUIState, context: Dict[str, Any]):
        if not state.show_help:
            return

        with gui.sub_window(self.name, self.x, self.y, self.width, self.height) as w:
            w.text("Controls")
            w.text("Drag: Rotate view")
            w.text("+/-: Zoom")
            w.text("WASD: Move scope")
            w.text("Q/E: Rotate scope")
            w.text("Space: Drill")
            w.text("V: Toggle view")


class StatsPanel(Panel):
    """통계 정보 패널 (디버그용)."""

    def __init__(self):
        super().__init__("Stats", x=0.80, y=0.01, width=0.19, height=0.15)

    def render(self, gui, state: GUIState, context: Dict[str, Any]):
        if not state.show_stats:
            return

        with gui.sub_window(self.name, self.x, self.y, self.width, self.height) as w:
            w.text("Statistics")
            w.text("")

            n_verts = context.get("n_vertices", 0)
            n_tris = context.get("n_triangles", 0)
            fps = context.get("fps", 0)

            w.text(f"Vertices: {n_verts}")
            w.text(f"Triangles: {n_tris}")
            w.text(f"FPS: {fps:.1f}")


class SelectedObjectPanel(Panel):
    """선택된 객체 상세 정보 패널."""

    def __init__(self):
        super().__init__("Selected", x=0.80, y=0.17, width=0.19, height=0.25)

    def render(self, gui, state: GUIState, context: Dict[str, Any]):
        if state.selected_object is None:
            return

        objects = context.get("objects", {})
        obj = objects.get(state.selected_object)
        if obj is None:
            return

        with gui.sub_window(self.name, self.x, self.y, self.width, self.height) as w:
            w.text(f"Object: {state.selected_object}")
            w.text("")

            # 위치
            pos = obj.mesh.transform.position
            w.text(f"Position:")
            w.text(f"  X: {pos[0]:.1f}")
            w.text(f"  Y: {pos[1]:.1f}")
            w.text(f"  Z: {pos[2]:.1f}")

            w.text("")

            # 메쉬 정보
            w.text(f"Vertices: {obj.mesh.n_vertices}")
            w.text(f"Faces: {obj.mesh.n_faces}")

            # 가시성
            w.text("")
            visible_text = "Visible" if obj.visible else "Hidden"
            if w.button(f"[{visible_text}]"):
                obj.visible = not obj.visible
                state.trigger_callback("update_render_data")
