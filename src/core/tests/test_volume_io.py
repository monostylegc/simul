"""VolumeLoader 및 VoxelVolume I/O 테스트."""

import pytest
import numpy as np
import tempfile
import warnings
from pathlib import Path

# SimpleITK 설치 여부 확인
try:
    import SimpleITK as sitk
    HAS_SITK = True
except ImportError:
    HAS_SITK = False


pytestmark = pytest.mark.skipif(not HAS_SITK, reason="SimpleITK 미설치")


@pytest.fixture
def sample_nrrd_file():
    """테스트용 NRRD 파일 생성."""
    with tempfile.NamedTemporaryFile(suffix=".nrrd", delete=False) as f:
        filepath = Path(f.name)

    # 간단한 3D 볼륨 생성
    data = np.zeros((32, 32, 32), dtype=np.float32)
    # 중앙에 구 형태
    for i in range(32):
        for j in range(32):
            for k in range(32):
                dist = np.sqrt((i-16)**2 + (j-16)**2 + (k-16)**2)
                if dist < 10:
                    data[i, j, k] = 1.0

    # [x,y,z] -> [z,y,x] 변환 (SimpleITK 형식)
    data_sitk = np.transpose(data, (2, 1, 0))

    image = sitk.GetImageFromArray(data_sitk)
    image.SetOrigin((0.0, 0.0, 0.0))
    image.SetSpacing((1.0, 1.0, 1.0))
    sitk.WriteImage(image, str(filepath))

    yield filepath

    # 정리
    filepath.unlink(missing_ok=True)


@pytest.fixture
def sample_labelmap_file():
    """테스트용 Labelmap 파일 생성."""
    with tempfile.NamedTemporaryFile(suffix=".nrrd", delete=False) as f:
        filepath = Path(f.name)

    # 라벨 데이터 생성
    data = np.zeros((32, 32, 32), dtype=np.int32)
    # 뼈 (label=1)
    data[10:22, 10:22, 10:22] = 1
    # 디스크 (label=2)
    data[14:18, 14:18, 14:18] = 2

    # [x,y,z] -> [z,y,x] 변환
    data_sitk = np.transpose(data, (2, 1, 0))

    image = sitk.GetImageFromArray(data_sitk.astype(np.int16))
    image.SetOrigin((-16.0, -16.0, -16.0))
    image.SetSpacing((1.0, 1.0, 1.0))
    sitk.WriteImage(image, str(filepath))

    yield filepath

    filepath.unlink(missing_ok=True)


@pytest.fixture
def anisotropic_nrrd_file():
    """비등방성 spacing을 가진 NRRD 파일 생성."""
    with tempfile.NamedTemporaryFile(suffix=".nrrd", delete=False) as f:
        filepath = Path(f.name)

    data = np.ones((20, 20, 40), dtype=np.float32)
    data_sitk = np.transpose(data, (2, 1, 0))

    image = sitk.GetImageFromArray(data_sitk)
    image.SetOrigin((0.0, 0.0, 0.0))
    # 비등방성 spacing: x=1, y=1, z=2
    image.SetSpacing((1.0, 1.0, 2.0))
    sitk.WriteImage(image, str(filepath))

    yield filepath

    filepath.unlink(missing_ok=True)


class TestVolumeLoader:
    """VolumeLoader 클래스 테스트."""

    def test_load_nrrd(self, sample_nrrd_file):
        """NRRD 파일 로드 테스트."""
        from src.core.volume_io import VolumeLoader

        data, metadata = VolumeLoader.load(sample_nrrd_file)

        # 축 순서 변환 확인 (x, y, z)
        assert data.shape == (32, 32, 32)
        assert metadata.origin == (0.0, 0.0, 0.0)
        assert metadata.spacing == (1.0, 1.0, 1.0)
        assert metadata.is_isotropic

        # 구가 올바르게 로드되었는지 확인
        assert data[16, 16, 16] == 1.0  # 중심
        assert data[0, 0, 0] == 0.0  # 모서리

    def test_load_labelmap(self, sample_labelmap_file):
        """Labelmap 로드 테스트."""
        from src.core.volume_io import VolumeLoader

        density, material, metadata = VolumeLoader.load_labelmap(sample_labelmap_file)

        # 밀도 확인
        assert density.shape == (32, 32, 32)
        assert density[16, 16, 16] == 1.0  # 디스크 영역
        assert density[0, 0, 0] == 0.0  # 배경

        # 재료 매핑 확인
        assert material[16, 16, 16] == 2  # 디스크
        assert material[10, 10, 10] == 1  # 뼈
        assert material[0, 0, 0] == 0  # empty

    def test_anisotropic_spacing_warning(self, anisotropic_nrrd_file):
        """비등방성 spacing 경고 테스트."""
        from src.core.volume_io import VolumeLoader

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            data, metadata = VolumeLoader.load(anisotropic_nrrd_file)

            # 경고 발생 확인
            assert len(w) == 1
            assert "비등방성" in str(w[0].message)

        # 최소 spacing 확인
        assert metadata.min_spacing == 1.0

    def test_save_and_reload(self, sample_nrrd_file):
        """저장 및 재로드 테스트."""
        from src.core.volume_io import VolumeLoader

        # 원본 로드
        data_orig, metadata_orig = VolumeLoader.load(sample_nrrd_file)

        # 임시 파일에 저장
        with tempfile.NamedTemporaryFile(suffix=".nrrd", delete=False) as f:
            save_path = Path(f.name)

        try:
            VolumeLoader.save_nrrd(save_path, data_orig)

            # 재로드
            data_reload, metadata_reload = VolumeLoader.load(save_path)

            # 데이터 일치 확인
            np.testing.assert_array_almost_equal(data_orig, data_reload)
        finally:
            save_path.unlink(missing_ok=True)

    def test_downsampling(self, sample_nrrd_file):
        """다운샘플링 테스트."""
        from src.core.volume_io import VolumeLoader

        # 원본 해상도보다 작게 요청
        data, metadata = VolumeLoader.load(sample_nrrd_file, max_resolution=16)

        # 다운샘플링 확인
        assert max(data.shape) <= 16

        # 새 spacing 확인 (약 2배)
        assert metadata.min_spacing >= 1.5


class TestVoxelVolumeIO:
    """VoxelVolume I/O 메서드 테스트."""

    def test_voxel_volume_load(self, sample_nrrd_file):
        """VoxelVolume.load() 테스트."""
        import taichi as ti
        ti.init(arch=ti.cpu, offline_cache=False)

        from src.core.volume import VoxelVolume

        volume = VoxelVolume.load(sample_nrrd_file)

        assert volume.nx == 32
        assert volume.ny == 32
        assert volume.nz == 32

        # 데이터 확인
        data = volume.to_numpy()
        assert data.max() > 0

    def test_voxel_volume_load_labelmap(self, sample_labelmap_file):
        """VoxelVolume.load_labelmap() 테스트."""
        import taichi as ti
        ti.init(arch=ti.cpu, offline_cache=False)

        from src.core.volume import VoxelVolume

        volume = VoxelVolume.load_labelmap(sample_labelmap_file)

        # 재료 확인
        material = volume.material.to_numpy()
        assert 1 in material  # 뼈
        assert 2 in material  # 디스크

    def test_voxel_volume_save_nrrd(self, sample_nrrd_file):
        """VoxelVolume.save_nrrd() 테스트."""
        import taichi as ti
        ti.init(arch=ti.cpu, offline_cache=False)

        from src.core.volume import VoxelVolume

        # 로드
        volume = VoxelVolume.load(sample_nrrd_file)

        # 저장
        with tempfile.NamedTemporaryFile(suffix=".nrrd", delete=False) as f:
            save_path = Path(f.name)

        try:
            volume.save_nrrd(save_path)

            # 재로드하여 확인
            volume2 = VoxelVolume.load(save_path)

            np.testing.assert_array_almost_equal(
                volume.to_numpy(),
                volume2.to_numpy(),
                decimal=5
            )
        finally:
            save_path.unlink(missing_ok=True)


class TestVolumeMetadata:
    """VolumeMetadata 테스트."""

    def test_is_isotropic(self):
        """등방성 확인 테스트."""
        from src.core.volume_io import VolumeMetadata

        # 등방성
        meta1 = VolumeMetadata(
            origin=(0, 0, 0),
            spacing=(1.0, 1.0, 1.0),
            direction=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
            size=(32, 32, 32)
        )
        assert meta1.is_isotropic

        # 비등방성
        meta2 = VolumeMetadata(
            origin=(0, 0, 0),
            spacing=(1.0, 1.0, 2.0),
            direction=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
            size=(32, 32, 32)
        )
        assert not meta2.is_isotropic

    def test_min_spacing(self):
        """최소 spacing 테스트."""
        from src.core.volume_io import VolumeMetadata

        meta = VolumeMetadata(
            origin=(0, 0, 0),
            spacing=(1.5, 1.0, 2.0),
            direction=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
            size=(32, 32, 32)
        )
        assert meta.min_spacing == 1.0
