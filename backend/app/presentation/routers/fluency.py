import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ai.fluency_gemini import analyze_fluency_audio_segment
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import authenticate_ws
from app.use_cases.fluency.prompt_builder import build_fluency_prompt
from app.use_cases.fluency.session_manager import FluencySessionState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fluency", tags=["fluency"])

ANALYSIS_INTERVAL_SECONDS = 5


@router.websocket("/session")
async def fluency_session_ws(
    ws: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_session),
):
    await ws.accept()

    try:
        user = await authenticate_ws(token, db)
    except Exception as exc:
        logger.error("Fluency WS auth error: %s", exc)
        await ws.close(code=4001, reason="Unauthorized")
        return

    if not user:
        await ws.close(code=4001, reason="Unauthorized")
        return

    try:
        start_msg = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
    except asyncio.TimeoutError:
        await ws.close(code=4002, reason="Expected start message")
        return
    except Exception as exc:
        logger.warning("Unexpected fluency start message error: %s", exc)
        await ws.close(code=4002, reason="Expected start message")
        return

    prompt_text = str(start_msg.get("prompt_text") or "").strip()
    state = FluencySessionState(user_id=str(user.id), prompt_text=prompt_text)
    prompt = build_fluency_prompt(prompt_text)
    stop_event = asyncio.Event()
    audio_buffer = bytearray()

    await ws.send_json({"type": "ready"})

    async def stream_audio():
        try:
            while not stop_event.is_set():
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    stop_event.set()
                    break
                if message.get("bytes"):
                    audio_buffer.extend(message["bytes"])
                    continue
                if message.get("text"):
                    data = json.loads(message["text"])
                    if data.get("type") == "end":
                        state.stop_reason = "user_ended"
                        stop_event.set()
        except WebSocketDisconnect:
            stop_event.set()
        except Exception as exc:
            logger.warning("Fluency audio stream error: %s", exc)
            stop_event.set()

    async def analysis_timer():
        while not stop_event.is_set():
            await asyncio.sleep(ANALYSIS_INTERVAL_SECONDS)
            if stop_event.is_set():
                break

            chunk = bytes(audio_buffer)
            audio_buffer.clear()

            analysis = await analyze_fluency_audio_segment(chunk, prompt)
            if analysis is None:
                continue

            should_warn, reason = state.evaluate_attention(analysis)
            await ws.send_json({"type": "analysis", "data": analysis})

            if should_warn and reason != "time_limit":
                await ws.send_json({"type": "warning", "reason": reason, "data": analysis})

            if reason == "time_limit":
                stop_event.set()

    async def session_limit_timer():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=state.MAX_DURATION_SEC)
        except asyncio.TimeoutError:
            state.stop_reason = "time_limit"
            stop_event.set()

    try:
        await asyncio.gather(
            stream_audio(),
            analysis_timer(),
            session_limit_timer(),
            return_exceptions=True,
        )
    except Exception as exc:
        logger.error("Unexpected fluency session error: %s", exc)
    finally:
        if not state.stop_reason:
            state.stop_reason = "user_ended"
        try:
            await ws.send_json({
                "type": "session_ended",
                "reason": state.stop_reason,
                "average_score": state.average_score(),
            })
            await ws.close()
        except Exception:
            pass
