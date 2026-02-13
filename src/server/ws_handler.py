"""WebSocket 핸들러 — 해석/세그멘테이션/메쉬추출 요청 수신, 진행률 전송, 결과 반환."""

import json
import asyncio
import traceback
from fastapi import WebSocket, WebSocketDisconnect

from .models import (
    AnalysisRequest, SegmentationRequest, MeshExtractRequest,
    AutoMaterialRequest, DicomPipelineRequest,
)


async def handle_websocket(ws: WebSocket):
    """WebSocket 연결 처리.

    프로토콜:
        클라이언트 → 서버:
            {"type": "run_analysis",        "data": AnalysisRequest}
            {"type": "segment",             "data": SegmentationRequest}
            {"type": "extract_meshes",      "data": MeshExtractRequest}
            {"type": "auto_material",       "data": AutoMaterialRequest}
            {"type": "run_dicom_pipeline",  "data": DicomPipelineRequest}
            {"type": "ping"}

        서버 → 클라이언트:
            {"type": "progress",           "data": {"step": "...", ...}}
            {"type": "result",             "data": {...}}
            {"type": "segment_result",     "data": {labels_path, n_labels, ...}}
            {"type": "meshes_result",      "data": {meshes: [...]}}
            {"type": "material_result",    "data": {materials: [...]}}
            {"type": "pipeline_step",      "data": {step, ...}}
            {"type": "pipeline_result",    "data": {meshes: [...]}}
            {"type": "error",              "data": {"message": "..."}}
    """
    await ws.accept()

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "run_analysis":
                await _handle_analysis(ws, msg.get("data", {}))
            elif msg_type == "segment":
                await _handle_segment(ws, msg.get("data", {}))
            elif msg_type == "extract_meshes":
                await _handle_extract_meshes(ws, msg.get("data", {}))
            elif msg_type == "auto_material":
                await _handle_auto_material(ws, msg.get("data", {}))
            elif msg_type == "run_dicom_pipeline":
                await _handle_dicom_pipeline(ws, msg.get("data", {}))
            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})
            else:
                await ws.send_json({
                    "type": "error",
                    "data": {"message": f"알 수 없는 메시지 타입: {msg_type}"},
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({
                "type": "error",
                "data": {"message": str(e)},
            })
        except Exception:
            pass


# ── 진행률 콜백 헬퍼 ──

def _make_progress_callback(ws: WebSocket, loop):
    """동기 → 비동기 진행률 콜백 생성."""
    async def _send(step: str, detail: dict):
        await ws.send_json({
            "type": "progress",
            "data": {"step": step, **detail},
        })

    def callback(step: str, detail: dict):
        asyncio.run_coroutine_threadsafe(_send(step, detail), loop)

    return callback


async def _run_in_thread(ws, result_type, func, *args):
    """블로킹 함수를 스레드풀에서 실행 후 결과 전송."""
    loop = asyncio.get_event_loop()
    progress_callback = _make_progress_callback(ws, loop)

    try:
        result = await loop.run_in_executor(
            None,
            lambda: func(*args, progress_callback=progress_callback),
        )
        await ws.send_json({"type": result_type, "data": result})
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {
                "message": str(e),
                "traceback": traceback.format_exc(),
            },
        })


# ── 명령 핸들러 ──

async def _handle_analysis(ws: WebSocket, data: dict):
    """해석 요청 처리."""
    try:
        request = AnalysisRequest(**data)
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {"message": f"요청 파싱 실패: {e}"},
        })
        return

    from .analysis_pipeline import run_analysis
    await _run_in_thread(ws, "result", run_analysis, request)


async def _handle_segment(ws: WebSocket, data: dict):
    """세그멘테이션 요청 처리."""
    try:
        request = SegmentationRequest(**data)
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {"message": f"세그멘테이션 요청 파싱 실패: {e}"},
        })
        return

    from .segmentation_pipeline import run_segmentation
    await _run_in_thread(ws, "segment_result", run_segmentation, request)


async def _handle_extract_meshes(ws: WebSocket, data: dict):
    """메쉬 추출 요청 처리."""
    try:
        request = MeshExtractRequest(**data)
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {"message": f"메쉬 추출 요청 파싱 실패: {e}"},
        })
        return

    from .mesh_extract_pipeline import extract_meshes
    await _run_in_thread(ws, "meshes_result", extract_meshes, request)


async def _handle_auto_material(ws: WebSocket, data: dict):
    """자동 재료 매핑 요청 처리."""
    try:
        request = AutoMaterialRequest(**data)
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {"message": f"재료 매핑 요청 파싱 실패: {e}"},
        })
        return

    from .auto_material import auto_assign_materials
    await _run_in_thread(ws, "material_result", auto_assign_materials, request)


async def _handle_dicom_pipeline(ws: WebSocket, data: dict):
    """DICOM 원클릭 파이프라인: 변환 → 세그멘테이션 → 메쉬 추출."""
    try:
        request = DicomPipelineRequest(**data)
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {"message": f"DICOM 파이프라인 요청 파싱 실패: {e}"},
        })
        return

    loop = asyncio.get_event_loop()

    async def send_step(step: str, detail: dict):
        await ws.send_json({"type": "pipeline_step", "data": {"step": step, **detail}})

    def progress_cb(step: str, detail: dict):
        asyncio.run_coroutine_threadsafe(send_step(step, detail), loop)

    try:
        # 1단계: DICOM → NIfTI 변환
        await send_step("dicom_convert", {"message": "DICOM 변환 시작...", "phase": 1})

        from .dicom_converter import convert_dicom_to_nifti
        convert_result = await loop.run_in_executor(
            None,
            lambda: convert_dicom_to_nifti(
                request.dicom_dir,
                progress_callback=progress_cb,
            ),
        )
        nifti_path = convert_result["nifti_path"]

        await send_step("dicom_convert_done", {
            "message": "DICOM 변환 완료",
            "nifti_path": nifti_path,
            "phase": 1,
            **convert_result,
        })

        # 2단계: 세그멘테이션
        await send_step("segmentation", {"message": "세그멘테이션 시작...", "phase": 2})

        from .segmentation_pipeline import run_segmentation
        seg_request = SegmentationRequest(
            input_path=nifti_path,
            engine=request.engine,
            device=request.device,
            fast=request.fast,
            modality=request.modality,
        )
        seg_result = await loop.run_in_executor(
            None,
            lambda: run_segmentation(seg_request, progress_callback=progress_cb),
        )

        await send_step("segmentation_done", {
            "message": f"세그멘테이션 완료: {seg_result['n_labels']}개 라벨",
            "labels_path": seg_result["labels_path"],
            "phase": 2,
            **seg_result,
        })

        # 3단계: 메쉬 추출
        await send_step("mesh_extract", {"message": "3D 모델 생성 시작...", "phase": 3})

        from .mesh_extract_pipeline import extract_meshes
        mesh_request = MeshExtractRequest(
            labels_path=seg_result["labels_path"],
            resolution=request.resolution,
            smooth=request.smooth,
        )
        mesh_result = await loop.run_in_executor(
            None,
            lambda: extract_meshes(mesh_request, progress_callback=progress_cb),
        )

        # 최종 결과 전송
        await ws.send_json({
            "type": "pipeline_result",
            "data": {
                "meshes": mesh_result["meshes"],
                "nifti_path": nifti_path,
                "labels_path": seg_result["labels_path"],
                "seg_info": seg_result.get("label_info", []),
                "patient_info": convert_result.get("patient_info", {}),
            },
        })

    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {
                "message": f"DICOM 파이프라인 실패: {e}",
                "traceback": traceback.format_exc(),
            },
        })
