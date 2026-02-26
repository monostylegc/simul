"""WebSocket 핸들러 — 해석/세그멘테이션/메쉬추출 요청 수신, 진행률 전송, 결과 반환.

역할: 순수 WS 디스패처. 비즈니스 로직은 services/ 패키지에 위임.

기능:
  - 해석 요청 (run_analysis) + 결과/진행률 전송
  - 해석 취소 (cancel_analysis) — asyncio.Task 기반
  - DICOM 파이프라인, 세그멘테이션, 메쉬추출 등
"""

import json
import asyncio
import traceback
from fastapi import WebSocket, WebSocketDisconnect

from .models import (
    AnalysisRequest, SegmentationRequest, MeshExtractRequest,
    AutoMaterialRequest, DicomPipelineRequest,
    ImplantMeshRequest, GuidelineRequest,
)

# 실행 중인 해석 태스크 추적 (request_id → asyncio.Task)
_running_tasks: dict[str, asyncio.Task] = {}


async def handle_websocket(ws: WebSocket):
    """WebSocket 연결 처리.

    프로토콜:
        클라이언트 → 서버:
            {"type": "run_analysis",        "data": AnalysisRequest}
            {"type": "segment",             "data": SegmentationRequest}
            {"type": "extract_meshes",      "data": MeshExtractRequest}
            {"type": "auto_material",       "data": AutoMaterialRequest}
            {"type": "run_dicom_pipeline",  "data": DicomPipelineRequest}
            {"type": "get_implant_mesh",    "data": ImplantMeshRequest}
            {"type": "get_guideline_meshes","data": GuidelineRequest}
            {"type": "ping"}

        서버 → 클라이언트:
            {"type": "progress",               "data": {"step": "...", ...}}
            {"type": "result",                 "data": {...}}
            {"type": "segment_result",         "data": {labels_path, n_labels, ...}}
            {"type": "meshes_result",          "data": {meshes: [...]}}
            {"type": "material_result",        "data": {materials: [...]}}
            {"type": "pipeline_step",          "data": {step, ...}}
            {"type": "pipeline_result",        "data": {meshes: [...]}}
            {"type": "implant_mesh_result",    "data": {name, implant_type, vertices, faces, color}}
            {"type": "guideline_meshes_result","data": {vertebra_name, meshes: [...]}}
            {"type": "error",                  "data": {"message": "..."}}
    """
    await ws.accept()

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "run_analysis":
                await _handle_analysis(ws, msg.get("data", {}))
            elif msg_type == "cancel_analysis":
                await _handle_cancel(ws, msg.get("data", {}))
            elif msg_type == "segment":
                await _handle_segment(ws, msg.get("data", {}))
            elif msg_type == "extract_meshes":
                await _handle_extract_meshes(ws, msg.get("data", {}))
            elif msg_type == "auto_material":
                await _handle_auto_material(ws, msg.get("data", {}))
            elif msg_type == "run_dicom_pipeline":
                await _handle_dicom_pipeline(ws, msg.get("data", {}))
            elif msg_type == "get_implant_mesh":
                await _handle_implant_mesh(ws, msg.get("data", {}))
            elif msg_type == "get_guideline_meshes":
                await _handle_guideline_meshes(ws, msg.get("data", {}))
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
    """동기 → 비동기 진행률 콜백 생성 (progress 타입)."""
    async def _send(step: str, detail: dict):
        await ws.send_json({
            "type": "progress",
            "data": {"step": step, **detail},
        })

    def callback(step: str, detail: dict):
        asyncio.run_coroutine_threadsafe(_send(step, detail), loop)

    return callback


def _make_pipeline_step_callback(ws: WebSocket, loop):
    """동기 → 비동기 파이프라인 단계 콜백 생성 (pipeline_step 타입)."""
    async def _send(step: str, detail: dict):
        await ws.send_json({
            "type": "pipeline_step",
            "data": {"step": step, **detail},
        })

    def callback(step: str, detail: dict):
        asyncio.run_coroutine_threadsafe(_send(step, detail), loop)

    return callback


async def _run_in_thread(ws, result_type, func, *args):
    """블로킹 함수를 스레드풀에서 실행 후 결과 전송."""
    loop = asyncio.get_running_loop()  # Python 3.10+ 권장: 현재 실행 중인 루프 반환
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
    """해석 요청 처리.

    request_id가 있으면 asyncio.Task로 실행해 나중에 취소 가능.
    """
    request_id = data.pop("request_id", None)

    try:
        request = AnalysisRequest(**data)
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {"message": f"요청 파싱 실패: {e}"},
        })
        return

    from .services.analysis import run_analysis

    async def _run():
        try:
            await _run_in_thread(ws, "result", run_analysis, request)
        except asyncio.CancelledError:
            # 취소됨 — cancelled 메시지 전송
            await ws.send_json({
                "type": "cancelled",
                "data": {"request_id": request_id or ""},
            })
        finally:
            if request_id and request_id in _running_tasks:
                del _running_tasks[request_id]

    task = asyncio.create_task(_run())
    if request_id:
        _running_tasks[request_id] = task


async def _handle_cancel(ws: WebSocket, data: dict):
    """해석 취소 요청 처리."""
    request_id = data.get("request_id")
    if not request_id:
        return

    task = _running_tasks.get(request_id)
    if task and not task.done():
        task.cancel()
        # cancelled 메시지는 task 정리 시 전송됨
    else:
        # 이미 완료됐거나 존재하지 않는 요청
        await ws.send_json({
            "type": "cancelled",
            "data": {"request_id": request_id},
        })


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

    from .services.segmentation import run_segmentation
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

    from .services.mesh_extract import extract_meshes
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

    from .services.auto_material import auto_assign_materials
    await _run_in_thread(ws, "material_result", auto_assign_materials, request)


async def _handle_dicom_pipeline(ws: WebSocket, data: dict):
    """DICOM 원클릭 파이프라인 — 변환 → 세그멘테이션 → 메쉬 추출.

    pipeline_step 메시지 타입으로 단계별 진행 상황 전송.
    """
    try:
        request = DicomPipelineRequest(**data)
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {"message": f"DICOM 파이프라인 요청 파싱 실패: {e}"},
        })
        return

    loop = asyncio.get_running_loop()  # Python 3.10+ 권장: 현재 실행 중인 루프 반환
    # pipeline_step 타입으로 전송하는 전용 콜백
    step_callback = _make_pipeline_step_callback(ws, loop)

    try:
        from .services.dicom_pipeline import run_dicom_pipeline
        result = await loop.run_in_executor(
            None,
            lambda: run_dicom_pipeline(request, progress_callback=step_callback),
        )
        await ws.send_json({"type": "pipeline_result", "data": result})
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {
                "message": f"DICOM 파이프라인 실패: {e}",
                "traceback": traceback.format_exc(),
            },
        })


async def _handle_implant_mesh(ws: WebSocket, data: dict):
    """임플란트 3D 메쉬 생성 요청 처리."""
    try:
        request = ImplantMeshRequest(**data)
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {"message": f"임플란트 요청 파싱 실패: {e}"},
        })
        return

    from .services.implants import generate_implant_mesh
    await _run_in_thread(ws, "implant_mesh_result", generate_implant_mesh, request)


async def _handle_guideline_meshes(ws: WebSocket, data: dict):
    """수술 가이드라인 메쉬 생성 요청 처리."""
    try:
        request = GuidelineRequest(**data)
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {"message": f"가이드라인 요청 파싱 실패: {e}"},
        })
        return

    from .services.guideline import generate_guideline_meshes
    await _run_in_thread(ws, "guideline_meshes_result", generate_guideline_meshes, request)
