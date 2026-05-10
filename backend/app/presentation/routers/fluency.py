from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import SessionStatusEnum
from app.domain.entities.fluency_metrics import FluencyMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.ai.fluency_gemini import analyze_fluency_audio_segment
from app.infrastructure.db.session import async_session_factory, get_session
from app.infrastructure.security.dependencies import authenticate_ws, get_current_user
from app.presentation.schemas.fluency import (
    FluencyMetricsOutput,
    FluencySessionDetail,
    FluencySessionListItem,
)
from app.use_cases.fluency.prompt_builder import build_fluency_prompt
from app.use_cases.fluency.session_manager import FluencySessionState
from app.use_cases.fluency.sessions import (
    get_fluency_session,
    list_fluency_sessions,
    persist_fluency_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fluency", tags=["fluency"])

ANALYSIS_INTERVAL_SECONDS = 5


def _build_detail(
    session_row: Session, metrics_row: FluencyMetrics
) -> FluencySessionDetail:
    return FluencySessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=FluencyMetricsOutput.model_validate(metrics_row),
    )


def _stop_reason_to_status(reason: str | None) -> SessionStatusEnum:
    """Map the WS stop reason to the persisted session status.

    user_ended/time_limit are normal terminations -> completed. Disconnects
    and unhandled errors -> aborted. The schema does not store the reason
    itself for fluency; only the status survives.
    """

    if reason in ("user_ended", "time_limit"):
        return SessionStatusEnum.completed
    return SessionStatusEnum.aborted


@router.websocket("/session")
async def fluency_session_ws(
    ws: WebSocket,
    token: str = Query(...),
):
    """Stream-based fluency evaluation.

    Protocol on the wire:
      client -> server: {"type": "start", "prompt_text": "..."} (within 10s)
      server -> client: {"type": "ready"}
      client -> server: <bytes>          # audio chunks (raw PCM 16k mono)
      client -> server: {"type": "end"}  # graceful stop
      server -> client: {"type": "analysis", "data": {...}} (every 5s)
      server -> client: {"type": "warning", "reason": "...", "data": {...}}
      server -> client: {"type": "session_ended", "reason": "...", "average_score": N|null,
                         "session_id": UUID|null}
      server: closes WS

    Persistence happens once at end: aggregated metrics are written to a
    single sessions+fluency_metrics row. An empty session (no analyses
    collected) is not persisted; session_id in session_ended will be null.
    """

    await ws.accept()

    # Authenticate against a private DB session: the WS lifecycle is long-lived
    # and we do not want to hold a request-scoped session for the whole stream.
    async with async_session_factory() as auth_db:
        try:
            user = await authenticate_ws(token, auth_db)
        except Exception as exc:
            logger.error("Fluency WS auth error: %s", exc)
            await ws.close(code=4001, reason="Unauthorized")
            return

    if not user:
        await ws.close(code=4001, reason="Unauthorized")
        return

    try:
        start_msg = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning("Fluency start message error: %s", exc)
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

        ended_at = datetime.now(timezone.utc)
        persisted_id: UUID | None = None
        try:
            async with async_session_factory() as persist_db:
                result = await persist_fluency_session(
                    db=persist_db,
                    user=user,
                    started_at=state.started_at,
                    ended_at=ended_at,
                    status=_stop_reason_to_status(state.stop_reason),
                    analyses=state.analyses,
                )
                if result is not None:
                    persisted_id = result[0].id
        except Exception as exc:
            logger.error("Fluency persistence failed: %s", exc)

        try:
            await ws.send_json({
                "type": "session_ended",
                "reason": state.stop_reason,
                "average_score": state.average_score(),
                "session_id": str(persisted_id) if persisted_id else None,
            })
            await ws.close()
        except Exception:
            pass


# HTTP history endpoints


@router.get("/sessions", response_model=list[FluencySessionListItem])
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[FluencySessionListItem]:
    rows = await list_fluency_sessions(db=db, user=user)
    return [
        FluencySessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            fluency_score=metrics_row.fluency_score,
            words_per_minute=float(metrics_row.words_per_minute),
        )
        for session_row, metrics_row in rows
    ]


@router.get("/sessions/{session_id}", response_model=FluencySessionDetail)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> FluencySessionDetail:
    found = await get_fluency_session(db=db, user=user, session_id=session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de fluidez no encontrada",
        )
    return _build_detail(*found)
