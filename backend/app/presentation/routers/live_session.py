# Full module documentation: documentacion/modulos/sesion-libre.md
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.ai.live_gemini import GeminiLiveService, GeminiLiveError
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.infrastructure.security.jwt import decode_access_token
from app.presentation.schemas.live_session import LiveSessionListItem, LiveSessionResponse
from app.use_cases.live_session.prompt_builder import build_system_prompt
from app.use_cases.live_session.save_session import list_live_sessions, save_live_session
from app.use_cases.live_session.session_manager import LiveSessionState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/live", tags=["live-session"])

ANALYSIS_INTERVAL_SECONDS = 5


async def _authenticate_ws(token: str, db: AsyncSession) -> User | None:
    """Validates JWT from query param and returns the active user, or None on failure."""
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    return user


def _extract_errors_for_dim(analysis: dict, dim: str | None) -> list:
    """Extracts the error list from a single dimension's analysis result."""
    if not dim:
        return []
    dim_data = analysis.get("dims", {}).get(dim, {})
    return dim_data.get("err") or dim_data.get("det") or []


@router.websocket("/session")
async def live_session_ws(
    ws: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_session),
):
    await ws.accept()

    user = await _authenticate_ws(token, db)
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
        session_id=str(user.id),
        user_id=str(user.id),
        selected_dims=dims,
    )
    prompt = build_system_prompt(dims)
    stop_event = asyncio.Event()

    try:
        async with GeminiLiveService(prompt) as gemini:
            await ws.send_json({"type": "ready"})

            async def stream_audio():
                """Reads binary audio frames from client and forwards to Gemini."""
                try:
                    while not stop_event.is_set():
                        message = await ws.receive()
                        if message["type"] == "websocket.disconnect":
                            stop_event.set()
                            break
                        if message.get("bytes"):
                            await gemini.send_audio_chunk(message["bytes"])
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
                """Triggers analysis every ANALYSIS_INTERVAL_SECONDS seconds."""
                while not stop_event.is_set():
                    await asyncio.sleep(ANALYSIS_INTERVAL_SECONDS)
                    if stop_event.is_set():
                        break
                    try:
                        await gemini.trigger_analysis()
                        analysis = await gemini.receive_analysis()
                    except Exception as exc:
                        logger.error("Analysis cycle failed: %s", exc)
                        stop_event.set()
                        break
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
                            "errors": _extract_errors_for_dim(analysis, dim),
                        })
                        stop_event.set()

            async def session_limit_timer():
                """Ends session after MAX_DURATION_SEC. Only sets the flag; the finally block sends session_ended."""
                await asyncio.sleep(state.MAX_DURATION_SEC)
                if not stop_event.is_set():
                    state.stop_reason = "time_limit"
                    stop_event.set()

            await asyncio.gather(
                stream_audio(),
                analysis_timer(),
                session_limit_timer(),
                return_exceptions=True,
            )

    except GeminiLiveError as exc:
        logger.error("Gemini Live error: %s", exc)
        try:
            await ws.send_json({"type": "error", "message": "Error al conectar con el servicio de analisis"})
        except Exception:
            pass
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
