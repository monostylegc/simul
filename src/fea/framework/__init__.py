"""구조 해석 프레임워크.

FEM과 Peridynamics를 통합하는 고수준 API.

사용 예시:
    from spine_sim.analysis.framework import SpineAnalysis

    # 해석 객체 생성
    analysis = SpineAnalysis()

    # STL 로드
    analysis.load_stl("L4.stl", name="L4", material="bone")
    analysis.load_stl("disc.stl", name="disc", material="disc")
    analysis.load_stl("L5.stl", name="L5", material="bone")

    # 경계 조건
    analysis.fix_bottom()
    analysis.apply_load(top=True, force=-3000)  # N

    # 해석 실행
    result = analysis.solve(method="fem")  # 또는 "pd"

    # 시각화
    result.plot()
    result.save("result.png")
"""

from .analysis import SpineAnalysis, AnalysisResult
from .materials import MaterialLibrary
from .mesh import MeshGenerator

__all__ = [
    "SpineAnalysis",
    "AnalysisResult",
    "MaterialLibrary",
    "MeshGenerator",
]
