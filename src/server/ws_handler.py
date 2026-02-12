"""WebSocket 핸들러 — 해석 요청 수신, 진행률 전송, 결과 반환."""

import json
import asyncio
import traceback
from fastapi import WebSocket, WebSocketDisconnect

from .models import AnalysisRequest
from .analysis_pipeline import run_analysis


async def handle_websocket(ws: WebSocket):
    """WebSocket 연결 처리.

    프로토콜:
        클라이언트 → 서버:
            {"type": "run_analysis", "data": AnalysisRequest}

        서버 → 클라이언트:
            {"type": "progress", "data": {"step": "...", "detail": {...}}}
            {"type": "result",   "data": {displacements, stress, damage, info}}
            {"type": "error",    "data": {"message": "..."}}
    """
    await ws.accept()

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "run_analysis":
                await _handle_analysis(ws, msg.get("data", {}))
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


async def _handle_analysis(ws: WebSocket, data: dict):
    """해석 요청 처리 — 별도 스레드에서 실행 + 진행률 전송."""
    try:
        request = AnalysisRequest(**data)
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {"message": f"요청 파싱 실패: {e}"},
        })
        return

    loop = asyncio.get_event_loop()

    # 진행률 콜백 (동기 → 비동기 브릿지)
    async def _send_progress(step: str, detail: dict):
        await ws.send_json({
            "type": "progress",
            "data": {"step": step, **detail},
        })

    def progress_callback(step: str, detail: dict):
        """동기 콜백 — 이벤트 루프에 비동기 전송 예약."""
        asyncio.run_coroutine_threadsafe(
            _send_progress(step, detail), loop
        )

    try:
        # CPU/GPU 해석은 블로킹이므로 스레드풀에서 실행
        result = await loop.run_in_executor(
            None,
            lambda: run_analysis(request, progress_callback),
        )

        await ws.send_json({"type": "result", "data": result})

    except Exception as e:
        await ws.send_json({
            "type": "error",
            "data": {
                "message": str(e),
                "traceback": traceback.format_exc(),
            },
        })
