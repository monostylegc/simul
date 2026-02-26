"""NRRD/NIFTI 볼륨 로더 모듈.

3D Slicer에서 생성한 CT 볼륨 및 세그멘테이션 labelmap을 VoxelVolume으로 로딩합니다.
"""

import numpy as np
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

try:
    import SimpleITK as sitk
except ImportError:
    sitk = None


@dataclass
class VolumeMetadata:
    """볼륨 메타데이터.

    Attributes:
        origin: 볼륨 원점 좌표 (x, y, z)
        spacing: 복셀 간격 (sx, sy, sz)
        direction: 3x3 방향 행렬
        size: 볼륨 크기 (nx, ny, nz)
    """
    origin: Tuple[float, float, float]
    spacing: Tuple[float, float, float]
    direction: Tuple[Tuple[float, ...], ...]
    size: Tuple[int, int, int]

    @property
    def is_isotropic(self) -> bool:
        """등방성 spacing 여부 확인."""
        tol = 0.01  # 1% 허용 오차
        sx, sy, sz = self.spacing
        mean_spacing = (sx + sy + sz) / 3
        return (abs(sx - mean_spacing) / mean_spacing < tol and
                abs(sy - mean_spacing) / mean_spacing < tol and
                abs(sz - mean_spacing) / mean_spacing < tol)

    @property
    def min_spacing(self) -> float:
        """최소 spacing 반환."""
        return min(self.spacing)


class VolumeLoader:
    """NRRD/NIFTI 볼륨 로더.

    SimpleITK를 사용하여 다양한 의료 영상 형식을 지원합니다.
    - NRRD (.nrrd, .nhdr)
    - NIFTI (.nii, .nii.gz)
    - MetaImage (.mha, .mhd)
    """

    # 기본 Label → Material 매핑
    # 0=empty, 1=bone, 2=disc, 3=soft tissue
    DEFAULT_LABEL_MAPPING = {
        0: 0,   # 배경 → empty
        1: 1,   # 뼈 → bone
        2: 2,   # 디스크 → disc
        3: 3,   # 연조직 → soft tissue
    }

    SUPPORTED_EXTENSIONS = {'.nrrd', '.nhdr', '.nii', '.nii.gz', '.mha', '.mhd'}

    @staticmethod
    def _check_sitk():
        """SimpleITK 설치 확인."""
        if sitk is None:
            raise ImportError(
                "SimpleITK가 설치되지 않았습니다. "
                "'pip install SimpleITK' 또는 'uv add SimpleITK'로 설치하세요."
            )

    @classmethod
    def load(
        cls,
        filepath: Union[str, Path],
        max_resolution: Optional[int] = None
    ) -> Tuple[np.ndarray, "VolumeMetadata"]:
        """볼륨 파일 로드.

        Args:
            filepath: NRRD/NIFTI 파일 경로
            max_resolution: 최대 해상도 (초과 시 다운샘플링)

        Returns:
            (data, metadata) 튜플
            - data: (nx, ny, nz) numpy 배열 (x, y, z 순서)
            - metadata: VolumeMetadata 객체
        """
        cls._check_sitk()

        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")

        # SimpleITK로 이미지 로드
        image = sitk.ReadImage(str(filepath))

        # 메타데이터 추출
        metadata = cls._extract_metadata(image)

        # 비등방성 spacing 경고
        if not metadata.is_isotropic:
            warnings.warn(
                f"비등방성 spacing 감지: {metadata.spacing}. "
                f"최소값 {metadata.min_spacing:.3f}을 사용합니다.",
                UserWarning
            )

        # numpy 배열로 변환 (SimpleITK는 z,y,x 순서)
        data = sitk.GetArrayFromImage(image)

        # 축 순서 변환: [z,y,x] → [x,y,z]
        data = np.transpose(data, (2, 1, 0))

        # 다운샘플링 (필요시)
        if max_resolution is not None:
            data, metadata = cls._downsample(data, metadata, max_resolution)

        return data, metadata

    @classmethod
    def load_labelmap(
        cls,
        filepath: Union[str, Path],
        label_mapping: Optional[Dict[int, int]] = None,
        max_resolution: Optional[int] = None
    ) -> Tuple[np.ndarray, np.ndarray, "VolumeMetadata"]:
        """세그멘테이션 labelmap 로드.

        Args:
            filepath: Labelmap 파일 경로
            label_mapping: label → material 매핑 딕셔너리
            max_resolution: 최대 해상도

        Returns:
            (density, material, metadata) 튜플
            - density: 밀도 배열 (0.0 또는 1.0)
            - material: 재료 타입 배열
            - metadata: VolumeMetadata 객체
        """
        cls._check_sitk()

        if label_mapping is None:
            label_mapping = cls.DEFAULT_LABEL_MAPPING

        # 볼륨 로드
        data, metadata = cls.load(filepath, max_resolution)

        # 정수형으로 변환
        labels = data.astype(np.int32)

        # 밀도 배열: label이 0이 아니면 1.0
        density = np.where(labels > 0, 1.0, 0.0).astype(np.float32)

        # 재료 배열: label → material 매핑
        material = np.zeros_like(labels, dtype=np.int32)
        for label, mat in label_mapping.items():
            material[labels == label] = mat

        return density, material, metadata

    @classmethod
    def save_nrrd(
        cls,
        filepath: Union[str, Path],
        data: np.ndarray,
        origin: Tuple[float, float, float] = (0, 0, 0),
        spacing: float = 1.0
    ):
        """NRRD 형식으로 저장.

        Args:
            filepath: 저장할 파일 경로
            data: (nx, ny, nz) numpy 배열
            origin: 원점 좌표
            spacing: 복셀 간격
        """
        cls._check_sitk()

        filepath = Path(filepath)

        # 축 순서 변환: [x,y,z] → [z,y,x]
        data_sitk = np.transpose(data, (2, 1, 0))

        # SimpleITK 이미지 생성
        image = sitk.GetImageFromArray(data_sitk)

        # 메타데이터 설정
        image.SetOrigin(origin)
        image.SetSpacing((spacing, spacing, spacing))

        # 저장
        sitk.WriteImage(image, str(filepath))

    @classmethod
    def _extract_metadata(cls, image) -> "VolumeMetadata":
        """SimpleITK 이미지에서 메타데이터 추출.

        Args:
            image: SimpleITK Image 객체

        Returns:
            VolumeMetadata 객체
        """
        # SimpleITK는 (x, y, z) 순서로 반환
        origin = image.GetOrigin()
        spacing = image.GetSpacing()
        direction = image.GetDirection()

        # GetSize()는 (x, y, z) 순서
        size = image.GetSize()

        # direction은 9개 원소의 flat tuple → 3x3 행렬
        dir_matrix = tuple(
            tuple(direction[i*3:(i+1)*3]) for i in range(3)
        )

        return VolumeMetadata(
            origin=origin,
            spacing=spacing,
            direction=dir_matrix,
            size=size
        )

    @classmethod
    def _downsample(
        cls,
        data: np.ndarray,
        metadata: "VolumeMetadata",
        max_resolution: int
    ) -> Tuple[np.ndarray, "VolumeMetadata"]:
        """볼륨 다운샘플링.

        가장 큰 차원이 max_resolution을 초과하면 다운샘플링합니다.

        Args:
            data: 원본 데이터
            metadata: 원본 메타데이터
            max_resolution: 최대 해상도

        Returns:
            (downsampled_data, updated_metadata) 튜플
        """
        current_max = max(data.shape)

        if current_max <= max_resolution:
            return data, metadata

        # 다운샘플링 비율 계산
        factor = current_max / max_resolution

        # scipy의 zoom을 사용한 다운샘플링
        from scipy.ndimage import zoom

        zoom_factor = 1.0 / factor
        downsampled = zoom(data, zoom_factor, order=1)  # 선형 보간

        # 새 spacing 계산
        new_spacing = tuple(s * factor for s in metadata.spacing)
        new_size = downsampled.shape

        new_metadata = VolumeMetadata(
            origin=metadata.origin,
            spacing=new_spacing,
            direction=metadata.direction,
            size=new_size
        )

        return downsampled, new_metadata
