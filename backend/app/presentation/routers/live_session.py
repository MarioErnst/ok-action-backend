# Full module documentation: documentacion/modulos/sesion-libre.md
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.ai.live_gemini import analyze_audio_segment
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import authenticate_ws, get_current_user
from app.presentation.schemas.live_session import LiveSessionListItem
from app.use_cases.live_session.errors import extract_errors_for_dim
from app.use_cases.live_session.prompt_builder import build_system_prompt
from app.use_cases.live_session.save_session import list_live_sessions, save_live_session
from app.use_cases.live_session.session_manager import LiveSessionState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/live", tags=["live-session"])

ANALYSIS_INTERVAL_SECONDS = 5


@router.websocket("/session")
async def live_session_ws(
    ws: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_session),
):
    await ws.accept()

    try:
        user = await authenticate_ws(token, db)
    except Exception as exc:
        logger.error("WS auth error: %s", exc)
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
        logger.warning("Unexpected error waiting for start message: %s", exc)
        await ws.close(code=4002, reason="Expected start message")
        return

    dims = start_msg.get("dims", [])
    if not dims or not all(d in ("pron", "acc", "mul") for d in dims):
        await ws.close(code=4003, reason="Invalid dims")
        return

    state = LiveSessionState(
        user_id=str(user.id),
        selected_dims=dims,
    )
    prompt = build_system_prompt(dims)
    stop_event = asyncio.Event()
    audio_buffer = bytearray()

    await ws.send_json({"type": "ready"})

    async def stream_audio():
        """Reads binary audio frames from the client and appends them to the shared buffer."""
        try:
            while not stop_event.is_set():
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    stop_event.set()
                    break
                if message.get("bytes"):
                    audio_buffer.extend(message["bytes"])
                elif message.get("text"):
                    data = json.loads(message["text"])
                    if data.get("type") == "end":
                        state.stop_reason = "user_ended"
                        stop_event.set()
        except WebSocketDisconnect:
            stop_event.set()
        except Exception as exc:
            logger.warning("Audio stream error: %s", exc)
            stop_event.set()

    async def analysis_timer():
        """Every ANALYSIS_INTERVAL_SECONDS, drains the buffer and requests analysis from Gemini."""
        while not stop_event.is_set():
            await asyncio.sleep(ANALYSIS_INTERVAL_SECONDS)
            if stop_event.is_set():
                break

            # Snapshot and clear atomically between awaits (asyncio is single-threaded)
            chunk = bytes(audio_buffer)
            audio_buffer.clear()

            analysis = await analyze_audio_segment(chunk, state.selected_dims, prompt)
            if analysis is None:
                continue

            should_stop, reason, dim = state.evaluate_thresholds(analysis)
            await ws.send_json({"type": "analysis", "data": analysis})

            if should_stop:
                state.stop_reason = reason
                await ws.send_json({
                    "type": "correction",
                    "dim": dim,
                    "reason": reason,
                    "errors": extract_errors_for_dim(analysis, dim),
                })
                stop_event.set()

    async def session_limit_timer():
        """Ends session after MAX_DURATION_SEC. Only sets the flag; the finally block sends session_ended."""
        await asyncio.sleep(state.MAX_DURATION_SEC)
        if not stop_event.is_set():
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
        logger.error("Unexpected error in live session: %s", exc)
    finally:
        if not state.stop_reason:
            state.stop_reason = "user_ended"
        try:
            await save_live_session(state, user, db)
        except Exception as exc:
            logger.error("Failed to save live session: %s", exc)
        try:
            await ws.send_json({"type": "session_ended", "reason": state.stop_reason})
            await ws.close()
        except Exception:
            pass


@router.get("/sessions", response_model=list[LiveSessionListItem])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    sessions = await list_live_sessions(user, db)
    return [
        LiveSessionListItem(
            id=str(s.id),
            selected_dims=s.selected_dims,
            overall_score=float(s.overall_score) if s.overall_score else None,
            stop_reason=s.stop_reason,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]
