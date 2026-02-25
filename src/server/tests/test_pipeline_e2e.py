"""DICOM 파이프라인 End-to-End 테스트.

합성 DICOM 데이터를 생성하여 전체 파이프라인(DICOM → NIfTI → 메쉬 추출)을 검증.
세그멘테이션은 실제 AI 모델이 필요하므로 합성 라벨맵으로 대체.
"""

import numpy as np
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestDicomToNiftiE2E:
    """1단계: 합성 DICOM → NIfTI 변환 E2E 테스트."""

    def _create_synthetic_dicom(self, output_dir: Path, n_slices: int = 10):
        """SimpleITK로 합성 DICOM 시리즈 생성.

        척추 뼈 구조를 모방한 간단한 볼륨:
        - 중심에 고밀도 원통 (뼈)
        - 원통 위아래에 저밀도 영역 (디스크)
        """
        import SimpleITK as sitk

        # 64x64x(n_slices) 볼륨 생성
        size = (64, 64, n_slices)
        image = sitk.Image(size, sitk.sitkInt16)
        image.SetSpacing((1.0, 1.0, 2.0))
        image.SetOrigin((0.0, 0.0, 0.0))

        # 뼈 영역: 중심 원통 (HU ≈ 700)
        arr = sitk.GetArrayFromImage(image)  # (z, y, x)
        for z in range(n_slices):
            for y in range(64):
                for x in range(64):
                    dist = ((x - 32) ** 2 + (y - 32) ** 2) ** 0.5
                    if dist < 15:
                        arr[z, y, x] = 700   # 뼈
                    elif dist < 20:
                        arr[z, y, x] = 200   # 연조직
                    else:
                        arr[z, y, x] = -100   # 공기/배경

        volume = sitk.GetImageFromArray(arr)
        volume.SetSpacing(image.GetSpacing())
        volume.SetOrigin(image.GetOrigin())

        # DICOM 시리즈로 저장
        output_dir.mkdir(parents=True, exist_ok=True)

        writer = sitk.ImageFileWriter()
        writer.KeepOriginalImageUIDOn()

        # 슬라이스별 DICOM 파일 생성
        modification_time = "120000"
        modification_date = "20260225"

        for i in range(volume.GetDepth()):
            image_slice = volume[:, :, i]

            # DICOM 메타데이터 설정
            image_slice.SetMetaData("0008|0060", "CT")           # Modality
            image_slice.SetMetaData("0008|0020", modification_date)  # StudyDate
            image_slice.SetMetaData("0008|0031", modification_time)  # SeriesTime
            image_slice.SetMetaData("0010|0010", "TestPatient")  # PatientName
            image_slice.SetMetaData("0010|0020", "TEST001")      # PatientID
            image_slice.SetMetaData("0020|000e",
                "1.2.826.0.1.3680043.2.1125.1.12345")           # SeriesInstanceUID
            image_slice.SetMetaData("0020|0013", str(i))         # InstanceNumber

            writer.SetFileName(str(output_dir / f"slice_{i:04d}.dcm"))
            writer.Execute(image_slice)

        return volume

    def test_synthetic_dicom_creation(self, tmp_path):
        """합성 DICOM 파일 생성 확인."""
        dicom_dir = tmp_path / "dicom"
        self._create_synthetic_dicom(dicom_dir, n_slices=10)

        dcm_files = list(dicom_dir.glob("*.dcm"))
        assert len(dcm_files) == 10, f"DICOM 파일 {len(dcm_files)}개 (예상: 10)"

    def test_dicom_to_nifti_conversion(self, tmp_path):
        """DICOM → NIfTI 변환 E2E."""
        dicom_dir = tmp_path / "dicom"
        self._create_synthetic_dicom(dicom_dir, n_slices=20)

        from src.server.services.dicom_convert import convert_dicom_to_nifti

        # 진행률 콜백 추적
        progress_msgs = []
        def cb(step, detail):
            progress_msgs.append((step, detail.get("message", "")))

        result = convert_dicom_to_nifti(
            str(dicom_dir),
            str(tmp_path / "output.nii.gz"),
            progress_callback=cb,
        )

        # 결과 검증
        assert Path(result["nifti_path"]).exists(), "NIfTI 파일이 생성되어야 함"
        assert result["n_slices"] == 20
        # DICOM 슬라이스 간격은 SimpleITK가 자동 계산 (정확한 값은 가변적)
        assert len(result["spacing"]) == 3
        assert result["size"][0] == 64  # X
        assert result["size"][1] == 64  # Y
        assert result["size"][2] == 20  # Z

        # 환자 정보
        pi = result.get("patient_info", {})
        assert pi.get("modality") == "CT"
        assert pi.get("patient_id") == "TEST001"

        # 콜백이 호출되었는지
        assert len(progress_msgs) >= 3

    def test_nifti_content_matches(self, tmp_path):
        """변환된 NIfTI 내용이 원본과 일치하는지 확인."""
        import SimpleITK as sitk

        dicom_dir = tmp_path / "dicom"
        self._create_synthetic_dicom(dicom_dir, n_slices=10)

        from src.server.services.dicom_convert import convert_dicom_to_nifti
        result = convert_dicom_to_nifti(str(dicom_dir), str(tmp_path / "out.nii.gz"))

        # NIfTI 다시 읽기
        nifti_img = sitk.ReadImage(result["nifti_path"])
        arr = sitk.GetArrayFromImage(nifti_img)

        # 중심 복셀이 뼈 (700) 값을 가지는지 확인
        center_val = arr[5, 32, 32]  # (z, y, x)
        assert center_val > 500, f"중심 복셀 값 {center_val}, 뼈(700) 기대"

        # 가장자리가 공기/배경인지 확인
        edge_val = arr[5, 0, 0]
        assert edge_val < 0, f"가장자리 복셀 값 {edge_val}, 공기(-100) 기대"


class TestLabelMapToMeshE2E:
    """3단계: 합성 라벨맵 → 메쉬 추출 E2E 테스트."""

    @pytest.fixture
    def spine_labelmap(self, tmp_path):
        """척추 구조를 모방한 합성 라벨맵 (NIfTI)."""
        import SimpleITK as sitk

        # 64x64x64 볼륨
        labels = np.zeros((64, 64, 64), dtype=np.int16)

        # L4 척추체 (label=123): 중심 상단 블록
        labels[35:55, 20:44, 20:44] = 123

        # L5 척추체 (label=124): 중심 하단 블록
        labels[8:28, 20:44, 20:44] = 124

        # L4-L5 디스크 (label=222): 중간 층
        labels[28:35, 22:42, 22:42] = 222

        # NIfTI로 저장
        img = sitk.GetImageFromArray(labels)
        img.SetSpacing((1.0, 1.0, 1.0))
        img.SetOrigin((0.0, 0.0, 0.0))

        nifti_path = tmp_path / "labels_standard.nii.gz"
        sitk.WriteImage(img, str(nifti_path))

        return str(nifti_path)

    def test_mesh_extraction_from_labelmap(self, spine_labelmap):
        """라벨맵에서 메쉬 추출 E2E."""
        from src.server.services.mesh_extract import extract_meshes
        from src.server.models import MeshExtractRequest

        request = MeshExtractRequest(
            labels_path=spine_labelmap,
            smooth=True,
            resolution=64,
        )

        progress_msgs = []
        def cb(step, detail):
            progress_msgs.append((step, detail.get("message", "")))

        result = extract_meshes(request, progress_callback=cb)

        # 3개 구조물이 추출되어야 함
        assert len(result["meshes"]) == 3, f"메쉬 {len(result['meshes'])}개 (예상: 3)"

        # 각 메쉬 검증
        names = {m["name"] for m in result["meshes"]}
        assert "L4" in names, "L4 메쉬가 있어야 함"
        assert "L5" in names, "L5 메쉬가 있어야 함"

        for m in result["meshes"]:
            # 필수 필드 확인
            assert m["n_vertices"] > 0, f"{m['name']} 정점이 없음"
            assert m["n_faces"] > 0, f"{m['name']} 면이 없음"
            # base64 인코딩 필드 확인
            assert "vertices_b64" in m, f"{m['name']} vertices_b64 필드 없음"
            assert "faces_b64" in m, f"{m['name']} faces_b64 필드 없음"
            assert isinstance(m["vertices_b64"], str), "vertices_b64는 문자열이어야 함"
            assert isinstance(m["faces_b64"], str), "faces_b64는 문자열이어야 함"
            # base64 디코딩 후 크기 검증
            import base64
            verts_bytes = base64.b64decode(m["vertices_b64"])
            faces_bytes = base64.b64decode(m["faces_b64"])
            assert len(verts_bytes) == m["n_vertices"] * 3 * 4, "vertices_b64 크기 불일치 (float32)"
            assert len(faces_bytes) == m["n_faces"] * 3 * 4, "faces_b64 크기 불일치 (int32)"
            assert m["color"].startswith("#"), f"{m['name']} 색상 형식 오류"
            assert "bounds" in m
            assert "min" in m["bounds"] and "max" in m["bounds"]

        # 재료 타입 확인
        mat_types = {m["name"]: m["material_type"] for m in result["meshes"]}
        # SpineLabel 120, 121 → bone, 218 → disc
        bone_names = [n for n, mt in mat_types.items() if mt == "bone"]
        disc_names = [n for n, mt in mat_types.items() if mt == "disc"]
        assert len(bone_names) >= 2, f"뼈 메쉬 {len(bone_names)}개 (예상: >= 2)"

    def test_mesh_extraction_selected_labels(self, spine_labelmap):
        """특정 라벨만 선택 추출."""
        from src.server.services.mesh_extract import extract_meshes
        from src.server.models import MeshExtractRequest

        request = MeshExtractRequest(
            labels_path=spine_labelmap,
            selected_labels=[123],  # L4만
            smooth=False,
        )
        result = extract_meshes(request)

        assert len(result["meshes"]) == 1
        assert result["meshes"][0]["label"] == 123

    def test_mesh_vertex_data_serializable(self, spine_labelmap):
        """메쉬 데이터가 JSON 직렬화 가능한지 확인 (WebSocket 전송용)."""
        import json
        import base64
        from src.server.services.mesh_extract import extract_meshes
        from src.server.models import MeshExtractRequest

        request = MeshExtractRequest(
            labels_path=spine_labelmap,
            smooth=False,
        )
        result = extract_meshes(request)

        # JSON 직렬화 테스트
        json_str = json.dumps(result)
        assert len(json_str) > 0

        # 역직렬화
        parsed = json.loads(json_str)
        assert len(parsed["meshes"]) == len(result["meshes"])

        # base64 인코딩 필드 확인 + 디코딩 검증
        for m in parsed["meshes"]:
            assert isinstance(m["vertices_b64"], str), "vertices_b64는 문자열이어야 함"
            assert isinstance(m["faces_b64"], str), "faces_b64는 문자열이어야 함"
            # base64 디코딩 → numpy 배열 복원
            verts_bytes = base64.b64decode(m["vertices_b64"])
            verts = np.frombuffer(verts_bytes, dtype=np.float32)
            assert len(verts) == m["n_vertices"] * 3, "정점 수 불일치"
            faces_bytes = base64.b64decode(m["faces_b64"])
            faces = np.frombuffer(faces_bytes, dtype=np.int32)
            assert len(faces) == m["n_faces"] * 3, "면 수 불일치"


class TestPipelineOrchestration:
    """전체 파이프라인 오케스트레이션 테스트 (세그멘테이션 mock)."""

    def _create_synthetic_dicom(self, output_dir: Path, n_slices: int = 10):
        """합성 DICOM 시리즈 생성 (TestDicomToNiftiE2E에서 재사용)."""
        import SimpleITK as sitk

        size = (32, 32, n_slices)
        arr = np.zeros(size[::-1], dtype=np.int16)  # (z, y, x)
        # 중심에 뼈 구조
        for z in range(n_slices):
            for y in range(32):
                for x in range(32):
                    dist = ((x - 16) ** 2 + (y - 16) ** 2) ** 0.5
                    if dist < 8:
                        arr[z, y, x] = 700

        volume = sitk.GetImageFromArray(arr)
        volume.SetSpacing((1.0, 1.0, 1.0))
        volume.SetOrigin((0.0, 0.0, 0.0))

        output_dir.mkdir(parents=True, exist_ok=True)
        writer = sitk.ImageFileWriter()
        writer.KeepOriginalImageUIDOn()

        for i in range(volume.GetDepth()):
            image_slice = volume[:, :, i]
            image_slice.SetMetaData("0008|0060", "CT")
            image_slice.SetMetaData("0010|0020", "TEST002")
            image_slice.SetMetaData("0020|000e", "1.2.3.4.5")
            image_slice.SetMetaData("0020|0013", str(i))
            writer.SetFileName(str(output_dir / f"s_{i:04d}.dcm"))
            writer.Execute(image_slice)

    def test_pipeline_stage1_and_stage3(self, tmp_path):
        """파이프라인 1단계 + 3단계 통합 (세그멘테이션 skip).

        실제 세그멘테이션 대신 합성 라벨맵을 사용하여
        DICOM → NIfTI → (합성 라벨맵) → 메쉬 추출 플로우 검증.
        """
        import SimpleITK as sitk
        from src.server.services.dicom_convert import convert_dicom_to_nifti
        from src.server.services.mesh_extract import extract_meshes
        from src.server.models import MeshExtractRequest

        # 1단계: DICOM → NIfTI
        dicom_dir = tmp_path / "dicom"
        self._create_synthetic_dicom(dicom_dir, n_slices=16)

        convert_result = convert_dicom_to_nifti(str(dicom_dir))
        nifti_path = convert_result["nifti_path"]
        assert Path(nifti_path).exists()

        # NIfTI 볼륨 읽기 → 합성 라벨맵 생성 (세그멘테이션 대체)
        nifti_img = sitk.ReadImage(nifti_path)
        vol_arr = sitk.GetArrayFromImage(nifti_img)

        # HU 기반 간단한 세그멘테이션 모방
        labels = np.zeros_like(vol_arr, dtype=np.int16)
        labels[vol_arr > 500] = 120  # 뼈 → L4
        labels[(vol_arr > 100) & (vol_arr <= 500)] = 301  # 연조직

        # 라벨맵을 NIfTI로 저장
        label_img = sitk.GetImageFromArray(labels)
        label_img.CopyInformation(nifti_img)
        label_path = tmp_path / "labels_standard.nii.gz"
        sitk.WriteImage(label_img, str(label_path))

        # 3단계: 라벨맵 → 메쉬 추출
        request = MeshExtractRequest(
            labels_path=str(label_path),
            smooth=True,
        )
        mesh_result = extract_meshes(request)

        # 검증: 메쉬가 생성되었는지
        assert len(mesh_result["meshes"]) >= 1, "최소 1개 메쉬 필요"

        # 뼈 메쉬가 있는지
        bone_meshes = [m for m in mesh_result["meshes"] if m["material_type"] == "bone"]
        assert len(bone_meshes) >= 1, "뼈 메쉬가 있어야 함"

        # 메쉬 데이터 형식 확인 (base64)
        import base64 as b64
        for m in mesh_result["meshes"]:
            assert isinstance(m["vertices_b64"], str), "vertices_b64는 문자열이어야 함"
            assert isinstance(m["faces_b64"], str), "faces_b64는 문자열이어야 함"
            assert m["n_vertices"] > 10, f"{m['name']} 정점이 너무 적음: {m['n_vertices']}"
            # base64 디코딩 가능 확인
            verts_bytes = b64.b64decode(m["vertices_b64"])
            assert len(verts_bytes) == m["n_vertices"] * 3 * 4

    def test_full_pipeline_with_mock_segmentation(self, tmp_path):
        """run_dicom_pipeline 전체 호출 (세그멘테이션 mock)."""
        import SimpleITK as sitk
        from src.server.models import DicomPipelineRequest

        # DICOM 생성
        dicom_dir = tmp_path / "dicom"
        self._create_synthetic_dicom(dicom_dir, n_slices=10)

        # 세그멘테이션 mock: run_segmentation을 합성 라벨맵 생성으로 교체
        def mock_run_segmentation(request, progress_callback=None):
            """합성 라벨맵을 생성하는 mock 세그멘테이션."""
            input_path = Path(request.input_path)
            output_dir = input_path.parent / "segmentation"
            output_dir.mkdir(parents=True, exist_ok=True)

            # NIfTI 읽기 → HU 기반 세그멘테이션
            nifti_img = sitk.ReadImage(str(input_path))
            vol_arr = sitk.GetArrayFromImage(nifti_img)

            labels = np.zeros_like(vol_arr, dtype=np.int16)
            labels[vol_arr > 500] = 123  # 뼈 (L4)

            # 표준 라벨맵 저장
            label_img = sitk.GetImageFromArray(labels)
            label_img.CopyInformation(nifti_img)
            std_path = output_dir / "labels_standard.nii.gz"
            sitk.WriteImage(label_img, str(std_path))

            if progress_callback:
                progress_callback("segment", {"message": "Mock 세그멘테이션 완료"})

            return {
                "labels_path": str(std_path),
                "n_labels": 1,
                "label_names": {123: "L4"},
                "label_info": [{"label": 123, "name": "L4", "material_type": "bone", "voxel_count": 100}],
                "metadata": {
                    "origin": list(nifti_img.GetOrigin()),
                    "spacing": list(nifti_img.GetSpacing()),
                    "size": list(nifti_img.GetSize()),
                },
            }

        # 파이프라인 실행 (세그멘테이션 mock — lazy import이므로 서비스 모듈에서 patch)
        with patch("src.server.services.segmentation.run_segmentation", mock_run_segmentation):
            from src.server.services.dicom_pipeline import run_dicom_pipeline

            request = DicomPipelineRequest(
                dicom_dir=str(dicom_dir),
                engine="auto",
                device="cpu",
                smooth=True,
            )

            progress_msgs = []
            def cb(step, detail):
                progress_msgs.append((step, detail.get("message", "")))

            result = run_dicom_pipeline(request, progress_callback=cb)

        # ── 최종 결과 검증 ──
        assert "meshes" in result
        assert len(result["meshes"]) >= 1, "최소 1개 메쉬 필요"
        assert "nifti_path" in result
        assert Path(result["nifti_path"]).exists()
        assert "labels_path" in result

        # 메쉬 구조 검증 (프론트엔드 호환 — base64)
        for m in result["meshes"]:
            assert "name" in m
            assert "vertices_b64" in m, "vertices_b64 필드 필수"
            assert "faces_b64" in m, "faces_b64 필드 필수"
            assert "material_type" in m
            assert "color" in m
            assert "n_vertices" in m
            assert "n_faces" in m
            assert isinstance(m["vertices_b64"], str)
            assert isinstance(m["faces_b64"], str)

        # 진행률 콜백이 여러 번 호출됨
        assert len(progress_msgs) >= 3
