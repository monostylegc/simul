"""범용 전처리 모듈.

라벨맵 → Scene 변환의 부위 무관 파이프라인.
"""

from .adjacency import find_adjacent_pairs, AdjacencyPair
from .voxel_to_hex import voxels_to_hex_mesh
from .assembly import assemble, AssemblyResult

__all__ = [
    "find_adjacent_pairs",
    "AdjacencyPair",
    "voxels_to_hex_mesh",
    "assemble",
    "AssemblyResult",
]
