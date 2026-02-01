"""GUI 상태 관리."""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any


class ToolMode(Enum):
    """도구 모드 열거형."""
    NAVIGATE = auto()    # 뷰 탐색
    POSITION = auto()    # 객체 배치
    DRILL = auto()       # 드릴링
    MEASURE = auto()     # 측정 (향후)
    IMPLANT = auto()     # 임플란트 배치 (향후)


@dataclass
class CameraState:
    """카메라 상태."""
    distance: float = 200.0
    theta: float = 0.0      # 수평 각도 (도)
    phi: float = 30.0       # 수직 각도 (도)
    target_x: float = 0.0
    target_y: float = 0.0
    target_z: float = 0.0
    fov: float = 60.0

    def zoom(self, delta: float, min_dist: float = 10.0, max_dist: float = 500.0):
        """줌 조절."""
        self.distance = max(min_dist, min(max_dist, self.distance + delta))

    def rotate(self, dtheta: float, dphi: float):
        """카메라 회전."""
        self.theta += dtheta
        self.phi = max(-89.0, min(89.0, self.phi + dphi))


@dataclass
class DrillState:
    """드릴링 상태."""
    radius: float = 2.0
    depth: float = 3.0
    active: bool = False
    volume_initialized: bool = False
    volume_resolution: tuple = (64, 64, 64)
    volume_size: float = 80.0


@dataclass
class EndoscopeState:
    """내시경 상태."""
    move_speed: float = 2.0
    rotate_speed: float = 2.0
    show_pip_view: bool = False


@dataclass
class GUIState:
    """전체 GUI 상태를 관리하는 클래스."""

    # 현재 도구 모드
    tool_mode: ToolMode = ToolMode.NAVIGATE

    # 선택된 객체
    selected_object: Optional[str] = None

    # 하위 상태들
    camera: CameraState = field(default_factory=CameraState)
    drill: DrillState = field(default_factory=DrillState)
    endoscope: EndoscopeState = field(default_factory=EndoscopeState)

    # 마우스 상태
    mouse_down: bool = False
    last_mouse_x: float = 0.0
    last_mouse_y: float = 0.0

    # UI 표시 상태
    show_help: bool = True
    show_stats: bool = False

    # 콜백 함수들 (시뮬레이터 액션과 연결)
    callbacks: Dict[str, Callable] = field(default_factory=dict)

    def set_tool_mode(self, mode: ToolMode):
        """도구 모드 변경."""
        self.tool_mode = mode

    def register_callback(self, name: str, callback: Callable):
        """콜백 함수 등록."""
        self.callbacks[name] = callback

    def trigger_callback(self, name: str, *args, **kwargs) -> Any:
        """콜백 함수 실행."""
        if name in self.callbacks:
            return self.callbacks[name](*args, **kwargs)
        return None
