import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ai.consistency_gemini import analyze_consistency_audio
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import authenticate_ws
from app.use_cases.consistency.prompt_builder import build_consistency_prompt
from app.use_cases.consistency.session_manager import (
    MIN_AUDIO_BYTES,
    ConsistencySessionState,
    build_no_audio_analysis,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/consistency", tags=["consistency"])


@router.websocket("/session")
async def consistency_session_ws(
    ws: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_session),
):
    await ws.accept()

    try:
        user = await authenticate_ws(token, db)
    except Exception as exc:
        logger.error("Consistency WS auth error: %s", exc)
        await ws.close(code=4001, reason="Unauthorized")
        return

    if not user:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await db.commit()

    try:
        start_msg = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
    except asyncio.TimeoutError:
        await ws.close(code=4002, reason="Expected start message")
        return
    except Exception as exc:
        logger.warning("Unexpected consistency start message error: %s", exc)
        await ws.close(code=4002, reason="Expected start message")
        return

    prompt_text = str(start_msg.get("prompt_text") or "").strip()
    state = ConsistencySessionState(user_id=str(user.id), prompt_text=prompt_text)
    prompt = build_consistency_prompt(prompt_text)
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
            logger.warning("Consistency audio stream error: %s", exc)
            stop_event.set()

    async def session_limit_timer():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=state.MAX_DURATION_SEC)
        except asyncio.TimeoutError:
            state.stop_reason = "time_limit"
            stop_event.set()

    try:
        await asyncio.gather(stream_audio(), session_limit_timer(), return_exceptions=True)
    except Exception as exc:
        logger.error("Unexpected consistency session error: %s", exc)
    finally:
        if not state.stop_reason:
            state.stop_reason = "user_ended"

        audio_bytes = bytes(audio_buffer)
        if len(audio_bytes) < MIN_AUDIO_BYTES:
            analysis = build_no_audio_analysis()
        else:
            analysis = await analyze_consistency_audio(audio_bytes, prompt)

        if analysis is None:
            try:
                await ws.send_json({"type": "error", "message": "No se pudo analizar la consistencia."})
                await ws.close()
            except Exception:
                pass
            return

        state.set_analysis(analysis)
        warning_reason = state.warning_reason()

        try:
            await ws.send_json({"type": "analysis", "data": analysis})
            if warning_reason:
                await ws.send_json({"type": "warning", "reason": warning_reason, "data": analysis})
            await ws.send_json({
                "type": "session_ended",
                "reason": state.stop_reason,
                "score": state.final_score(),
            })
            await ws.close()
        except Exception:
            pass
