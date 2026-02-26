"""부위별 해부학 특화 모듈.

AnatomyProfile 인터페이스를 통해 부위별 재료 물성,
접촉 규칙, 특수 구조 검출 로직을 캡슐화한다.
"""

from .base import AnatomyProfile, MaterialProps
from .spine import SpineProfile, FacetJoint

__all__ = [
    "AnatomyProfile",
    "MaterialProps",
    "SpineProfile",
    "FacetJoint",
]
