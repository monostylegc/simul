# API Reference

Spine Surgery Planner 백엔드 REST/WebSocket API 레퍼런스.

서버 기본 주소: `http://localhost:8000`

---

## REST 엔드포인트

### GET `/`

프론트엔드 메인 페이지 (`frontend/dist/index.html`) 서빙.

### POST `/api/upload`

단일 파일 업로드 (NIfTI, STL 등).

**파라미터**: `file` (multipart/form-data, UploadFile)

**응답**:
```json
{
  "path": "/home/user/.spine_sim/abc12345/sample.nii.gz",
  "filename": "sample.nii.gz",
  "size": 1048576,
  "session_id": "abc12345"
}
```

### POST `/api/upload_dicom`

DICOM 다중 파일 업로드. `webkitdirectory`로 선택한 폴더의 파일들을 flat 구조로 저장.

**파라미터**: `files` (multipart/form-data, List[UploadFile])

**응답**:
```json
{
  "dicom_dir": "/home/user/.spine_sim/abc12345/dicom",
  "n_files": 129,
  "session_id": "abc12345",
  "total_size": 67108864
}
```

> 이미지 확장자(.jpg, .png 등)와 비-DICOM 파일은 자동 필터링됩니다.

### POST `/api/upload_plan`

수술 계획 JSON 파일 업로드. 파싱된 JSON을 그대로 반환.

**파라미터**: `file` (multipart/form-data, JSON UploadFile)

### GET `/api/gpu-info`

GPU 사용 가능 여부 및 정보 조회.

**응답**:
```json
{
  "available": true,
  "name": "NVIDIA GeForce RTX 4070 Ti SUPER",
  "memory_mb": 16376,
  "cuda_version": "12.4",
  "driver_version": "581.57"
}
```

---

## WebSocket 프로토콜

엔드포인트: `ws://localhost:8000/ws`

모든 메시지는 JSON 형식이며 `{"type": string, "data": object}` 구조를 따릅니다.

### 클라이언트 → 서버 메시지

| type | 설명 | data 모델 |
|------|------|-----------|
| `run_analysis` | FEA 해석 실행 | `AnalysisRequest` |
| `cancel_analysis` | 실행 중인 해석 취소 | `{request_id: string}` |
| `segment` | CT/MRI 세그멘테이션 | `SegmentationRequest` |
| `extract_meshes` | 라벨맵 → 3D 메쉬 추출 | `MeshExtractRequest` |
| `auto_material` | 라벨 기반 자동 재료 매핑 | `AutoMaterialRequest` |
| `run_dicom_pipeline` | DICOM 원클릭 파이프라인 | `DicomPipelineRequest` |
| `get_implant_mesh` | 임플란트 메쉬 생성 | `ImplantMeshRequest` |
| `get_guideline_meshes` | 수술 가이드라인 생성 | `GuidelineRequest` |
| `ping` | 연결 유지 | 없음 |

### 서버 → 클라이언트 메시지

| type | 설명 |
|------|------|
| `progress` | 해석 진행률 (`{step, iteration, residual, ...}`) |
| `result` | 해석 완료 결과 (`{displacements, stress, ...}`) |
| `cancelled` | 해석 취소 확인 (`{request_id}`) |
| `segment_result` | 세그멘테이션 완료 (`{labels_path, n_labels}`) |
| `meshes_result` | 메쉬 추출 완료 (`{meshes: [...]}`) |
| `material_result` | 자동 재료 매핑 결과 (`{materials: [...]}`) |
| `pipeline_step` | DICOM 파이프라인 스테이지 진행 (`{step, ...}`) |
| `pipeline_result` | DICOM 파이프라인 완료 (`{meshes: [...]}`) |
| `implant_mesh_result` | 임플란트 메쉬 (`{name, implant_type, vertices, faces}`) |
| `guideline_meshes_result` | 가이드라인 메쉬 (`{vertebra_name, meshes: [...]}`) |
| `error` | 오류 (`{message: string}`) |
| `pong` | ping 응답 |

---

## 요청 모델 스키마

### AnalysisRequest

FEA 해석 요청.

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `positions` | `list[list[float]]` | 필수 | (n, 3) 노드/입자 좌표 |
| `volumes` | `list[float]` | 필수 | (n,) 복셀 체적 |
| `method` | `"fem" \| "pd" \| "spg" \| "coupled"` | 필수 | 해석 방법 |
| `boundary_conditions` | `list[BoundaryCondition]` | 필수 | 경계조건 목록 |
| `materials` | `list[MaterialRegion]` | 필수 | 재료 영역 목록 |
| `options` | `dict` | `{}` | 솔버별 옵션 (dt, n_steps 등) |

### BoundaryCondition

| 필드 | 타입 | 설명 |
|------|------|------|
| `type` | `"fixed" \| "force"` | 고정 또는 하중 |
| `node_indices` | `list[int]` | 적용 대상 노드 인덱스 |
| `values` | `list[list[float]]` | (n, dim) 변위/힘 벡터 |

### MaterialRegion

재료 영역 — 특정 노드 그룹에 할당.

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `name` | `str` | 필수 | 영역 이름 ("bone", "disc" 등) |
| `method` | `"fem" \| "pd" \| "spg" \| "coupled"` | `"fem"` | 솔버 |
| `E` | `float` | 필수 | 영률 [Pa] |
| `nu` | `float` | 필수 | 포아송비 |
| `density` | `float` | `1000.0` | 밀도 [kg/m³] |
| `constitutive_model` | `str` | `"linear_elastic"` | 구성 모델 |
| `C10`, `C01` | `float?` | - | Mooney-Rivlin 상수 [Pa] |
| `D1` | `float?` | - | 비압축성 파라미터 [1/Pa] |
| `mu_ogden`, `alpha_ogden` | `float?` | - | Ogden 파라미터 |
| `node_indices` | `list[int]` | 필수 | 이 재료에 속하는 노드 인덱스 |
| `nodes` | `list[list[float]]?` | - | FEM HEX8 노드 좌표 |
| `elements` | `list[list[int]]?` | - | FEM HEX8 요소 연결 |
| `boundary_conditions` | `list[BC]?` | - | 영역별 경계조건 |
| `coupling` | `CouplingConfig?` | - | 커플링 설정 |

### CouplingConfig

FEM↔PD/SPG 커플링 설정.

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `mode` | `"manual" \| "auto"` | `"manual"` | 커플링 모드 |
| `particle_method` | `"pd" \| "spg"` | `"pd"` | 파괴 해석 방법 |
| `pd_element_indices` | `list[int]?` | - | 수동 모드: PD 영역 요소 |
| `von_mises_threshold` | `float?` | - | 자동 모드: VM 응력 임계값 [Pa] |
| `max_strain_threshold` | `float?` | - | 자동 모드: 최대 변형률 임계값 |
| `buffer_layers` | `int` | `1` | 인접 요소 확장 레이어 |
| `coupling_tol` | `float` | `1e-4` | 수렴 허용 오차 |
| `max_coupling_iters` | `int` | `20` | 최대 반복 수 |

### SegmentationRequest

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `input_path` | `str` | 필수 | 입력 볼륨 경로 |
| `engine` | `str` | `"totalspineseg"` | 세그멘테이션 엔진 |
| `device` | `str` | `"gpu"` | 연산 장치 |
| `fast` | `bool` | `false` | 빠른 모드 (저해상도) |
| `modality` | `str?` | `null` | CT / MRI / null(자동) |

### MeshExtractRequest

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `labels_path` | `str` | 필수 | 라벨맵 NIfTI 경로 |
| `selected_labels` | `list[int]?` | `null` | 추출할 라벨 (null=전체) |
| `resolution` | `int` | `64` | 메쉬 해상도 |
| `smooth` | `bool` | `true` | 스무딩 적용 |

### AutoMaterialRequest

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `label_values` | `list[int]` | 필수 | 각 노드의 SpineLabel 값 |
| `implant_materials` | `dict` | `{}` | 임플란트명 → 재료명 매핑 |

### DicomPipelineRequest

DICOM 원클릭 파이프라인: DICOM → NIfTI 변환 → 세그멘테이션 → 메쉬 추출.

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `dicom_dir` | `str` | 필수 | DICOM 파일 디렉토리 |
| `engine` | `str` | `"auto"` | 세그멘테이션 엔진 |
| `device` | `str` | `"gpu"` | 연산 장치 |
| `fast` | `bool` | `false` | 빠른 모드 |
| `modality` | `str?` | `null` | CT / MRI / null |
| `smooth` | `bool` | `true` | 메쉬 스무딩 |
| `resolution` | `int` | `64` | 메쉬 해상도 |

### ImplantMeshRequest

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `implant_type` | `"screw" \| "cage" \| "rod"` | `"screw"` | 임플란트 유형 |
| `screw_spec` | `ScrewSpecModel?` | - | 스크류 규격 |
| `cage_spec` | `CageSpecModel?` | - | 케이지 규격 |
| `rod_length` | `float` | `100.0` | 로드 길이 (mm) |
| `rod_diameter` | `float` | `5.5` | 로드 직경 (mm) |
| `size` | `str` | `""` | 표준 규격 문자열 (예: "M6x45") |

### ScrewSpecModel

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `diameter` | `6.0` | 직경 (mm) |
| `length` | `45.0` | 길이 (mm) |
| `head_diameter` | `10.0` | 헤드 직경 (mm) |
| `head_height` | `5.0` | 헤드 높이 (mm) |
| `thread_pitch` | `2.5` | 나사산 피치 (mm) |
| `thread_depth` | `0.5` | 나사산 깊이 (mm) |

### CageSpecModel

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `width` | `26.0` | 폭 (mm) |
| `depth` | `10.0` | 깊이 (mm) |
| `height` | `12.0` | 높이 (mm) |
| `angle` | `6.0` | 전만각 (도) |

### GuidelineRequest

수술 가이드라인 (Pedicle Screw 삽입 경로) 생성.

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `vertebra_position` | `list[float]` | 필수 | 척추 중심 [x, y, z] (mm) |
| `vertebra_name` | `str` | `"L4"` | 척추 이름 |
| `pedicle_offset` | `float` | `15.0` | 척추경 좌우 오프셋 (mm) |
| `medial_angle` | `float` | `10.0` | 내측각 (도) |
| `caudal_angle` | `float` | `0.0` | 두측각 (도) |
| `depth` | `float` | `45.0` | 삽입 깊이 (mm) |
| `show_trajectory` | `bool` | `true` | 삽입 경로 표시 |
| `show_safe_zone` | `bool` | `true` | 안전 영역 표시 |
| `show_depth_marker` | `bool` | `true` | 깊이 마커 표시 |

### SurgicalPlan

수술 계획 전체를 묶는 최상위 모델.

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `implants` | `list[ImplantPlacement]` | `[]` | 임플란트 배치 목록 |
| `bone_modifications` | `dict` | `{}` | 뼈 수정 데이터 |
| `boundary_conditions` | `list[BoundaryCondition]` | `[]` | 경계조건 |
| `materials` | `list[MaterialRegion]` | `[]` | 재료 영역 |

### ImplantPlacement

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `name` | `str` | 필수 | 임플란트 이름 |
| `stl_path` | `str` | 필수 | STL 파일 경로 |
| `position` | `list[float]` | 필수 | [x, y, z] 위치 |
| `rotation` | `list[float]` | `[0,0,0]` | Euler 회전 (라디안) |
| `scale` | `list[float]` | `[1,1,1]` | 스케일 |
| `material` | `str` | `"titanium"` | 재료 ("titanium", "peek", "custom") |
| `E`, `nu`, `density` | `float?` | - | 커스텀 재료 물성 |

---

## 소스 파일

| 모듈 | 경로 |
|------|------|
| FastAPI 앱 | `backend/api/app.py` |
| WebSocket 핸들러 | `backend/api/ws_handler.py` |
| 서버 설정 | `backend/api/config.py` |
| 해석 모델 | `backend/api/models/analysis.py` |
| 영상 모델 | `backend/api/models/imaging.py` |
| 수술 모델 | `backend/api/models/surgical.py` |
